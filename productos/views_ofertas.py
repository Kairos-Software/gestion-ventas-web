import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Producto, CategoriaProducto, Oferta, AplicacionOferta, TipoOferta, BaseCalculoUmbral
from core.permisos import chequear_permiso


def _serializar_oferta(o):
    return {
        'pk':             o.pk,
        'nombre':         o.nombre,
        'tipo':           o.tipo,
        'porcentaje':     str(o.porcentaje) if o.porcentaje is not None else '',
        'cantidad_lleva': o.cantidad_lleva,
        'cantidad_paga':  o.cantidad_paga,
        'monto_minimo':   str(o.monto_minimo) if o.monto_minimo is not None else '',
        'base_calculo':   o.base_calculo,
        'fecha_inicio':   o.fecha_inicio.isoformat(),
        'fecha_fin':      o.fecha_fin.isoformat(),
        'dias_semana':    o.dias_semana_lista(),
        'aplicacion':     o.aplicacion,
        'activa':         o.activa,
        'orden':          o.orden,
        'productos':      [
            {'pk': p.pk, 'nombre': p.nombre, 'codigo': p.codigo}
            for p in o.productos.all()
        ],
        'categorias':     list(o.categorias.values_list('pk', flat=True)),
        'vigente_hoy':    o.vigente_en(timezone.now().date()),
    }


# ══════════════════════════════════════════════════════════════════
#  PÁGINA — Gestión de ofertas (sección propia del menú)
# ══════════════════════════════════════════════════════════════════

class GestionOfertasView(LoginRequiredMixin, TemplateView):
    """Página dedicada a ofertas — no vive dentro de Productos."""
    template_name = 'productos/ofertas.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'gestionar_ofertas'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['categorias'] = CategoriaProducto.objects.filter(activo=True).order_by('orden', 'nombre')
        return ctx


# ══════════════════════════════════════════════════════════════════
#  OFERTAS — AJAX
# ══════════════════════════════════════════════════════════════════

class OfertaListaAjax(LoginRequiredMixin, View):
    """GET → lista todas las ofertas."""

    def get(self, request):
        if not chequear_permiso(request.user, 'gestionar_ofertas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs   = Oferta.objects.all().prefetch_related('productos', 'categorias').order_by('-fecha_inicio', 'orden', 'nombre')
        data = [_serializar_oferta(o) for o in qs]
        return JsonResponse({'results': data})


class OfertaAccionesAjax(LoginRequiredMixin, View):
    """POST → crea o edita una oferta."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_ofertas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        errors = {}

        nombre = body.get('nombre', '').strip()
        if not nombre:
            errors['nombre'] = ['El nombre es obligatorio.']

        tipo = body.get('tipo', TipoOferta.PORCENTAJE)
        if tipo not in TipoOferta.values:
            errors['tipo'] = ['Tipo de oferta inválido.']
            tipo = TipoOferta.PORCENTAJE

        porcentaje = None
        cantidad_lleva = None
        cantidad_paga = None
        monto_minimo = None
        base_calculo = ''

        if tipo == TipoOferta.NXM:
            try:
                cantidad_lleva = int(body.get('cantidad_lleva', ''))
                cantidad_paga  = int(body.get('cantidad_paga', ''))
                if cantidad_lleva < 2:
                    errors['cantidad_lleva'] = ['Tiene que ser al menos 2 (ej: 2 en un 2x1).']
                if cantidad_paga < 1:
                    errors['cantidad_paga'] = ['Tiene que ser al menos 1.']
                if cantidad_lleva and cantidad_paga and cantidad_paga >= cantidad_lleva:
                    errors['cantidad_paga'] = ['Tiene que ser menor que "Llevá" (si no, no hay descuento).']
            except (ValueError, TypeError):
                errors['cantidad_lleva'] = ['Completá "Llevá" y "Pagá" con números enteros.']
                cantidad_lleva = cantidad_paga = None
        elif tipo == TipoOferta.UMBRAL:
            try:
                porcentaje = Decimal(str(body.get('porcentaje', '')))
                if porcentaje < 0 or porcentaje > 100:
                    errors['porcentaje'] = ['El porcentaje debe estar entre 0 y 100.']
            except Exception:
                errors['porcentaje'] = ['El porcentaje es inválido.']
                porcentaje = None
            try:
                monto_minimo = Decimal(str(body.get('monto_minimo', '')))
                if monto_minimo <= 0:
                    errors['monto_minimo'] = ['Tiene que ser mayor a 0.']
            except Exception:
                errors['monto_minimo'] = ['El monto mínimo es inválido.']
                monto_minimo = None
            base_calculo = body.get('base_calculo', BaseCalculoUmbral.NETO)
            if base_calculo not in BaseCalculoUmbral.values:
                errors['base_calculo'] = ['Base de cálculo inválida.']
        else:
            try:
                porcentaje = Decimal(str(body.get('porcentaje', '')))
                if porcentaje < 0 or porcentaje > 100:
                    errors['porcentaje'] = ['El porcentaje debe estar entre 0 y 100.']
            except Exception:
                errors['porcentaje'] = ['El porcentaje es inválido.']
                porcentaje = None

        try:
            fecha_inicio = date.fromisoformat(body.get('fecha_inicio', ''))
        except (ValueError, TypeError):
            errors['fecha_inicio'] = ['Fecha de inicio inválida.']
            fecha_inicio = None

        try:
            fecha_fin = date.fromisoformat(body.get('fecha_fin', ''))
        except (ValueError, TypeError):
            errors['fecha_fin'] = ['Fecha de fin inválida.']
            fecha_fin = None

        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            errors['fecha_fin'] = ['La fecha de fin no puede ser anterior a la de inicio.']

        dias_semana_raw = body.get('dias_semana', [])
        try:
            dias_semana = sorted({int(d) for d in dias_semana_raw})
            if any(d < 0 or d > 6 for d in dias_semana):
                raise ValueError
        except (ValueError, TypeError):
            errors['dias_semana'] = ['Días de la semana inválidos.']
            dias_semana = []

        aplicacion = body.get('aplicacion', AplicacionOferta.AUTOMATICA)
        if aplicacion not in AplicacionOferta.values:
            errors['aplicacion'] = ['Aplicación inválida.']

        pk = body.get('pk')
        if pk:
            oferta = get_object_or_404(Oferta, pk=pk)
        else:
            oferta = Oferta()

        if nombre:
            qs = Oferta.objects.filter(nombre__iexact=nombre)
            if oferta.pk:
                qs = qs.exclude(pk=oferta.pk)
            if qs.exists():
                errors['nombre'] = ['Ya existe una oferta con ese nombre.']

        if errors:
            return JsonResponse({'ok': False, 'errors': errors}, status=400)

        # El alcance por producto/categoría no aplica a UMBRAL (es sobre
        # el total de la venta, no sobre un producto puntual).
        productos_pks  = [] if tipo == TipoOferta.UMBRAL else body.get('productos', [])
        categorias_pks = [] if tipo == TipoOferta.UMBRAL else body.get('categorias', [])

        oferta.nombre          = nombre
        oferta.tipo            = tipo
        oferta.porcentaje      = porcentaje
        oferta.cantidad_lleva  = cantidad_lleva
        oferta.cantidad_paga   = cantidad_paga
        oferta.monto_minimo    = monto_minimo
        oferta.base_calculo    = base_calculo
        oferta.fecha_inicio = fecha_inicio
        oferta.fecha_fin    = fecha_fin
        oferta.dias_semana  = ','.join(str(d) for d in dias_semana)
        oferta.aplicacion   = aplicacion
        oferta.orden        = int(body.get('orden', oferta.orden if oferta.pk else 0))
        oferta.activa       = body.get('activa', True)
        oferta.save()

        oferta.productos.set(Producto.objects.filter(pk__in=productos_pks))
        oferta.categorias.set(CategoriaProducto.objects.filter(pk__in=categorias_pks))

        return JsonResponse({
            'ok':     True,
            'pk':     oferta.pk,
            'nombre': oferta.nombre,
            'creado': pk is None,
            'data':   _serializar_oferta(oferta),
        })


class OfertaEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina una oferta.

    No hay relación por clave foránea con ventas ya cargadas (el
    ítem de venta solo guarda el nombre como texto suelto, igual que
    ListaDescuento), así que borrarla no rompe nada del historial.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_ofertas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)

        oferta = get_object_or_404(Oferta, pk=pk)
        nombre = oferta.nombre
        oferta.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})
