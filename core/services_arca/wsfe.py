"""
core/services_arca/wsfe.py

Cliente de WSFEv1 (facturación electrónica) de ARCA: FEDummy,
FECompUltimoAutorizado y FECAESolicitar. Namespace
(http://ar.gov.afip.dif.FEV1/) y el campo obligatorio
CondicionIVAReceptorId (RG 5616) verificados a mano contra homologación el
2026-07-20 — ver secrets/arca/wsfe_cae_request.xml para el pedido que
efectivamente aprobó ARCA (CAE 86290614276501).
"""
import re
from datetime import date

import requests

from core.models import AmbienteArca
from .wsaa import obtener_token, ArcaError

WSFE_URLS = {
    AmbienteArca.TESTING: 'https://wswhomo.afip.gov.ar/wsfev1/service.asmx',
    AmbienteArca.PRODUCCION: 'https://servicios1.afip.gov.ar/wsfev1/service.asmx',
}

NS = 'http://ar.gov.afip.dif.FEV1/'


def _post(config, metodo, cuerpo_xml):
    url = WSFE_URLS[config.ambiente]
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="{NS}">\n'
        '   <soapenv:Header/>\n'
        f'   <soapenv:Body>\n      {cuerpo_xml}\n   </soapenv:Body>\n'
        '</soapenv:Envelope>'
    )
    try:
        resp = requests.post(
            url,
            data=envelope.encode('utf-8'),
            headers={
                'Content-Type': 'text/xml;charset=UTF-8',
                'SOAPAction': f'{NS}{metodo}',
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise ArcaError(f'No se pudo conectar a WSFE ({url}): {exc}') from exc
    return resp.text


def _auth_xml(cuit, token, sign):
    return (
        '<ar:Auth>\n'
        f'            <ar:Token>{token}</ar:Token>\n'
        f'            <ar:Sign>{sign}</ar:Sign>\n'
        f'            <ar:Cuit>{cuit}</ar:Cuit>\n'
        '         </ar:Auth>'
    )


def _extraer_errores(texto):
    errores = re.findall(r'<Err><Code>(\d+)</Code><Msg>(.*?)</Msg></Err>', texto, re.S)
    observaciones = re.findall(r'<Obs><Code>(\d+)</Code><Msg>(.*?)</Msg></Obs>', texto, re.S)
    return [f'[{code}] {msg}' for code, msg in errores + observaciones]


def fe_dummy(config):
    """Chequeo de estado del servicio — no requiere autenticación."""
    texto = _post(config, 'FEDummy', '<ar:FEDummy/>')
    app = re.search(r'<AppServer>(.*?)</AppServer>', texto)
    db = re.search(r'<DbServer>(.*?)</DbServer>', texto)
    auth = re.search(r'<AuthServer>(.*?)</AuthServer>', texto)
    if not (app and db and auth):
        raise ArcaError(f'Respuesta inesperada de FEDummy: {texto[:300]}')
    return {'AppServer': app.group(1), 'DbServer': db.group(1), 'AuthServer': auth.group(1)}


def comp_ultimo_autorizado(config, cuit, pto_vta, cbte_tipo):
    """Último número de comprobante autorizado para (punto de venta, tipo).
    0 si todavía no se emitió ninguno de ese tipo en ese punto de venta."""
    token, sign = obtener_token(config)
    cuerpo = (
        '<ar:FECompUltimoAutorizado>\n'
        f'         {_auth_xml(cuit, token, sign)}\n'
        f'         <ar:PtoVta>{pto_vta}</ar:PtoVta>\n'
        f'         <ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>\n'
        '      </ar:FECompUltimoAutorizado>'
    )
    texto = _post(config, 'FECompUltimoAutorizado', cuerpo)
    errores = _extraer_errores(texto)
    if errores:
        raise ArcaError('; '.join(errores))
    match = re.search(r'<CbteNro>(\d+)</CbteNro>', texto)
    if not match:
        raise ArcaError(f'Respuesta inesperada de FECompUltimoAutorizado: {texto[:300]}')
    return int(match.group(1))


def solicitar_cae(config, *, cuit, tipo_comprobante, doc_tipo, doc_nro,
                   condicion_iva_receptor_id, importe_total, importe_neto=None,
                   importe_iva=0, concepto=1, moneda='PES', cotizacion=1):
    """
    Pide un CAE para el próximo número disponible del punto de venta
    configurado. Devuelve dict con numero/cae/cae_vencimiento/respuesta_cruda.
    Levanta ArcaError (con el motivo que informó ARCA) si lo rechaza.
    """
    if importe_neto is None:
        importe_neto = importe_total - importe_iva

    token, sign = obtener_token(config)
    numero = comp_ultimo_autorizado(config, cuit, config.punto_venta, tipo_comprobante) + 1
    hoy = date.today().strftime('%Y%m%d')

    cuerpo = (
        '<ar:FECAESolicitar>\n'
        f'         {_auth_xml(cuit, token, sign)}\n'
        '         <ar:FeCAEReq>\n'
        '            <ar:FeCabReq>\n'
        '               <ar:CantReg>1</ar:CantReg>\n'
        f'               <ar:PtoVta>{config.punto_venta}</ar:PtoVta>\n'
        f'               <ar:CbteTipo>{tipo_comprobante}</ar:CbteTipo>\n'
        '            </ar:FeCabReq>\n'
        '            <ar:FeDetReq>\n'
        '               <ar:FECAEDetRequest>\n'
        f'                  <ar:Concepto>{concepto}</ar:Concepto>\n'
        f'                  <ar:DocTipo>{doc_tipo}</ar:DocTipo>\n'
        f'                  <ar:DocNro>{doc_nro}</ar:DocNro>\n'
        f'                  <ar:CbteDesde>{numero}</ar:CbteDesde>\n'
        f'                  <ar:CbteHasta>{numero}</ar:CbteHasta>\n'
        f'                  <ar:CbteFch>{hoy}</ar:CbteFch>\n'
        f'                  <ar:ImpTotal>{importe_total:.2f}</ar:ImpTotal>\n'
        '                  <ar:ImpTotConc>0</ar:ImpTotConc>\n'
        f'                  <ar:ImpNeto>{importe_neto:.2f}</ar:ImpNeto>\n'
        '                  <ar:ImpOpEx>0</ar:ImpOpEx>\n'
        f'                  <ar:ImpIVA>{importe_iva:.2f}</ar:ImpIVA>\n'
        '                  <ar:ImpTrib>0</ar:ImpTrib>\n'
        f'                  <ar:MonId>{moneda}</ar:MonId>\n'
        f'                  <ar:MonCotiz>{cotizacion}</ar:MonCotiz>\n'
        f'                  <ar:CondicionIVAReceptorId>{condicion_iva_receptor_id}</ar:CondicionIVAReceptorId>\n'
        '               </ar:FECAEDetRequest>\n'
        '            </ar:FeDetReq>\n'
        '         </ar:FeCAEReq>\n'
        '      </ar:FECAESolicitar>'
    )

    texto = _post(config, 'FECAESolicitar', cuerpo)

    resultado = re.search(r'<FeDetResp><FECAEDetResponse>.*?<Resultado>(\w)</Resultado>', texto, re.S)
    if not resultado or resultado.group(1) != 'A':
        motivos = _extraer_errores(texto)
        raise ArcaError('ARCA rechazó el comprobante: ' + ('; '.join(motivos) if motivos else texto[:300]))

    cae_match = re.search(r'<CAE>(\d+)</CAE>', texto)
    vto_match = re.search(r'<CAEFchVto>(\d+)</CAEFchVto>', texto)
    if not cae_match or not vto_match:
        raise ArcaError(f'ARCA aprobó el comprobante pero no devolvió CAE: {texto[:300]}')

    vto_str = vto_match.group(1)
    cae_vencimiento = date(int(vto_str[:4]), int(vto_str[4:6]), int(vto_str[6:8]))

    return {
        'numero': numero,
        'cae': cae_match.group(1),
        'cae_vencimiento': cae_vencimiento,
        'respuesta_cruda': texto,
    }
