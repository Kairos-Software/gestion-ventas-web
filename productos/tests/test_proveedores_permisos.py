from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos import views_proveedores
from productos.models import Proveedor


class BotonesSegunPermisoTests(TestCase):
    """La vista calculaba puede_crear/editar/eliminar pero la plantilla no
    los usaba: quien solo podía ver proveedores veía los botones de crear,
    editar y eliminar, y al usarlos el guardado fallaba sin ningún aviso."""

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('ana', password='x'))
        Proveedor.objects.create(nombre='Distribuidora del Norte')

    def _pagina(self, *permisos):
        with patch.object(views_proveedores, 'chequear_permiso', lambda u, p: p in permisos):
            return self.client.get(reverse('productos:gestion_proveedores')).content.decode()

    def test_solo_ver_no_muestra_crear_editar_ni_eliminar(self):
        html = self._pagina('ver_proveedores')
        self.assertIn('Distribuidora del Norte', html)
        self.assertNotIn('id="btn-nuevo-proveedor"', html)
        self.assertNotIn('btn-editar', html)
        self.assertNotIn('btn-eliminar', html)

    def test_con_todos_los_permisos_muestra_los_botones(self):
        html = self._pagina('ver_proveedores', 'crear_proveedores', 'editar_proveedores',
                            'eliminar_proveedores')
        self.assertIn('id="btn-nuevo-proveedor"', html)
        self.assertIn('btn-editar', html)
        self.assertIn('btn-eliminar', html)
