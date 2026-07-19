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
from django.shortcuts import render
from django.utils import timezone

from .services_estadisticas import rango_por_preset
from .services_estadisticas import ventas as stats_ventas
from .services_estadisticas import compras as stats_compras
from .services_estadisticas import productos as stats_productos
from .services_estadisticas import clientes as stats_clientes
from .services_estadisticas import caja as stats_caja
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
    hoy = timezone.now().date()
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
    }

    if chequear_permiso(request.user, 'ver_caja'):
        contexto['situacion_financiera'] = stats_caja.situacion_financiera()

    return render(request, 'core/estadisticas/resumen.html', contexto)


@login_required
def ventas(request):
    if not chequear_permiso(request.user, 'ver_ventas'):
        return render(request, 'core/estadisticas/ventas.html', {'sin_permiso': True})

    hoy = timezone.now().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    por_dia_semana = stats_ventas.por_dia_semana(desde, hasta)
    por_dia_semana_json = json.dumps([
        {'dia': f['dia'], 'ingresos': float(f['ingresos'])}
        for f in por_dia_semana
    ], cls=DjangoJSONEncoder)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'ranking_empleados': stats_ventas.ranking_empleados(desde, hasta),
        'ranking_productos': stats_ventas.ranking_productos(desde, hasta),
        'ranking_categorias': stats_ventas.ranking_categorias(desde, hasta),
        'por_medio_pago': stats_ventas.por_medio_pago(desde, hasta),
        'por_dia_semana_json': por_dia_semana_json,
        'impacto_descuentos': stats_ventas.impacto_descuentos(desde, hasta),
    }
    return render(request, 'core/estadisticas/ventas.html', contexto)


@login_required
def compras(request):
    if not chequear_permiso(request.user, 'ver_compras'):
        return render(request, 'core/estadisticas/compras.html', {'sin_permiso': True})

    hoy = timezone.now().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    serie = stats_compras.serie_mensual(hoy, meses=12)
    serie_json = json.dumps([
        {'mes': f['mes'].strftime('%b %Y'), 'total': float(f['total'])}
        for f in serie
    ], cls=DjangoJSONEncoder)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'resumen': stats_compras.resumen_compras(desde, hasta),
        'comparacion': stats_compras.comparacion_periodo(desde, hasta),
        'comparacion_label': ETIQUETAS_COMPARACION.get(preset, 'que el período anterior'),
        'ranking_proveedores': stats_compras.ranking_proveedores(desde, hasta),
        'por_medio_pago': stats_compras.por_medio_pago(desde, hasta),
        'serie_mensual_json': serie_json,
    }
    return render(request, 'core/estadisticas/compras.html', contexto)


@login_required
def productos(request):
    if not chequear_permiso(request.user, 'ver_productos'):
        return render(request, 'core/estadisticas/productos.html', {'sin_permiso': True})

    hoy = timezone.now().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'valorizacion_stock': stats_productos.valorizacion_stock(),
        'stock_bajo': stats_productos.stock_bajo(),
        'sin_movimiento': stats_productos.sin_movimiento(),
        'rendimiento_paquetes': stats_productos.rendimiento_paquetes(desde, hasta),
        'perdidas_periodo': stats_productos.perdidas_del_periodo(desde, hasta),
        'perdidas_actuales': stats_productos.perdidas_vencimiento(),
    }
    return render(request, 'core/estadisticas/productos.html', contexto)


@login_required
def clientes(request):
    if not chequear_permiso(request.user, 'ver_clientes'):
        return render(request, 'core/estadisticas/clientes.html', {'sin_permiso': True})

    hoy = timezone.now().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'mejores_clientes': stats_clientes.mejores_clientes(desde, hasta),
        'nuevos_vs_recurrentes': stats_clientes.nuevos_vs_recurrentes(desde, hasta),
        'clientes_inactivos': stats_clientes.clientes_inactivos(),
        'distribucion_riesgo': stats_clientes.distribucion_riesgo(),
        'distribucion_estado': stats_clientes.distribucion_estado(),
    }
    return render(request, 'core/estadisticas/clientes.html', contexto)


@login_required
def caja(request):
    if not chequear_permiso(request.user, 'ver_caja'):
        return render(request, 'core/estadisticas/caja.html', {'sin_permiso': True})

    hoy = timezone.now().date()
    preset, desde, hasta = _resolver_rango(request, hoy)

    gastos_categoria = stats_caja.gastos_por_categoria(desde, hasta)
    gastos_categoria_json = json.dumps([
        {'categoria': g['descripcion'], 'total': float(g['total'] or 0)}
        for g in gastos_categoria
    ], cls=DjangoJSONEncoder)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'situacion_financiera': stats_caja.situacion_financiera(),
        'gastos_categoria': gastos_categoria,
        'gastos_categoria_json': gastos_categoria_json,
        'historial_arqueos': stats_caja.historial_arqueos(desde, hasta),
    }
    return render(request, 'core/estadisticas/caja.html', contexto)
