from datetime import timedelta

from django.utils import timezone

from ..models import HistorialNotificacion


def ya_notificado(tipo, referencia, dentro_de_dias):
    """
    True si ya se mandó (con éxito) una notificación de este tipo y
    referencia dentro de la ventana de días indicada. Evita re-avisar
    todos los días la misma condición (ej: el mismo lote por vencer).
    """
    limite = timezone.now() - timedelta(days=dentro_de_dias)
    return HistorialNotificacion.objects.filter(
        tipo=tipo, referencia=str(referencia), exito=True, enviado_el__gte=limite,
    ).exists()
