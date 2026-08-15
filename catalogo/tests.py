import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from productos.models import CategoriaProducto

from .models import BannerCatalogo, ConfiguracionCatalogo, GondolaAlmacenCatalogo, TileDestacadoCatalogo
from .views_config import (
    CatalogoBannerGuardarAjax,
    CatalogoGondolaAlmacenEliminarAjax,
    CatalogoGondolaAlmacenGuardarAjax,
    CatalogoTileGuardarAjax,
)


class GondolaAlmacenConfigTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True)
        self.config = ConfiguracionCatalogo.get_solo()

    def _post(self, view, body):
        request = self.factory.post(
            '/catalogo/config/gondolas-almacen/',
            data=json.dumps(body),
            content_type='application/json',
        )
        request.user = self.user
        with patch('catalogo.views_config.chequear_permiso', return_value=True):
            return view.as_view()(request)

    def test_crea_y_edita_una_gondola(self):
        categoria = CategoriaProducto.objects.create(nombre='Limpieza')
        response = self._post(CatalogoGondolaAlmacenGuardarAjax, {
            'categoria': categoria.pk,
            'titulo': 'Todo para tu casa',
            'subtitulo': 'Reposición semanal',
        })
        self.assertEqual(response.status_code, 200)
        gondola = GondolaAlmacenCatalogo.objects.get()
        self.assertEqual(gondola.titulo, 'Todo para tu casa')

        response = self._post(CatalogoGondolaAlmacenGuardarAjax, {
            'pk': gondola.pk,
            'categoria': categoria.pk,
            'titulo': 'Limpieza del hogar',
        })
        self.assertEqual(response.status_code, 200)
        gondola.refresh_from_db()
        self.assertEqual(gondola.titulo, 'Limpieza del hogar')

    def test_impide_repetir_categoria_y_superar_tres_gondolas(self):
        categorias = [CategoriaProducto.objects.create(nombre=f'Categoría {i}') for i in range(4)]
        for categoria in categorias[:3]:
            response = self._post(CatalogoGondolaAlmacenGuardarAjax, {'categoria': categoria.pk})
            self.assertEqual(response.status_code, 200)

        repetida = self._post(CatalogoGondolaAlmacenGuardarAjax, {'categoria': categorias[0].pk})
        self.assertEqual(repetida.status_code, 400)
        excedida = self._post(CatalogoGondolaAlmacenGuardarAjax, {'categoria': categorias[3].pk})
        self.assertEqual(excedida.status_code, 400)

    def test_elimina_solo_la_gondola(self):
        categoria = CategoriaProducto.objects.create(nombre='Bebidas')
        gondola = GondolaAlmacenCatalogo.objects.create(
            configuracion=self.config,
            categoria=categoria,
        )
        response = self._post(CatalogoGondolaAlmacenEliminarAjax, {'pk': gondola.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(GondolaAlmacenCatalogo.objects.exists())
        self.assertTrue(CategoriaProducto.objects.filter(pk=categoria.pk).exists())

    def test_categoria_y_marca_no_cambian_de_tipo_al_editarlas(self):
        categoria = CategoriaProducto.objects.create(nombre='Instrumentos')
        tile = TileDestacadoCatalogo.objects.create(
            configuracion=self.config,
            tipo='categoria',
            categoria=categoria,
        )

        response = self._post(CatalogoTileGuardarAjax, {
            'pk': tile.pk,
            'tipo': 'marca',
            'categoria': categoria.pk,
            'marca': 'Marca que debe ignorarse',
            'etiqueta': 'Instrumentos destacados',
        })

        self.assertEqual(response.status_code, 200)
        tile.refresh_from_db()
        self.assertEqual(tile.tipo, 'categoria')
        self.assertEqual(tile.categoria, categoria)
        self.assertEqual(tile.marca, '')

    def test_banner_no_cambia_de_ubicacion_al_editarlo(self):
        banner = BannerCatalogo.objects.create(
            configuracion=self.config,
            posicion='antes_destacados',
            titulo='Oferta semanal',
        )

        response = self._post(CatalogoBannerGuardarAjax, {
            'pk': banner.pk,
            'posicion': 'debajo_hero',
            'titulo': 'Oferta actualizada',
        })

        self.assertEqual(response.status_code, 200)
        banner.refresh_from_db()
        self.assertEqual(banner.posicion, 'antes_destacados')
        self.assertEqual(banner.titulo, 'Oferta actualizada')
