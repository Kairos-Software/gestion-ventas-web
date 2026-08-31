"""
core/context_processors.py

`perms_kai` — objeto para consultar permisos desde cualquier template sin
tener que pasarlos uno por uno en el contexto de cada vista. Resuelve el
set de permisos efectivos del usuario (rol + overrides) UNA sola vez por
request.

Uso en templates:

    {% if perms_kai.ver_ventas %} ... {% endif %}
    {% if 'ver_ventas' in perms_kai %} ... {% endif %}
    {% if perms_kai.ver_ventas or perms_kai.ver_compras %} ... {% endif %}

Un permiso inexistente o no concedido devuelve False (nunca rompe el
render). El backend NO se apoya en esto: cada vista sigue chequeando con
`chequear_permiso` — esto es solo para mostrar/ocultar en la UI.
"""

from .permisos import permisos_efectivos


class _PermisosProxy:
    """Wrapper de solo-lectura sobre el set de códigos concedidos."""

    __slots__ = ('_codigos',)

    def __init__(self, codigos):
        object.__setattr__(self, '_codigos', codigos)

    def __contains__(self, codigo):
        return codigo in self._codigos

    def __getattr__(self, codigo):
        # __getattr__ solo se llama si el atributo no existe por la vía
        # normal, así que '_codigos' (slot) nunca cae acá.
        return codigo in self._codigos

    def __bool__(self):
        return bool(self._codigos)

    def __iter__(self):
        return iter(self._codigos)


def perms_kai(request):
    usuario = getattr(request, 'user', None)
    if usuario is None or not usuario.is_authenticated:
        return {'perms_kai': _PermisosProxy(frozenset())}
    return {'perms_kai': _PermisosProxy(frozenset(permisos_efectivos(usuario)))}
