from django.db import models


class CanalNotificacion(models.TextChoices):
    EMAIL = 'email', 'Solo email'
    WHATSAPP = 'whatsapp', 'Solo WhatsApp'
    AMBOS = 'ambos', 'Email y WhatsApp'
    NINGUNO = 'ninguno', 'Ninguno (desactivado)'


class PreferenciaAsistencia(models.Model):
    """
    Configuración de cuándo y cómo se mandan los reportes/alertas de
    asistencia. Modelo singleton (mismo patrón que core.DatosEmpresa):
    es la preferencia del DUEÑO del negocio, no de cada usuario/
    empleado, por eso no hay un selector de "a qué usuario pertenece".

    El acceso pasa por el permiso 'gestionar_notificaciones' (ver
    core/views.py:configuracion y asistencia/views.py), que está en
    PERMISOS_RESTRINGIDOS (core.models): solo un superusuario puede
    otorgárselo a otro usuario —nadie puede delegarlo por su cuenta,
    ni siquiera alguien con 'gestionar_permisos'—, pero quien lo
    recibe (típicamente el dueño del negocio) lo usa sin necesitar
    ser superusuario.
    """
    canal = models.CharField(
        max_length=10, choices=CanalNotificacion.choices, default=CanalNotificacion.EMAIL,
    )
    email_destino = models.EmailField(
        blank=True, help_text='Si se deja vacío, se usa el email de Datos de la empresa.',
    )
    whatsapp_destino = models.CharField(
        max_length=30, blank=True,
        help_text='Número con código de país (ej: 5491122334455). Todavía no implementado.',
    )

    recibir_reporte_mensual = models.BooleanField(default=True)
    dia_mes_reporte = models.PositiveSmallIntegerField(
        default=1, help_text='Día del mes (1-28) en que se manda el reporte mensual.',
    )
    recibir_reporte_semanal = models.BooleanField(default=False)
    dia_semana_reporte = models.PositiveSmallIntegerField(
        default=0, help_text='Día de la semana del reporte semanal (0=lunes ... 6=domingo).',
    )

    recibir_alerta_vencimiento = models.BooleanField(default=True)
    dias_aviso_vencimiento = models.PositiveSmallIntegerField(
        default=14, help_text='Avisar productos que vencen dentro de esta cantidad de días.',
    )
    recibir_alerta_deuda = models.BooleanField(default=True)
    dias_aviso_deuda = models.PositiveSmallIntegerField(
        default=2, help_text='Avisar deudas que vencen dentro de esta cantidad de días.',
    )
    recibir_deuda_pagada = models.BooleanField(default=True)
    recibir_stock_estancado = models.BooleanField(default=True)
    dias_stock_estancado = models.PositiveSmallIntegerField(
        default=60, help_text='Sin ventas en esta cantidad de días = stock estancado.',
    )
    recibir_alerta_cheques = models.BooleanField(default=True)

    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Preferencia de asistencia'
        verbose_name_plural = 'Preferencia de asistencia'

    def __str__(self):
        return 'Preferencias de asistencia'

    @classmethod
    def get_solo(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def email_efectivo(self):
        """
        A propósito NO cae en DatosEmpresa.email como respaldo: ese es
        el mail público (el mismo que se imprime en los tickets), y acá
        nunca se le avisó al usuario que sus reportes/alertas podrían
        terminar ahí. Si no cargó un email acá, simplemente no se manda
        nada — mejor eso que mandarlo a un lugar inesperado.
        """
        if self.canal not in (CanalNotificacion.EMAIL, CanalNotificacion.AMBOS):
            return None
        return self.email_destino or None

    @property
    def whatsapp_efectivo(self):
        if self.canal not in (CanalNotificacion.WHATSAPP, CanalNotificacion.AMBOS):
            return None
        return self.whatsapp_destino


class TipoNotificacion(models.TextChoices):
    REPORTE_PERIODICO = 'reporte_periodico', 'Reporte periódico'
    ALERTA_VENCIMIENTO = 'alerta_vencimiento', 'Producto por vencer'
    ALERTA_DEUDA = 'alerta_deuda', 'Deuda próxima a vencer'
    DEUDA_PAGADA = 'deuda_pagada', 'Deuda pagada'
    STOCK_ESTANCADO = 'stock_estancado', 'Stock sin movimiento'
    ALERTA_CHEQUE = 'alerta_cheque', 'Cheque próximo a vencer'


class HistorialNotificacion(models.Model):
    """
    Registro de cada notificación enviada (o intentada). Permite no
    repetir la misma alerta mientras la condición siga activa (ej: un
    lote por vencer no se re-avisa a diario) y da trazabilidad de qué
    se mandó y cuándo.
    """
    tipo = models.CharField(max_length=30, choices=TipoNotificacion.choices)
    referencia = models.CharField(
        max_length=50, blank=True,
        help_text='Identificador del objeto referido (código de lote, id de cuota, etc).',
    )
    destinatario = models.EmailField()
    asunto = models.CharField(max_length=255)
    canal = models.CharField(max_length=10, default='email')
    exito = models.BooleanField(default=True)
    detalle_error = models.TextField(blank=True)
    enviado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notificación enviada'
        verbose_name_plural = 'Historial de notificaciones'
        ordering = ['-enviado_el']
        indexes = [
            models.Index(fields=['tipo', 'referencia', 'enviado_el']),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} → {self.destinatario} ({self.enviado_el:%Y-%m-%d})'
