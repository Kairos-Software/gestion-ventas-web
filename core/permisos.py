# core/permisos.py
#
# HELPER CENTRAL DE PERMISOS
# ─────────────────────────────────────────────────────────────────
# Este archivo es el único lugar donde vive la lógica híbrida.
# Cualquier view que necesite chequear un permiso importa de acá.
#
# USO en cualquier view:
#
#   from .permisos import chequear_permiso, permisos_del_usuario
#
#   if not chequear_permiso(request.user, 'crear_usuarios'):
#       return JsonResponse({'error': 'Sin permiso'}, status=403)
#
# ─────────────────────────────────────────────────────────────────

from .models import UsuarioPermisoOverride, CODIGOS_PERMISOS, PERMISOS_RESTRINGIDOS


def chequear_permiso(usuario, codigo_permiso):
    """
    Devuelve True si el usuario tiene el permiso dado.

    Lógica híbrida:
    1. Superusuario → siempre True (sin chequeos)
    2. Override individual → gana siempre (True o False)
    3. Permiso del rol → si no hay override, se usa el rol
    4. Sin rol y sin override → False
    """
    if usuario.is_superuser:
        return True

    if codigo_permiso not in CODIGOS_PERMISOS:
        return False  # permiso inexistente → denegar

    # Buscar override individual
    try:
        override = UsuarioPermisoOverride.objects.get(
            usuario=usuario,
            permiso=codigo_permiso
        )
        return override.concedido
    except UsuarioPermisoOverride.DoesNotExist:
        pass

    # Usar permisos del rol
    if usuario.rol:
        return codigo_permiso in usuario.rol.get_permisos()

    return False


def filtrar_permisos_otorgables(codigos, solicitante):
    """
    Dado un conjunto de códigos de permiso que alguien quiere otorgar
    (a un usuario individual o a un Rol completo), devuelve solo los
    que `solicitante` está autorizado a otorgar.

    Los códigos en PERMISOS_RESTRINGIDOS (ej: 'editar_empresa') solo
    pueden ser otorgados por un superusuario — ni siquiera alguien
    con 'gestionar_permisos' puede asignarlos. Hay que llamar a esta
    función en TODO lugar donde se guarden permisos: tanto al guardar
    overrides individuales (guardar_permisos_usuario) como al guardar
    el listado de permisos de un Rol (en views_permisos.py).
    """
    codigos = set(codigos)
    if solicitante and solicitante.is_superuser:
        return codigos
    return codigos - PERMISOS_RESTRINGIDOS


def permisos_del_usuario(usuario, solicitante=None):
    """
    Devuelve un dict completo con el estado de cada permiso para un usuario.
    Útil para renderizar la pantalla de gestión de permisos.

    `solicitante` es el usuario logueado que está viendo/editando la
    pantalla (el admin). Se usa solo para calcular 'editable': si es
    False, el template debe renderizar ese permiso como bloqueado
    (el solicitante puede ver su estado actual, pero no cambiarlo).

    Formato devuelto:
    {
        'ver_usuarios': {
            'concedido': True,
            'fuente': 'rol' | 'override_positivo' | 'override_negativo' | 'sin_permiso' | 'superusuario',
            'editable': True | False
        },
        ...
    }
    """
    from .models import PERMISOS_CHOICES

    if usuario.is_superuser:
        return {
            codigo: {'concedido': True, 'fuente': 'superusuario', 'editable': False}
            for codigo, _ in PERMISOS_CHOICES
        }

    permisos_rol = usuario.rol.get_permisos() if usuario.rol else set()

    overrides = {
        o.permiso: o.concedido
        for o in UsuarioPermisoOverride.objects.filter(usuario=usuario)
    }

    resultado = {}
    for codigo, _ in PERMISOS_CHOICES:
        if codigo in overrides:
            concedido = overrides[codigo]
            fuente = 'override_positivo' if concedido else 'override_negativo'
        elif codigo in permisos_rol:
            concedido = True
            fuente = 'rol'
        else:
            concedido = False
            fuente = 'sin_permiso'

        es_restringido = codigo in PERMISOS_RESTRINGIDOS
        editable = not es_restringido or (solicitante is not None and solicitante.is_superuser)

        resultado[codigo] = {
            'concedido': concedido,
            'fuente': fuente,
            'editable': editable,
        }

    return resultado


def guardar_permisos_usuario(usuario, permisos_enviados, solicitante):
    """
    Recibe un dict {codigo: bool} con los permisos que el admin quiere setear.
    Calcula qué es override (difiere del rol) y qué no, y guarda solo los overrides.

    `solicitante` = el usuario logueado que está guardando (el admin).
    Si `permisos_enviados` incluye un código restringido (ver
    PERMISOS_RESTRINGIDOS) y `solicitante` no es superusuario, ese
    código se ignora en silencio — no se guarda, no rompe el resto.

    permisos_enviados = {'ver_usuarios': True, 'crear_usuarios': False, ...}
    """
    permisos_rol = usuario.rol.get_permisos() if usuario.rol else set()

    codigos_permitidos = filtrar_permisos_otorgables(permisos_enviados.keys(), solicitante)

    for codigo, concedido in permisos_enviados.items():
        if codigo not in CODIGOS_PERMISOS:
            continue
        if codigo not in codigos_permitidos:
            continue  # restringido y el solicitante no es superusuario

        en_rol = codigo in permisos_rol

        if concedido == en_rol:
            # Coincide con el rol → no necesita override, borramos si existía
            UsuarioPermisoOverride.objects.filter(
                usuario=usuario, permiso=codigo
            ).delete()
        else:
            # Difiere del rol → guardamos override
            UsuarioPermisoOverride.objects.update_or_create(
                usuario=usuario,
                permiso=codigo,
                defaults={'concedido': concedido}
            )