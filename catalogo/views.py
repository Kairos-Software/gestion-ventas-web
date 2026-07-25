from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, TemplateView

from core.models import DatosEmpresa
from productos.models import (
    AplicacionOferta, CategoriaProducto, EstadoProducto, Producto, TipoOferta, ofertas_vigentes_hoy,
)

from .models import ConfiguracionCatalogo, PlantillaCatalogo

# Estados de producto que se muestran en el catálogo público. INACTIVO y
# DISCONTINUADO quedan afuera aunque alguien se olvide de despublicarlos:
# "publicado" es la intención del dueño, pero estos dos estados pisan esa
# intención porque significan "esto ya no se vende".
ESTADOS_VISIBLES_CATALOGO = [EstadoProducto.ACTIVO, EstadoProducto.AGOTADO]

# Un producto se marca "Nuevo" en la card si se dio de alta hace menos de
# esto — no es un campo del modelo, se calcula al vuelo desde fecha_alta.
DIAS_PRODUCTO_NUEVO = 14

PRODUCTOS_POR_PAGINA = 12

SECCIONES_VALIDAS = {'todos', 'productos', 'ofertas', 'paquetes'}

ORDENES_CATALOGO = {
    'precio_asc':  ('precio_venta',),
    'precio_desc': ('-precio_venta',),
    'nuevos':      ('-fecha_alta',),
}


def _productos_publicados_base():
    return (
        Producto.objects
        .filter(publicado=True, estado__in=ESTADOS_VISIBLES_CATALOGO)
        .select_related('categoria')
        .prefetch_related('imagenes')
    )


def _categorias_footer():
    """Categorías con al menos un producto publicado — para el pie de página, en todas las vistas."""
    return list(
        CategoriaProducto.objects
        .filter(activo=True, productos__publicado=True, productos__estado__in=ESTADOS_VISIBLES_CATALOGO)
        .distinct()[:8]
    )


def _fmt_pct(pct):
    """12.50 -> '12,5' / 50.00 -> '50' — sin ceros de relleno, con coma decimal."""
    return f'{pct.normalize():f}'.replace('.', ',')


def _info_oferta(producto, ofertas, cantidad=1):
    """
    De las ofertas vigentes hoy, la primera (ya vienen ordenadas por
    `orden`/nombre) que alcance a este producto — o None. Devuelve además
    el precio ya descontado y un texto corto de badge para la card.
    Las ofertas UMBRAL no se evalúan acá: son sobre el total del carrito,
    no sobre un producto puntual (se muestran aparte, como banner).

    `cantidad` importa solo para NXM ("llevá X, pagá Y"): el % efectivo
    depende de cuántas unidades se llevan (2x1 con 1 unidad no da nada;
    con 2, sí — ver Oferta.descuento_equivalente). Por default es 1
    (navegando el catálogo con una sola unidad no hay descuento todavía);
    CrearPedidoAjax pasa la cantidad real del carrito para cobrar bien.

    Solo se consideran ofertas de aplicación AUTOMÁTICA: el visitante del
    catálogo no tiene forma de "elegir" una oferta MANUAL — esas quedan
    para que el vendedor las aplique a mano desde Nueva Venta. Sin este
    filtro, una oferta pensada para casos puntuales terminaría
    aplicándose sola a todo el mundo en el catálogo público.
    """
    precio = producto.precio_venta
    for oferta in ofertas:
        if oferta.tipo == TipoOferta.UMBRAL:
            continue
        if oferta.aplicacion != AplicacionOferta.AUTOMATICA:
            continue
        if not oferta.aplica_a_producto(producto):
            continue
        if oferta.tipo == TipoOferta.NXM:
            pct = oferta.descuento_equivalente(cantidad)
            precio_final = None
            if precio is not None:
                precio_final = (precio * (1 - pct / 100)).quantize(Decimal('0.01'))
            return {
                'oferta': oferta,
                'badge': f'{oferta.cantidad_lleva}x{oferta.cantidad_paga}',
                'precio_final': precio_final,
            }
        # PORCENTAJE
        pct = oferta.porcentaje or Decimal('0')
        precio_final = None
        if precio is not None:
            precio_final = (precio * (1 - pct / 100)).quantize(Decimal('0.01'))
        return {
            'oferta': oferta,
            'badge': f'-{_fmt_pct(pct)}%',
            'precio_final': precio_final,
        }
    return None


def _ofertas_umbral_automaticas_json(ofertas):
    """
    Ofertas UMBRAL con aplicación AUTOMÁTICA, listas para mandar al
    carrito del catálogo (ver carrito.js) — el visitante no elige nada,
    así que las manuales quedan afuera (esas las aplica el vendedor a
    mano desde Nueva Venta). Mismos datos que usa el descuento global
    del pedido en CrearPedidoAjax, para que el total que ve acá coincida
    con el que termina guardado.
    """
    return [
        {
            'nombre': o.nombre,
            'porcentaje': str(o.porcentaje) if o.porcentaje is not None else '0',
            'monto_minimo': str(o.monto_minimo) if o.monto_minimo is not None else '0',
            'base_calculo': o.base_calculo,
        }
        for o in ofertas
        if o.tipo == TipoOferta.UMBRAL and o.aplicacion == AplicacionOferta.AUTOMATICA
    ]


def _ofertas_nxm_automaticas_json(ofertas):
    """
    Ofertas NXM ("llevá X, pagá Y") automáticas, con su alcance —
    para que el carrito del catálogo pueda recalcular el % efectivo
    según la cantidad de cada línea (2x1 con 1 unidad no da nada; con 2,
    sí), igual que hace _info_oferta acá en el servidor. Sin esto, el
    carrito mostraría un precio distinto al que termina cobrándose al
    confirmar el pedido.
    """
    return [
        {
            'nombre': o.nombre,
            'cantidad_lleva': o.cantidad_lleva,
            'cantidad_paga': o.cantidad_paga,
            'productos': list(o.productos.values_list('pk', flat=True)),
            'categorias': list(o.categorias.values_list('pk', flat=True)),
        }
        for o in ofertas
        if o.tipo == TipoOferta.NXM and o.aplicacion == AplicacionOferta.AUTOMATICA
    ]


def _ahorro_paquete(paquete):
    """
    $ que se ahorra llevando el paquete armado en vez de sus componentes
    sueltos al precio de lista de cada uno — o None si no hay ahorro
    real (o algún componente no tiene precio cargado). Usa el prefetch
    de 'componentes__producto' ya hecho en CatalogoHomeView.
    """
    if paquete.precio_venta is None:
        return None
    suma = Decimal('0')
    for c in paquete.componentes.all():
        if c.producto.precio_venta is None:
            return None
        suma += c.cantidad * c.producto.precio_venta
    ahorro = suma - paquete.precio_venta
    return {'suma': suma, 'ahorro': ahorro} if ahorro > 0 else None


def _es_nuevo(producto):
    limite = timezone.now() - timezone.timedelta(days=DIAS_PRODUCTO_NUEVO)
    return producto.fecha_alta >= limite


def _disponible_compra(producto):
    """Tiene precio y no está sin stock — condición para mostrar 'Agregar' en vez de nada."""
    if producto.precio_venta is None or producto.estado == EstadoProducto.AGOTADO:
        return False
    if producto.gestiona_stock and producto.stock_actual <= 0:
        return False
    return True


def _url_sin(get_params, *campos):
    """Querystring actual sin `campos` — para los links "quitar" de los filtros activos."""
    copia = get_params.copy()
    for campo in campos:
        copia.pop(campo, None)
    return copia.urlencode()


def _url_con(get_params, **cambios):
    """
    Querystring actual con `cambios` aplicados (o removidos si el valor es
    None/vacío) — para que los links de categoría/marca/sección no se
    pisen entre sí ni resetee la búsqueda al cambiar de filtro.
    """
    copia = get_params.copy()
    for campo, valor in cambios.items():
        if valor:
            copia[campo] = valor
        else:
            copia.pop(campo, None)
    return copia.urlencode()


def _decimal_o_none(valor):
    if not valor:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


@method_decorator(ensure_csrf_cookie, name='dispatch')
# El default de Django es X-Frame-Options: DENY. Esta vista necesita
# permitir same-origin para la vista previa en vivo de la pantalla de
# Configuración (ver core/templates/core/configuracion.html, iframe
# #catalogoPreviewFrame) — sigue bloqueado para cualquier otro origen.
@method_decorator(xframe_options_sameorigin, name='dispatch')
class CatalogoHomeView(TemplateView):

    def get_template_names(self):
        # ?preview_plantilla=<codigo> fuerza una plantilla puntual sin tocar
        # la guardada — lo usa la pantalla "Catálogo online" (ver
        # core/templates/core/catalogo_online.html) para mostrar, con datos
        # reales, tanto las miniaturas de cada plantilla como el preview
        # grande al instante al cambiar de selección, sin esperar a guardar.
        # No requiere permiso: no expone nada que la página real no muestre.
        plantilla = self.request.GET.get('preview_plantilla')
        if plantilla not in PlantillaCatalogo.values:
            plantilla = ConfiguracionCatalogo.get_solo().plantilla
        if plantilla == PlantillaCatalogo.BENTO:
            return ['catalogo/plantillas/bento/home.html']
        return ['catalogo/home.html']

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET

        seccion = get.get('seccion', 'todos').strip()
        if seccion not in SECCIONES_VALIDAS:
            seccion = 'todos'
        categoria_slug = get.get('categoria', '').strip()
        marca = get.get('marca', '').strip()
        q = get.get('q', '').strip()
        orden = get.get('orden', '').strip()
        precio_min = _decimal_o_none(get.get('precio_min', '').strip())
        precio_max = _decimal_o_none(get.get('precio_max', '').strip())

        ofertas = ofertas_vigentes_hoy()
        ofertas_umbral = [o for o in ofertas if o.tipo == TipoOferta.UMBRAL]

        def _con_oferta_y_nuevo(qs):
            items = list(qs)
            for it in items:
                it.oferta_info = _info_oferta(it, ofertas)
                it.es_nuevo = _es_nuevo(it)
                it.disponible_compra = _disponible_compra(it)
            return items

        paquetes_qs = _productos_publicados_base().filter(es_paquete=True) \
            .prefetch_related('componentes__producto').order_by('-destacado', 'nombre')
        paquetes = _con_oferta_y_nuevo(paquetes_qs)
        for pq in paquetes:
            pq.ahorro = _ahorro_paquete(pq)

        # "Vidriera" — Destacados / Ofertas del momento: solo tiene sentido
        # mostrarla en la vista limpia (sin filtros ni búsqueda), porque
        # muestra una selección fija que no depende de lo que se está
        # filtrando en la grilla de abajo.
        mostrar_vidriera = (
            seccion == 'todos' and not categoria_slug and not marca and not q
            and precio_min is None and precio_max is None
            and get.get('pagina', '1').strip() in ('', '1')
        )
        destacados = []
        ofertas_destacadas = []
        if mostrar_vidriera:
            destacados = _con_oferta_y_nuevo(
                _productos_publicados_base().filter(es_paquete=False, destacado=True).order_by('-fecha_alta')[:4]
            )
            candidatos_oferta = _con_oferta_y_nuevo(
                _productos_publicados_base().filter(es_paquete=False).exclude(precio_venta=None)
            )
            ofertas_destacadas = [p for p in candidatos_oferta if p.oferta_info][:4]

        productos_qs = _productos_publicados_base().filter(es_paquete=False)
        if categoria_slug:
            productos_qs = productos_qs.filter(categoria__slug=categoria_slug)
        if marca:
            productos_qs = productos_qs.filter(marca=marca)
        if q:
            productos_qs = productos_qs.filter(nombre__icontains=q)
        if precio_min is not None:
            productos_qs = productos_qs.filter(precio_venta__gte=precio_min)
        if precio_max is not None:
            productos_qs = productos_qs.filter(precio_venta__lte=precio_max)
        # Relevancia (default): destacados primero, después el orden habitual (nombre).
        productos_qs = productos_qs.order_by(*ORDENES_CATALOGO.get(orden, ('-destacado', 'nombre')))

        # Qué se muestra según la sección elegida (tabs). "ofertas" filtra
        # sobre la lista ya resuelta en Python porque `_info_oferta` mira
        # reglas (categorías/productos alcanzados, NXM, etc.) que no se
        # pueden traducir 1:1 a un filtro de queryset.
        mostrar_productos = seccion in ('todos', 'productos', 'ofertas')
        mostrar_paquetes = seccion in ('todos', 'paquetes', 'ofertas')

        productos = []
        pagina = paginas = None
        url_pagina_anterior = url_pagina_siguiente = ''
        total_productos = 0

        if mostrar_productos:
            if seccion == 'ofertas':
                todos_los_productos = _con_oferta_y_nuevo(productos_qs)
                productos = [p for p in todos_los_productos if p.oferta_info]
                total_productos = len(productos)
            else:
                paginator = Paginator(productos_qs, PRODUCTOS_POR_PAGINA)
                try:
                    pagina_num = int(get.get('pagina', 1))
                except ValueError:
                    pagina_num = 1
                pagina = paginator.get_page(pagina_num)
                productos = _con_oferta_y_nuevo(pagina.object_list)
                total_productos = paginator.count
                paginas = [
                    {'numero': n, 'url': '?' + _url_con(get, pagina=str(n)), 'activa': n == pagina.number}
                    for n in paginator.page_range
                ]
                url_pagina_anterior = (
                    '?' + _url_con(get, pagina=str(pagina.previous_page_number())) if pagina.has_previous() else ''
                )
                url_pagina_siguiente = (
                    '?' + _url_con(get, pagina=str(pagina.next_page_number())) if pagina.has_next() else ''
                )

        if mostrar_paquetes:
            if seccion == 'ofertas':
                paquetes = [pq for pq in paquetes if pq.oferta_info]
            total_productos += len(paquetes)
        else:
            paquetes = []

        categorias_qs = (
            CategoriaProducto.objects
            .filter(activo=True, productos__publicado=True, productos__estado__in=ESTADOS_VISIBLES_CATALOGO)
            .annotate(num_productos=Count(
                'productos',
                filter=Q(productos__publicado=True, productos__estado__in=ESTADOS_VISIBLES_CATALOGO, productos__es_paquete=False),
                distinct=True,
            ))
            .distinct()
        )
        marcas_qs = (
            _productos_publicados_base().filter(es_paquete=False)
            .exclude(marca='').values_list('marca', flat=True).distinct().order_by('marca')
        )

        categorias = [
            {'nombre': c.nombre, 'slug': c.slug, 'activa': c.slug == categoria_slug,
             'url': '?' + _url_con(get, categoria=c.slug), 'cantidad': c.num_productos}
            for c in categorias_qs
        ]
        total_catalogo = _productos_publicados_base().filter(es_paquete=False).count()
        marcas = [
            {'nombre': m, 'activa': m == marca, 'url': '?' + _url_con(get, marca=None if m == marca else m)}
            for m in marcas_qs
        ]

        secciones = [
            {'id': s, 'nombre': n, 'url': '?' + _url_con(get, seccion=None if s == 'todos' else s), 'activa': s == seccion}
            for s, n in [('todos', 'Todos'), ('productos', 'Productos'), ('ofertas', 'Ofertas'), ('paquetes', 'Paquetes')]
        ]

        # Filtros activos, para la fila de chips removibles arriba de la grilla.
        filtros_activos = []
        if categoria_slug:
            cat = next((c for c in categorias_qs if c.slug == categoria_slug), None)
            filtros_activos.append({'etiqueta': cat.nombre if cat else categoria_slug, 'quitar': _url_sin(get, 'categoria')})
        if marca:
            filtros_activos.append({'etiqueta': marca, 'quitar': _url_sin(get, 'marca')})
        if q:
            filtros_activos.append({'etiqueta': f'"{q}"', 'quitar': _url_sin(get, 'q')})
        if precio_min is not None or precio_max is not None:
            desde = f'${precio_min:.0f}' if precio_min is not None else ''
            hasta = f'${precio_max:.0f}' if precio_max is not None else ''
            etiqueta = f'{desde} - {hasta}'.strip(' -') if (desde or hasta) else ''
            filtros_activos.append({'etiqueta': f'Precio {etiqueta}', 'quitar': _url_sin(get, 'precio_min', 'precio_max')})

        ctx['empresa'] = DatosEmpresa.get_solo()
        ctx['config_catalogo'] = ConfiguracionCatalogo.get_solo()
        ctx['default_hero_subtitulo'] = ConfiguracionCatalogo.DEFAULT_HERO_SUBTITULO
        ctx['default_sobre_nosotros'] = ConfiguracionCatalogo.DEFAULT_SOBRE_NOSOTROS
        # Exclude(imagen='') defensivo: un slide creado sin llegar a subirle
        # imagen (ej. el usuario cerró el modal a mitad de camino, ver
        # catalogo/views_config.py) no debe aparecer roto en el carrusel.
        ctx['slides'] = ctx['config_catalogo'].slides.exclude(imagen='')
        ctx['secciones'] = secciones
        ctx['seccion_activa'] = seccion
        ctx['mostrar_productos'] = mostrar_productos
        ctx['mostrar_paquetes'] = mostrar_paquetes
        ctx['productos'] = productos
        ctx['paquetes'] = paquetes
        ctx['categorias'] = categorias
        ctx['categorias_footer'] = list(categorias_qs)[:8]
        ctx['marcas'] = list(marcas)
        ctx['url_todas_categorias'] = '?' + _url_con(get, categoria=None)
        ctx['categoria_activa'] = categoria_slug
        ctx['marca_activa'] = marca
        ctx['precio_min'] = precio_min
        ctx['precio_max'] = precio_max
        ctx['ofertas_umbral'] = ofertas_umbral
        ctx['ofertas_umbral_json'] = _ofertas_umbral_automaticas_json(ofertas)
        ctx['ofertas_nxm_json'] = _ofertas_nxm_automaticas_json(ofertas)
        ctx['mostrar_vidriera'] = mostrar_vidriera
        ctx['destacados'] = destacados
        ctx['ofertas_destacadas'] = ofertas_destacadas
        ctx['total_catalogo'] = total_catalogo
        ctx['orden_activo'] = orden
        ctx['filtros_activos'] = filtros_activos
        ctx['pagina'] = pagina
        ctx['paginas'] = paginas
        ctx['url_pagina_anterior'] = url_pagina_anterior
        ctx['url_pagina_siguiente'] = url_pagina_siguiente
        ctx['total_productos'] = total_productos
        return ctx


@method_decorator(ensure_csrf_cookie, name='dispatch')
class ProductoDetalleView(DetailView):
    context_object_name = 'producto'

    def get_template_names(self):
        if ConfiguracionCatalogo.get_solo().plantilla == PlantillaCatalogo.BENTO:
            return ['catalogo/plantillas/bento/detalle.html']
        return ['catalogo/detalle.html']

    def get_queryset(self):
        return _productos_publicados_base()

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ofertas = ofertas_vigentes_hoy()
        ctx['empresa'] = DatosEmpresa.get_solo()
        ctx['config_catalogo'] = ConfiguracionCatalogo.get_solo()
        ctx['default_hero_subtitulo'] = ConfiguracionCatalogo.DEFAULT_HERO_SUBTITULO
        ctx['default_sobre_nosotros'] = ConfiguracionCatalogo.DEFAULT_SOBRE_NOSOTROS
        ctx['categorias_footer'] = _categorias_footer()
        ctx['oferta_info'] = _info_oferta(self.object, ofertas)
        ctx['ofertas_umbral_json'] = _ofertas_umbral_automaticas_json(ofertas)
        ctx['ofertas_nxm_json'] = _ofertas_nxm_automaticas_json(ofertas)
        ctx['imagenes'] = list(self.object.imagenes.all())
        ctx['es_nuevo'] = _es_nuevo(self.object)
        ctx['disponible_compra'] = _disponible_compra(self.object)
        if self.object.es_paquete:
            ctx['componentes'] = list(
                self.object.componentes.select_related('producto', 'combinacion')
            )
        return ctx
