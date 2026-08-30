"""
Lector de archivos .xlsx (Excel) sin dependencias externas.

Contraparte de `xlsx_writer.py`. Un .xlsx es un ZIP con XML adentro
(OOXML / ECMA-376). Acá se lee lo necesario para recuperar una tabla
plana: encabezados + filas, todo como texto crudo. El parseo a número /
booleano / opción lo hace quien consume esto (`import_productos.py`).

Qué soporta:
  - texto: shared strings (t="s"), inline (t="inlineStr" / "str")
  - números: se devuelven tal cual el XML los guarda ("12.5")
  - booleanos (t="b"): "1"/"0" -> "Sí"/"No"
  - celdas con formato de porcentaje: el valor crudo se multiplica ×100
    (Excel guarda "35%" como 0.35 — sin esto la importación lo tomaría mal)
  - elige la hoja "de datos" si hay varias, salteando hojas de instrucciones
  - detecta la fila de encabezados aunque haya un título o filas en blanco
    arriba (usando `pistas_encabezado`, si se pasan)

Qué NO:
  - fechas como serial de Excel (los productos no tienen campos fecha
    importables, así que no hace falta decodificarlas)

Uso:
    from productos.xlsx_reader import leer_xlsx, XlsxError
    headers, filas, meta = leer_xlsx(contenido_bytes, pistas_encabezado={...})
"""

import io
import re
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

MAX_FILAS = 3000
MAX_COLUMNAS = 200
_FILAS_A_ESCANEAR_ENCABEZADO = 15

# numFmtId de formato de porcentaje "de fábrica" en OOXML.
_PORCENTAJE_BUILTIN = {9, 10}


class XlsxError(Exception):
    """El archivo no es un .xlsx legible."""


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _col_a_indice(ref):
    m = re.match(r'^([A-Za-z]+)\d+$', ref or '')
    if not m:
        return None
    n = 0
    for c in m.group(1).upper():
        n = n * 26 + (ord(c) - 64)
    return n - 1


def _leer_shared_strings(z):
    try:
        raw = z.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise XlsxError(f'sharedStrings.xml ilegible: {e}')
    strings = []
    for si in root:
        if _local(si.tag) != 'si':
            continue
        partes = [t.text for t in si.iter() if _local(t.tag) == 't' and t.text]
        strings.append(''.join(partes))
    return strings


def _leer_estilos_porcentaje(z):
    """Set de índices de estilo (cellXfs) que son formato de porcentaje."""
    try:
        root = ET.fromstring(z.read('xl/styles.xml'))
    except (KeyError, ET.ParseError):
        return set()

    fmt_porcentaje = set(_PORCENTAJE_BUILTIN)
    for hijo in root:
        if _local(hijo.tag) != 'numFmts':
            continue
        for nf in hijo:
            code = (nf.attrib.get('formatCode') or '')
            if '%' in code:
                try:
                    fmt_porcentaje.add(int(nf.attrib.get('numFmtId')))
                except (TypeError, ValueError):
                    pass

    estilos_pct = set()
    for hijo in root:
        if _local(hijo.tag) != 'cellXfs':
            continue
        for i, xf in enumerate(hijo):
            try:
                if int(xf.attrib.get('numFmtId', 0)) in fmt_porcentaje:
                    estilos_pct.add(i)
            except (TypeError, ValueError):
                pass
    return estilos_pct


def _hojas_del_libro(z):
    """[(nombre, path_en_zip)] en el orden del libro."""
    try:
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    except (KeyError, ET.ParseError):
        fb = 'xl/worksheets/sheet1.xml'
        return [('Hoja1', fb)] if fb in z.namelist() else []

    rid_target = {}
    for rel in rels:
        rid_target[rel.attrib.get('Id')] = rel.attrib.get('Target', '')

    hojas = []
    for sheets in wb:
        if _local(sheets.tag) != 'sheets':
            continue
        for sheet in sheets:
            nombre = sheet.attrib.get('name', '')
            rid = None
            for k, v in sheet.attrib.items():
                if _local(k) == 'id':
                    rid = v
            target = (rid_target.get(rid) or '').lstrip('/')
            if target and not target.startswith('xl/'):
                target = 'xl/' + target
            if target in z.namelist():
                hojas.append((nombre, target))
    if not hojas:
        fb = 'xl/worksheets/sheet1.xml'
        if fb in z.namelist():
            hojas.append(('Hoja1', fb))
    return hojas


_HOJA_DATOS_RE = re.compile(r'(producto|articulo|artículo|item|listado|lista|catalog|precio|stock)', re.I)
_HOJA_EVITAR_RE = re.compile(r'(instruc|ayuda|leame|readme|ejemplo|manual|guia|guía)', re.I)


def _elegir_hoja(hojas):
    """Prefiere una hoja cuyo nombre sugiera 'datos'; evita 'instrucciones'."""
    if not hojas:
        return None
    for nombre, path in hojas:
        if _HOJA_DATOS_RE.search(nombre or ''):
            return nombre, path
    for nombre, path in hojas:
        if not _HOJA_EVITAR_RE.search(nombre or ''):
            return nombre, path
    return hojas[0]


def _valor_celda(c, shared, estilos_pct):
    """Texto de una celda <c> ('' si vacía). Aplica ×100 a porcentajes."""
    t = c.attrib.get('t', 'n')

    if t == 'inlineStr':
        return ''.join(x.text for x in c.iter() if _local(x.tag) == 't' and x.text)

    v = None
    for hijo in c:
        if _local(hijo.tag) == 'v':
            v = hijo.text
            break
    if v is None:
        return ''

    if t == 's':
        try:
            return shared[int(v)]
        except (ValueError, IndexError):
            return ''
    if t == 'b':
        return 'Sí' if v.strip() == '1' else 'No'
    if t in ('n', None) or t == '':
        try:
            s_idx = int(c.attrib.get('s', -1))
        except (TypeError, ValueError):
            s_idx = -1
        if s_idx in estilos_pct:
            try:
                d = Decimal(v) * 100
                return format(d.normalize(), 'f')
            except (InvalidOperation, ValueError):
                pass
    return v


def _leer_filas_crudas(root, shared, estilos_pct):
    sheet_data = None
    for hijo in root:
        if _local(hijo.tag) == 'sheetData':
            sheet_data = hijo
            break
    if sheet_data is None:
        return [], False

    filas = []
    truncado = False
    for row in sheet_data:
        if _local(row.tag) != 'row':
            continue
        celdas = {}
        idx_libre = 0
        for c in row:
            if _local(c.tag) != 'c':
                continue
            ref = c.attrib.get('r')
            idx = _col_a_indice(ref) if ref else None
            if idx is None:
                idx = idx_libre
            idx_libre = idx + 1
            if idx > MAX_COLUMNAS:
                continue
            celdas[idx] = _valor_celda(c, shared, estilos_pct)
        if not celdas:
            filas.append([])
            continue
        filas.append([celdas.get(i, '') for i in range(max(celdas) + 1)])
        if len(filas) > MAX_FILAS + 200:
            truncado = True
            break
    return filas, truncado


def _elegir_fila_encabezados(filas_crudas, pistas):
    """Índice de la fila de encabezados. Con `pistas` (set de textos
    conocidos, en minúscula) elige la fila que más coincidencias tenga
    dentro de las primeras filas; sin pistas, la primera con contenido."""
    primera_con_datos = None
    for i, fila in enumerate(filas_crudas):
        if any(str(v).strip() for v in fila):
            if primera_con_datos is None:
                primera_con_datos = i

    if not pistas:
        return primera_con_datos

    mejor_i, mejor_score = None, 0
    limite = min(len(filas_crudas), _FILAS_A_ESCANEAR_ENCABEZADO)
    for i in range(limite):
        fila = filas_crudas[i]
        score = sum(
            1 for v in fila
            if str(v).strip().lower() in pistas
        )
        if score > mejor_score:
            mejor_i, mejor_score = i, score
    if mejor_i is not None and mejor_score >= 2:
        return mejor_i
    return primera_con_datos


def leer_xlsx(contenido, pistas_encabezado=None):
    """
    `contenido` = bytes del .xlsx.  `pistas_encabezado` = set opcional de
    nombres de columna conocidos (minúscula) para ubicar la fila de títulos.

    Devuelve (headers, filas, meta):
      - headers: lista de strings
      - filas:   lista de listas de strings alineadas a headers
      - meta:    {'hoja', 'truncado', 'fila_encabezados', 'filas_totales'}

    Lanza XlsxError si el archivo no se puede leer.
    """
    pistas = {p.strip().lower() for p in pistas_encabezado} if pistas_encabezado else set()

    try:
        z = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        raise XlsxError('El archivo no es un Excel válido (.xlsx).')

    with z:
        shared = _leer_shared_strings(z)
        estilos_pct = _leer_estilos_porcentaje(z)
        hojas = _hojas_del_libro(z)
        elegida = _elegir_hoja(hojas)
        if not elegida:
            raise XlsxError('El archivo no tiene ninguna hoja legible.')
        hoja_nombre, hoja_path = elegida
        try:
            root = ET.fromstring(z.read(hoja_path))
        except ET.ParseError as e:
            raise XlsxError(f'La hoja no se pudo leer: {e}')
        filas_crudas, truncado = _leer_filas_crudas(root, shared, estilos_pct)

    meta = {'hoja': hoja_nombre, 'truncado': truncado,
            'fila_encabezados': 0, 'filas_totales': 0}

    inicio = _elegir_fila_encabezados(filas_crudas, pistas)
    if inicio is None:
        return [], [], meta
    meta['fila_encabezados'] = inicio + 1

    headers = [str(v).strip() for v in filas_crudas[inicio]]
    while headers and not headers[-1]:
        headers.pop()
    if not headers:
        return [], [], meta
    n_cols = len(headers)

    filas = []
    for fila in filas_crudas[inicio + 1:]:
        if not any(str(v).strip() for v in fila):
            continue
        filas.append([str(fila[i]).strip() if i < len(fila) else '' for i in range(n_cols)])
        if len(filas) >= MAX_FILAS:
            truncado = truncado or len(filas_crudas) - inicio - 1 > MAX_FILAS
            break

    meta['truncado'] = truncado
    meta['filas_totales'] = len(filas)
    return headers, filas, meta
