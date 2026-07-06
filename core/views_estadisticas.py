"""
core/views_estadisticas.py

Vista del dashboard de Estadísticas. Vive como archivo separado para
no ensuciar tu views.py principal — importá `estadisticas` desde
core/urls.py como se indica más abajo.
"""

import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render
from django.utils import timezone

from . import services_estadisticas as stats


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


@login_required
def estadisticas(request):
    hoy = timezone.now().date()

    preset = request.GET.get('preset', 'mes_actual')
    desde_str = request.GET.get('desde')
    hasta_str = request.GET.get('hasta')

    # IMPORTANTE: solo usamos las fechas manuales cuando el preset es
    # explícitamente 'personalizado' (viene del formulario de rango
    # custom). Si viniera de los botones rápidos, ignoramos cualquier
    # desde/hasta que pudiera colarse por error.
    if preset == 'personalizado' and desde_str and hasta_str:
        try:
            desde = date.fromisoformat(desde_str)
            hasta = date.fromisoformat(hasta_str)
        except ValueError:
            preset = 'mes_actual'
            desde, hasta = stats.rango_por_preset(preset, hoy)
    else:
        desde, hasta = stats.rango_por_preset(preset, hoy)

    resumen = stats.resumen_ganancia(desde, hasta)
    perdidas_periodo = stats.perdidas_del_periodo(desde, hasta)
    serie = stats.serie_mensual(hoy, meses=12)
    gastos_categoria = stats.gastos_por_categoria(desde, hasta)

    # Ganancia final: lo que realmente te quedó después de gastos Y
    # después de descontar lo perdido por vencimiento/merma en el período.
    ganancia_final = resumen['ganancia_neta'] - perdidas_periodo['total_perdidas_periodo']

    # Ticket promedio general del período (para la tarjeta de ventas).
    ticket_promedio = (
        round(resumen['ingresos'] / resumen['cantidad_ventas'], 2)
        if resumen['cantidad_ventas'] else 0
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

    gastos_categoria_json = json.dumps([
        {'categoria': g['descripcion'], 'total': float(g['total'] or 0)}
        for g in gastos_categoria
    ], cls=DjangoJSONEncoder)

    contexto = {
        'desde': desde,
        'hasta': hasta,
        'preset': preset,
        'resumen': resumen,
        'ganancia_final': ganancia_final,
        'ticket_promedio': ticket_promedio,
        'comparacion': stats.comparacion_periodo(desde, hasta),
        'comparacion_label': ETIQUETAS_COMPARACION.get(preset, 'que el período anterior'),
        'ranking_empleados': stats.ranking_empleados(desde, hasta),
        'ranking_productos': stats.ranking_productos(desde, hasta),
        'perdidas_periodo': perdidas_periodo,
        'perdidas_actuales': stats.perdidas_vencimiento(),
        'gastos_categoria': gastos_categoria,
        'serie_mensual_json': serie_json,
        'gastos_categoria_json': gastos_categoria_json,
    }
    return render(request, 'core/estadisticas.html', contexto)