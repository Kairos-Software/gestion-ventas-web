import os
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views import View
from django.http import JsonResponse

from core.permisos import chequear_permiso

from .models import ConfiguracionCatalogo, PlantillaCatalogo, SlideHeroCatalogo

EXTENSIONES_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_SLIDES = 6


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

        config = ConfiguracionCatalogo.get_solo()
        config.plantilla       = plantilla
        config.hero_titulo     = (body.get('hero_titulo') or '').strip()
        config.hero_subtitulo  = (body.get('hero_subtitulo') or '').strip()
        config.sobre_nosotros  = (body.get('sobre_nosotros') or '').strip()
        config.contacto_texto  = (body.get('contacto_texto') or '').strip()
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
