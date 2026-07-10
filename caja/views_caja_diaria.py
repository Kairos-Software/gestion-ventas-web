import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse

from core.permisos import chequear_permiso
from .models import TurnoCaja, EstadoTurno


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Caja Diaria
# ══════════════════════════════════════════════════════════════════

class CajaDiariaView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/caja_diaria.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_caja'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_ver'] = True
        
        # Obtener turno actual
        turno_actual = TurnoCaja.turno_actual()
        ctx['turno_actual'] = turno_actual
        
        if turno_actual:
            ctx['totales_medio_pago'] = turno_actual.totales_medio_pago
            ctx['total_recaudado'] = turno_actual.total_recaudado
            ctx['monto_inicial'] = turno_actual.monto_inicial_efectivo
            ctx['efectivo_ventas'] = turno_actual.efectivo_ventas
            ctx['efectivo_total'] = turno_actual.efectivo_total
            ctx['ganancia_turno'] = turno_actual.ganancia_turno
        else:
            # No hay turno abierto: si el último turno cerrado tuvo una
            # diferencia de efectivo, se muestra como banner persistente
            # (no alcanza con el alert() del momento del cierre, que se
            # puede perder si alguien no estaba mirando la pantalla).
            ultimo_cerrado = TurnoCaja.objects.filter(
                estado=EstadoTurno.CERRADO
            ).order_by('-fecha_cierre').first()
            if ultimo_cerrado and ultimo_cerrado.alerta_diferencia:
                ctx['alerta_ultimo_turno'] = ultimo_cerrado
        
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Abrir Turno
# ══════════════════════════════════════════════════════════════════

class AbrirTurnoAjax(LoginRequiredMixin, View):
    """
    POST JSON (negocio con una o más cajas físicas):
    {
        "cajas": [
            {"nombre": "Caja 1", "monto": 100.00},
            {"nombre": "Caja 2", "monto": 50.00}
        ]
    }
    También acepta el formato viejo (compatibilidad, una sola caja):
    {
        "monto_inicial_efectivo": 100.00
    }
    Abre un nuevo turno de caja diaria. El monto_inicial_efectivo del
    turno queda como la SUMA de todas las cajas declaradas — el resto
    del sistema sigue viendo un único total, como siempre.
    """
    
    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_caja'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)
        
        cajas_input = body.get('cajas')
        if cajas_input is None:
            # Compatibilidad con el formato viejo de una sola caja
            cajas_input = [{'nombre': 'Caja 1', 'monto': body.get('monto_inicial_efectivo', 0)}]
        
        if not isinstance(cajas_input, list) or len(cajas_input) == 0:
            return JsonResponse({'error': 'Tenés que declarar al menos una caja.'}, status=400)
        
        cajas = []
        for i, c in enumerate(cajas_input):
            nombre = (c.get('nombre') or f'Caja {i + 1}').strip() or f'Caja {i + 1}'
            try:
                monto = Decimal(str(c.get('monto', 0)))
            except Exception:
                return JsonResponse({'error': f'Monto inválido en "{nombre}".'}, status=400)
            if monto < 0:
                return JsonResponse({'error': f'El monto de "{nombre}" no puede ser negativo.'}, status=400)
            cajas.append({'nombre': nombre, 'monto': monto})
        
        try:
            turno = TurnoCaja.abrir(cajas=cajas, usuario=request.user)
            return JsonResponse({
                'ok': True,
                'turno': {
                    'numero': turno.numero,
                    'fecha_apertura': turno.fecha_apertura.strftime('%d/%m/%Y %H:%M'),
                    'monto_inicial_efectivo': str(turno.monto_inicial_efectivo),
                    'cajas': [
                        {'id': cf.pk, 'nombre': cf.nombre, 'monto_inicial': str(cf.monto_inicial)}
                        for cf in turno.cajas_fisicas.all()
                    ],
                }
            })
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Error al abrir turno: {e}'}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Cerrar Turno
# ══════════════════════════════════════════════════════════════════

class CerrarTurnoAjax(LoginRequiredMixin, View):
    """
    POST JSON (una o más cajas físicas):
    {
        "cajas": [
            {"id": 5, "nombre": "Caja 1", "monto": 2000.00},
            {"id": 6, "nombre": "Caja 2", "monto": 500.00}
        ],
        "notas": "..."
    }
    "id" es opcional (para emparejar con la caja física declarada en
    la apertura); si no viene, se empareja por nombre. También acepta
    el formato viejo (compatibilidad, una sola caja):
    {
        "monto_final_efectivo": 2000.00,
        "notas": "..."
    }
    Cierra el turno actual. monto_final_efectivo del turno queda como
    la SUMA de todas las cajas declaradas — el resto de la lógica
    (esperado, diferencia, alerta) sigue operando sobre ese total.
    """
    
    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_caja'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)
        
        notas = body.get('notas', '')
        cajas_input = body.get('cajas')
        
        if cajas_input is None:
            # Compatibilidad con el formato viejo de una sola caja
            monto_final = body.get('monto_final_efectivo')
            if monto_final is None:
                return JsonResponse({'error': 'Monto final requerido.'}, status=400)
            cajas_input = [{'nombre': 'Caja 1', 'monto': monto_final}]
        
        if not isinstance(cajas_input, list) or len(cajas_input) == 0:
            return JsonResponse({'error': 'Tenés que declarar el efectivo de al menos una caja.'}, status=400)
        
        cajas = []
        for i, c in enumerate(cajas_input):
            nombre = (c.get('nombre') or f'Caja {i + 1}').strip() or f'Caja {i + 1}'
            try:
                monto = Decimal(str(c.get('monto', 0)))
            except Exception:
                return JsonResponse({'error': f'Monto inválido en "{nombre}".'}, status=400)
            if monto < 0:
                return JsonResponse({'error': f'El monto de "{nombre}" no puede ser negativo.'}, status=400)
            cajas.append({'id': c.get('id'), 'nombre': nombre, 'monto': monto})
        
        turno = TurnoCaja.turno_actual()
        if not turno:
            return JsonResponse({'error': 'No hay un turno abierto.'}, status=400)
        
        # Calcular el efectivo esperado según el sistema (a nivel total)
        efectivo_esperado = turno.efectivo_total
        monto_final_total = sum(c['monto'] for c in cajas)
        
        try:
            turno.cerrar(cajas=cajas, usuario=request.user, notas=notas)
            diferencia = turno.diferencia_efectivo or Decimal('0')

            return JsonResponse({
                'ok': True,
                'turno': {
                    'numero': turno.numero,
                    'fecha_cierre': turno.fecha_cierre.strftime('%d/%m/%Y %H:%M'),
                    'monto_final_efectivo': str(turno.monto_final_efectivo),
                    'diferencia_efectivo': str(turno.diferencia_efectivo) if turno.diferencia_efectivo else '0',
                    'cajas': [
                        {
                            'id': cf.pk, 'nombre': cf.nombre,
                            'monto_inicial': str(cf.monto_inicial),
                            'monto_final': str(cf.monto_final) if cf.monto_final is not None else None,
                        }
                        for cf in turno.cajas_fisicas.all()
                    ],
                },
                'comparacion': {
                    'efectivo_esperado': str(efectivo_esperado),
                    'efectivo_declarado': str(monto_final_total),
                    'diferencia': str(diferencia),
                    'estado': 'coincide' if abs(diferencia) < 0.01 else ('sobra' if diferencia > 0 else 'falta')
                },
                # Alerta explícita para que el frontend la muestre con
                # urgencia (color rojo, modal, notificación, etc.)
                'alerta': {
                    'hay_diferencia': turno.alerta_diferencia,
                    'mensaje': turno.mensaje_alerta,
                } if turno.alerta_diferencia else None,
            })
        except Exception as e:
            return JsonResponse({'error': f'Error al cerrar turno: {e}'}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Estado Actual de Caja Diaria
# ══════════════════════════════════════════════════════════════════

class EstadoCajaDiariaAjax(LoginRequiredMixin, View):
    """
    GET: Devuelve el estado actual de la caja diaria.
    """
    
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_caja'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        turno = TurnoCaja.turno_actual()
        
        if not turno:
            return JsonResponse({
                'hay_turno': False,
                'mensaje': 'No hay un turno abierto'
            })
        
        totales = turno.totales_medio_pago
        
        return JsonResponse({
            'hay_turno': True,
            'turno': {
                'numero': turno.numero,
                'fecha_apertura': turno.fecha_apertura.strftime('%d/%m/%Y %H:%M'),
                'monto_inicial_efectivo': str(turno.monto_inicial_efectivo),
                'abierto_por': turno.abierto_por.get_full_name() if turno.abierto_por else 'N/A',
                'efectivo_total': str(turno.efectivo_total),
                'total_recaudado': str(turno.total_recaudado),
                'ganancia_turno': str(turno.ganancia_turno),
                'efectivo_ventas': str(turno.efectivo_ventas),
                # Desglose declarado en la apertura — el frontend lo usa
                # para pre-cargar los nombres de caja en el modal de cierre.
                'cajas': [
                    {'id': cf.pk, 'nombre': cf.nombre, 'monto_inicial': str(cf.monto_inicial)}
                    for cf in turno.cajas_fisicas.all()
                ],
            },
            'totales_medio_pago': {k: str(v) for k, v in totales.items()},
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Historial de Turnos
# ══════════════════════════════════════════════════════════════════

class HistorialTurnosAjax(LoginRequiredMixin, View):
    """
    GET: Devuelve el historial de turnos.
    """
    
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_caja'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        turnos = TurnoCaja.objects.all().order_by('-fecha_apertura').prefetch_related('cajas_fisicas')
        
        data = []
        for turno in turnos:
            data.append({
                'numero': turno.numero,
                'estado': turno.get_estado_display(),
                'fecha_apertura': turno.fecha_apertura.strftime('%d/%m/%Y %H:%M'),
                'fecha_cierre': turno.fecha_cierre.strftime('%d/%m/%Y %H:%M') if turno.fecha_cierre else None,
                'monto_inicial_efectivo': str(turno.monto_inicial_efectivo),
                'monto_final_efectivo': str(turno.monto_final_efectivo) if turno.monto_final_efectivo else None,
                'diferencia_efectivo': str(turno.diferencia_efectivo) if turno.diferencia_efectivo else None,
                'abierto_por': turno.abierto_por.get_full_name() if turno.abierto_por else 'N/A',
                'cerrado_por': turno.cerrado_por.get_full_name() if turno.cerrado_por else None,
                'total_recaudado': str(turno.total_recaudado),
                'efectivo_ventas': str(turno.efectivo_ventas),
                'efectivo_total': str(turno.efectivo_total),
                'ganancia_turno': str(turno.ganancia_turno),
                'alerta_diferencia': turno.alerta_diferencia,
                'mensaje_alerta': turno.mensaje_alerta,
                # Detalle secundario, solo informativo (no tiene
                # "diferencia" propia — ver CajaFisicaTurno). Se muestra
                # colapsado en el frontend, no como dato principal.
                'cajas': [
                    {
                        'nombre': cf.nombre,
                        'monto_inicial': str(cf.monto_inicial),
                        'monto_final': str(cf.monto_final) if cf.monto_final is not None else None,
                    }
                    for cf in turno.cajas_fisicas.all()
                ],
            })

        return JsonResponse({
            'turnos': data,
            # Para que el frontend pueda pintar un banner global de
            # "hay turnos con diferencias sin revisar" apenas carga.
            'hay_alertas': any(t['alerta_diferencia'] for t in data),
        })


# ══════════════════════════════════════════════════════════════════
#  VISTA — Historial de Turnos
# ══════════════════════════════════════════════════════════════════

class HistorialTurnosView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/historial_turnos.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_caja'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_ver'] = True
        
        # Obtener todos los turnos
        turnos = TurnoCaja.objects.all().order_by('-fecha_apertura').prefetch_related('cajas_fisicas')
        ctx['turnos'] = turnos
        ctx['hay_alertas'] = any(t.alerta_diferencia for t in turnos)
        
        return ctx


# ══════════════════════════════════════════════════════════════════
#  VISTA — Historial Diario
# ══════════════════════════════════════════════════════════════════

class HistorialDiarioView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/historial_diario.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_caja'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_ver'] = True
        
        from django.db.models import Sum, Count
        from django.db.models.functions import TruncDate
        
        # Agrupar turnos por fecha y calcular totales
        turnos_por_fecha = TurnoCaja.objects.annotate(
            fecha=TruncDate('fecha_apertura')
        ).values('fecha').annotate(
            cantidad_turnos=Count('id'),
            total_monto_inicial=Sum('monto_inicial_efectivo'),
            total_monto_final=Sum('monto_final_efectivo'),
            total_diferencia=Sum('diferencia_efectivo')
        ).order_by('-fecha')
        
        # Para cada fecha, obtener los turnos individuales
        historial = []
        for entry in turnos_por_fecha:
            fecha = entry['fecha']
            turnos_fecha = TurnoCaja.objects.filter(
                fecha_apertura__date=fecha
            ).order_by('fecha_apertura').prefetch_related('cajas_fisicas')
            
            # Calcular totales por medio de pago para todos los turnos del día.
            # Usamos la propiedad totales_medio_pago (no el método directo)
            # para que los turnos ya CERRADOS usen su snapshot congelado en
            # vez de recalcularse en caliente contra PagoVenta.
            totales_medio_pago = {}
            hay_alerta = False
            for turno in turnos_fecha:
                totales = turno.totales_medio_pago
                for medio, monto in totales.items():
                    totales_medio_pago[medio] = totales_medio_pago.get(medio, 0) + monto
                if turno.alerta_diferencia:
                    hay_alerta = True
            
            historial.append({
                'fecha': fecha,
                'cantidad_turnos': entry['cantidad_turnos'],
                'total_monto_inicial': entry['total_monto_inicial'] or 0,
                'total_monto_final': entry['total_monto_final'] or 0,
                'total_diferencia': entry['total_diferencia'] or 0,
                'totales_medio_pago': totales_medio_pago,
                'turnos': turnos_fecha,
                'hay_alerta': hay_alerta,
            })
        
        ctx['historial'] = historial
        ctx['hay_alertas'] = any(dia['hay_alerta'] for dia in historial)
        ctx['total_turnos'] = TurnoCaja.objects.count()
        
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar Todo el Historial (Admin Only)
# ══════════════════════════════════════════════════════════════════

class EliminarHistorialAjax(LoginRequiredMixin, View):
    """
    POST: Elimina todos los turnos de caja (solo admin/superusuario).
    """
    
    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Solo administradores pueden eliminar el historial.'}, status=403)
        
        try:
            cantidad = TurnoCaja.objects.count()
            TurnoCaja.objects.all().delete()
            
            return JsonResponse({
                'ok': True,
                'mensaje': f'Se eliminaron {cantidad} turnos del historial.'
            })
        except Exception as e:
            return JsonResponse({'error': f'Error al eliminar historial: {e}'}, status=500)