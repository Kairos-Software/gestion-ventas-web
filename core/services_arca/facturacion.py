"""
core/services_arca/facturacion.py

Punto de entrada único para facturar una Venta ya confirmada — lo usan tanto
ConfirmarVentaAjax (al confirmar) como VentaFacturarAjax (reintento manual),
misma lógica, sin duplicar. Nunca toca la Venta en sí: si algo falla, se
puede reintentar cuantas veces haga falta sin riesgo de duplicar nada.

Soporta Factura A, B y C. La regla es simple: si el EMISOR (esta empresa)
no es Responsable Inscripto, siempre es Factura C (Monotributista/Exento
nunca discriminan IVA). Si el emisor SÍ es Responsable Inscripto, se elige
A si el RECEPTOR también es Responsable Inscripto (para que pueda tomarse
el IVA como crédito fiscal), o B para cualquier otro caso.
"""
from core.models import ConfiguracionArca, DatosEmpresa, CondicionIVA

from . import wsfe
from .tipos import (
    CondicionIvaReceptor, DOC_TIPO_CUIT, DOC_TIPO_CUIL, DOC_TIPO_DNI,
    DOC_TIPO_CONSUMIDOR_FINAL, ALICUOTA_IVA_A_ID_ARCA, condicion_iva_a_receptor,
)
from .wsaa import ArcaError


def _resolver_receptor(cliente):
    """
    (doc_tipo, doc_nro) para el comprobante. Sin cliente → Consumidor Final.

    El CUIT se prioriza SIEMPRE que esté cargado, sea persona física o
    empresa — un monotributista o Responsable Inscripto puede ser
    perfectamente una persona física, y en ese caso ARCA exige
    identificarlo por CUIT igual que a una empresa (ver
    `_validar_receptor_identificable` más abajo: sin CUIT, facturarle
    como A o B es rechazado con error 10243).
    """
    if cliente is None:
        return DOC_TIPO_CONSUMIDOR_FINAL, '0'
    if cliente.cuit:
        return DOC_TIPO_CUIT, cliente.cuit.replace('-', '').strip()
    if cliente.dni:
        return DOC_TIPO_DNI, cliente.dni.replace('.', '').strip()
    if cliente.cuil:
        return DOC_TIPO_CUIL, cliente.cuil.replace('-', '').strip()
    return DOC_TIPO_CONSUMIDOR_FINAL, '0'


def _validar_receptor_identificable(cliente, condicion_iva_receptor_id):
    """
    ARCA (RG 5616) exige que todo receptor que no sea Consumidor Final esté
    identificado por CUIT — DNI/CUIL no alcanzan. Sin esto, ARCA rechaza el
    comprobante recién al pedir el CAE, con un error genérico ("Condicion
    IVA receptor no es valido para la clase de comprobante") que no dice
    nada de CUIT. Se corta acá antes, con un mensaje que sí dice qué falta.
    """
    if condicion_iva_receptor_id == CondicionIvaReceptor.CONSUMIDOR_FINAL:
        return
    if cliente is not None and cliente.cuit:
        return
    nombre = cliente.get_nombre_display() if cliente is not None else 'el cliente'
    raise ArcaError(
        f'{nombre} tiene condición de IVA "{CondicionIvaReceptor.LABELS.get(condicion_iva_receptor_id, "")}" '
        'pero no tiene CUIT cargado. ARCA exige CUIT para facturar a cualquier '
        'receptor que no sea Consumidor Final: cargalo en la ficha del cliente '
        '(Personas / Clientes / Facturación) y volvé a intentar.'
    )


def _resolver_condicion_iva_receptor(cliente, condicion_iva_receptor_id):
    """
    El valor explícito (elegido a mano en el selector de detalle_venta,
    o mandado por un caller que ya lo sabe) gana siempre. Si no vino,
    se deriva de la condición de IVA cargada en la ficha del cliente —
    así el vendedor no tiene que elegirla en cada venta. Sin nada de
    lo anterior, Consumidor Final (comportamiento de siempre).
    """
    if condicion_iva_receptor_id:
        return condicion_iva_receptor_id
    if cliente is not None and cliente.cond_iva:
        derivada = condicion_iva_a_receptor(cliente.cond_iva)
        if derivada:
            return derivada
    return CondicionIvaReceptor.CONSUMIDOR_FINAL


def _elegir_tipo_comprobante(condicion_iva_emisor, condicion_iva_receptor_id):
    """Monotributista/Exento -> siempre C. Responsable Inscripto -> A si el
    receptor también es RI (crédito fiscal), B para cualquier otro caso."""
    from ventas.models import TipoComprobante

    if condicion_iva_emisor != CondicionIVA.RESPONSABLE_INSCRIPTO:
        return TipoComprobante.FACTURA_C
    if condicion_iva_receptor_id == CondicionIvaReceptor.RESPONSABLE_INSCRIPTO:
        return TipoComprobante.FACTURA_A
    return TipoComprobante.FACTURA_B


def tipo_comprobante_previsto(cliente):
    """
    Qué tipo de comprobante saldría HOY para este cliente, sin llamar a
    ARCA — para mostrarlo en la UI antes de facturar de verdad (mismo
    criterio exacto que facturar_venta). None si la empresa todavía no
    tiene condición de IVA cargada (no se puede predecir nada todavía).
    """
    empresa = DatosEmpresa.get_solo()
    if not empresa.condicion_iva:
        return None
    cond_iva_receptor = _resolver_condicion_iva_receptor(cliente, None)
    return _elegir_tipo_comprobante(empresa.condicion_iva, cond_iva_receptor)


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
    if not empresa.condicion_iva:
        raise ArcaError('Falta cargar la condición de IVA de la empresa en Configuración.')
    if not empresa.cuit:
        raise ArcaError('Falta cargar el CUIT de la empresa en Configuración.')

    cond_iva_receptor = _resolver_condicion_iva_receptor(cliente, condicion_iva_receptor_id)
    _validar_receptor_identificable(cliente, cond_iva_receptor)
    doc_tipo, doc_nro = _resolver_receptor(cliente)
    tipo_comprobante = _elegir_tipo_comprobante(empresa.condicion_iva, cond_iva_receptor)

    if tipo_comprobante == TipoComprobante.FACTURA_C:
        importe_neto, importe_iva, iva_detalle = venta.total, 0, None
    else:
        desglose = venta.calcular_iva_por_alicuota()
        importe_neto = desglose['neto_total']
        importe_iva  = desglose['iva_total']
        iva_detalle  = [
            {
                'id':       ALICUOTA_IVA_A_ID_ARCA.get(g['alicuota'], ALICUOTA_IVA_A_ID_ARCA['21']),
                'base_imp': g['neto'],
                'importe':  g['iva'],
            }
            for g in desglose['grupos']
        ]

    resultado = wsfe.solicitar_cae(
        config,
        cuit=empresa.cuit.replace('-', '').strip(),
        tipo_comprobante=tipo_comprobante,
        doc_tipo=doc_tipo,
        doc_nro=doc_nro,
        condicion_iva_receptor_id=cond_iva_receptor,
        importe_total=venta.total,
        importe_neto=importe_neto,
        importe_iva=importe_iva,
        iva_detalle=iva_detalle,
    )

    return ComprobanteArca.objects.create(
        venta=venta,
        tipo_comprobante=tipo_comprobante,
        punto_venta=config.punto_venta,
        numero=resultado['numero'],
        cae=resultado['cae'],
        cae_vencimiento=resultado['cae_vencimiento'],
        ambiente=config.ambiente,
        doc_tipo=doc_tipo,
        doc_nro=doc_nro or '',
        condicion_iva_receptor_id=cond_iva_receptor,
        importe_total=venta.total,
        importe_neto=importe_neto,
        importe_iva=importe_iva,
        respuesta_json={'respuesta_cruda': resultado['respuesta_cruda']},
    )
