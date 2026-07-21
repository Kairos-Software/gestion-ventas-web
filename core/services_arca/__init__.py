"""
core/services_arca/

Cliente de los web services de ARCA (ex AFIP) para facturación electrónica:
WSAA (autenticación) y WSFEv1 (comprobantes). Formatos de XML, namespaces y
reglas (incluida la CondicionIVAReceptorId de la RG 5616) verificados a mano
contra el ambiente de homologación real el 2026-07-20 antes de escribir este
código — ver secrets/arca/ para los XML de esa prueba manual.

Un módulo por servicio:
- tipos.py: códigos/tablas de referencia de ARCA (tipos de comprobante,
  condición de IVA del receptor, tipos de documento).
- wsaa.py: autenticación (obtener_token), con cache en ConfiguracionArca.
- wsfe.py: FEDummy, FECompUltimoAutorizado, FECAESolicitar.

Todas las funciones reciben un `core.models.ConfiguracionArca` como primer
argumento (de dónde sacan certificado, ambiente y punto de venta) y levantan
`ArcaError` (definida en wsaa.py) si ARCA rechaza el pedido — el motivo que
trae la excepción es el que informó ARCA, no un mensaje genérico.
"""
