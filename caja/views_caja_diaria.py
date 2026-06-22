from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from core.permisos import chequear_permiso


# ══════════════════════════════════════════════════════════════════
#  CAJA DIARIA — pendiente de desarrollo
#  Acá va a vivir la lógica de la caja chica/diaria: lo que se
#  factura día a día, probablemente con apertura/cierre de turno
#  y conciliación contra la caja grande. Se construye en el
#  siguiente paso, siguiendo el mismo patrón que views_caja_grande.py.
# ══════════════════════════════════════════════════════════════════

class CajaDiariaView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/caja_diaria.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_caja'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_ver'] = True
        ctx['en_construccion'] = True
        return ctx