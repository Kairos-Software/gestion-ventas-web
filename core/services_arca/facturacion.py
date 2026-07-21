"""
core/services_arca/facturacion.py

Punto de entrada único para facturar una Venta ya confirmada — lo usan tanto
ConfirmarVentaAjax (al confirmar) como VentaFacturarAjax (reintento manual),
misma lógica, sin duplicar. Nunca toca la Venta en sí: si algo falla, se
puede reintentar cuantas veces haga falta sin riesgo de duplicar nada.

Fase 2 sólo soporta Factura C (emisor Monotributista o Exento) — Factura A/B
requeriría desglosar IVA por producto, que ItemVenta no guarda hoy.
"""
from core.models import ConfiguracionArca, DatosEmpresa, CondicionIVA

from . import wsfe
from .tipos import (
    CondicionIvaReceptor, DOC_TIPO_CUIT, DOC_TIPO_CUIL, DOC_TIPO_DNI,
    DOC_TIPO_CONSUMIDOR_FINAL,
)
from .wsaa import ArcaError


def _resolver_receptor(cliente):
    """(doc_tipo, doc_nro) para el comprobante. Sin cliente → Consumidor Final."""
    if cliente is None:
        return DOC_TIPO_CONSUMIDOR_FINAL, '0'
    if cliente.tipo == 'empresa' and cliente.cuit:
        return DOC_TIPO_CUIT, cliente.cuit.replace('-', '').strip()
    if cliente.dni:
        return DOC_TIPO_DNI, cliente.dni.replace('.', '').strip()
    if cliente.cuil:
        return DOC_TIPO_CUIL, cliente.cuil.replace('-', '').strip()
    return DOC_TIPO_CONSUMIDOR_FINAL, '0'


def facturar_venta(venta, *, cliente=None, condicion_iva_receptor_id=None):
    """
    Pide el CAE para `venta` y crea su ComprobanteArca. Devuelve la
    instancia creada. Levanta ArcaError (con el motivo, listo para
    mostrarle al usuario) si no se pudo facturar.
    """
    # Import acá adentro (no al tope del módulo) para evitar el ciclo
    # ventas.models -> core.models -> core.services_arca -> ventas.models.
    from ventas.models import ComprobanteArca, TipoComprobante

    if hasattr(venta, 'comprobante_arca'):
        raise ArcaError('Esta venta ya tiene un comprobante ARCA asociado.')

    config = ConfiguracionArca.get_solo()
    if not config.habilitado:
        raise ArcaError('La facturación electrónica no está habilitada en Configuración.')
    if not config.tiene_certificado():
        raise ArcaError('No hay certificado ARCA cargado en Configuración.')

    empresa = DatosEmpresa.get_solo()
    if empresa.condicion_iva not in (CondicionIVA.MONOTRIBUTISTA, CondicionIVA.EXENTO):
        raise ArcaError(
            'Esta instalación factura como "'
            + (empresa.get_condicion_iva_display() or 'condición de IVA sin configurar')
            + '" — por ahora solo está implementada la Factura C '
              '(Monotributista/Exento). Factura A/B queda para más adelante.'
        )
    if not empresa.cuit:
        raise ArcaError('Falta cargar el CUIT de la empresa en Configuración.')

    doc_tipo, doc_nro = _resolver_receptor(cliente)
    cond_iva_receptor = condicion_iva_receptor_id or CondicionIvaReceptor.CONSUMIDOR_FINAL

    resultado = wsfe.solicitar_cae(
        config,
        cuit=empresa.cuit.replace('-', '').strip(),
        tipo_comprobante=TipoComprobante.FACTURA_C,
        doc_tipo=doc_tipo,
        doc_nro=doc_nro,
        condicion_iva_receptor_id=cond_iva_receptor,
        importe_total=venta.total,
        importe_neto=venta.total,
        importe_iva=0,
    )

    return ComprobanteArca.objects.create(
        venta=venta,
        tipo_comprobante=TipoComprobante.FACTURA_C,
        punto_venta=config.punto_venta,
        numero=resultado['numero'],
        cae=resultado['cae'],
        cae_vencimiento=resultado['cae_vencimiento'],
        ambiente=config.ambiente,
        doc_tipo=doc_tipo,
        doc_nro=doc_nro or '',
        condicion_iva_receptor_id=cond_iva_receptor,
        importe_total=venta.total,
        importe_neto=venta.total,
        importe_iva=0,
        respuesta_json={'respuesta_cruda': resultado['respuesta_cruda']},
    )
