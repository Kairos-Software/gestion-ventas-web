# core/views_permisos.py
import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from .models import Usuario, Rol, PERMISOS_CHOICES
from .permisos import (
    chequear_permiso,
    permisos_del_usuario,
    guardar_permisos_usuario,
    filtrar_permisos_otorgables,
)


# Agrupación exclusivamente visual para que la matriz de permisos sea fácil de
# recorrer. Los códigos y la lógica de autorización no cambian.
SECCIONES_PERMISOS = (
    ('Administración', {'Usuarios', 'Permisos', 'Empresa', 'Notificaciones'}),
    ('Productos e inventario', {'Stock', 'Productos', 'Categorias', 'Descuento', 'Ofertas', 'Paquetes', 'Catalogo'}),
    ('Compras y proveedores', {'Proveedores', 'Compras'}),
    ('Clientes y ventas', {'Clientes', 'Ventas', 'Devoluciones', 'Presupuestos', 'Pedidos', 'Balanza'}),
    ('Caja y movimientos', {'Cuentas', 'Recargos', 'Caja', 'Turno', 'Transacciones', 'Gastos'}),
    ('Créditos y valores', {'Deudas', 'Deuda', 'Cobrar', 'Cobro', 'Cheques'}),
    ('Organización', {'Notas', 'Privadas'}),
)

SECCION_POR_MODULO = {
    modulo: seccion
    for seccion, modulos in SECCIONES_PERMISOS
    for modulo in modulos
}


class GestionPermisosView(LoginRequiredMixin, View):
    def get(self, request, pk):
        # Sin permiso → volvemos a gestion_usuarios con mensaje, no página rota
        if not chequear_permiso(request.user, 'gestionar_permisos'):
            qs = Usuario.objects.filter(is_superuser=False).order_by('username')
            if not request.user.is_superuser:
                qs = qs.exclude(pk=request.user.pk)
            return render(request, 'core/gestion_usuarios.html', {
                'usuarios': qs,
                'sin_permiso': False,
                'puede_crear': chequear_permiso(request.user, 'crear_usuarios'),
                'puede_editar': chequear_permiso(request.user, 'editar_usuarios'),
                'puede_eliminar': chequear_permiso(request.user, 'eliminar_usuarios'),
                'puede_gestionar_permisos': False,
                'error_msg': 'No tenés permiso para gestionar permisos de otros usuarios.',
            }, status=403)

        usuario_obj = get_object_or_404(Usuario, pk=pk, is_superuser=False)

        # Pasamos solicitante=request.user para que cada permiso traiga
        # 'editable': False si es restringido y quien mira la pantalla
        # no es superusuario (el template puede usarlo para deshabilitar
        # el checkbox y mostrar un candado).
        estado = permisos_del_usuario(usuario_obj, solicitante=request.user)

        # Antes cada última palabra del código generaba una tarjeta diferente
        # (más de 30 tarjetas para 75 permisos). Se mantienen esos módulos como
        # referencia interna, pero se presentan en áreas funcionales amplias.
        secciones = {nombre: [] for nombre, _ in SECCIONES_PERMISOS}
        for codigo, label in PERMISOS_CHOICES:
            partes = codigo.split('_')
            modulo = partes[-1].capitalize() if len(partes) > 1 else 'General'
            seccion = SECCION_POR_MODULO.get(modulo, 'Otros')
            secciones.setdefault(seccion, []).append({
                'codigo': codigo,
                'label': label,
                'modulo': modulo,
                **estado[codigo],
            })

        secciones = [(nombre, permisos) for nombre, permisos in secciones.items() if permisos]

        context = {
            'usuario_obj': usuario_obj,
            'modulos': secciones,
            'tiene_rol': usuario_obj.rol is not None,
            'rol_nombre': usuario_obj.rol.nombre if usuario_obj.rol else None,
        }
        return render(request, 'core/permisos_usuario.html', context)


class GuardarPermisosAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'gestionar_permisos'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario_obj = get_object_or_404(Usuario, pk=pk, is_superuser=False)

        try:
            body = json.loads(request.body)
            permisos_enviados = body.get('permisos', {})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        permisos_bool = {k: bool(v) for k, v in permisos_enviados.items()}

        # solicitante=request.user → si manda 'editar_empresa' y no es
        # superusuario, guardar_permisos_usuario lo ignora en silencio.
        guardar_permisos_usuario(usuario_obj, permisos_bool, solicitante=request.user)
        return JsonResponse({'success': True})


class GuardarPermisosRolAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_permisos'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        try:
            body = json.loads(request.body)
            rol_pk = body.get('rol_pk')
            permisos_lista = body.get('permisos', [])
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        rol = get_object_or_404(Rol, pk=rol_pk)

        # Este era el agujero: sin este filtro, el dueño podía meter
        # 'editar_empresa' en un Rol y asignárselo a cualquier empleado,
        # esquivando por completo la restricción de arriba.
        permisos_permitidos = filtrar_permisos_otorgables(permisos_lista, request.user)
        rol.set_permisos(permisos_permitidos)
        return JsonResponse({'success': True})
