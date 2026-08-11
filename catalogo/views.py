from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, TemplateView

from core.models import DatosEmpresa
from productos.models import (
    AplicacionOferta, CategoriaProducto, EstadoProducto, Producto, TipoOferta, TipoProducto, ofertas_vigentes_hoy,
)

from .models import ConfiguracionCatalogo, PlantillaCatalogo, PosicionBanner, TipoTileDestacado
from .utils import google_maps_link, wa_link_ar

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


def _filtro_busqueda(q):
    """
    Filtro de búsqueda del catálogo público — no solo nombre, para que
    buscar por marca/modelo/una palabra de la descripción o un tag
    también encuentre el producto (antes solo miraba `nombre`). Usado
    tanto por la grilla de la home como por el desplegable de
    sugerencias en vivo (BuscarSugerenciasAjax), para que ambos
    encuentren exactamente lo mismo.
    """
    return (
        Q(nombre__icontains=q) | Q(marca__icontains=q) | Q(modelo__icontains=q) |
        Q(descripcion_publica__icontains=q) | Q(descripcion__icontains=q) |
        Q(tags__icontains=q) | Q(categoria__nombre__icontains=q)
    )


def _contexto_base(request):
    """
    Contexto común a las 3 vistas públicas del catálogo (home, detalle,
    institucional) — todo lo que necesita el header/footer compartidos de
    base_catalogo.html (marca, nav, color) más lo que necesita el carrito
    (ofertas vigentes). Devuelve (ctx, ofertas): casi todos los callers
    también necesitan `ofertas` para su propia lógica, así se calcula
    una sola vez.
    """
    empresa = DatosEmpresa.get_solo()
    config = ConfiguracionCatalogo.get_solo()
    ofertas = ofertas_vigentes_hoy()
    ctx = {
        'empresa': empresa,
        'config_catalogo': config,
        'whatsapp_url': wa_link_ar(empresa.telefono) if empresa.telefono else '',
        'default_hero_subtitulo': ConfiguracionCatalogo.DEFAULT_HERO_SUBTITULO,
        'default_sobre_nosotros': ConfiguracionCatalogo.DEFAULT_SOBRE_NOSOTROS,
        'default_color_marca': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA,
        'default_color_marca_secundario': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO,
        'default_color_marca_bento': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_BENTO,
        'default_color_marca_secundario_bento': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_BENTO,
        'default_color_fondo_bento': ConfiguracionCatalogo.DEFAULT_COLOR_FONDO_BENTO,
        'default_color_fondo_bento_oscuro': ConfiguracionCatalogo.DEFAULT_COLOR_FONDO_BENTO_OSCURO,
        'default_color_marca_kinetic': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_KINETIC,
        'default_color_marca_secundario_kinetic': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_KINETIC,
        'default_color_marca_lumina': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_LUMINA,
        'default_color_marca_secundario_lumina': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_LUMINA,
        'default_nav_catalogo': ConfiguracionCatalogo.DEFAULT_NAV_CATALOGO,
        'default_nav_ofertas': ConfiguracionCatalogo.DEFAULT_NAV_OFERTAS,
        'default_nav_combos': ConfiguracionCatalogo.DEFAULT_NAV_COMBOS,
        'default_nav_tienda': ConfiguracionCatalogo.DEFAULT_NAV_TIENDA,
        'ofertas_umbral_json': _ofertas_umbral_automaticas_json(ofertas),
        'ofertas_nxm_json': _ofertas_nxm_automaticas_json(ofertas),
    }
    return ctx, ofertas


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


def _productos_relacionados(producto, ofertas, limite=8):
    """
    Candidatos para "También te puede interesar" en el detalle: misma
    categoría primero, completa con misma marca y, si todavía falta,
    con destacados — en cascada y sin duplicados.
    """
    base = _productos_publicados_base().filter(es_paquete=False).exclude(pk=producto.pk)
    vistos = {producto.pk}
    resultado = []

    if producto.categoria_id:
        extra = [
            p for p in base.filter(categoria_id=producto.categoria_id).order_by('-destacado', 'nombre')[:limite]
            if p.pk not in vistos
        ]
        resultado += extra
        vistos |= {p.pk for p in extra}

    if len(resultado) < limite and producto.marca:
        faltan = limite - len(resultado)
        extra = list(
            base.filter(marca=producto.marca).exclude(pk__in=vistos).order_by('-destacado', 'nombre')[:faltan]
        )
        resultado += extra
        vistos |= {p.pk for p in extra}

    if len(resultado) < limite:
        faltan = limite - len(resultado)
        resultado += list(
            base.filter(destacado=True).exclude(pk__in=vistos).order_by('-fecha_alta')[:faltan]
        )

    resultado = resultado[:limite]
    for p in resultado:
        p.oferta_info = _info_oferta(p, ofertas)
        p.es_nuevo = _es_nuevo(p)
        p.disponible_compra = _disponible_compra(p)
    return resultado


def _hero_producto(ofertas, config):
    """
    Producto (o combo) destacado en la tarjeta del hero de la home. Si el
    negocio eligió uno a mano (config.hero_producto, ver Configuración →
    Catálogo online → Apariencia) y sigue publicado, se respeta esa
    elección — aunque no tenga precio cargado (la tarjeta ya sabe mostrar
    "A consultar"), porque es una elección explícita del dueño. Si no hay
    elección manual, mismo criterio automático de siempre ("lo más
    representativo"): primero algo marcado destacado=True, si no hay, lo
    último cargado — ahí sí evitamos productos sin precio, para no elegir
    al azar algo que se vea incompleto.
    """
    base = _productos_publicados_base()
    candidato = None
    if config.hero_producto_id:
        candidato = base.filter(pk=config.hero_producto_id).first()
    if not candidato:
        base_con_precio = base.exclude(precio_venta=None)
        candidato = base_con_precio.filter(destacado=True).order_by('-fecha_alta').first()
    if not candidato:
        candidato = base_con_precio.order_by('-fecha_alta').first()
    if candidato:
        candidato.oferta_info = _info_oferta(candidato, ofertas)
        candidato.disponible_compra = _disponible_compra(candidato)
    return candidato


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


def _url_toggle(get_params, campo, valor):
    """Querystring actual con `valor` agregado a la lista de `campo` si no
    estaba, o sacado si ya estaba — para filtros de multi-selección
    (varias categorías/tipos tildados a la vez, ej: ?categoria=a&categoria=b)."""
    copia = get_params.copy()
    actuales = copia.getlist(campo)
    if valor in actuales:
        actuales = [v for v in actuales if v != valor]
    else:
        actuales = actuales + [valor]
    copia.setlist(campo, actuales)
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
        if plantilla == PlantillaCatalogo.KINETIC:
            return ['catalogo/plantillas/kinetic/home.html']
        if plantilla == PlantillaCatalogo.LUMINA:
            return ['catalogo/plantillas/lumina/home.html']
        return ['catalogo/home.html']

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        base_ctx, ofertas = _contexto_base(self.request)

        seccion = get.get('seccion', 'todos').strip()
        if seccion not in SECCIONES_VALIDAS:
            seccion = 'todos'
        # Multi-selección: se puede tildar varias categorías/tipos a la vez
        # (?categoria=a&categoria=b), no una sola — ver _url_toggle.
        categoria_slugs = [s.strip() for s in get.getlist('categoria') if s.strip()]
        tipo_slugs = [s.strip() for s in get.getlist('tipo') if s.strip()]
        marca = get.get('marca', '').strip()
        q = get.get('q', '').strip()
        orden = get.get('orden', '').strip()
        precio_min = _decimal_o_none(get.get('precio_min', '').strip())
        precio_max = _decimal_o_none(get.get('precio_max', '').strip())

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
        if q:
            paquetes_qs = paquetes_qs.filter(_filtro_busqueda(q))
        paquetes = _con_oferta_y_nuevo(paquetes_qs)
        for pq in paquetes:
            pq.ahorro = _ahorro_paquete(pq)

        # "Vidriera" — Destacados / Ofertas del momento: solo tiene sentido
        # mostrarla en la vista limpia (sin filtros ni búsqueda), porque
        # muestra una selección fija que no depende de lo que se está
        # filtrando en la grilla de abajo.
        mostrar_vidriera = (
            seccion == 'todos' and not categoria_slugs and not tipo_slugs and not marca and not q
            and precio_min is None and precio_max is None
            and get.get('pagina', '1').strip() in ('', '1')
        )
        destacados = []
        ofertas_destacadas = []
        paquetes_destacados = []
        # Versión "amplia" de las 3 listas de arriba — solo para los
        # carruseles de la vidriera de Almacén (ver catalogo/home.html),
        # que ahora pueden mostrar más de 4 ítems con flechas manuales.
        # Deliberadamente NO se toca destacados/ofertas_destacadas/
        # paquetes_destacados (siguen en [:4]) porque Bento/Kinetic/Lumina
        # consumen esos mismos nombres — así el cambio queda 100% acotado
        # a Almacén sin riesgo de romper las otras 3 plantillas.
        destacados_amplio = []
        ofertas_destacadas_amplio = []
        paquetes_destacados_amplio = []
        if mostrar_vidriera:
            destacados_qs = _con_oferta_y_nuevo(
                _productos_publicados_base().filter(es_paquete=False, destacado=True).order_by('-fecha_alta')[:10]
            )
            destacados = destacados_qs[:4]
            destacados_amplio = destacados_qs
            candidatos_oferta = _con_oferta_y_nuevo(
                _productos_publicados_base().filter(es_paquete=False).exclude(precio_venta=None)
            )
            ofertas_con_info = [p for p in candidatos_oferta if p.oferta_info]
            ofertas_destacadas = ofertas_con_info[:4]
            ofertas_destacadas_amplio = ofertas_con_info[:10]
            # Vidriera de combos: solo un adelanto — la lista completa (`paquetes`)
            # se muestra más abajo, en la grilla, así no se repite el mismo
            # contenido dos veces en la misma vista sin filtros.
            paquetes_destacados = paquetes[:4]
            paquetes_destacados_amplio = paquetes[:10]

        productos_qs = _productos_publicados_base().filter(es_paquete=False)
        if categoria_slugs:
            productos_qs = productos_qs.filter(categoria__slug__in=categoria_slugs)
        if tipo_slugs:
            productos_qs = productos_qs.filter(tipo__slug__in=tipo_slugs)
        if marca:
            productos_qs = productos_qs.filter(marca=marca)
        if q:
            productos_qs = productos_qs.filter(_filtro_busqueda(q))
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
                    {'numero': n, 'url': '?' + _url_con(get, pagina=str(n)) + '#kcCatalogo', 'activa': n == pagina.number}
                    for n in paginator.page_range
                ]
                url_pagina_anterior = (
                    '?' + _url_con(get, pagina=str(pagina.previous_page_number())) + '#kcCatalogo' if pagina.has_previous() else ''
                )
                url_pagina_siguiente = (
                    '?' + _url_con(get, pagina=str(pagina.next_page_number())) + '#kcCatalogo' if pagina.has_next() else ''
                )

        if mostrar_paquetes:
            if seccion == 'ofertas':
                paquetes = [pq for pq in paquetes if pq.oferta_info]
            total_productos += len(paquetes)
        else:
            paquetes = []

        # "También puede interesarte" — solo en modo búsqueda (`q`) y solo
        # cuando la búsqueda encontró poco: completa con productos de las
        # mismas categorías que ya aparecieron, sin repetir. Simple a
        # propósito (sin scoring de similitud) — el filtro ampliado de
        # _filtro_busqueda ya hace la mayor parte del trabajo de encontrar
        # cosas relacionadas antes de llegar acá.
        similares = []
        if q and total_productos < 4:
            categorias_encontradas = {p.categoria_id for p in productos if p.categoria_id}
            if categorias_encontradas:
                ya_vistos = {p.pk for p in productos} | {pq.pk for pq in paquetes}
                similares_qs = _productos_publicados_base().filter(
                    categoria_id__in=categorias_encontradas, es_paquete=False,
                ).exclude(pk__in=ya_vistos).order_by('-destacado', 'nombre')[:8]
                similares = _con_oferta_y_nuevo(similares_qs)

        categorias_qs = (
            CategoriaProducto.objects
            .filter(activo=True, productos__publicado=True, productos__estado__in=ESTADOS_VISIBLES_CATALOGO)
            .annotate(num_productos=Count(
                'productos',
                filter=Q(productos__publicado=True, productos__estado__in=ESTADOS_VISIBLES_CATALOGO, productos__es_paquete=False),
                distinct=True,
            ))
            .distinct()
            .order_by('nombre')
        )
        tipos_qs = (
            TipoProducto.objects
            .filter(activo=True, productos__publicado=True, productos__estado__in=ESTADOS_VISIBLES_CATALOGO)
            .select_related('categoria')
            .annotate(num_productos=Count(
                'productos',
                filter=Q(productos__publicado=True, productos__estado__in=ESTADOS_VISIBLES_CATALOGO, productos__es_paquete=False),
                distinct=True,
            ))
            .distinct()
            .order_by('nombre')
        )
        # Un tipo vive dentro de una categoría — con categorías tildadas,
        # "Tipo" solo ofrece los tipos de esas categorías (si buscás un
        # zapato, no tiene sentido ver "con capucha").
        if categoria_slugs:
            tipos_qs = tipos_qs.filter(categoria__slug__in=categoria_slugs)
        marcas_qs = (
            _productos_publicados_base().filter(es_paquete=False)
            .exclude(marca='').values_list('marca', flat=True).distinct().order_by('marca')
        )

        categorias = [
            {'nombre': c.nombre, 'slug': c.slug, 'activa': c.slug in categoria_slugs,
             'url': '?' + _url_toggle(get, 'categoria', c.slug) + '#kcCatalogo', 'cantidad': c.num_productos}
            for c in categorias_qs
        ]
        tipos = [
            {'nombre': t.nombre, 'slug': t.slug, 'activa': t.slug in tipo_slugs,
             'url': '?' + _url_toggle(get, 'tipo', t.slug) + '#kcCatalogo', 'cantidad': t.num_productos,
             'categoria_slug': t.categoria.slug if t.categoria_id else ''}
            for t in tipos_qs
        ]
        total_catalogo = _productos_publicados_base().filter(es_paquete=False).count()
        marcas = [
            {'nombre': m, 'activa': m == marca, 'url': '?' + _url_con(get, marca=None if m == marca else m) + '#kcCatalogo'}
            for m in marcas_qs
        ]

        secciones = [
            {'id': s, 'nombre': n, 'url': '?' + _url_con(get, seccion=None if s == 'todos' else s) + '#kcCatalogo', 'activa': s == seccion}
            for s, n in [('todos', 'Todos'), ('productos', 'Productos'), ('ofertas', 'Ofertas'), ('paquetes', 'Paquetes')]
        ]

        # Filtros activos, para la fila de chips removibles arriba de la grilla
        # — uno por cada categoría/tipo tildado (puede haber varios a la vez).
        filtros_activos = []
        for slug in categoria_slugs:
            cat = next((c for c in categorias_qs if c.slug == slug), None)
            filtros_activos.append({'etiqueta': cat.nombre if cat else slug, 'quitar': _url_toggle(get, 'categoria', slug) + '#kcCatalogo'})
        for slug in tipo_slugs:
            tip = next((t for t in tipos_qs if t.slug == slug), None)
            filtros_activos.append({'etiqueta': tip.nombre if tip else slug, 'quitar': _url_toggle(get, 'tipo', slug) + '#kcCatalogo'})
        if marca:
            filtros_activos.append({'etiqueta': marca, 'quitar': _url_sin(get, 'marca') + '#kcCatalogo'})
        if q:
            filtros_activos.append({'etiqueta': f'"{q}"', 'quitar': _url_sin(get, 'q') + '#kcCatalogo'})
        if precio_min is not None or precio_max is not None:
            desde = f'${precio_min:.0f}' if precio_min is not None else ''
            hasta = f'${precio_max:.0f}' if precio_max is not None else ''
            etiqueta = f'{desde} - {hasta}'.strip(' -') if (desde or hasta) else ''
            filtros_activos.append({'etiqueta': f'Precio {etiqueta}', 'quitar': _url_sin(get, 'precio_min', 'precio_max') + '#kcCatalogo'})

        ctx.update(base_ctx)
        ctx['hero_producto'] = _hero_producto(ofertas, base_ctx['config_catalogo'])
        # Exclude(imagen='') defensivo: un slide creado sin llegar a subirle
        # imagen (ej. el usuario cerró el modal a mitad de camino, ver
        # catalogo/views_config.py) no debe aparecer roto en el carrusel.
        ctx['slides'] = ctx['config_catalogo'].slides.exclude(imagen='')
        # Banners promocionales opcionales — exclusivos de "almacen" por
        # ahora (el resto de las plantillas no los renderiza todavía).
        banners_activos = ctx['config_catalogo'].banners.filter(activo=True)
        ctx['banners_debajo_hero'] = banners_activos.filter(posicion=PosicionBanner.DEBAJO_HERO)
        ctx['banners_antes_grilla'] = banners_activos.filter(posicion=PosicionBanner.ANTES_GRILLA)
        ctx['banners_antes_destacados'] = banners_activos.filter(posicion=PosicionBanner.ANTES_DESTACADOS)
        ctx['banners_antes_combos'] = banners_activos.filter(posicion=PosicionBanner.ANTES_COMBOS)
        # Categorías/marcas destacadas — accesos directos con imagen que
        # filtran el catálogo al click, exclusivos de "almacen" por ahora.
        # Se resuelve acá (no en el template) para poder armar la URL de
        # filtro fresca (_url_con, no _url_toggle: un tile fija el filtro,
        # no lo acumula con lo que ya esté tildado) y saltear tiles mal
        # configurados (ej. categoría borrada) sin romper el template.
        tiles_destacados = []
        if mostrar_vidriera:
            tiles_qs = ctx['config_catalogo'].tiles_destacados.filter(activo=True).exclude(imagen='').select_related('categoria')
            for t in tiles_qs:
                if t.tipo == TipoTileDestacado.CATEGORIA and t.categoria_id:
                    url = '?' + _url_con(get, categoria=t.categoria.slug) + '#kcCatalogo'
                    etiqueta = t.etiqueta or t.categoria.nombre
                elif t.tipo == TipoTileDestacado.MARCA and t.marca:
                    url = '?' + _url_con(get, marca=t.marca) + '#kcCatalogo'
                    etiqueta = t.etiqueta or t.marca
                else:
                    continue
                tiles_destacados.append({'imagen_url': t.imagen.url, 'etiqueta': etiqueta, 'url': url})
        ctx['tiles_destacados'] = tiles_destacados
        ctx['secciones'] = secciones
        ctx['seccion_activa'] = seccion
        ctx['mostrar_productos'] = mostrar_productos
        ctx['mostrar_paquetes'] = mostrar_paquetes
        ctx['productos'] = productos
        ctx['paquetes'] = paquetes
        ctx['categorias'] = categorias
        ctx['tipos'] = tipos
        ctx['marcas'] = list(marcas)
        ctx['url_todas_categorias'] = '?' + _url_sin(get, 'categoria') + '#kcCatalogo'
        ctx['url_todos_tipos'] = '?' + _url_sin(get, 'tipo') + '#kcCatalogo'
        ctx['url_limpiar_categoria_tipo'] = '?' + _url_sin(get, 'categoria', 'tipo') + '#kcCatalogo'
        ctx['categoria_activa'] = categoria_slugs
        ctx['tipo_activo'] = tipo_slugs
        ctx['marca_activa'] = marca
        ctx['precio_min'] = precio_min
        ctx['precio_max'] = precio_max
        ctx['ofertas_umbral'] = ofertas_umbral
        ctx['mostrar_vidriera'] = mostrar_vidriera
        ctx['q'] = q
        ctx['similares'] = similares
        ctx['destacados'] = destacados
        ctx['ofertas_destacadas'] = ofertas_destacadas
        ctx['paquetes_destacados'] = paquetes_destacados
        ctx['destacados_amplio'] = destacados_amplio
        ctx['ofertas_destacadas_amplio'] = ofertas_destacadas_amplio
        ctx['paquetes_destacados_amplio'] = paquetes_destacados_amplio
        # Las 2 tarjetas "spotlight" del hero de Bento (ver bento/home.html).
        # Prioridad por tarjeta: imagen propia cargada > producto elegido a
        # mano > automático. Resuelto acá (no en el template) porque Django
        # templates no tienen forma limpia de "cortar" un {% for %} en el
        # primer match, y porque mezclar las 2 tarjetas + imagen/producto
        # en el template se vuelve ilegible.
        config_bento = base_ctx['config_catalogo']
        hero_combo_1 = paquetes_destacados[0] if paquetes_destacados and not config_bento.hero_producto_id else None
        auto_spot_1 = hero_combo_1 or ctx['hero_producto']

        if config_bento.hero_spot1_imagen:
            ctx['hero_spot1_tipo'] = 'imagen'
            ctx['hero_spot1_imagen_url'] = config_bento.hero_spot1_imagen.url
        else:
            ctx['hero_spot1_tipo'] = 'producto'
            ctx['hero_spot_1'] = auto_spot_1
            ctx['hero_spot_1_es_combo'] = hero_combo_1 is not None

        if config_bento.hero_spot2_imagen:
            ctx['hero_spot2_tipo'] = 'imagen'
            ctx['hero_spot2_imagen_url'] = config_bento.hero_spot2_imagen.url
        else:
            ctx['hero_spot2_tipo'] = 'producto'
            if config_bento.hero_spot2_producto_id:
                hero_spot_2 = config_bento.hero_spot2_producto
                hero_spot_2_es_combo = hero_spot_2.es_paquete
            else:
                hero_spot_2 = None
                hero_spot_2_es_combo = False
                evitar_pk = auto_spot_1.pk if auto_spot_1 else None
                if hero_combo_1 is None and paquetes_destacados:
                    hero_spot_2 = paquetes_destacados[0]
                    hero_spot_2_es_combo = True
                if hero_spot_2 is None:
                    for d in destacados:
                        if d.pk != evitar_pk:
                            hero_spot_2 = d
                            break
            ctx['hero_spot_2'] = hero_spot_2
            ctx['hero_spot_2_es_combo'] = hero_spot_2_es_combo
        ctx['total_catalogo'] = total_catalogo
        ctx['orden_activo'] = orden
        ctx['filtros_activos'] = filtros_activos
        ctx['pagina'] = pagina
        ctx['paginas'] = paginas
        ctx['url_pagina_anterior'] = url_pagina_anterior
        ctx['url_pagina_siguiente'] = url_pagina_siguiente
        ctx['total_productos'] = total_productos
        return ctx


class BuscarSugerenciasAjax(View):
    """
    Desplegable en vivo del buscador del header (ver initBuscadorSugerencias
    en catalogo.js). Liviano a propósito: no calcula ofertas vigentes ni
    disponibilidad de compra — eso ya lo hace la pantalla de resultados
    real cuando el visitante llega ahí.
    """

    def get(self, request):
        q = request.GET.get('q', '').strip()
        if len(q) < 2:
            return JsonResponse({'resultados': []})
        productos = (
            _productos_publicados_base().filter(es_paquete=False)
            .filter(_filtro_busqueda(q))
            .order_by('-destacado', 'nombre')[:6]
        )
        resultados = [
            {
                'nombre': p.nombre,
                'imagen': p.imagenes.first().imagen.url if p.imagenes.first() else '',
                'precio': f'${p.precio_venta:.0f}' if p.precio_venta else 'A consultar',
                'categoria': p.categoria.nombre if p.categoria else '',
            }
            for p in productos
        ]
        return JsonResponse({'resultados': resultados})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class ProductoDetalleView(DetailView):
    context_object_name = 'producto'

    def get_template_names(self):
        plantilla = ConfiguracionCatalogo.get_solo().plantilla
        if plantilla == PlantillaCatalogo.BENTO:
            return ['catalogo/plantillas/bento/detalle.html']
        if plantilla == PlantillaCatalogo.KINETIC:
            return ['catalogo/plantillas/kinetic/detalle.html']
        if plantilla == PlantillaCatalogo.LUMINA:
            return ['catalogo/plantillas/lumina/detalle.html']
        return ['catalogo/detalle.html']

    def get_queryset(self):
        return _productos_publicados_base()

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_ctx, ofertas = _contexto_base(self.request)
        ctx.update(base_ctx)
        ctx['oferta_info'] = _info_oferta(self.object, ofertas)
        precio_final = ctx['oferta_info']['precio_final'] if ctx['oferta_info'] else None
        if precio_final and self.object.precio_venta:
            ahorro = self.object.precio_venta - precio_final
            ctx['ahorro_pct'] = round(ahorro / self.object.precio_venta * 100)
        ctx['imagenes'] = list(self.object.imagenes.all())
        ctx['es_nuevo'] = _es_nuevo(self.object)
        ctx['disponible_compra'] = _disponible_compra(self.object)
        ctx['tags_producto'] = [t.strip() for t in self.object.tags.split(',') if t.strip()]
        if self.object.es_paquete:
            ctx['componentes'] = list(
                self.object.componentes.select_related('producto', 'combinacion')
            )
            ctx['ahorro'] = _ahorro_paquete(self.object)
        else:
            ctx['relacionados'] = _productos_relacionados(self.object, ofertas)
        return ctx


@method_decorator(ensure_csrf_cookie, name='dispatch')
# Mismo motivo que en CatalogoHomeView: permitir same-origin para la vista
# previa en vivo del panel "Catálogo online" (tab "La tienda").
@method_decorator(xframe_options_sameorigin, name='dispatch')
class TiendaInstitucionalView(TemplateView):
    """
    Página institucional del catálogo (/la-tienda/) — la "página web" del
    negocio (historia, destacados, galería, horarios, ubicación, redes),
    separada a propósito del catálogo de productos: quien entra a comprar
    (la home) no ve nada de esto, pero está a un click vía el nav.
    """

    def get_template_names(self):
        # Mismo criterio que CatalogoHomeView/ProductoDetalleView: ?preview_plantilla=
        # fuerza una plantilla puntual para el preview en vivo de /catalogo-online/,
        # sin tocar la guardada.
        plantilla = self.request.GET.get('preview_plantilla')
        if plantilla not in PlantillaCatalogo.values:
            plantilla = ConfiguracionCatalogo.get_solo().plantilla
        if plantilla == PlantillaCatalogo.BENTO:
            return ['catalogo/plantillas/bento/institucional.html']
        if plantilla == PlantillaCatalogo.KINETIC:
            return ['catalogo/plantillas/kinetic/institucional.html']
        if plantilla == PlantillaCatalogo.LUMINA:
            return ['catalogo/plantillas/lumina/institucional.html']
        return ['catalogo/institucional.html']

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_ctx, ofertas = _contexto_base(self.request)
        ctx.update(base_ctx)
        empresa = base_ctx['empresa']
        config = base_ctx['config_catalogo']
        ctx['maps_url'] = google_maps_link(empresa.domicilio)
        ctx['galeria'] = config.galeria.exclude(imagen='')
        ctx['default_institucional_titulo'] = ConfiguracionCatalogo.DEFAULT_INSTITUCIONAL_TITULO
        ctx['default_institucional_bajada'] = ConfiguracionCatalogo.DEFAULT_INSTITUCIONAL_BAJADA
        ctx['default_destacado1_titulo'] = ConfiguracionCatalogo.DEFAULT_DESTACADO1_TITULO
        ctx['default_destacado1_texto'] = ConfiguracionCatalogo.DEFAULT_DESTACADO1_TEXTO
        ctx['default_destacado2_titulo'] = ConfiguracionCatalogo.DEFAULT_DESTACADO2_TITULO
        ctx['default_destacado2_texto'] = ConfiguracionCatalogo.DEFAULT_DESTACADO2_TEXTO
        ctx['default_destacado3_titulo'] = ConfiguracionCatalogo.DEFAULT_DESTACADO3_TITULO
        ctx['default_destacado3_texto'] = ConfiguracionCatalogo.DEFAULT_DESTACADO3_TEXTO
        # Cifras reales del negocio — exclusivas de la franja "por qué
        # elegirnos" de Almacén (ver institucional.html), pero se calculan
        # acá para todas las plantillas por si en el futuro alguna otra
        # las suma también.
        ctx['total_catalogo'] = _productos_publicados_base().filter(es_paquete=False).count()
        ctx['total_categorias'] = CategoriaProducto.objects.filter(
            productos__in=_productos_publicados_base()
        ).distinct().count()
        ctx['total_ofertas_activas'] = len(ofertas)
        return ctx
