"""
Generador de archivos .xlsx (Excel) sin dependencias externas.

Un .xlsx es un ZIP con unos pocos XML adentro (formato OOXML / ECMA-376).
Acá se arma el mínimo indispensable para una planilla plana de una sola
hoja: encabezado en negrita + fila congelada + autofiltro + ancho de
columna automático. Suficiente para exportar tablas; no soporta fórmulas,
estilos por celda ni varias hojas (no hace falta para este sistema y así
evitamos sumar `openpyxl` a requirements.txt y tener que instalarlo en
cada VPS — ver memoria vps_multi_tenant_despliegue).

Uso:
    from productos.xlsx_writer import generar_xlsx
    contenido = generar_xlsx(['Código', 'Nombre'], filas, sheet_name='Productos')
    # `filas` es un iterable de listas/tuplas alineadas a los encabezados.
"""

import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal

# Caracteres de control que XML 1.0 no admite (rompen el archivo en Excel).
# Se conservan tab (\x09), LF (\x0a) y CR (\x0d).
_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

_ANCHO_MIN = 8
_ANCHO_MAX = 60

# Excel no admite más de 32767 caracteres por celda.
_MAX_CHARS_CELDA = 32767


def _escapar(texto):
    """Escapa un string para incrustarlo como texto en XML."""
    texto = _CONTROL_RE.sub('', texto)
    return (
        texto.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;')
    )


def _letra_columna(n):
    """1 -> 'A', 26 -> 'Z', 27 -> 'AA', ..."""
    letras = ''
    while n > 0:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _valor_para_celda(valor):
    """
    Normaliza un valor Python a (tipo, contenido) para escribir la celda:
      - ('num', '123.45')  -> celda numérica real
      - ('str', 'texto')   -> celda de texto (inline string, ya escapado)
      - ('vacio', '')      -> celda vacía
    """
    if valor is None or valor == '':
        return ('vacio', '')

    if isinstance(valor, bool):
        return ('str', 'Sí' if valor else 'No')

    if isinstance(valor, Decimal):
        return ('num', format(valor, 'f'))
    if isinstance(valor, int):
        return ('num', str(valor))
    if isinstance(valor, float):
        return ('num', repr(valor))

    if isinstance(valor, datetime):
        return ('str', _escapar(valor.strftime('%d/%m/%Y %H:%M')))
    if isinstance(valor, date):
        return ('str', _escapar(valor.strftime('%d/%m/%Y')))

    return ('str', _escapar(str(valor)[:_MAX_CHARS_CELDA]))


def _celda_xml(ref, valor, es_encabezado=False):
    tipo, contenido = _valor_para_celda(valor)
    estilo = ' s="1"' if es_encabezado else ''

    if tipo == 'vacio':
        return f'<c r="{ref}"{estilo}/>'
    if tipo == 'num':
        return f'<c r="{ref}"{estilo}><v>{contenido}</v></c>'
    return (
        f'<c r="{ref}"{estilo} t="inlineStr">'
        f'<is><t xml:space="preserve">{contenido}</t></is></c>'
    )


def _largo_visible(valor):
    if valor is None:
        return 0
    if isinstance(valor, bool):
        return 2
    if isinstance(valor, datetime):
        return 16
    if isinstance(valor, date):
        return 10
    if isinstance(valor, Decimal):
        return len(format(valor, 'f'))
    return len(str(valor))


# ──────────────────────────────────────────────────────────────────
#  Partes fijas del paquete
# ──────────────────────────────────────────────────────────────────

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>'
)

_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>'
)

_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
)

# Estilo 0 = normal, estilo 1 = negrita (para la fila de encabezado).
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="2">'
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font>'
    '</fonts>'
    '<fills count="2">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '</fills>'
    '<borders count="1"><border/></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '</cellXfs>'
    '<cellStyles count="1">'
    '<cellStyle name="Normal" xfId="0" builtinId="0"/>'
    '</cellStyles>'
    '</styleSheet>'
)


def _workbook_xml(sheet_name):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView/></bookViews>'
        f'<sheets><sheet name="{_escapar(sheet_name)[:31]}" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def _sheet_xml(headers, filas):
    n_cols = len(headers)
    ultima_col = _letra_columna(n_cols) if n_cols else 'A'

    anchos = [max(_ANCHO_MIN, min(_ANCHO_MAX, _largo_visible(h) + 2)) for h in headers]

    partes_filas = []

    # Fila 1: encabezados
    celdas = [
        _celda_xml(f'{_letra_columna(i + 1)}1', h, es_encabezado=True)
        for i, h in enumerate(headers)
    ]
    partes_filas.append(f'<row r="1">{"".join(celdas)}</row>')

    # Filas de datos
    nro = 1
    for fila in filas:
        nro += 1
        celdas = []
        for i in range(n_cols):
            valor = fila[i] if i < len(fila) else None
            celdas.append(_celda_xml(f'{_letra_columna(i + 1)}{nro}', valor))
            largo = _largo_visible(valor) + 2
            if largo > anchos[i]:
                anchos[i] = min(_ANCHO_MAX, largo)
        partes_filas.append(f'<row r="{nro}">{"".join(celdas)}</row>')

    total_filas = nro

    cols_xml = ''.join(
        f'<col min="{i + 1}" max="{i + 1}" width="{round(a, 2)}" customWidth="1"/>'
        for i, a in enumerate(anchos)
    )
    cols_bloque = f'<cols>{cols_xml}</cols>' if cols_xml else ''

    dimension = f'A1:{ultima_col}{total_filas}'
    autofiltro = f'<autoFilter ref="A1:{ultima_col}{max(total_filas, 1)}"/>' if n_cols else ''

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'{cols_bloque}'
        f'<sheetData>{"".join(partes_filas)}</sheetData>'
        f'{autofiltro}'
        '</worksheet>'
    )


def generar_xlsx(headers, filas, sheet_name='Hoja1'):
    """
    Devuelve los bytes de un archivo .xlsx.

    headers : lista de strings (fila 1, en negrita)
    filas   : iterable de listas/tuplas. Cada valor se mapea a:
              número (int/float/Decimal), texto, "Sí/No" (bool),
              fecha formateada (date/datetime) o celda vacía (None/'').
    """
    headers = list(headers)
    filas = [list(f) for f in filas]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', _CONTENT_TYPES)
        z.writestr('_rels/.rels', _RELS)
        z.writestr('xl/workbook.xml', _workbook_xml(sheet_name))
        z.writestr('xl/_rels/workbook.xml.rels', _WORKBOOK_RELS)
        z.writestr('xl/styles.xml', _STYLES)
        z.writestr('xl/worksheets/sheet1.xml', _sheet_xml(headers, filas))

    return buffer.getvalue()
