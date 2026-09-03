from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from .models import (
    DatosEmpresa, ConfiguracionArca, AmbienteArca, ConfiguracionVentas,
    recalcular_scoring_pendientes,
)
from .permisos import chequear_permiso
from .services_estadisticas.ventas import resumen_ganancia

from caja.models import (
    CuentaCaja, TipoCaja, TipoCuenta, CUENTA_EFECTIVO_DEFAULT_NOMBRE, TurnoCaja,
    CuentaPredeterminadaMedio,
)
from compras.models import LoteCompra
from productos.models import CategoriaProducto, EstadoProducto, Moneda, Producto
from asistencia.models import CanalNotificacion, PreferenciaAsistencia
from asistencia.services.alertas import productos_por_vencer
from catalogo.models import (
    ConfiguracionCatalogo, PlantillaCatalogo, PosicionBanner,
    PosicionBannerBento, TipoTileDestacado,
)


class CustomLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('core:home')

class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('catalogo:home')

@login_required
def home(request):
    user = request.user
    hoy = timezone.localtime().date()

    # Scoring de clientes: la mora envejece sola sin que nadie toque la
    # ficha. Aprovechamos el paso por el inicio para poner al día, de a
    # tandas, los puntajes vencidos — igual que descartar_borradores_vencidos.
    # No hace falta una tarea programada aparte.
    recalcular_scoring_pendientes()

    permisos = {
        'ventas':       chequear_permiso(user, 'ver_ventas'),
        'compras':      chequear_permiso(user, 'ver_compras'),
        'productos':    chequear_permiso(user, 'ver_productos'),
        'proveedores':  chequear_permiso(user, 'ver_proveedores'),
        'stock':        chequear_permiso(user, 'ver_stock'),
        'caja':         chequear_permiso(user, 'ver_caja'),
        'clientes':     chequear_permiso(user, 'ver_clientes'),
        'usuarios':     chequear_permiso(user, 'ver_usuarios'),
    }

    ctx = {
        'fecha_actual': hoy,
        'permisos': permisos,
    }

    # ── KPIs de hoy (ventas) ────────────────────────────────────────
    if permisos['ventas']:
        ctx['kpi_ventas_hoy'] = resumen_ganancia(hoy, hoy)

    # ── Estado de la caja diaria ─────────────────────────────────────
    if permisos['caja']:
        ctx['turno_actual'] = TurnoCaja.turno_actual()

    # ── Alertas de stock / vencimientos ──────────────────────────────
    if permisos['productos'] or permisos['stock']:
        ctx['stock_bajo_count'] = Producto.objects.filter(
            gestiona_stock=True, stock_actual__gt=0,
            stock_actual__lte=F('stock_minimo'),
        ).count()
        ctx['lotes_vencidos_count'] = LoteCompra.objects.filter(
            activo=True, cantidad_actual__gt=0, fecha_vencimiento__lt=hoy,
        ).count()
        ctx['lotes_por_vencer_count'] = LoteCompra.objects.filter(
            activo=True, cantidad_actual__gt=0,
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=hoy + timezone.timedelta(days=30),
        ).count()

    # ── Pendientes operativos: vencimientos y stock bajo, SIN montos y
    # SIN deudas/cheques — eso es información financiera del negocio,
    # no algo que le corresponda a cualquier usuario con acceso a
    # productos/stock (a diferencia de la plata que se debe, esto es
    # mercadería: cualquiera que reponga o venda necesita saberlo).
    pendientes = []

    if permisos['productos'] or permisos['stock']:
        for lote in productos_por_vencer(30, hoy=hoy)['lotes'][:5]:
            pendientes.append({
                'icono': 'vencimiento',
                'titulo': lote['producto_nombre'],
                'detalle': f"Lote {lote['codigo']}",
                'dias_restantes': lote['dias_restantes'],
                'url': reverse('core:estadisticas_productos'),
            })

        productos_stock_bajo = Producto.objects.filter(
            gestiona_stock=True, stock_actual__gt=0,
            stock_actual__lte=F('stock_minimo'),
        ).order_by('stock_actual')[:5]
        for p in productos_stock_bajo:
            pendientes.append({
                'icono': 'stock',
                'titulo': p.nombre,
                'detalle': f"Quedan {p.stock_actual} (mínimo {p.stock_minimo})",
                'dias_restantes': None,
                'url': reverse('productos:stock'),
            })

    pendientes.sort(key=lambda p: -1 if p['dias_restantes'] is None else p['dias_restantes'])
    ctx['pendientes'] = pendientes[:6]
    ctx['pendientes_restantes'] = max(0, len(pendientes) - 6)

    return render(request, 'core/home.html', ctx)

@login_required
def mi_perfil(request):
    return render(request, 'core/mi_perfil.html')

@login_required
def configuracion(request):
    cuentas = (
        CuentaCaja.objects
        .filter(caja=TipoCaja.GRANDE)
        .exclude(nombre=CUENTA_EFECTIVO_DEFAULT_NOMBRE)
        .order_by('-activa', 'orden', 'nombre')
    )
    # Cuentas que pueden ser destino de un cobro (para el selector de
    # "cuenta por defecto por medio de pago"): activas, no tarjeta de
    # crédito propia. El efectivo ya quedó afuera por nombre.
    cuentas_para_cobro = [c for c in cuentas if c.activa and not c.es_credito]
    _predet = CuentaPredeterminadaMedio.como_dict()
    medios_predeterminables = [
        {'valor': v, 'label': l, 'cuenta_pk': _predet.get(v)}
        for v, l in CuentaPredeterminadaMedio.Medio.choices
    ]
    return render(request, 'core/configuracion.html', {
        'datos_empresa':        DatosEmpresa.get_solo(),
        'puede_editar_empresa': chequear_permiso(request.user, 'editar_empresa'),
        'cuentas':              cuentas,
        'cuentas_para_cobro':   cuentas_para_cobro,
        'medios_predeterminables': medios_predeterminables,
        'puede_editar_cuentas': chequear_permiso(request.user, 'editar_cuentas'),
        'monedas':              Moneda.choices,
        # 'gestionar_notificaciones' está en PERMISOS_RESTRINGIDOS: solo
        # un superusuario puede otorgarlo (ver filtrar_permisos_otorgables),
        # pero una vez otorgado a alguien —típicamente el dueño del
        # negocio— esa persona puede configurar esto sin ser superusuario.
        'puede_editar_asistencia': chequear_permiso(request.user, 'gestionar_notificaciones'),
        'preferencia_asistencia': PreferenciaAsistencia.get_solo(),
        'canales_notificacion':   CanalNotificacion.choices,
        'configuracion_arca':     ConfiguracionArca.get_solo(),
        'ambientes_arca':         AmbienteArca.choices,
        # Preferencias operativas de ventas — sección "Ventas". La gestiona
        # el dueño (mismo permiso que Datos de la empresa).
        'configuracion_ventas':   ConfiguracionVentas.get_solo(),
        'puede_editar_config_ventas': chequear_permiso(request.user, 'editar_empresa'),
    })


@login_required
def manual_usuario(request):
    return render(request, 'core/manual.html')


@login_required
def catalogo_online(request):
    """Pantalla dedicada al catálogo público — plantilla, textos y slides.
    Antes vivía como una sección más dentro de Configuración; se sacó a su
    propio ítem del menú para tener más espacio (ver core/templates/core/
    base.html) y una vista previa en vivo más grande."""
    productos_para_hero = (
        Producto.objects
        .filter(publicado=True, estado__in=[EstadoProducto.ACTIVO, EstadoProducto.AGOTADO])
        .order_by('es_paquete', 'nombre')
    )
    config_catalogo = ConfiguracionCatalogo.get_solo()
    # El color por default depende de la plantilla ACTIVA — si no, el
    # selector de color arranca mostrando naranja/navy (los de "almacen")
    # aunque el catálogo real esté en "bento"/"kinetic", y el preview en
    # vivo termina repintando mal apenas carga.
    defaults_color_por_plantilla = {
        PlantillaCatalogo.BENTO: (
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_BENTO,
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_BENTO,
        ),
        PlantillaCatalogo.KINETIC: (
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_KINETIC,
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_KINETIC,
        ),
        PlantillaCatalogo.LUMINA: (
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_LUMINA,
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_LUMINA,
        ),
        PlantillaCatalogo.EDITORIAL: (
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_EDITORIAL,
            ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_EDITORIAL,
        ),
    }
    default_color_marca_actual, default_color_marca_secundario_actual = defaults_color_por_plantilla.get(
        config_catalogo.plantilla,
        (ConfiguracionCatalogo.DEFAULT_COLOR_MARCA, ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO),
    )
    # Mismo criterio que arriba pero para el valor REAL guardado (no el
    # default) — cada plantilla tiene sus propios campos de color desde
    # ahora, así que el input tiene que arrancar mostrando el de la
    # plantilla activa, no siempre el de "almacen".
    valores_color_por_plantilla = {
        PlantillaCatalogo.BENTO: (config_catalogo.color_marca_bento, config_catalogo.color_marca_secundario_bento),
        PlantillaCatalogo.LUMINA: (config_catalogo.color_marca_lumina, config_catalogo.color_marca_secundario_lumina),
        PlantillaCatalogo.KINETIC: (config_catalogo.color_marca_kinetic, ''),
        PlantillaCatalogo.EDITORIAL: (
            config_catalogo.color_marca_editorial,
            config_catalogo.color_marca_secundario_editorial,
        ),
    }
    color_marca_actual, color_marca_secundario_actual = valores_color_por_plantilla.get(
        config_catalogo.plantilla,
        (config_catalogo.color_marca, config_catalogo.color_marca_secundario),
    )
    banners_almacen = config_catalogo.banners.all()
    grupos_banners_almacen = [
        {
            'codigo': PosicionBanner.DEBAJO_HERO,
            'titulo': 'Debajo del hero',
            'descripcion': 'Cartel ancho de apertura, antes de los accesos de categorías y marcas.',
            'banners': banners_almacen.filter(posicion=PosicionBanner.DEBAJO_HERO),
        },
        {
            'codigo': PosicionBanner.ANTES_GRILLA,
            'titulo': 'Arriba de los productos',
            'descripcion': 'Cartel integrado al sector de productos, junto a los filtros.',
            'banners': banners_almacen.filter(posicion=PosicionBanner.ANTES_GRILLA),
        },
        {
            'codigo': PosicionBanner.ANTES_DESTACADOS,
            'titulo': 'Antes de Destacados',
            'descripcion': 'Separador ancho previo a la vidriera de productos destacados.',
            'banners': banners_almacen.filter(posicion=PosicionBanner.ANTES_DESTACADOS),
        },
        {
            'codigo': PosicionBanner.ANTES_COMBOS,
            'titulo': 'Antes de Combos',
            'descripcion': 'Separador ancho previo a los combos armados.',
            'banners': banners_almacen.filter(posicion=PosicionBanner.ANTES_COMBOS),
        },
    ]
    tiles_almacen = config_catalogo.tiles_destacados.all()
    grupos_tiles_almacen = [
        {
            'codigo': TipoTileDestacado.CATEGORIA,
            'titulo': 'Categorías',
            'descripcion': 'Accesos visuales que aplican directamente el filtro de categoría.',
            'tiles': tiles_almacen.filter(tipo=TipoTileDestacado.CATEGORIA),
        },
        {
            'codigo': TipoTileDestacado.MARCA,
            'titulo': 'Marcas',
            'descripcion': 'Accesos visuales que filtran por el nombre de la marca.',
            'tiles': tiles_almacen.filter(tipo=TipoTileDestacado.MARCA),
        },
    ]
    banners_bento = config_catalogo.banners_bento.all()
    grupos_banners_bento = [
        {
            'codigo': 'novedades',
            'titulo': 'Novedades',
            'descripcion': 'Tarjetas apaisadas que se recorren en un rail debajo de las categorías.',
            'posicion_default': PosicionBannerBento.NOVEDADES,
            'banners': banners_bento.filter(posicion=PosicionBannerBento.NOVEDADES),
        },
        {
            'codigo': 'promos',
            'titulo': 'Promos del mes',
            'descripcion': 'Piezas verticales de la grilla promocional.',
            'posicion_default': PosicionBannerBento.PROMOS_MES,
            'banners': banners_bento.filter(posicion=PosicionBannerBento.PROMOS_MES),
        },
        {
            'codigo': 'franjas',
            'titulo': 'Franjas anchas',
            'descripcion': 'Banners horizontales que separan Destacados o Combos.',
            'posicion_default': PosicionBannerBento.ANTES_DESTACADOS,
            'banners': banners_bento.filter(posicion__in=[
                PosicionBannerBento.ANTES_DESTACADOS,
                PosicionBannerBento.ANTES_COMBOS,
            ]),
        },
    ]
    return render(request, 'core/catalogo_online.html', {
        'datos_empresa':          DatosEmpresa.get_solo(),
        'configuracion_catalogo': config_catalogo,
        'plantillas_catalogo':    PlantillaCatalogo.choices,
        'puede_editar_catalogo':  chequear_permiso(request.user, 'editar_catalogo'),
        'productos_para_hero':    productos_para_hero,
        'categorias_para_tiles':  CategoriaProducto.objects.filter(activo=True).order_by('orden', 'nombre'),
        'grupos_banners_almacen': grupos_banners_almacen,
        'grupos_tiles_almacen':   grupos_tiles_almacen,
        'grupos_banners_bento':   grupos_banners_bento,
        'default_hero_subtitulo': ConfiguracionCatalogo.DEFAULT_HERO_SUBTITULO,
        'default_sobre_nosotros': ConfiguracionCatalogo.DEFAULT_SOBRE_NOSOTROS,
        'default_color_marca':    ConfiguracionCatalogo.DEFAULT_COLOR_MARCA,
        'default_color_marca_secundario': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO,
        'default_color_marca_bento': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_BENTO,
        'default_color_marca_secundario_bento': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_BENTO,
        # Fondo — exclusivo de Bento, no cambia de valor según la plantilla
        # activa (a diferencia de color_marca_actual/etc. arriba), así que
        # va directo sin pasar por el mecanismo de resolución por plantilla.
        'default_color_fondo_bento': ConfiguracionCatalogo.DEFAULT_COLOR_FONDO_BENTO,
        'default_color_fondo_bento_oscuro': ConfiguracionCatalogo.DEFAULT_COLOR_FONDO_BENTO_OSCURO,
        'color_fondo_bento_actual': config_catalogo.color_fondo_bento,
        'color_fondo_bento_oscuro_actual': config_catalogo.color_fondo_bento_oscuro,
        'default_color_marca_kinetic': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_KINETIC,
        'default_color_marca_secundario_kinetic': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_KINETIC,
        # Fondo — exclusivo de Kinetic, mismo criterio que el de Bento arriba.
        'default_color_fondo_kinetic': ConfiguracionCatalogo.DEFAULT_COLOR_FONDO_KINETIC,
        'color_fondo_kinetic_actual': config_catalogo.color_fondo_kinetic,
        'default_kinetic_hero_stat1_titulo': ConfiguracionCatalogo.DEFAULT_KINETIC_HERO_STAT1_TITULO,
        'default_kinetic_hero_stat2_titulo': ConfiguracionCatalogo.DEFAULT_KINETIC_HERO_STAT2_TITULO,
        'default_kinetic_hero_stat2_valor': ConfiguracionCatalogo.DEFAULT_KINETIC_HERO_STAT2_VALOR,
        'default_kinetic_hero_stat3_titulo': ConfiguracionCatalogo.DEFAULT_KINETIC_HERO_STAT3_TITULO,
        'default_color_marca_lumina': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_LUMINA,
        'default_color_marca_secundario_lumina': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_LUMINA,
        'default_color_marca_editorial': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_EDITORIAL,
        'default_color_marca_secundario_editorial': ConfiguracionCatalogo.DEFAULT_COLOR_MARCA_SECUNDARIO_EDITORIAL,
        'default_color_marca_actual': default_color_marca_actual,
        'default_color_marca_secundario_actual': default_color_marca_secundario_actual,
        'color_marca_actual': color_marca_actual,
        'color_marca_secundario_actual': color_marca_secundario_actual,
        'default_nav_catalogo':   ConfiguracionCatalogo.DEFAULT_NAV_CATALOGO,
        'default_nav_ofertas':    ConfiguracionCatalogo.DEFAULT_NAV_OFERTAS,
        'default_nav_combos':     ConfiguracionCatalogo.DEFAULT_NAV_COMBOS,
        'default_nav_tienda':     ConfiguracionCatalogo.DEFAULT_NAV_TIENDA,
        'default_institucional_titulo': ConfiguracionCatalogo.DEFAULT_INSTITUCIONAL_TITULO,
        'default_institucional_bajada': ConfiguracionCatalogo.DEFAULT_INSTITUCIONAL_BAJADA,
        'default_destacado1_titulo': ConfiguracionCatalogo.DEFAULT_DESTACADO1_TITULO,
        'default_destacado1_texto':  ConfiguracionCatalogo.DEFAULT_DESTACADO1_TEXTO,
        'default_destacado2_titulo': ConfiguracionCatalogo.DEFAULT_DESTACADO2_TITULO,
        'default_destacado2_texto':  ConfiguracionCatalogo.DEFAULT_DESTACADO2_TEXTO,
        'default_destacado3_titulo': ConfiguracionCatalogo.DEFAULT_DESTACADO3_TITULO,
        'default_destacado3_texto':  ConfiguracionCatalogo.DEFAULT_DESTACADO3_TEXTO,
    })
