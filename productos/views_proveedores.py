import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

from .models import Proveedor
from .forms import ProveedorForm
from core.permisos import chequear_permiso  # ← único import nuevo


class GestionProveedoresView(LoginRequiredMixin, TemplateView):
    """Vista principal — renderiza la página con la tabla de proveedores."""
    template_name = 'productos/proveedores.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # ── Permisos para el template ─────────────────────────────
        ctx['puede_crear']    = chequear_permiso(self.request.user, 'crear_proveedores')
        ctx['puede_editar']   = chequear_permiso(self.request.user, 'editar_proveedores')
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, 'eliminar_proveedores')

        if not chequear_permiso(self.request.user, 'ver_proveedores'):
            ctx['sin_permiso'] = True
            return ctx

        qs = Proveedor.objects.all().order_by('nombre')

        # Búsqueda rápida
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(cuit__icontains=q)

        # Filtro activo/inactivo
        estado = self.request.GET.get('estado', '')
        if estado == 'activo':
            qs = qs.filter(activo=True)
        elif estado == 'inactivo':
            qs = qs.filter(activo=False)

        paginator = Paginator(qs, 20)
        page      = self.request.GET.get('page', 1)

        ctx['proveedores'] = paginator.get_page(page)
        ctx['form']        = ProveedorForm()
        ctx['total']       = Proveedor.objects.count()
        ctx['activos']     = Proveedor.objects.filter(activo=True).count()
        ctx['q']           = q
        ctx['estado']      = estado
        return ctx


class ProveedorCrearEditarAjax(LoginRequiredMixin, View):
    """GET: datos para pre-llenar el modal. POST: crea o edita un proveedor."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_proveedores'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.GET.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)

        proveedor = get_object_or_404(Proveedor, pk=pk)
        data = {
            'pk':              proveedor.pk,
            'nombre':          proveedor.nombre,
            'cuit':            proveedor.cuit,
            'tipo':            proveedor.tipo,
            'activo':          proveedor.activo,
            'sitio_web':       proveedor.sitio_web,
            'descripcion':     proveedor.descripcion,
            'email':           proveedor.email,
            'telefono':        proveedor.telefono,
            'contacto_nombre': proveedor.contacto_nombre,
            'contacto_cargo':  proveedor.contacto_cargo,
            'calle':           proveedor.calle,
            'ciudad':          proveedor.ciudad,
            'provincia':       proveedor.provincia,
            'pais':            proveedor.pais,
            'condicion_pago':  proveedor.condicion_pago,
            'moneda':          proveedor.moneda,
            'dias_entrega':    proveedor.dias_entrega,
            'notas':           proveedor.notas,
        }
        return JsonResponse(data)

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')

        # Si tiene pk es edición, si no es creación — permiso distinto para cada caso
        if pk:
            if not chequear_permiso(request.user, 'editar_proveedores'):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)
        else:
            if not chequear_permiso(request.user, 'crear_proveedores'):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)

        inst = get_object_or_404(Proveedor, pk=pk) if pk else None
        form = ProveedorForm(body, instance=inst)

        if form.is_valid():
            proveedor = form.save()
            return JsonResponse({
                'ok':     True,
                'pk':     proveedor.pk,
                'nombre': proveedor.nombre,
                'creado': inst is None,
            })

        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)


class ProveedorEliminarAjax(LoginRequiredMixin, View):
    """POST: elimina un proveedor."""

    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_proveedores'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)

        proveedor = get_object_or_404(Proveedor, pk=pk)
        nombre    = proveedor.nombre
        proveedor.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})


class ProveedorBuscarAjax(LoginRequiredMixin, View):
    """GET: búsqueda rápida para selects/autocomplete (ej: en compras)."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_proveedores'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q  = request.GET.get('q', '').strip()
        qs = Proveedor.objects.filter(activo=True).order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q)
        data = [{'pk': p.pk, 'nombre': p.nombre} for p in qs[:20]]
        return JsonResponse({'results': data})