"""
Catálogo de columnas y armado del queryset para la exportación de
productos a Excel (ver views_export.py).

Una sola fuente de verdad para:
  - qué columnas existen, su etiqueta y cómo se saca el valor de un Producto
  - los grupos en que se muestran en el modal de exportación
  - el preset "Resumen"
  - cómo se traducen los filtros del modal a un queryset

Los filtros replican los de GestionProductosView (productos/views_productos.py):
estado, categoría, tipo, publicado y búsqueda de texto. Se agrega `stock`
(con / sin / bajo) que en la pantalla es un checkbox de "stock bajo".
"""

from django.db.models import F, Q

from .models import Producto


# ══════════════════════════════════════════════════════════════════
#  CATÁLOGO DE COLUMNAS
#  (clave, etiqueta, función que recibe un Producto y devuelve el valor)
# ══════════════════════════════════════════════════════════════════

COLUMNAS = [
    # — Identificación —
    ('id',                  'ID',                       lambda p: p.pk),
    ('codigo',              'Código',                   lambda p: p.codigo),
    ('sku',                 'SKU',                      lambda p: p.sku),
    ('codigo_barras',       'Código de barras',         lambda p: p.codigo_barras),
    ('codigo_proveedor',    'Código del proveedor',     lambda p: p.codigo_proveedor),
    ('nombre',              'Nombre',                   lambda p: p.nombre),
    ('nombre_corto',        'Nombre corto',             lambda p: p.nombre_corto),
    ('descripcion',         'Descripción interna',      lambda p: p.descripcion),
    ('descripcion_publica', 'Descripción pública',      lambda p: p.descripcion_publica),

    # — Clasificación —
    ('categoria',           'Categoría',                lambda p: p.categoria.nombre if p.categoria_id else ''),
    ('tipo',                'Tipo',                     lambda p: p.tipo.nombre if p.tipo_id else ''),
    ('marca',               'Marca',                    lambda p: p.marca),
    ('modelo',              'Modelo',                   lambda p: p.modelo),
    ('fabricante',          'Fabricante',               lambda p: p.fabricante),
    ('pais_origen',         'País de origen',           lambda p: p.pais_origen),
    ('proveedor',           'Proveedor principal',      lambda p: p.proveedor.nombre if p.proveedor_id else ''),
    ('tags',                'Tags',                     lambda p: p.tags),

    # — Unidad y medidas —
    ('unidad_medida',       'Unidad de medida',         lambda p: p.get_unidad_medida_display()),
    ('unidades_por_presentacion', 'Unidades por presentación', lambda p: p.unidades_por_presentacion),
    ('contenido_neto',      'Contenido neto',           lambda p: p.contenido_neto),
    ('peso_kg',             'Peso (kg)',                lambda p: p.peso_kg),
    ('alto_cm',             'Alto (cm)',                lambda p: p.alto_cm),
    ('ancho_cm',            'Ancho (cm)',               lambda p: p.ancho_cm),
    ('profundidad_cm',      'Profundidad (cm)',         lambda p: p.profundidad_cm),

    # — Precio —
    ('precio_venta',        'Precio de venta',          lambda p: p.precio_venta),
    ('precio_neto',         'Precio neto (sin IVA)',    lambda p: p.precio_neto),
    ('monto_iva',           'Monto de IVA',             lambda p: p.monto_iva),
    ('alicuota_iva',        'Alícuota IVA',             lambda p: p.get_alicuota_iva_display()),
    ('precio_incluye_iva',  'Precio incluye IVA',       lambda p: p.precio_incluye_iva),
    ('modo_precio',         'Modo de precio',           lambda p: p.get_modo_precio_display()),
    ('porcentaje_ganancia', '% de ganancia',            lambda p: p.porcentaje_ganancia),
    ('costo_actual',        'Costo actual',             lambda p: p.costo_actual),
    ('costo',               'Costo de referencia',      lambda p: p.costo),

    # — Stock —
    ('gestiona_stock',      'Gestiona stock',           lambda p: p.gestiona_stock),
    ('stock_actual',        'Stock actual',             lambda p: p.stock_actual),
    ('stock_minimo',        'Stock mínimo',             lambda p: p.stock_minimo),
    ('stock_maximo',        'Stock máximo',             lambda p: p.stock_maximo),
    ('gestiona_variantes',  'Gestiona variantes',       lambda p: p.gestiona_variantes),
    ('es_paquete',          'Es un paquete',            lambda p: p.es_paquete),

    # — Estado y logística —
    ('estado',              'Estado',                   lambda p: p.get_estado_display()),
    ('publicado',           'Publicado en catálogo',    lambda p: p.publicado),
    ('destacado',           'Destacado',                lambda p: p.destacado),
    ('requiere_refrigeracion', 'Requiere refrigeración', lambda p: p.requiere_refrigeracion),
    ('es_fragil',           'Es frágil',                lambda p: p.es_fragil),
    ('es_peligroso',        'Es peligroso',             lambda p: p.es_peligroso),
    ('es_perecedero',       'Es perecedero',            lambda p: p.es_perecedero),
    ('posicion_deposito',   'Posición en depósito',     lambda p: p.posicion_deposito),
    ('notas',               'Notas internas',           lambda p: p.notas),

    # — Auditoría —
    ('fecha_alta',          'Fecha de alta',            lambda p: p.fecha_alta),
    ('fecha_modificacion',  'Última modificación',      lambda p: p.fecha_modificacion),
]

COLUMNAS_MAP    = {clave: fn for clave, _, fn in COLUMNAS}
ETIQUETAS       = {clave: etiqueta for clave, etiqueta, _ in COLUMNAS}
CLAVES_ORDEN    = [clave for clave, _, _ in COLUMNAS]

# Grupos para el modal (título, [claves...])
GRUPOS = [
    ('Identificación', ['id', 'codigo', 'sku', 'codigo_barras', 'codigo_proveedor',
                        'nombre', 'nombre_corto', 'descripcion', 'descripcion_publica']),
    ('Clasificación', ['categoria', 'tipo', 'marca', 'modelo', 'fabricante',
                       'pais_origen', 'proveedor', 'tags']),
    ('Unidad y medidas', ['unidad_medida', 'unidades_por_presentacion', 'contenido_neto',
                          'peso_kg', 'alto_cm', 'ancho_cm', 'profundidad_cm']),
    ('Precio', ['precio_venta', 'precio_neto', 'monto_iva', 'alicuota_iva',
                'precio_incluye_iva', 'modo_precio', 'porcentaje_ganancia',
                'costo_actual', 'costo']),
    ('Stock', ['gestiona_stock', 'stock_actual', 'stock_minimo', 'stock_maximo',
               'gestiona_variantes', 'es_paquete']),
    ('Estado y logística', ['estado', 'publicado', 'destacado', 'requiere_refrigeracion',
                            'es_fragil', 'es_peligroso', 'es_perecedero',
                            'posicion_deposito', 'notas']),
    ('Auditoría', ['fecha_alta', 'fecha_modificacion']),
]

# Preset "Resumen" — lo esencial para una lista rápida.
COLUMNAS_RESUMEN = [
    'codigo', 'nombre', 'categoria', 'tipo', 'precio_venta',
    'stock_actual', 'unidad_medida', 'estado', 'publicado',
]


def grupos_para_template():
    """[(titulo, [(clave, etiqueta), ...]), ...] para renderizar el modal."""
    return [
        (titulo, [(clave, ETIQUETAS[clave]) for clave in claves])
        for titulo, claves in GRUPOS
    ]


def normalizar_columnas(param):
    """
    `param` = string separado por comas con claves de columna.
    Devuelve la lista de claves válidas EN EL ORDEN del catálogo.
    Si no vino nada válido, devuelve todas.
    """
    pedidas = {c.strip() for c in (param or '').split(',') if c.strip()}
    elegidas = [c for c in CLAVES_ORDEN if c in pedidas]
    return elegidas or list(CLAVES_ORDEN)


# ══════════════════════════════════════════════════════════════════
#  QUERYSET
# ══════════════════════════════════════════════════════════════════

def construir_queryset(params):
    """
    `params` = request.GET (o cualquier dict-like).

    Si viene `solo` (lista de PKs separada por comas), exporta exactamente
    esos productos e ignora el resto de los filtros — es el modo
    "solo los seleccionados" de la tabla.

    Si no, aplica los filtros del modal: q, estado, categoria, tipo,
    publicado, stock.
    """
    qs = Producto.objects.select_related('categoria', 'tipo', 'proveedor')

    solo = (params.get('solo') or '').strip()
    if solo:
        pks = [int(x) for x in solo.split(',') if x.strip().isdigit()]
        return qs.filter(pk__in=pks).order_by('nombre')

    q = (params.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) | Q(codigo__icontains=q) | Q(sku__icontains=q)
            | Q(marca__icontains=q) | Q(codigo_barras__icontains=q)
            | Q(codigo_proveedor__icontains=q)
        )

    estado = (params.get('estado') or '').strip()
    if estado:
        qs = qs.filter(estado=estado)

    categoria = (params.get('categoria') or '').strip()
    if categoria.isdigit():
        qs = qs.filter(categoria__pk=categoria)

    tipo = (params.get('tipo') or '').strip()
    if tipo.isdigit():
        qs = qs.filter(tipo__pk=tipo)

    publicado = (params.get('publicado') or '').strip()
    if publicado == '1':
        qs = qs.filter(publicado=True)
    elif publicado == '0':
        qs = qs.filter(publicado=False)

    stock = (params.get('stock') or '').strip()
    if stock == 'con':
        qs = qs.filter(gestiona_stock=True, stock_actual__gt=0)
    elif stock == 'sin':
        qs = qs.filter(gestiona_stock=True, stock_actual__lte=0)
    elif stock == 'bajo':
        qs = qs.filter(gestiona_stock=True, stock_minimo__gt=0,
                       stock_actual__lte=F('stock_minimo'))

    return qs.order_by('nombre')


def generar_filas(qs, claves):
    """Itera el queryset y devuelve, por producto, la lista de valores
    correspondiente a `claves` (en ese orden)."""
    getters = [COLUMNAS_MAP[c] for c in claves]
    for producto in qs.iterator():
        yield [getter(producto) for getter in getters]
