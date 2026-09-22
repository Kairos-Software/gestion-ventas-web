"""
core/views_estadisticas.py

Vistas de las páginas de Estadísticas — una por sección (Resumen,
Ventas, Productos y Stock, Caja y Finanzas, y las que se vayan
sumando). Cada una arma su propio contexto liviano y renderiza su
propio template; lo único compartido es el parseo del filtro de
fecha (`_resolver_rango`) y las queries en `core.services_estadisticas`.
"""

import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from productos.models import Moneda

from .models import Cliente, ConfiguracionLimiteContable
from .services_estadisticas import rango_por_preset
from .services_estadisticas import ventas as stats_ventas
from .services_estadisticas import compras as stats_compras
from .services_estadisticas import productos as stats_productos
from .services_estadisticas import clientes as stats_clientes
from .services_estadisticas import cliente_perfil as stats_cliente_perfil
from .services_estadisticas import caja as stats_caja
from .services_estadisticas.limite_contable import resumen_limite_contable
from .permisos import chequear_permiso


# Texto en criollo para la comparación con el período anterior,
# según qué filtro rápido está activo (evita el genérico y confuso
# "período anterior" en los KPIs).
ETIQUETAS_COMPARACION = {
    'hoy': 'que ayer',
    'semana': 'que los 7 días anteriores',
    'mes_actual': 'que el mes pasado',
    'mes_anterior': 'que el mes previo a ese',
    'anio': 'que el año pasado',
    'personalizado': 'que el período anterior (misma duración)',
}


def _medio_pago_ars_json(por_medio_pago):
    """
    Serializa por_medio_pago para el gráfico de torta. Se limita a ARS
    a propósito: un solo gráfico no puede mezclar pesos y dólares sin
    mentir sobre la proporción real (ver el mismo criterio en
    services_estadisticas.ventas.por_medio_pago). El detalle con todas
    las monedas se sigue mostrando en la lista de abajo.
    """
    return json.dumps([
        {'label': f['medio_label'], 'total': float(f['total'])}
        for f in por_medio_pago if f['moneda'] == 'ARS'
    ], cls=DjangoJSONEncoder)


def _resolver_rango(request, hoy):
    """
    Parsea `preset`/`desde`/`hasta` de la querystring, compartido por
    todas las páginas de Estadísticas. Devuelve (preset, desde, hasta).

    IMPORTANTE: solo usamos las fechas manuales cuando el preset es
    explícitamente 'personalizado' (viene del formulario de rango
    custom). Si viniera de los botones rápidos, ignoramos cualquier
    desde/hasta que pudiera colarse por error.
    """
    preset = request.GET.get('preset', 'mes_actual')
    desde_str = request.GET.get('desde')
    hasta_str = request.GET.get('hasta')

    if preset == 'personalizado' and desde_str and hasta_str:
        try:
            desde = date.fromisoformat(desde_str)
            hasta = date.fromisoformat(hasta_str)
        except ValueError:
            preset = 'mes_actual'
            desde, hasta = rango_por_preset(preset, hoy)
    else:
        desde, hasta = rango_por_preset(preset, hoy)

    return preset, desde, hasta


@login_required
def resumen(request):
    if not chequear_permiso(request.user, 'ver_estadisticas'):
        return render(request, 'core/estadisticas/resumen.html', {'sin_permiso': True})

    hoy = timezone.localtime().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    resumen_ganancia = stats_ventas.resumen_ganancia(desde, hasta)
    perdidas_periodo = stats_productos.perdidas_del_periodo(desde, hasta)
    serie = stats_ventas.serie_mensual(hoy, meses=12)

    # Ganancia final: lo que realmente te quedó después de gastos Y
    # después de descontar lo perdido por vencimiento/merma en el período.
    ganancia_final = resumen_ganancia['ganancia_neta'] - perdidas_periodo['total_perdidas_periodo']

    # Ticket promedio general del período (para la tarjeta de ventas).
    ticket_promedio = (
        round(resumen_ganancia['ingresos'] / resumen_ganancia['cantidad_ventas'], 2)
        if resumen_ganancia['cantidad_ventas'] else 0
    )

    serie_json = json.dumps([
        {
            'mes': f['mes'].strftime('%b %Y'),
            'ingresos': float(f['ingresos']),
            'costo': float(f['costo']),
            'ganancia': float(f['ganancia']),
        }
        for f in serie
    ], cls=DjangoJSONEncoder)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'resumen': resumen_ganancia,
        'ganancia_final': ganancia_final,
        'ticket_promedio': ticket_promedio,
        'comparacion': stats_ventas.comparacion_periodo(desde, hasta),
        'comparacion_label': ETIQUETAS_COMPARACION.get(preset, 'que el período anterior'),
        'perdidas_periodo': perdidas_periodo,
        'serie_mensual_json': serie_json,
        'facturacion_arca': stats_ventas.facturacion_arca(desde, hasta),
        'devoluciones_periodo': stats_ventas.resumen_devoluciones(desde, hasta),
        'puede_ver_ventas': chequear_permiso(request.user, 'ver_ventas'),
        'puede_ver_productos': chequear_permiso(request.user, 'ver_productos'),
    }

    puede_compras = chequear_permiso(request.user, 'ver_compras')
    puede_caja = chequear_permiso(request.user, 'ver_caja')
    contexto['puede_ver_caja'] = puede_caja

    if puede_compras:
        contexto['compras_periodo'] = stats_compras.resumen_compras(desde, hasta)

    if puede_caja:
        contexto['situacion_financiera'] = stats_caja.situacion_financiera()
        contexto['obligaciones_periodo'] = stats_caja.obligaciones_del_periodo(desde, hasta)
        contexto['cobros_periodo'] = stats_caja.cobros_del_periodo(desde, hasta)

    # "Cuánto te queda realmente" — waterfall simple en un solo lugar, en
    # ARS (mismo criterio que el resto de Estadísticas: ventas/compras/
    # gastos no se abren por moneda). Solo se arma si hay permiso para ver
    # las piezas que le faltan a "resumen" (compras y deudas/gastos de
    # caja) — si falta alguno, se omite la tarjeta entera antes que mostrar
    # un número incompleto sin avisar.
    #
    # "Total vendido" y "Total comprado" son ACCRUAL (se reconocen al
    # confirmar la venta/compra, no cuando se cobra/paga de verdad) — una
    # venta a cuenta corriente o una compra financiada (tarjeta/cheque/
    # cuenta corriente con el proveedor) cuentan ahí ENTERAS aunque no
    # haya entrado/salido un peso todavía. Para no mentir en un waterfall
    # de CAJA, se les resta esa porción sin cobrar/pagar y en su lugar se
    # suma lo que efectivamente se cobró de CxC en el período (de esta
    # venta o de una anterior) — "deudas_pagadas" ya cubre el lado
    # simétrico de lo comprado a crédito, sea de este período o no.
    if puede_compras and puede_caja:
        vendido = resumen_ganancia['ingresos']
        vendido_a_cuenta_corriente = stats_ventas.monto_vendido_a_cuenta_corriente(desde, hasta)
        cobrado_cxc = stats_caja.cxc_cobrado_blend(desde, hasta)
        devuelto = contexto['devoluciones_periodo']['total_devuelto']
        comprado = contexto['compras_periodo']['total_comprado']
        comprado_a_credito = stats_compras.monto_comprado_a_credito(desde, hasta)
        gastado = resumen_ganancia['gastos']
        deudas_pagadas = stats_caja.deudas_y_tarjetas_pagadas_blend(desde, hasta)
        contexto['queda_realmente'] = {
            'vendido': vendido,
            'vendido_a_cuenta_corriente': vendido_a_cuenta_corriente,
            'cobrado_cxc': cobrado_cxc,
            'devuelto': devuelto,
            'comprado': comprado,
            'comprado_a_credito': comprado_a_credito,
            'gastado': gastado,
            'deudas_pagadas': deudas_pagadas,
            'total': (
                vendido - vendido_a_cuenta_corriente + cobrado_cxc - devuelto
                - (comprado - comprado_a_credito) - gastado - deudas_pagadas
            ),
        }

    # Límite contable (monotributo): mismo permiso que edita la
    # configuración (Configuración → Límite contable) — no todo el que
    # ve Estadísticas tiene por qué ver esto.
    if chequear_permiso(request.user, 'editar_empresa'):
        config_limite = ConfiguracionLimiteContable.get_solo()
        if config_limite.activo:
            contexto['configuracion_limite_contable'] = config_limite
            contexto['limite_contable'] = resumen_limite_contable(hoy, config_limite)

    return render(request, 'core/estadisticas/resumen.html', contexto)


@login_required
def ventas(request):
    if not chequear_permiso(request.user, 'ver_ventas'):
        return render(request, 'core/estadisticas/ventas.html', {'sin_permiso': True})

    hoy = timezone.localtime().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    comparacion = stats_ventas.comparacion_periodo(desde, hasta)
    resumen_ventas = comparacion['actual']
    ticket_promedio = (
        round(resumen_ventas['ingresos'] / resumen_ventas['cantidad_ventas'], 2)
        if resumen_ventas['cantidad_ventas'] else 0
    )
    por_dia_semana = stats_ventas.por_dia_semana(desde, hasta)
    max_dia = max((fila['ingresos'] for fila in por_dia_semana), default=0)
    for fila in por_dia_semana:
        fila['porcentaje_visual'] = round(fila['ingresos'] / max_dia * 100) if max_dia else 0

    por_medio_pago = stats_ventas.por_medio_pago(desde, hasta)
    por_medio_pago_ars_json = _medio_pago_ars_json(por_medio_pago)
    facturacion_arca = stats_ventas.facturacion_arca(desde, hasta)
    facturacion_arca_json = json.dumps([
        {'label': f['label'], 'total': float(f['total'])}
        for f in facturacion_arca['por_tipo']
    ] + ([{'label': 'Sin facturar', 'total': float(facturacion_arca['total_sin_facturar'])}]
         if facturacion_arca['total_sin_facturar'] else []), cls=DjangoJSONEncoder)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'resumen_ventas': resumen_ventas,
        'comparacion': comparacion,
        'ticket_promedio': ticket_promedio,
        'ranking_empleados': stats_ventas.ranking_empleados(desde, hasta),
        'ranking_productos': stats_ventas.ranking_productos(desde, hasta),
        'ranking_categorias': stats_ventas.ranking_categorias(desde, hasta),
        'por_medio_pago': por_medio_pago,
        'por_medio_pago_ars_json': por_medio_pago_ars_json,
        'por_dia_semana': por_dia_semana,
        'impacto_descuentos': stats_ventas.impacto_descuentos(desde, hasta),
        'facturacion_arca': facturacion_arca,
        'facturacion_arca_json': facturacion_arca_json,
        'ventas_tiene_graficos': (
            por_medio_pago_ars_json != '[]' or facturacion_arca_json != '[]'
        ),
    }
    return render(request, 'core/estadisticas/ventas.html', contexto)


@login_required
def compras(request):
    if not chequear_permiso(request.user, 'ver_compras'):
        return render(request, 'core/estadisticas/compras.html', {'sin_permiso': True})

    hoy = timezone.localtime().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    serie = stats_compras.serie_mensual(hoy, meses=12)
    serie_json = json.dumps([
        {'mes': f['mes'].strftime('%b %Y'), 'total': float(f['total'])}
        for f in serie
    ], cls=DjangoJSONEncoder)

    comparacion = stats_compras.comparacion_periodo(desde, hasta)
    resumen_compras = comparacion['actual']
    promedio_compra = (
        round(resumen_compras['total_comprado'] / resumen_compras['cantidad_compras'], 2)
        if resumen_compras['cantidad_compras'] else 0
    )
    por_medio_pago = stats_compras.por_medio_pago(desde, hasta)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'resumen': resumen_compras,
        'comparacion': comparacion,
        'promedio_compra': promedio_compra,
        'ranking_proveedores': stats_compras.ranking_proveedores(desde, hasta),
        'por_medio_pago': por_medio_pago,
        'por_medio_pago_ars_json': _medio_pago_ars_json(por_medio_pago),
        'serie_mensual_json': serie_json,
        'serie_tiene_datos': any(f['total'] for f in serie),
    }
    return render(request, 'core/estadisticas/compras.html', contexto)


@login_required
def productos(request):
    if not chequear_permiso(request.user, 'ver_productos'):
        return render(request, 'core/estadisticas/productos.html', {'sin_permiso': True})

    hoy = timezone.localtime().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    contexto = {
        'hoy': hoy,
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'valorizacion_stock': stats_productos.valorizacion_stock(),
        'stock_bajo': stats_productos.stock_bajo(),
        'stock_bajo_total': stats_productos.contar_stock_bajo(),
        'sin_movimiento': stats_productos.sin_movimiento(),
        'rendimiento_paquetes': stats_productos.rendimiento_paquetes(desde, hasta),
        'perdidas_periodo': stats_productos.perdidas_del_periodo(desde, hasta),
        'perdidas_actuales': stats_productos.perdidas_vencimiento(),
    }
    return render(request, 'core/estadisticas/productos.html', contexto)


@login_required
def predicciones(request):
    if not chequear_permiso(request.user, 'ver_productos'):
        return render(request, 'core/estadisticas/predicciones.html', {'sin_permiso': True})

    prediccion = stats_productos.prediccion_reposicion()
    max_costo = max((b['total_estimado'] for b in prediccion['buckets']), default=0)
    for bucket in prediccion['buckets']:
        bucket['porcentaje_visual'] = (
            max(3, round(bucket['total_estimado'] / max_costo * 100))
            if max_costo and bucket['total_estimado'] else 0
        )

    contexto = {
        'prediccion_reposicion': prediccion,
        'prediccion_futuros': [b for b in prediccion['buckets'][1:] if b['cantidad_productos']],
    }
    return render(request, 'core/estadisticas/predicciones.html', contexto)


@login_required
def clientes(request):
    if not chequear_permiso(request.user, 'ver_clientes'):
        return render(request, 'core/estadisticas/clientes.html', {'sin_permiso': True})

    hoy = timezone.localtime().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    distribucion_tipo = stats_clientes.distribucion_tipo()
    distribucion_estado = stats_clientes.distribucion_estado()
    mejores_clientes_divisas = []
    for moneda in (Moneda.USD, Moneda.EUR):
        ranking = stats_clientes.mejores_clientes(desde, hasta, moneda=moneda)
        if ranking:
            mejores_clientes_divisas.append({'moneda': moneda, 'clientes': ranking})

    contexto = {
        'hoy': hoy,
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'mejores_clientes': stats_clientes.mejores_clientes(desde, hasta),
        'mejores_clientes_divisas': mejores_clientes_divisas,
        'nuevos_vs_recurrentes': stats_clientes.nuevos_vs_recurrentes(desde, hasta),
        'clientes_inactivos': stats_clientes.clientes_inactivos(),
        'distribucion_tipo': distribucion_tipo,
        'distribucion_estado': distribucion_estado,
        'distribucion_tipo_json': json.dumps([
            {'label': f['label'], 'cantidad': f['cantidad']} for f in distribucion_tipo
        ], cls=DjangoJSONEncoder),
        'distribucion_estado_json': json.dumps([
            {'label': f['label'], 'cantidad': f['cantidad']} for f in distribucion_estado
        ], cls=DjangoJSONEncoder),
    }

    if chequear_permiso(request.user, 'ver_cuentas_cobrar'):
        contexto['cuentas_por_cobrar'] = stats_clientes.cuentas_por_cobrar(desde, hasta)

    return render(request, 'core/estadisticas/clientes.html', contexto)


@login_required
def cliente_perfil(request, pk):
    if not chequear_permiso(request.user, 'ver_clientes'):
        return render(request, 'core/estadisticas/cliente_perfil.html', {'sin_permiso': True})

    cliente = get_object_or_404(Cliente, pk=pk)
    puede_ver_deuda = chequear_permiso(request.user, 'ver_cuentas_cobrar')

    contexto = {
        'cliente': cliente,
        'puede_ver_deuda': puede_ver_deuda,
        'perfil_valor': stats_cliente_perfil.perfil_valor(cliente),
    }

    if puede_ver_deuda:
        deudas = stats_cliente_perfil.deudas_activas(cliente)
        historial = stats_cliente_perfil.historial_cliente(cliente)
        scoring_historial = stats_cliente_perfil.historial_scoring(cliente)
        contexto.update({
            'comportamiento_pago': stats_cliente_perfil.comportamiento_pago(cliente),
            'deudas_activas': deudas,
            'deudas_activas_json': json.dumps(deudas, cls=DjangoJSONEncoder),
            'historial': historial,
            'historial_json': json.dumps(historial, cls=DjangoJSONEncoder),
            'scoring_historial': scoring_historial,
            'scoring_historial_json': json.dumps(scoring_historial, cls=DjangoJSONEncoder),
        })

    return render(request, 'core/estadisticas/cliente_perfil.html', contexto)


@login_required
def caja(request):
    if not chequear_permiso(request.user, 'ver_caja'):
        return render(request, 'core/estadisticas/caja.html', {'sin_permiso': True})

    hoy = timezone.localtime().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    mov_concepto = stats_caja.movimientos_por_concepto(desde, hasta)
    mov_concepto_chart_data = {
        'por_moneda': [
            {
                'moneda': grupo['moneda'],
                'egresos': [{'categoria': e['concepto'], 'total': float(e['total'])} for e in grupo['egresos']],
                'ingresos': [{'categoria': i['concepto'], 'total': float(i['total'])} for i in grupo['ingresos']],
            }
            for grupo in mov_concepto['por_moneda']
        ],
    }
    serie_conceptos = stats_caja.serie_mensual_conceptos(hoy, meses=6)

    serie_conceptos_data = {
        'meses': [m.strftime('%b %Y') for m in serie_conceptos['meses']],
        'por_moneda': [
            {'moneda': grupo['moneda'], 'series': [
                {'concepto': s['concepto'], 'valores': [float(v) for v in s['valores']]}
                for s in grupo['series']
            ]}
            for grupo in serie_conceptos['por_moneda']
        ],
    }

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'situacion_financiera': stats_caja.situacion_financiera(),
        'obligaciones_periodo': stats_caja.obligaciones_del_periodo(desde, hasta),
        'cobros_periodo': stats_caja.cobros_del_periodo(desde, hasta),
        'mov_concepto': mov_concepto,
        'mov_concepto_chart_data': mov_concepto_chart_data,
        'tiene_otros_ingresos': any(grupo['ingresos'] for grupo in mov_concepto['por_moneda']),
        'serie_conceptos': serie_conceptos,
        'serie_conceptos_data': serie_conceptos_data,
        'historial_arqueos': stats_caja.historial_arqueos(desde, hasta),
    }
    return render(request, 'core/estadisticas/caja.html', contexto)
