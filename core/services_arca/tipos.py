"""
core/services_arca/tipos.py

Códigos y tablas de referencia de ARCA. La lista de CondicionIvaReceptor es
la que devolvió FEParamGetCondicionIvaReceptor en homologación el
2026-07-20 (ver secrets/arca/wsfe_condiva.xml) — no está inventada.
"""


class CondicionIvaReceptor:
    RESPONSABLE_INSCRIPTO = 1
    EXENTO = 4
    CONSUMIDOR_FINAL = 5
    MONOTRIBUTO = 6
    SUJETO_NO_CATEGORIZADO = 7
    PROVEEDOR_EXTERIOR = 8
    CLIENTE_EXTERIOR = 9
    IVA_LIBERADO_LEY_19640 = 10
    MONOTRIBUTO_SOCIAL = 13
    IVA_NO_ALCANZADO = 15
    MONOTRIBUTO_TRABAJADOR_INDEPENDIENTE = 16

    LABELS = {
        RESPONSABLE_INSCRIPTO: 'IVA Responsable Inscripto',
        EXENTO: 'IVA Sujeto Exento',
        CONSUMIDOR_FINAL: 'Consumidor Final',
        MONOTRIBUTO: 'Responsable Monotributo',
        SUJETO_NO_CATEGORIZADO: 'Sujeto No Categorizado',
        PROVEEDOR_EXTERIOR: 'Proveedor del Exterior',
        CLIENTE_EXTERIOR: 'Cliente del Exterior',
        IVA_LIBERADO_LEY_19640: 'IVA Liberado - Ley N° 19.640',
        MONOTRIBUTO_SOCIAL: 'Monotributista Social',
        IVA_NO_ALCANZADO: 'IVA No Alcanzado',
        MONOTRIBUTO_TRABAJADOR_INDEPENDIENTE: 'Monotributo Trabajador Independiente Promovido',
    }


# Códigos de tipo de documento del receptor (WSFEv1 DocTipo).
DOC_TIPO_CUIT = 80
DOC_TIPO_CUIL = 86
DOC_TIPO_DNI = 96
DOC_TIPO_CONSUMIDOR_FINAL = 99
