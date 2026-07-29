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


# Conecta el dato simple que carga el usuario (Cliente.cond_iva /
# DatosEmpresa.condicion_iva, core.models.CondicionIVA: RI/M/E/CF) con el
# código real que exige WSFEv1 en CondicionIVAReceptorId. Import acá adentro
# (no al tope del módulo) para evitar el ciclo core.models -> core.services_arca.
def condicion_iva_a_receptor(condicion_iva):
    from core.models import CondicionIVA
    mapa = {
        CondicionIVA.RESPONSABLE_INSCRIPTO: CondicionIvaReceptor.RESPONSABLE_INSCRIPTO,
        CondicionIVA.MONOTRIBUTISTA:        CondicionIvaReceptor.MONOTRIBUTO,
        CondicionIVA.EXENTO:                CondicionIvaReceptor.EXENTO,
        CondicionIVA.CONSUMIDOR_FINAL:      CondicionIvaReceptor.CONSUMIDOR_FINAL,
    }
    return mapa.get(condicion_iva)


# Códigos `Id` de la tabla FEParamGetTiposIva de ARCA, por alícuota
# (productos.models.AlicuotaIVA: '0', '10.5', '21', '27').
ALICUOTA_IVA_A_ID_ARCA = {
    '0':    3,
    '10.5': 4,
    '21':   5,
    '27':   6,
}
