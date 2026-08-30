"""
Importación de productos desde un .xlsx (crear / actualizar en lote).

Filosofía: MÁXIMA FLEXIBILIDAD. Cada cliente trae su propia planilla y
ninguna es igual.

  - Columna **Código**: si el código existe → se ACTUALIZA ese producto;
    si está vacío o no existe → se CREA uno nuevo (código automático).
  - **Celda vacía = no se toca ese campo.** Lo que ya está cargado en el
    sistema se mantiene. Solo se pisa lo que viene con un valor.
  - **Columnas que el sistema no conoce = se ignoran** (se informan, no
    frenan nada). Faltan columnas = no importa, se importa lo que se pueda.
  - Lo ÚNICO que marca un problema es un valor con el tipo equivocado
    (un precio con "$", letras en un número, algo que no es "Sí/No"…).
    Y ni siquiera eso frena: se ignora ESA celda, el resto de la fila
    entra igual, y se informa con detalle.
  - Categoría / tipo / proveedor por nombre: si el nombre no existe, ese
    campo se deja como está (no es un error).

Qué NO toca nunca: `stock_actual`, `costo_actual`, y los toggles
estructurales de variantes / paquete. El stock se trabaja a mano.

Dos pasos: `analizar(headers, filas)` (no escribe) y `aplicar(headers,
filas)` (transacción). La vista manda el archivo en las dos llamadas.
"""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction

from .models import (
    Producto, CategoriaProducto, TipoProducto, Proveedor,
    UnidadMedida, AlicuotaIVA, ModoPrecio, EstadoProducto,
)
from .export_productos import ETIQUETAS


# Valores que la gente usa para decir "no tengo este dato" → se tratan
# como celda vacía (no se toca el campo en el sistema).
_ES_VACIO = {
    '', '-', '--', '---', '—', '.', '..', 's/d', 'n/d', 'n/a', 'na',
    'null', 'none', 'nan', 'sin dato', 'sin datos', '#n/a',
}

# Campos cuyo cambio obliga a recalcular costo_actual / precio_venta.
_CAMPOS_PRECIO = {
    'costo', 'modo_precio', 'porcentaje_ganancia', 'precio_incluye_iva',
    'alicuota_iva', 'precio_venta',
}


def _limpiar(s):
    """Normaliza una celda: NBSP/tabs → espacio, colapsa espacios, recorta."""
    return re.sub(r'\s+', ' ', (s or '').replace('\xa0', ' ')).strip()


def _es_vacio(s):
    return _limpiar(s).lower() in _ES_VACIO


# "1.500" (un punto, exactamente 3 dígitos detrás, sin coma) es ambiguo:
# 1,5 o mil quinientos. Se toma como decimal pero se avisa.
_AMBIGUO_MILES_RE = re.compile(r'^\d{1,3}\.\d{3}$')


# ══════════════════════════════════════════════════════════════════
#  PARSERS
#  (valor_str) -> (valor|None, nivel|None, mensaje|None)
#    nivel 'error' : el valor no es del tipo esperado (se ignora la celda)
#    nivel 'aviso' : se pudo interpretar pero con un ajuste, o el nombre
#                    de una opción/FK no existe (se ignora o se recorta)
#    valor is not None  → se aplica (aunque haya aviso: p. ej. texto recortado)
# ══════════════════════════════════════════════════════════════════

def _p_texto(maxlen):
    def parser(v):
        v = _limpiar(v)
        if len(v) > maxlen:
            return v[:maxlen], 'aviso', f'texto muy largo, se recortó a {maxlen} caracteres'
        return v, None, None
    return parser


def _a_decimal(v):
    """Texto -> Decimal. Acepta '1234.56' y '1.234,56' (formato es-AR).
    Un valor con una sola coma se toma como separador decimal."""
    v = v.strip().replace(' ', '').replace(' ', '')
    if ',' in v and '.' in v:
        v = v.replace('.', '').replace(',', '.')
    elif ',' in v:
        v = v.replace(',', '.')
    return Decimal(v)


def _p_decimal(max_digits, decimal_places):
    tope = Decimal(10) ** (max_digits - decimal_places)
    cuant = Decimal(1).scaleb(-decimal_places)

    def parser(v):
        crudo = _limpiar(v)
        pct = crudo.endswith('%')
        if pct:
            crudo = crudo[:-1].strip()
        try:
            d = _a_decimal(crudo)
        except (InvalidOperation, ValueError):
            return None, 'error', 'no es un número (¿tiene $, letras o símbolos?)'
        if not d.is_finite():
            return None, 'error', 'no es un número válido'
        if d < 0:
            return None, 'error', 'no puede ser negativo'
        d = d.quantize(cuant, rounding=ROUND_HALF_UP)
        if d >= tope:
            return None, 'error', 'el número es demasiado grande'
        if pct:
            return d, 'aviso', f'se interpretó "{_limpiar(v)}" como {d}'
        if _AMBIGUO_MILES_RE.match(crudo.replace(' ', '')):
            return d, 'aviso', (
                f'"{crudo}" se tomó como {d} — si querías decir '
                f'{crudo.replace(".", "")}, escribilo sin punto o con coma decimal'
            )
        return d, None, None
    return parser


def _p_entero(minimo=1, maximo=2147483647):
    def parser(v):
        try:
            d = _a_decimal(_limpiar(v).rstrip('%'))
        except (InvalidOperation, ValueError):
            return None, 'error', 'no es un número entero'
        d = d.to_integral_value(rounding=ROUND_HALF_UP)
        n = int(d)
        if n < minimo:
            return None, 'error', f'tiene que ser {minimo} o más'
        if n > maximo:
            return None, 'error', 'el número es demasiado grande'
        return n, None, None
    return parser


_BOOL_SI = {'si', 'sí', 's', 'x', '1', 'true', 'verdadero', 'v', 'y', 'yes',
            'ok', '✓', '✔', '√', 'activo', 'habilitado', 'publicado'}
_BOOL_NO = {'no', 'n', '0', 'false', 'falso', 'f', 'inactivo', 'deshabilitado',
            '✗', '✘'}


def _p_bool(v):
    t = _limpiar(v).lower()
    if t in _BOOL_SI:
        return True, None, None
    if t in _BOOL_NO:
        return False, None, None
    return None, 'error', 'no es un Sí/No (poné Sí, No, 1 o 0)'


def _p_choice(choices_cls):
    mapa = {}
    etiquetas = []
    for value, label in choices_cls.choices:
        mapa[str(value).lower()] = value
        mapa[str(label).lower()] = value
        mapa.setdefault(str(label).split('(')[0].strip().lower(), value)
        etiquetas.append(str(label))

    def parser(v):
        t = _limpiar(v).lower().rstrip('%').strip()
        if t in mapa:
            return mapa[t], None, None
        return None, 'aviso', (
            f'"{_limpiar(v)}" no es una opción conocida — no se cambió ese campo '
            f'(opciones: {", ".join(etiquetas)})'
        )
    return parser


def _p_fk(modelo, que):
    def parser(v):
        nombre = _limpiar(v)
        obj = modelo.objects.filter(nombre__iexact=nombre).first()
        if obj is None:
            # segundo intento: ignorando espacios internos
            objs = [o for o in modelo.objects.all()
                    if _limpiar(o.nombre).lower() == nombre.lower()]
            obj = objs[0] if len(objs) == 1 else None
        if obj is None:
            return None, 'aviso', f'{que} "{v.strip()}" no existe en el sistema — no se cambió ese campo'
        return obj, None, None
    return parser


# ══════════════════════════════════════════════════════════════════
#  CATÁLOGO DE CAMPOS IMPORTABLES
# ══════════════════════════════════════════════════════════════════

FK_CLAVES = {'categoria', 'tipo', 'proveedor'}

CAMPOS = {
    # — Texto —
    'sku':                 _p_texto(100),
    'codigo_barras':       _p_texto(100),
    'codigo_proveedor':    _p_texto(100),
    'nombre':              _p_texto(255),
    'nombre_corto':        _p_texto(80),
    'descripcion':         _p_texto(20000),
    'descripcion_publica': _p_texto(20000),
    'marca':               _p_texto(100),
    'modelo':              _p_texto(100),
    'fabricante':          _p_texto(150),
    'pais_origen':         _p_texto(100),
    'posicion_deposito':   _p_texto(50),
    'notas':               _p_texto(20000),
    'tags':                _p_texto(500),

    # — Clasificación (FK por nombre) —
    'categoria':           _p_fk(CategoriaProducto, 'La categoría'),
    'tipo':                _p_fk(TipoProducto, 'El tipo'),
    'proveedor':           _p_fk(Proveedor, 'El proveedor'),

    # — Opciones —
    'unidad_medida':       _p_choice(UnidadMedida),
    'alicuota_iva':        _p_choice(AlicuotaIVA),
    'modo_precio':         _p_choice(ModoPrecio),
    'estado':              _p_choice(EstadoProducto),

    # — Números (max_digits, decimal_places del modelo) —
    'precio_venta':        _p_decimal(12, 2),
    'porcentaje_ganancia': _p_decimal(6, 2),
    'costo':               _p_decimal(12, 2),
    'contenido_neto':      _p_decimal(10, 3),
    'peso_kg':             _p_decimal(8, 3),
    'alto_cm':             _p_decimal(7, 2),
    'ancho_cm':            _p_decimal(7, 2),
    'profundidad_cm':      _p_decimal(7, 2),
    'stock_minimo':        _p_decimal(12, 3),
    'stock_maximo':        _p_decimal(12, 3),
    'unidades_por_presentacion': _p_entero(1),

    # — Booleanos —
    'precio_incluye_iva':      _p_bool,
    'gestiona_stock':          _p_bool,
    'permite_stock_negativo':  _p_bool,
    'publicado':               _p_bool,
    'destacado':               _p_bool,
    'requiere_refrigeracion':  _p_bool,
    'es_fragil':               _p_bool,
    'es_peligroso':            _p_bool,
    'es_perecedero':           _p_bool,
}

# Orden para la plantilla (mismo criterio que el export).
CLAVES_ORDEN = [
    'codigo', 'sku', 'codigo_barras', 'codigo_proveedor', 'nombre', 'nombre_corto',
    'descripcion', 'descripcion_publica',
    'categoria', 'tipo', 'marca', 'modelo', 'fabricante', 'pais_origen', 'proveedor', 'tags',
    'unidad_medida', 'unidades_por_presentacion', 'contenido_neto',
    'peso_kg', 'alto_cm', 'ancho_cm', 'profundidad_cm',
    'precio_venta', 'modo_precio', 'porcentaje_ganancia', 'alicuota_iva',
    'precio_incluye_iva', 'costo',
    'gestiona_stock', 'stock_minimo', 'stock_maximo', 'permite_stock_negativo',
    'estado', 'publicado', 'destacado',
    'requiere_refrigeracion', 'es_fragil', 'es_peligroso', 'es_perecedero',
    'posicion_deposito', 'notas',
]

# Sinónimos de encabezado frecuentes -> clave del modelo. Los matcheos por
# etiqueta exacta o por nombre de campo tienen prioridad sobre estos.
ALIAS_ENCABEZADOS = {
    'codigo': 'codigo', 'código': 'codigo', 'cod': 'codigo', 'cod.': 'codigo',
    'precio': 'precio_venta', 'precio venta': 'precio_venta',
    'precio de lista': 'precio_venta', 'pvp': 'precio_venta',
    'costo': 'costo', 'costo referencia': 'costo', 'costo de referencia': 'costo',
    'rubro': 'categoria', 'categoria': 'categoria',
    'subrubro': 'tipo', 'tipo de producto': 'tipo',
    'iva': 'alicuota_iva', 'alicuota': 'alicuota_iva', 'alícuota': 'alicuota_iva',
    'ganancia': 'porcentaje_ganancia', '% ganancia': 'porcentaje_ganancia',
    'margen': 'porcentaje_ganancia',
    'descripcion': 'descripcion', 'descripción': 'descripcion',
    'detalle': 'descripcion',
    'observaciones': 'notas', 'obs': 'notas', 'notas': 'notas',
    'ean': 'codigo_barras', 'barras': 'codigo_barras',
    'codigo de barras': 'codigo_barras', 'cod barras': 'codigo_barras',
    'cod proveedor': 'codigo_proveedor', 'codigo proveedor': 'codigo_proveedor',
    'unidad': 'unidad_medida', 'um': 'unidad_medida',
    'stock minimo': 'stock_minimo', 'stock mínimo': 'stock_minimo', 'minimo': 'stock_minimo',
    'stock maximo': 'stock_maximo', 'stock máximo': 'stock_maximo', 'maximo': 'stock_maximo',
    'peso': 'peso_kg', 'peso kg': 'peso_kg',
    'marca comercial': 'marca',
    'publicado en catalogo': 'publicado', 'destacar': 'destacado',
    'nombre producto': 'nombre', 'producto': 'nombre', 'articulo': 'nombre',
    'artículo': 'nombre', 'denominacion': 'nombre', 'denominación': 'nombre',
}


def _lookup_encabezados():
    lookup = {}
    for clave in list(CAMPOS) + ['codigo']:
        lookup[clave.lower()] = clave
        lookup[clave.replace('_', ' ')] = clave
        if clave in ETIQUETAS:
            lookup[ETIQUETAS[clave].strip().lower()] = clave
    for alias, clave in ALIAS_ENCABEZADOS.items():
        lookup.setdefault(alias, clave)
    return lookup


def pistas_encabezado():
    """Set de textos (minúscula) que sugieren 'esta fila es de títulos'.
    Se lo pasa el lector para ubicar la fila de encabezados."""
    return set(_lookup_encabezados())


def plantilla_headers():
    """Encabezados para el .xlsx de plantilla (en orden)."""
    return [ETIQUETAS[c] for c in CLAVES_ORDEN]


# ══════════════════════════════════════════════════════════════════
#  MAPEO DE ENCABEZADOS
# ══════════════════════════════════════════════════════════════════

def _mapa_columnas(headers):
    """
    (col_por_clave, ignoradas, duplicadas)
      col_por_clave: {clave_modelo: indice_columna}
      ignoradas:     [encabezados sin correspondencia]
      duplicadas:    [encabezados que apuntan a una columna ya tomada]
    """
    lookup = _lookup_encabezados()

    col_por_clave = {}
    ignoradas = []
    duplicadas = []
    for i, h in enumerate(headers):
        k = _limpiar(h).lower()
        clave = lookup.get(k)
        if clave and clave not in col_por_clave:
            col_por_clave[clave] = i
        elif clave:
            duplicadas.append(_limpiar(h))
        elif _limpiar(h):
            ignoradas.append(_limpiar(h))
    return col_por_clave, ignoradas, duplicadas


# ══════════════════════════════════════════════════════════════════
#  ANÁLISIS
# ══════════════════════════════════════════════════════════════════

def _valor_actual(producto, clave):
    if clave in FK_CLAVES:
        return getattr(producto, clave + '_id')
    return getattr(producto, clave)


def _difiere(producto, clave, valor):
    actual = _valor_actual(producto, clave)
    if clave in FK_CLAVES:
        return actual != (valor.pk if valor is not None else None)
    if isinstance(actual, bool) or isinstance(valor, bool):
        return bool(actual) != bool(valor)
    if isinstance(actual, Decimal) or isinstance(valor, Decimal):
        try:
            return Decimal(str(actual or 0)) != Decimal(str(valor or 0))
        except (InvalidOperation, ValueError):
            return actual != valor
    return (actual or '') != (valor if valor is not None else '')


class FilaAnalizada:
    __slots__ = ('numero', 'accion', 'codigo', 'nombre', 'instancia',
                 'datos', 'problemas', 'cambios', 'omitida', 'motivo_omitida',
                 'codigo_no_encontrado', 'es_paquete')

    def __init__(self, numero):
        self.numero = numero
        self.accion = 'crear'
        self.codigo = ''
        self.nombre = ''
        self.instancia = None
        self.datos = {}              # {clave: valor} que se aplicará
        self.problemas = []          # [{nivel, campo, msg}]
        self.cambios = []            # [etiquetas] que cambiarían (para el preview)
        self.omitida = False         # True → la fila entera se saltea
        self.motivo_omitida = ''
        self.codigo_no_encontrado = False
        self.es_paquete = False

    def aviso(self, campo, msg):
        self.problemas.append({'nivel': 'aviso', 'campo': campo, 'msg': msg})

    def a_dict(self):
        return {
            'numero': self.numero,
            'accion': self.accion,
            'codigo': self.codigo,
            'nombre': self.nombre,
            'cambios': self.cambios,
            'problemas': self.problemas,
            'omitida': self.omitida,
            'motivo_omitida': self.motivo_omitida,
            'codigo_no_encontrado': self.codigo_no_encontrado,
        }


class ResultadoAnalisis:
    def __init__(self):
        self.filas = []
        self.columnas_ignoradas = []
        self.columnas_reconocidas = []
        self.columnas_duplicadas = []
        self.error_global = None
        self.tiene_columna_codigo = True
        self.avisos_archivo = []       # [str] — hoja usada, filas truncadas, etc.

    def resumen(self):
        crear = sum(1 for f in self.filas if not f.omitida and f.accion == 'crear')
        act = sum(1 for f in self.filas if not f.omitida and f.accion == 'actualizar' and f.cambios)
        igual = sum(1 for f in self.filas if not f.omitida and f.accion == 'actualizar' and not f.cambios)
        omit = sum(1 for f in self.filas if f.omitida)
        con_probl = sum(1 for f in self.filas if f.problemas)
        return {
            'crear': crear, 'actualizar': act, 'sin_cambios': igual,
            'omitidas': omit, 'con_problemas': con_probl, 'total': len(self.filas),
        }

    def a_dict(self):
        return {
            'error_global': self.error_global,
            'columnas_ignoradas': self.columnas_ignoradas,
            'columnas_reconocidas': self.columnas_reconocidas,
            'columnas_duplicadas': self.columnas_duplicadas,
            'avisos_archivo': self.avisos_archivo,
            'tiene_columna_codigo': self.tiene_columna_codigo,
            'resumen': self.resumen(),
            'filas': [f.a_dict() for f in self.filas],
        }


def _celda(fila, idx):
    return fila[idx] if idx < len(fila) else ''


def analizar(headers, filas, meta=None):
    """`headers` / `filas` / `meta` de xlsx_reader.leer_xlsx().
    Devuelve ResultadoAnalisis. NO escribe nada."""
    res = ResultadoAnalisis()

    if meta:
        if meta.get('hoja'):
            res.avisos_archivo.append(f'Se leyó la hoja "{meta["hoja"]}".')
        if meta.get('fila_encabezados', 1) > 1:
            res.avisos_archivo.append(
                f'Los encabezados se detectaron en la fila {meta["fila_encabezados"]}.')
        if meta.get('truncado'):
            res.avisos_archivo.append(
                f'El archivo tiene muchas filas: solo se procesan las primeras {MAX_FILAS}.')

    if not headers:
        res.error_global = 'La planilla no tiene encabezados.'
        return res

    col, ignoradas, duplicadas = _mapa_columnas(headers)
    res.columnas_ignoradas = ignoradas
    res.columnas_duplicadas = duplicadas
    res.columnas_reconocidas = [ETIQUETAS.get(c, c) for c in col if c != 'codigo']
    res.tiene_columna_codigo = 'codigo' in col

    escribibles = [c for c in col if c != 'codigo']
    if not escribibles:
        res.error_global = (
            'No se reconoció ninguna columna para importar. Revisá los '
            'encabezados o descargá la plantilla.'
        )
        return res
    if not filas:
        res.error_global = 'La planilla no tiene filas de datos.'
        return res

    # Precarga de productos por código (mayúsculas: PRD-00001).
    codigos = set()
    if res.tiene_columna_codigo:
        ci = col['codigo']
        for fila in filas:
            c = _limpiar(_celda(fila, ci)).upper()
            if c:
                codigos.add(c)
    por_codigo = {}
    if codigos:
        for p in Producto.objects.filter(codigo__in=codigos):
            por_codigo[p.codigo.upper()] = p

    # Para detectar "esta fila nueva ya existe": nombre y código de barras
    # de todo el catálogo (para no crear duplicados sin querer).
    nombre_idx = col.get('nombre')
    barras_idx = col.get('codigo_barras')
    catalogo_nombre, catalogo_barras = {}, {}
    if nombre_idx is not None or barras_idx is not None:
        for p in Producto.objects.values('pk', 'codigo', 'nombre', 'codigo_barras'):
            if p['nombre']:
                catalogo_nombre.setdefault(p['nombre'].strip().lower(), p)
            if p['codigo_barras']:
                catalogo_barras.setdefault(p['codigo_barras'].strip().lower(), p)

    codigos_vistos = {}   # código_upper -> nro de la primera fila donde apareció

    for n, fila in enumerate(filas, start=1):
        fa = FilaAnalizada(n)

        codigo_val = ''
        if res.tiene_columna_codigo:
            codigo_val = _limpiar(_celda(fila, col['codigo']))
        fa.codigo = codigo_val

        inst = por_codigo.get(codigo_val.upper()) if codigo_val else None
        if inst is not None:
            fa.accion = 'actualizar'
            fa.instancia = inst
            fa.es_paquete = inst.es_paquete
        else:
            fa.accion = 'crear'
            fa.instancia = Producto()
            fa.codigo_no_encontrado = bool(codigo_val)

        # — Parseo celda por celda —
        for clave, idx in col.items():
            if clave == 'codigo':
                continue
            crudo = _celda(fila, idx)
            if _es_vacio(crudo):
                continue  # VACÍO / "-" / "s/d" = no tocar ese campo
            valor, nivel, msg = CAMPOS[clave](crudo)
            if nivel:
                fa.problemas.append({'nivel': nivel, 'campo': ETIQUETAS.get(clave, clave), 'msg': msg})
            if valor is not None:
                fa.datos[clave] = valor

        fa.nombre = fa.datos.get('nombre') or getattr(fa.instancia, 'nombre', '') or ''

        # Fila de puro ruido → se descarta silenciosamente.
        if fa.accion == 'crear' and not fa.datos:
            continue

        res.filas.append(fa)

        # Código repetido dentro del MISMO archivo → aviso.
        if codigo_val:
            cu = codigo_val.upper()
            if cu in codigos_vistos:
                fa.aviso('Código', f'el código "{codigo_val}" también está en la fila '
                                    f'{codigos_vistos[cu]} — se aplican las dos, en orden')
            else:
                codigos_vistos[cu] = n

        # Crear sin nombre = imposible → única fila que no entra.
        if fa.accion == 'crear' and not fa.datos.get('nombre'):
            fa.omitida = True
            fa.motivo_omitida = 'no se puede crear un producto sin nombre'
            continue

        # ¿Esta fila NUEVA ya existe (mismo nombre o mismo código de barras)?
        if fa.accion == 'crear':
            match = None
            nom = (fa.datos.get('nombre') or '').strip().lower()
            bar = (fa.datos.get('codigo_barras') or '').strip().lower()
            if bar and bar in catalogo_barras:
                match = catalogo_barras[bar]
                motivo = 'el mismo código de barras'
            elif nom and nom in catalogo_nombre:
                match = catalogo_nombre[nom]
                motivo = 'el mismo nombre'
            if match:
                fa.aviso('Código', (
                    f'ya existe un producto con {motivo} ({match["codigo"]} — '
                    f'{match["nombre"]}). Esta fila creará OTRO producto. Si querías '
                    f'actualizarlo, poné su código en la columna Código.'
                ))

        # Paquete (combo): sus datos se calculan de los componentes.
        if fa.es_paquete:
            fa.aviso('Código', f'{fa.codigo} es un paquete (combo) — algunos campos '
                                f'como precio y stock se calculan de sus componentes')

        # Qué cambiaría (para el preview).
        if fa.accion == 'actualizar':
            fa.cambios = [
                ETIQUETAS.get(k, k) for k, v in fa.datos.items()
                if _difiere(fa.instancia, k, v)
            ]
        else:
            fa.cambios = [ETIQUETAS.get(k, k) for k in fa.datos]

        # Aviso suave: automático sin % de ganancia (no frena).
        modo = fa.datos.get('modo_precio', getattr(fa.instancia, 'modo_precio', None))
        pct = fa.datos.get('porcentaje_ganancia', getattr(fa.instancia, 'porcentaje_ganancia', None))
        if modo == ModoPrecio.AUTOMATICO and pct is None:
            fa.aviso(ETIQUETAS['modo_precio'],
                     'modo automático sin % de ganancia — el precio se calculará con 0% de margen')

    return res


def _aplicar_datos_en_memoria(producto, datos):
    for clave, valor in datos.items():
        setattr(producto, clave, valor)


# ══════════════════════════════════════════════════════════════════
#  APLICACIÓN
# ══════════════════════════════════════════════════════════════════

class ResultadoAplicacion:
    def __init__(self):
        self.error_global = None
        self.creados = []        # [{codigo, nombre}]
        self.actualizados = []   # [{codigo, nombre, campos:[...]}]
        self.sin_cambios = []    # [{codigo, nombre}]
        self.omitidas = []       # [{numero, motivo}]
        self.con_notas = []      # [{numero, codigo, nombre, notas:[...]}]
        self.fallidas = []       # [{numero, codigo, nombre, error}]
        self.columnas_ignoradas = []
        self.avisos_archivo = []

    def a_dict(self):
        return {
            'ok': self.error_global is None,
            'error_global': self.error_global,
            'creados': self.creados,
            'actualizados': self.actualizados,
            'sin_cambios': self.sin_cambios,
            'omitidas': self.omitidas,
            'con_notas': self.con_notas,
            'fallidas': self.fallidas,
            'columnas_ignoradas': self.columnas_ignoradas,
            'avisos_archivo': self.avisos_archivo,
            'total_creados': len(self.creados),
            'total_actualizados': len(self.actualizados),
            'total_sin_cambios': len(self.sin_cambios),
            'total_omitidas': len(self.omitidas) + len(self.fallidas),
        }


def aplicar(headers, filas, meta=None):
    """Analiza y aplica todo lo aplicable. Cada fila va en su propio
    savepoint: si una falla por algo inesperado, se informa y se saltea,
    las demás se guardan igual."""
    out = ResultadoAplicacion()
    res = analizar(headers, filas, meta)

    out.columnas_ignoradas = res.columnas_ignoradas
    out.avisos_archivo = res.avisos_archivo
    if res.error_global:
        out.error_global = res.error_global
        return out
    if not res.filas:
        out.error_global = 'La planilla no tiene ninguna fila con datos para importar.'
        return out

    with transaction.atomic():
        for fa in res.filas:
            if fa.omitida:
                out.omitidas.append({'numero': fa.numero, 'motivo': fa.motivo_omitida})
                continue
            try:
                with transaction.atomic():          # savepoint por fila
                    cambios = _guardar_fila(fa)
            except Exception as e:
                out.fallidas.append({
                    'numero': fa.numero,
                    'codigo': fa.codigo or (fa.instancia.codigo if fa.instancia.pk else ''),
                    'nombre': fa.nombre,
                    'error': str(e)[:300],
                })
                continue

            item = {'codigo': fa.instancia.codigo, 'nombre': fa.instancia.nombre}
            if fa.accion == 'crear':
                out.creados.append(item)
            elif cambios:
                out.actualizados.append({**item, 'campos': cambios})
            else:
                out.sin_cambios.append(item)

            if fa.problemas:
                out.con_notas.append({
                    'numero': fa.numero,
                    'codigo': fa.instancia.codigo,
                    'nombre': fa.instancia.nombre,
                    'notas': [f"{p['campo']}: {p['msg']}" for p in fa.problemas],
                })

    return out


def _guardar_fila(fa):
    """Crea/actualiza el producto. Devuelve la lista de etiquetas de campos
    que cambiaron de verdad (para el reporte)."""
    producto = fa.instancia
    antes = {k: _valor_actual(producto, k) for k in fa.datos}

    _aplicar_datos_en_memoria(producto, fa.datos)
    producto.save()

    # Modo manual + "no incluye IVA": el número guardado es el precio SIN
    # IVA → pasarlo a precio final (igual que el alta manual).
    if 'precio_venta' in fa.datos and producto.modo_precio == ModoPrecio.MANUAL:
        final = producto.calcular_precio_final(fa.datos['precio_venta'])
        if final is not None and final != producto.precio_venta:
            producto.precio_venta = final
            producto.save(update_fields=['precio_venta'])

    # Recalcular costo/precio SOLO si la fila tocó algo relacionado al precio
    # (evita recálculos y consultas cuando la fila solo cambia notas, marca…).
    if _CAMPOS_PRECIO & set(fa.datos):
        producto.actualizar_costo_y_precio()

    cambios = []
    for k in fa.datos:
        if _valor_actual(producto, k) != antes[k]:
            cambios.append(ETIQUETAS.get(k, k))
    return cambios
