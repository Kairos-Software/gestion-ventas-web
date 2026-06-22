import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Q, Count

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import Gasto, sincronizar_movimiento_gasto


PERMISO_VER    = 'ver_gastos'
PERMISO_CREAR  = 'crear_gastos'
PERMISO_EDITAR = 'editar_gastos'
PERMISO_ELIMINAR = 'eliminar_gastos'


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Gestión de gastos
# ══════════════════════════════════════════════════════════════════

class GastosView(LoginRequiredMixin, TemplateView):
    """
    Pantalla de gestión de gastos: historial + modal para crear/editar.
    """
    template_name = 'caja/gastos.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx
        
        ctx['puede_ver'] = True
        ctx['puede_crear'] = chequear_permiso(self.request.user, PERMISO_CREAR)
        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, PERMISO_ELIMINAR)
        
        ctx['monedas'] = Moneda.choices
        ctx['today'] = timezone.now().date().isoformat()
        
        from django.urls import reverse
        ctx['url_listar'] = reverse('caja:listar_gastos')
        ctx['url_crear'] = reverse('caja:crear_gasto')
        # Las URLs de editar y eliminar se construyen dinámicamente en el JS
        ctx['url_editar'] = reverse('caja:editar_gasto', args=[0])  # Placeholder
        ctx['url_eliminar'] = reverse('caja:eliminar_gasto', args=[0])  # Placeholder
        
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listar gastos (con filtros + paginación)
# ══════════════════════════════════════════════════════════════════

class ListarGastosAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        qs = Gasto.objects.all().select_related('creado_por')
        
        # Filtros
        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()
        moneda = request.GET.get('moneda', '').strip()
        q = request.GET.get('q', '').strip()
        
        if desde:
            qs = qs.filter(fecha__gte=desde)
        if hasta:
            qs = qs.filter(fecha__lte=hasta)
        if moneda:
            qs = qs.filter(moneda=moneda)
        if q:
            qs = qs.filter(descripcion__icontains=q)
        
        # Paginación
        try:
            pagina = max(int(request.GET.get('pagina', 1)), 1)
            por_pagina = min(max(int(request.GET.get('por_pagina', 50)), 1), 200)
        except ValueError:
            pagina, por_pagina = 1, 50
        
        total = qs.count()
        inicio = (pagina - 1) * por_pagina
        items = qs[inicio:inicio + por_pagina]
        
        data = [
            {
                'pk': g.pk,
                'fecha': g.fecha.isoformat() if hasattr(g.fecha, 'isoformat') else str(g.fecha),
                'hora': g.hora.strftime('%H:%M') if g.hora and hasattr(g.hora, 'strftime') else str(g.hora) if g.hora else '',
                'monto': str(g.monto),
                'moneda': g.moneda,
                'descripcion': g.descripcion,
                'creado_por': str(g.creado_por) if g.creado_por else '',
                'fecha_alta': g.fecha_alta.isoformat() if hasattr(g.fecha_alta, 'isoformat') else str(g.fecha_alta),
            }
            for g in items
        ]
        
        return JsonResponse({
            'results': data,
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear gasto
# ══════════════════════════════════════════════════════════════════

class CrearGastoAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        try:
            data = json.loads(request.body)
            
            fecha = data.get('fecha')
            monto = data.get('monto')
            moneda = data.get('moneda', 'ARS')
            descripcion = data.get('descripcion', '').strip()
            
            if not fecha or not monto:
                return JsonResponse({'error': 'Faltan datos obligatorios: fecha, monto'}, status=400)
            
            try:
                monto = Decimal(monto)
                if monto <= 0:
                    return JsonResponse({'error': 'El monto debe ser mayor a 0'}, status=400)
            except (InvalidOperation, ValueError):
                return JsonResponse({'error': 'Monto inválido'}, status=400)
            
            gasto = Gasto.objects.create(
                fecha=fecha,
                monto=monto,
                moneda=moneda,
                descripcion=descripcion,
                creado_por=request.user,
            )
            
            return JsonResponse({
                'success': True,
                'gasto': {
                    'pk': gasto.pk,
                    'fecha': gasto.fecha.isoformat() if hasattr(gasto.fecha, 'isoformat') else str(gasto.fecha),
                    'hora': gasto.hora.strftime('%H:%M') if gasto.hora and hasattr(gasto.hora, 'strftime') else str(gasto.hora) if gasto.hora else '',
                    'monto': str(gasto.monto),
                    'moneda': gasto.moneda,
                    'descripcion': gasto.descripcion,
                }
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Editar gasto
# ══════════════════════════════════════════════════════════════════

class EditarGastoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        gasto = get_object_or_404(Gasto, pk=pk)
        
        try:
            data = json.loads(request.body)
            
            fecha = data.get('fecha')
            monto = data.get('monto')
            moneda = data.get('moneda')
            descripcion = data.get('descripcion', '').strip()
            
            if fecha:
                gasto.fecha = fecha
            if monto:
                try:
                    monto = Decimal(monto)
                    if monto <= 0:
                        return JsonResponse({'error': 'El monto debe ser mayor a 0'}, status=400)
                    gasto.monto = monto
                except (InvalidOperation, ValueError):
                    return JsonResponse({'error': 'Monto inválido'}, status=400)
            if moneda:
                gasto.moneda = moneda
            if descripcion:
                gasto.descripcion = descripcion
            
            gasto.save()
            
            # Sincronizar movimiento de caja
            sincronizar_movimiento_gasto(gasto)
            
            return JsonResponse({
                'success': True,
                'gasto': {
                    'pk': gasto.pk,
                    'fecha': gasto.fecha.isoformat() if hasattr(gasto.fecha, 'isoformat') else str(gasto.fecha),
                    'hora': gasto.hora.strftime('%H:%M') if gasto.hora and hasattr(gasto.hora, 'strftime') else str(gasto.hora) if gasto.hora else '',
                    'monto': str(gasto.monto),
                    'moneda': gasto.moneda,
                    'descripcion': gasto.descripcion,
                }
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar gasto
# ══════════════════════════════════════════════════════════════════

class EliminarGastoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        gasto = get_object_or_404(Gasto, pk=pk)
        
        try:
            gasto.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
