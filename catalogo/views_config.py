import os
import json
import re

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views import View
from django.http import JsonResponse

from core.permisos import chequear_permiso
from productos.models import CategoriaProducto

from .models import (
    BannerCatalogo, ConfiguracionCatalogo, ImagenInstitucional, PlantillaCatalogo,
    PosicionBanner, SlideHeroCatalogo, TileDestacadoCatalogo, TipoTileDestacado,
)
from .views import _productos_publicados_base

EXTENSIONES_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_SLIDES = 6
MAX_GALERIA = 8
MAX_BANNERS = 6
MAX_TILES = 16


class CatalogoConfigGuardarAjax(LoginRequiredMixin, View):
    """POST JSON con los textos y la plantilla del catálogo público (crea o actualiza el único registro)."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        plantilla = body.get('plantilla') or PlantillaCatalogo.ALMACEN
        if plantilla not in PlantillaCatalogo.values:
            return JsonResponse({'error': 'Plantilla inválida.'}, status=400)

        color_marca = (body.get('color_marca') or '').strip()
        if color_marca and not re.fullmatch(r'#[0-9a-fA-F]{6}', color_marca):
            return JsonResponse({'error': 'Color de marca inválido.'}, status=400)

        color_marca_secundario = (body.get('color_marca_secundario') or '').strip()
        if color_marca_secundario and not re.fullmatch(r'#[0-9a-fA-F]{6}', color_marca_secundario):
            return JsonResponse({'error': 'Color secundario inválido.'}, status=400)

        colores_por_plantilla = {}
        for campo in (
            'color_marca_bento', 'color_marca_secundario_bento',
            'color_marca_lumina', 'color_marca_secundario_lumina',
            'color_fondo_bento', 'color_fondo_bento_oscuro',
        ):
            valor = (body.get(campo) or '').strip()
            if valor and not re.fullmatch(r'#[0-9a-fA-F]{6}', valor):
                return JsonResponse({'error': 'Color inválido.'}, status=400)
            colores_por_plantilla[campo] = valor

        hero_producto_id = body.get('hero_producto') or None
        hero_producto = None
        if hero_producto_id:
            hero_producto = _productos_publicados_base().filter(pk=hero_producto_id).first()
            if not hero_producto:
                return JsonResponse({'error': 'Producto de hero inválido.'}, status=400)

        hero_spot2_producto_id = body.get('hero_spot2_producto') or None
        hero_spot2_producto = None
        if hero_spot2_producto_id:
            hero_spot2_producto = _productos_publicados_base().filter(pk=hero_spot2_producto_id).first()
            if not hero_spot2_producto:
                return JsonResponse({'error': 'Producto de la tarjeta 2 del hero inválido.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        config.plantilla          = plantilla
        config.hero_titulo        = (body.get('hero_titulo') or '').strip()
        config.hero_subtitulo     = (body.get('hero_subtitulo') or '').strip()
        config.hero_producto      = hero_producto
        config.hero_imagen_sin_fondo = bool(body.get('hero_imagen_sin_fondo'))
        config.tiles_destacados_titulo = (body.get('tiles_destacados_titulo') or '').strip()
        config.hero_spot2_producto = hero_spot2_producto
        config.sobre_nosotros     = (body.get('sobre_nosotros') or '').strip()
        config.contacto_texto     = (body.get('contacto_texto') or '').strip()
        config.color_marca        = color_marca
        config.color_marca_secundario = color_marca_secundario
        config.color_marca_bento              = colores_por_plantilla['color_marca_bento']
        config.color_marca_secundario_bento   = colores_por_plantilla['color_marca_secundario_bento']
        config.color_marca_lumina             = colores_por_plantilla['color_marca_lumina']
        config.color_marca_secundario_lumina  = colores_por_plantilla['color_marca_secundario_lumina']
        config.color_fondo_bento              = colores_por_plantilla['color_fondo_bento']
        config.color_fondo_bento_oscuro       = colores_por_plantilla['color_fondo_bento_oscuro']
        config.nav_catalogo_label = (body.get('nav_catalogo_label') or '').strip()[:30]
        config.nav_ofertas_label  = (body.get('nav_ofertas_label') or '').strip()[:30]
        config.nav_combos_label   = (body.get('nav_combos_label') or '').strip()[:30]
        config.nav_tienda_label   = (body.get('nav_tienda_label') or '').strip()[:30]

        config.institucional_titulo = (body.get('institucional_titulo') or '').strip()
        config.institucional_bajada = (body.get('institucional_bajada') or '').strip()
        config.destacado1_titulo = (body.get('destacado1_titulo') or '').strip()[:80]
        config.destacado1_texto  = (body.get('destacado1_texto') or '').strip()[:200]
        config.destacado2_titulo = (body.get('destacado2_titulo') or '').strip()[:80]
        config.destacado2_texto  = (body.get('destacado2_texto') or '').strip()[:200]
        config.destacado3_titulo = (body.get('destacado3_titulo') or '').strip()[:80]
        config.destacado3_texto  = (body.get('destacado3_texto') or '').strip()[:200]
        config.horarios_texto = (body.get('horarios_texto') or '').strip()
        config.instagram_url  = (body.get('instagram_url') or '').strip()[:200]
        config.facebook_url   = (body.get('facebook_url') or '').strip()[:200]
        config.tiktok_url     = (body.get('tiktok_url') or '').strip()[:200]
        config.save()

        return JsonResponse({'ok': True})


class CatalogoConfigHeroImagenAjax(LoginRequiredMixin, View):
    """POST (FormData, campo 'imagen') = subir/reemplazar la imagen del hero. DELETE = quitarla."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.hero_imagen = archivo
        config.save(update_fields=['hero_imagen'])
        return JsonResponse({'ok': True, 'imagen_url': config.hero_imagen.url})

    def delete(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.hero_imagen = None
        config.save(update_fields=['hero_imagen'])
        return JsonResponse({'ok': True})

    def _borrar_archivo_actual(self, config):
        if config.hero_imagen and os.path.isfile(config.hero_imagen.path):
            os.remove(config.hero_imagen.path)


class CatalogoConfigHeroSpot1ImagenAjax(LoginRequiredMixin, View):
    """POST (FormData, campo 'imagen') = subir/reemplazar la imagen de la tarjeta 1 del hero (Bento). DELETE = quitarla."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.hero_spot1_imagen = archivo
        config.save(update_fields=['hero_spot1_imagen'])
        return JsonResponse({'ok': True, 'imagen_url': config.hero_spot1_imagen.url})

    def delete(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.hero_spot1_imagen = None
        config.save(update_fields=['hero_spot1_imagen'])
        return JsonResponse({'ok': True})

    def _borrar_archivo_actual(self, config):
        if config.hero_spot1_imagen and os.path.isfile(config.hero_spot1_imagen.path):
            os.remove(config.hero_spot1_imagen.path)


class CatalogoConfigHeroSpot2ImagenAjax(LoginRequiredMixin, View):
    """POST (FormData, campo 'imagen') = subir/reemplazar la imagen de la tarjeta 2 del hero (Bento). DELETE = quitarla."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.hero_spot2_imagen = archivo
        config.save(update_fields=['hero_spot2_imagen'])
        return JsonResponse({'ok': True, 'imagen_url': config.hero_spot2_imagen.url})

    def delete(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.hero_spot2_imagen = None
        config.save(update_fields=['hero_spot2_imagen'])
        return JsonResponse({'ok': True})

    def _borrar_archivo_actual(self, config):
        if config.hero_spot2_imagen and os.path.isfile(config.hero_spot2_imagen.path):
            os.remove(config.hero_spot2_imagen.path)


class CatalogoKineticHeroFondoAjax(LoginRequiredMixin, View):
    """POST (FormData, campo 'imagen') = subir/reemplazar el fondo del hero de "Kinetic". DELETE = quitarlo."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.kinetic_hero_fondo = archivo
        config.save(update_fields=['kinetic_hero_fondo'])
        return JsonResponse({'ok': True, 'imagen_url': config.kinetic_hero_fondo.url})

    def delete(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.kinetic_hero_fondo = None
        config.save(update_fields=['kinetic_hero_fondo'])
        return JsonResponse({'ok': True})

    def _borrar_archivo_actual(self, config):
        if config.kinetic_hero_fondo and os.path.isfile(config.kinetic_hero_fondo.path):
            os.remove(config.kinetic_hero_fondo.path)


class CatalogoInstitucionalImagenAjax(LoginRequiredMixin, View):
    """POST (FormData, campo 'imagen') = subir/reemplazar la portada de /la-tienda/. DELETE = quitarla."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.institucional_imagen = archivo
        config.save(update_fields=['institucional_imagen'])
        return JsonResponse({'ok': True, 'imagen_url': config.institucional_imagen.url})

    def delete(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        config = ConfiguracionCatalogo.get_solo()
        self._borrar_archivo_actual(config)
        config.institucional_imagen = None
        config.save(update_fields=['institucional_imagen'])
        return JsonResponse({'ok': True})

    def _borrar_archivo_actual(self, config):
        if config.institucional_imagen and os.path.isfile(config.institucional_imagen.path):
            os.remove(config.institucional_imagen.path)


class CatalogoSlideGuardarAjax(LoginRequiredMixin, View):
    """
    POST JSON con los textos de un slide del carrusel (plantilla "bento").
    Sin 'pk' = crea uno nuevo (hasta MAX_SLIDES). Con 'pk' = actualiza.
    La imagen se sube después, en un segundo paso, contra
    CatalogoSlideImagenAjax — recién ahí existe un pk al que asociarla.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        titulo = (body.get('titulo') or '').strip()
        if not titulo:
            return JsonResponse({'error': 'El título es obligatorio.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        pk = body.get('pk')
        if pk:
            slide = get_object_or_404(SlideHeroCatalogo, pk=pk, configuracion=config)
        else:
            if config.slides.count() >= MAX_SLIDES:
                return JsonResponse({'error': f'Máximo {MAX_SLIDES} slides.'}, status=400)
            slide = SlideHeroCatalogo(configuracion=config)

        slide.eyebrow     = (body.get('eyebrow') or '').strip()
        slide.titulo      = titulo
        slide.descripcion = (body.get('descripcion') or '').strip()
        slide.cta_texto   = (body.get('cta_texto') or '').strip() or 'Ver catálogo completo'
        slide.save()

        return JsonResponse({'ok': True, 'pk': slide.pk})


class CatalogoSlideImagenAjax(LoginRequiredMixin, View):
    """POST (FormData, campos 'pk' + 'imagen') = subir/reemplazar la imagen de un slide ya creado."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.POST.get('pk')
        slide = get_object_or_404(SlideHeroCatalogo, pk=pk, configuracion=ConfiguracionCatalogo.get_solo())

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        if slide.imagen and os.path.isfile(slide.imagen.path):
            os.remove(slide.imagen.path)
        slide.imagen = archivo
        slide.save(update_fields=['imagen'])
        return JsonResponse({'ok': True, 'imagen_url': slide.imagen.url})


class CatalogoSlideEliminarAjax(LoginRequiredMixin, View):
    """POST JSON {'pk': ...} — borra un slide y su imagen. Borrado físico simple: a
    diferencia de CuentaCaja, un slide no tiene ninguna relación downstream."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        slide = get_object_or_404(
            SlideHeroCatalogo, pk=body.get('pk'), configuracion=ConfiguracionCatalogo.get_solo(),
        )
        if slide.imagen and os.path.isfile(slide.imagen.path):
            os.remove(slide.imagen.path)
        slide.delete()
        return JsonResponse({'ok': True})


class CatalogoBannerGuardarAjax(LoginRequiredMixin, View):
    """
    POST JSON con los textos de un banner promocional (opcional, hasta
    MAX_BANNERS). Sin 'pk' = crea uno nuevo. Con 'pk' = actualiza. La
    imagen (opcional) se sube después, en un segundo paso, contra
    CatalogoBannerImagenAjax — mismo patrón que los slides.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        titulo = (body.get('titulo') or '').strip()
        if not titulo:
            return JsonResponse({'error': 'El título es obligatorio.'}, status=400)

        posicion = body.get('posicion') or PosicionBanner.DEBAJO_HERO
        if posicion not in PosicionBanner.values:
            return JsonResponse({'error': 'Ubicación inválida.'}, status=400)

        color_fondo = (body.get('color_fondo') or '').strip()
        if color_fondo and not re.fullmatch(r'#[0-9a-fA-F]{6}', color_fondo):
            return JsonResponse({'error': 'Color de fondo inválido.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        pk = body.get('pk')
        if pk:
            banner = get_object_or_404(BannerCatalogo, pk=pk, configuracion=config)
        else:
            if config.banners.count() >= MAX_BANNERS:
                return JsonResponse({'error': f'Máximo {MAX_BANNERS} banners.'}, status=400)
            banner = BannerCatalogo(configuracion=config)

        banner.titulo      = titulo
        banner.texto       = (body.get('texto') or '').strip()
        banner.posicion    = posicion
        banner.color_fondo = color_fondo
        banner.cta_texto   = (body.get('cta_texto') or '').strip()
        banner.cta_url     = (body.get('cta_url') or '').strip()
        banner.activo      = bool(body.get('activo', True))
        banner.save()

        return JsonResponse({'ok': True, 'pk': banner.pk})


class CatalogoBannerImagenAjax(LoginRequiredMixin, View):
    """POST (FormData, campos 'pk' + 'imagen') = subir/reemplazar la imagen de un banner ya creado."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.POST.get('pk')
        banner = get_object_or_404(BannerCatalogo, pk=pk, configuracion=ConfiguracionCatalogo.get_solo())

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        if banner.imagen and os.path.isfile(banner.imagen.path):
            os.remove(banner.imagen.path)
        banner.imagen = archivo
        banner.save(update_fields=['imagen'])
        return JsonResponse({'ok': True, 'imagen_url': banner.imagen.url})

    def delete(self, request):
        """Quitar la imagen sin borrar el banner — vuelve a mostrarse como bloque de color sólido."""
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        banner = get_object_or_404(BannerCatalogo, pk=body.get('pk'), configuracion=ConfiguracionCatalogo.get_solo())
        if banner.imagen and os.path.isfile(banner.imagen.path):
            os.remove(banner.imagen.path)
        banner.imagen = None
        banner.save(update_fields=['imagen'])
        return JsonResponse({'ok': True})


class CatalogoBannerEliminarAjax(LoginRequiredMixin, View):
    """POST JSON {'pk': ...} — borra un banner y su imagen."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        banner = get_object_or_404(
            BannerCatalogo, pk=body.get('pk'), configuracion=ConfiguracionCatalogo.get_solo(),
        )
        if banner.imagen and os.path.isfile(banner.imagen.path):
            os.remove(banner.imagen.path)
        banner.delete()
        return JsonResponse({'ok': True})


class CatalogoTileGuardarAjax(LoginRequiredMixin, View):
    """
    POST JSON con los datos de un tile de categoría/marca destacada
    (plantilla "almacen"). Sin 'pk' = crea uno nuevo (hasta MAX_TILES).
    Con 'pk' = actualiza. La imagen se sube después, en un segundo paso,
    contra CatalogoTileImagenAjax — mismo patrón que los slides.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        tipo = body.get('tipo') or TipoTileDestacado.CATEGORIA
        if tipo not in TipoTileDestacado.values:
            return JsonResponse({'error': 'Tipo inválido.'}, status=400)

        categoria = None
        marca = ''
        if tipo == TipoTileDestacado.CATEGORIA:
            categoria_id = body.get('categoria') or None
            if not categoria_id:
                return JsonResponse({'error': 'Elegí una categoría.'}, status=400)
            categoria = CategoriaProducto.objects.filter(pk=categoria_id).first()
            if not categoria:
                return JsonResponse({'error': 'Categoría inválida.'}, status=400)
        else:
            marca = (body.get('marca') or '').strip()
            if not marca:
                return JsonResponse({'error': 'Escribí una marca.'}, status=400)

        config = ConfiguracionCatalogo.get_solo()
        pk = body.get('pk')
        if pk:
            tile = get_object_or_404(TileDestacadoCatalogo, pk=pk, configuracion=config)
        else:
            if config.tiles_destacados.count() >= MAX_TILES:
                return JsonResponse({'error': f'Máximo {MAX_TILES} categorías/marcas destacadas.'}, status=400)
            tile = TileDestacadoCatalogo(configuracion=config)

        tile.tipo      = tipo
        tile.categoria = categoria
        tile.marca     = marca
        tile.etiqueta  = (body.get('etiqueta') or '').strip()
        tile.activo    = bool(body.get('activo', True))
        tile.save()

        return JsonResponse({'ok': True, 'pk': tile.pk})


class CatalogoTileImagenAjax(LoginRequiredMixin, View):
    """POST (FormData, campos 'pk' + 'imagen') = subir/reemplazar la imagen de un tile ya creado."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.POST.get('pk')
        tile = get_object_or_404(TileDestacadoCatalogo, pk=pk, configuracion=ConfiguracionCatalogo.get_solo())

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        if tile.imagen and os.path.isfile(tile.imagen.path):
            os.remove(tile.imagen.path)
        tile.imagen = archivo
        tile.save(update_fields=['imagen'])
        return JsonResponse({'ok': True, 'imagen_url': tile.imagen.url})


class CatalogoTileEliminarAjax(LoginRequiredMixin, View):
    """POST JSON {'pk': ...} — borra un tile y su imagen."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        tile = get_object_or_404(
            TileDestacadoCatalogo, pk=body.get('pk'), configuracion=ConfiguracionCatalogo.get_solo(),
        )
        if tile.imagen and os.path.isfile(tile.imagen.path):
            os.remove(tile.imagen.path)
        tile.delete()
        return JsonResponse({'ok': True})


class CatalogoGaleriaImagenAjax(LoginRequiredMixin, View):
    """
    POST (FormData: 'imagen' + 'titulo' opcional) = agrega una foto nueva
    a la galería de /la-tienda/. A diferencia de los slides, no hace falta
    un paso previo para crear la fila — acá no hay ningún campo de texto
    obligatorio, así que foto y caption se cargan juntos en un solo paso.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        config = ConfiguracionCatalogo.get_solo()
        if config.galeria.count() >= MAX_GALERIA:
            return JsonResponse({'error': f'Máximo {MAX_GALERIA} fotos.'}, status=400)

        archivo = request.FILES.get('imagen')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        imagen = ImagenInstitucional.objects.create(
            configuracion=config, titulo=(request.POST.get('titulo') or '').strip()[:100],
        )
        imagen.imagen = archivo
        imagen.save(update_fields=['imagen'])
        return JsonResponse({'ok': True, 'pk': imagen.pk, 'imagen_url': imagen.imagen.url})


class CatalogoGaleriaEliminarAjax(LoginRequiredMixin, View):
    """POST JSON {'pk': ...} — borra una foto de la galería y su archivo."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_catalogo'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        imagen = get_object_or_404(
            ImagenInstitucional, pk=body.get('pk'), configuracion=ConfiguracionCatalogo.get_solo(),
        )
        if imagen.imagen and os.path.isfile(imagen.imagen.path):
            os.remove(imagen.imagen.path)
        imagen.delete()
        return JsonResponse({'ok': True})
