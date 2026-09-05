"""
core/services_estadisticas/limite_contable.py

Acumulado de facturación para el seguimiento del tope de categoría de
monotributo (ver core.models.ConfiguracionLimiteContable). ARCA evalúa
la recategorización sobre una ventana MÓVIL de 12 meses calendario (no
el año calendario), y cuenta todos los medios de pago y toda venta
confirmada, esté o no facturada electrónicamente — no hay excepción
legal para "no efectivo" ni para "no facturado con ARCA".
`incluir_efectivo=False`/`solo_facturado_arca=True` solo dan vistas
adicionales (lo que es más difícil de no declarar / lo que queda
trazado en ARCA), no cambian lo que la ley exige.

Se muestra en Estadísticas → Resumen (no en Configuración, que solo
tiene el formulario) — ver views_estadisticas.resumen.
"""

from datetime import timedelta
from decimal import Decimal

from ventas.models import PagoVenta, EstadoVenta, MedioPago


def resumen_limite_contable(hoy, config):
    """
    `hoy`: date de referencia. `config`: ConfiguracionLimiteContable (ver
    get_solo()). Devuelve la serie de 12 meses (mes actual + 11
    anteriores, con total incluyendo y excluyendo efectivo) y, para cada
    tope configurado (`limite_mensual`/`limite_anual`, ambos opcionales —
    0 = no se controla), un bloque {total, limite, porcentaje, estado}
    con estado 'ok'/'cerca'/'superado'. El bloque es None si ese límite
    no está configurado.
    """
    primer_mes_ventana = (hoy.replace(day=1) - timedelta(days=30 * 11)).replace(day=1)
    mes_actual = hoy.replace(day=1)

    # PagoVenta.monto_ars es una property (convierte a pesos según la
    # cotización cargada), no una expresión de ORM — para no mezclar
    # monedas hay que sumarla en Python en vez de un Sum() del queryset.
    pagos = (
        PagoVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA, venta__fecha__gte=primer_mes_ventana, venta__fecha__lte=hoy)
        .select_related('venta', 'cuenta')
    )
    if config.solo_facturado_arca:
        pagos = pagos.filter(venta__comprobante_arca__isnull=False)

    totales_con_efectivo = {}
    totales_sin_efectivo = {}
    for pago in pagos:
        mes = pago.venta.fecha.replace(day=1)
        monto = pago.monto_ars
        totales_con_efectivo[mes] = totales_con_efectivo.get(mes, Decimal('0')) + monto
        if pago.medio != MedioPago.EFECTIVO:
            totales_sin_efectivo[mes] = totales_sin_efectivo.get(mes, Decimal('0')) + monto

    # Igual que serie_mensual (ventas.py): se generan explícitamente los
    # 12 casilleros del calendario, en orden, para que la tabla se vea
    # completa aunque algunos meses no tengan ventas cargadas.
    serie = []
    cursor = primer_mes_ventana
    for _ in range(12):
        serie.append({
            'mes': cursor,
            'total_con_efectivo': totales_con_efectivo.get(cursor, Decimal('0')),
            'total_sin_efectivo': totales_sin_efectivo.get(cursor, Decimal('0')),
        })
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    clave = 'total_con_efectivo' if config.incluir_efectivo else 'total_sin_efectivo'
    acumulado_12m = sum((fila[clave] for fila in serie), Decimal('0'))
    total_mes_actual = next((fila[clave] for fila in serie if fila['mes'] == mes_actual), Decimal('0'))

    def _bloque(total, limite):
        if not limite:
            return None
        porcentaje = total / limite * 100
        if porcentaje >= 100:
            estado = 'superado'
        elif porcentaje >= config.umbral_alerta_pct:
            estado = 'cerca'
        else:
            estado = 'ok'
        return {'total': total, 'limite': limite, 'porcentaje': porcentaje, 'estado': estado}

    return {
        'serie': serie,
        'mensual': _bloque(total_mes_actual, config.limite_mensual),
        'anual': _bloque(acumulado_12m, config.limite_anual),
    }
