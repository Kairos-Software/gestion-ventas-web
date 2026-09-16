# core/views_permisos.py
import json
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from .models import Usuario, Rol, PERMISOS_CHOICES, PERMISOS_RESTRINGIDOS, CODIGOS_PERMISOS
from .permisos import (
    chequear_permiso,
    permisos_del_usuario,
    permisos_efectivos,
    guardar_permisos_usuario,
    filtrar_permisos_otorgables,
)


# Agrupación exclusivamente visual para que la matriz de permisos sea fácil de
# recorrer. Los códigos y la lógica de autorización no cambian.
SECCIONES_PERMISOS = (
    ('Administración', {'Usuarios', 'Permisos', 'Roles', 'Empresa', 'Notificaciones'}),
    ('Estadísticas', {'Estadisticas'}),
    ('Productos e inventario', {'Stock', 'Productos', 'Categorias', 'Descuento', 'Ofertas', 'Paquetes', 'Catalogo'}),
    ('Compras y proveedores', {'Proveedores', 'Compras', 'Inicial'}),
    ('Clientes y ventas', {'Clientes', 'Ventas', 'Devoluciones', 'Presupuestos', 'Pedidos', 'Balanza'}),
    ('Caja y movimientos', {'Cuentas', 'Recargos', 'Caja', 'Turno', 'Transacciones', 'Gastos', 'Bienes', 'Celulares'}),
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


class RolesListarAjax(LoginRequiredMixin, View):
    """
    Lista fresca de perfiles con su cantidad de usuarios asignados. El modal
    de "Perfiles de permisos" la pide cada vez que se abre en vez de confiar
    en la lista que vino en el HTML inicial de la página — si se crea/edita
    un usuario con un perfil sin recargar la pantalla, esa lista inicial
    queda con los conteos viejos.
    """
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_roles'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        roles = Rol.objects.annotate(num_usuarios=Count('usuario')).order_by('nombre')
        return JsonResponse({
            'roles': [
                {'pk': r.pk, 'nombre': r.nombre, 'num_usuarios': r.num_usuarios}
                for r in roles
            ],
        })


class RolPermisosView(LoginRequiredMixin, View):
    """
    Pantalla de un perfil de permisos — copia fiel de GestionPermisosView /
    permisos_usuario.html (mismo buscador, filtros, tarjetas por módulo con
    candado en lo restringido) para que armar o editar un perfil se sienta
    exactamente igual a tocar los permisos de un usuario puntual. `pk` ausente
    = alta nueva; con `pk` = edición de un perfil existente.
    """
    def get(self, request, pk=None):
        permiso_requerido = 'editar_roles' if pk else 'crear_roles'
        if not chequear_permiso(request.user, permiso_requerido):
            qs = Usuario.objects.filter(is_superuser=False).order_by('username')
            if not request.user.is_superuser:
                qs = qs.exclude(pk=request.user.pk)
            return render(request, 'core/gestion_usuarios.html', {
                'usuarios': qs,
                'sin_permiso': False,
                'puede_crear': chequear_permiso(request.user, 'crear_usuarios'),
                'puede_editar': chequear_permiso(request.user, 'editar_usuarios'),
                'puede_eliminar': chequear_permiso(request.user, 'eliminar_usuarios'),
                'error_msg': 'No tenés permiso para gestionar perfiles de permisos.',
            }, status=403)

        rol = get_object_or_404(Rol, pk=pk) if pk else None
        permisos_rol = rol.get_permisos() if rol else set()

        solicitante_superuser = request.user.is_superuser
        propios = permisos_efectivos(request.user) if not solicitante_superuser else set()

        secciones = {nombre: [] for nombre, _ in SECCIONES_PERMISOS}
        for codigo, label in PERMISOS_CHOICES:
            partes = codigo.split('_')
            modulo = partes[-1].capitalize() if len(partes) > 1 else 'General'
            seccion = SECCION_POR_MODULO.get(modulo, 'Otros')
            restringido = codigo in PERMISOS_RESTRINGIDOS
            if solicitante_superuser:
                editable, motivo_bloqueo = True, None
            elif restringido:
                editable, motivo_bloqueo = False, 'restringido'
            elif codigo not in propios:
                editable, motivo_bloqueo = False, 'sin_permiso_propio'
            else:
                editable, motivo_bloqueo = True, None
            secciones.setdefault(seccion, []).append({
                'codigo': codigo,
                'label': label,
                'modulo': modulo,
                'concedido': codigo in permisos_rol,
                'editable': editable,
                'motivo_bloqueo': motivo_bloqueo,
            })

        secciones = [(nombre, permisos) for nombre, permisos in secciones.items() if permisos]

        return render(request, 'core/rol_permisos.html', {
            'rol': rol,
            'secciones': secciones,
        })


class RolCrearEditarAjax(LoginRequiredMixin, View):
    """POST crea o edita un perfil según venga 'pk' en el body (usado por
    rol_permisos.html al guardar)."""

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        pk = body.get('pk')
        # Alta y edición son dos permisos distintos, aunque compartan endpoint.
        permiso_requerido = 'editar_roles' if pk else 'crear_roles'
        if not chequear_permiso(request.user, permiso_requerido):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        nombre = (body.get('nombre') or '').strip()
        if not nombre:
            return JsonResponse({'error': 'Ponele un nombre al perfil.'}, status=400)
        qs_dup = Rol.objects.filter(nombre__iexact=nombre)
        if pk:
            qs_dup = qs_dup.exclude(pk=pk)
        if qs_dup.exists():
            return JsonResponse({'error': f'Ya existe un perfil llamado "{nombre}".'}, status=400)

        if pk:
            rol = get_object_or_404(Rol, pk=pk)
        else:
            rol = Rol()

        # No se reemplaza la lista entera a lo bruto: se calcula qué códigos
        # puede tocar `request.user` (mismo filtro que cualquier otra
        # pantalla de permisos — nada nuevo) y SOLO esos se actualizan según
        # lo que llegó tildado. Todo lo que quede fuera de su alcance (un
        # restringido, o algo que un solicitante no-superusuario nunca tuvo
        # concedido a sí mismo) se deja EXACTAMENTE como estaba, sin importar
        # qué haya llegado en el POST. Si no fuera así, un checkbox
        # bloqueado-pero-tildado (algo restringido que otro superusuario le
        # había puesto antes a este perfil) se perdería solo con guardar
        # cualquier otro cambio del perfil — mismo criterio que ya usa
        # guardar_permisos_usuario() para overrides individuales.
        otorgables = filtrar_permisos_otorgables(CODIGOS_PERMISOS, request.user)
        enviados = set(body.get('permisos', []))
        permisos_finales = (rol.get_permisos() - otorgables) | (enviados & otorgables)

        rol.nombre = nombre
        rol.descripcion = (body.get('descripcion') or '').strip()
        rol.save()
        rol.set_permisos(permisos_finales)

        return JsonResponse({'success': True, 'pk': rol.pk})


class RolEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_roles'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        rol = get_object_or_404(Rol, pk=body.get('pk'))

        cantidad = Usuario.objects.filter(rol=rol).count()
        if cantidad:
            plural = 'usuario tiene' if cantidad == 1 else 'usuarios tienen'
            return JsonResponse({
                'error': f'No se puede borrar: {cantidad} {plural} este perfil asignado. '
                         f'Reasignalos a otro perfil (o sacáselo) antes de borrarlo.',
            }, status=400)

        rol.delete()
        return JsonResponse({'success': True})
