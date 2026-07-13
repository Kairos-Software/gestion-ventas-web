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


def _permisos_efectivos(usuario):
    """
    Devuelve el set de códigos de permiso que `usuario` tiene
    concedidos ahora mismo (rol + overrides ya resueltos).
    Una sola query extra — se usa para no repetir chequear_permiso()
    (que consulta la base) por cada código del catálogo.
    """
    if usuario.is_superuser:
        return set(CODIGOS_PERMISOS)

    permisos_rol = usuario.rol.get_permisos() if usuario.rol else set()
    overrides = {
        o.permiso: o.concedido
        for o in UsuarioPermisoOverride.objects.filter(usuario=usuario)
    }

    resultado = set()
    for codigo in CODIGOS_PERMISOS:
        if codigo in overrides:
            if overrides[codigo]:
                resultado.add(codigo)
        elif codigo in permisos_rol:
            resultado.add(codigo)
    return resultado


def filtrar_permisos_otorgables(codigos, solicitante):
    """
    Dado un conjunto de códigos de permiso que alguien quiere otorgar
    (a un usuario individual o a un Rol completo), devuelve solo los
    que `solicitante` está autorizado a otorgar.

    Dos reglas, ambas obligatorias:

    1. Nadie puede otorgar un permiso que no tiene él mismo. Un
       solicitante sin 'eliminar_clientes' no puede dárselo a otro
       usuario aunque tenga 'gestionar_permisos' — solo puede
       redistribuir lo que ya posee. Esto es transitivo y por lo
       tanto siempre seguro: si A le da 'gestionar_permisos' a B sin
       darle 'eliminar_clientes', B tampoco va a poder otorgar
       'eliminar_clientes' a nadie, porque B no lo tiene.
    2. Los códigos en PERMISOS_RESTRINGIDOS (ej: 'editar_empresa')
       solo puede otorgarlos un superusuario, incluso si el
       solicitante los tiene concedidos a sí mismo.

    Los superusuarios están exentos de ambas reglas.

    Hay que llamar a esta función en TODO lugar donde se guarden
    permisos: tanto al guardar overrides individuales
    (guardar_permisos_usuario) como al guardar el listado de permisos
    de un Rol (en views_permisos.py).
    """
    codigos = set(codigos)
    if not solicitante:
        return set()
    if solicitante.is_superuser:
        return codigos

    permisos_solicitante = _permisos_efectivos(solicitante)
    return {
        c for c in codigos
        if c not in PERMISOS_RESTRINGIDOS and c in permisos_solicitante
    }


def permisos_del_usuario(usuario, solicitante=None):
    """
    Devuelve un dict completo con el estado de cada permiso para un usuario.
    Útil para renderizar la pantalla de gestión de permisos.

    `solicitante` es el usuario logueado que está viendo/editando la
    pantalla (el admin). Se usa para calcular 'editable': si es
    False, el template debe renderizar ese permiso como bloqueado
    (el solicitante puede ver su estado actual, pero no cambiarlo) —
    'motivo_bloqueo' explica por qué (candado distinto en cada caso).

    Formato devuelto:
    {
        'ver_usuarios': {
            'concedido': True,
            'fuente': 'rol' | 'override_positivo' | 'override_negativo' | 'sin_permiso' | 'superusuario',
            'editable': True | False,
            'motivo_bloqueo': None | 'restringido' | 'sin_permiso_propio' | 'sin_solicitante',
        },
        ...
    }
    """
    from .models import PERMISOS_CHOICES

    if usuario.is_superuser:
        return {
            codigo: {
                'concedido': True, 'fuente': 'superusuario',
                'editable': False, 'motivo_bloqueo': None,
            }
            for codigo, _ in PERMISOS_CHOICES
        }

    permisos_rol = usuario.rol.get_permisos() if usuario.rol else set()

    overrides = {
        o.permiso: o.concedido
        for o in UsuarioPermisoOverride.objects.filter(usuario=usuario)
    }

    # Permisos que el propio `solicitante` tiene concedidos ahora mismo —
    # se usa para no poder otorgar más de lo que uno mismo posee (ver
    # filtrar_permisos_otorgables). Una sola query extra, no una por código.
    solicitante_superuser = bool(solicitante and solicitante.is_superuser)
    permisos_solicitante = (
        _permisos_efectivos(solicitante)
        if solicitante and not solicitante_superuser
        else set()
    )

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

        if solicitante is None:
            editable, motivo_bloqueo = False, 'sin_solicitante'
        elif solicitante_superuser:
            editable, motivo_bloqueo = True, None
        elif es_restringido:
            editable, motivo_bloqueo = False, 'restringido'
        elif codigo not in permisos_solicitante:
            editable, motivo_bloqueo = False, 'sin_permiso_propio'
        else:
            editable, motivo_bloqueo = True, None

        resultado[codigo] = {
            'concedido': concedido,
            'fuente': fuente,
            'editable': editable,
            'motivo_bloqueo': motivo_bloqueo,
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