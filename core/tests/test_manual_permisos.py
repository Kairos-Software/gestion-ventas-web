from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core import views


def _render(**permitidos):
    """Renderiza el manual con un `ver` donde todo es False salvo lo pasado."""
    ver = defaultdict(bool, permitidos)
    return render_to_string('core/manual.html', {'ver': ver})


class ManualSegunPermisosTests(SimpleTestCase):
    def test_sin_permisos_no_manda_secciones_de_pantallas_ajenas(self):
        html = _render()
        for seccion in ('usuarios', 'ventas', 'compras', 'caja', 'deudas', 'cobros',
                        'cheques', 'estadisticas', 'celulares', 'recomendaciones'):
            self.assertNotIn(f'id="seccion-{seccion}"', html, seccion)
            # Ni su entrada en el índice. (Las menciones dentro del texto de
            # otras secciones las convierte en texto plano manual.js.)
            self.assertNotIn(f'href="#seccion-{seccion}"><svg', html, seccion)
        # Lo que cualquiera puede usar sigue estando.
        for seccion in ('primeros-pasos', 'configuracion', 'mi-perfil', 'herramientas'):
            self.assertIn(f'id="seccion-{seccion}"', html, seccion)

    def test_cajero_ve_la_caja_pero_no_como_reabrir_un_turno(self):
        html = _render(caja=True, caja_turno=True, caja_seccion=True, finanzas=True)
        self.assertIn('id="seccion-caja"', html)
        self.assertIn('<h3>Abrir el turno</h3>', html)
        self.assertNotIn('Reabrir un turno cerrado', html)
        self.assertNotIn('id="seccion-caja-ingresos-egresos"', html)
        # La tabla del menú lista solo sus pantallas de Finanzas.
        self.assertNotIn('Resúmenes de tarjeta', html)

    def test_quien_solo_ve_usuarios_no_ve_como_administrarlos(self):
        html = _render(usuarios=True, personas=True)
        self.assertIn('id="seccion-usuarios"', html)
        self.assertIn('<h3>La lista del personal</h3>', html)
        for h3 in ('Dar de alta a un empleado', 'Corregir datos o quitarle el acceso a alguien',
                   'Ajustar los permisos de una persona', 'Perfiles de permisos'):
            self.assertNotIn(f'<h3>{h3}</h3>', html, h3)
        self.assertNotIn('<span class="manual-ui">Eliminar</span> le quita', html)

    def test_quien_solo_ve_clientes_no_ve_como_cargarlos_ni_eliminarlos(self):
        html = _render(clientes=True, personas=True)
        self.assertIn('<h3>La lista de clientes</h3>', html)
        self.assertIn('<h3>Scoring: qué tan bien paga</h3>', html)
        self.assertNotIn('<h3>Cargar o corregir un cliente</h3>', html)
        self.assertNotIn('<h3>Eliminar un cliente</h3>', html)
        self.assertNotIn('Ajustar manualmente</strong>', html)

    def test_quien_solo_ve_productos_y_stock_no_ve_como_modificarlos(self):
        html = _render(productos=True, stock=True, catalogo=True)
        for h3 in ('La lista de productos', 'Stock: cuánto tenés de cada cosa',
                   'Historial de un producto: de dónde salió cada unidad'):
            self.assertIn(f'<h3>{h3}</h3>', html, h3)
        for h3 in ('Cargar un producto', 'Precios: manual o automático', 'Eliminar un producto',
                   'Corregir el stock a mano', 'Cargar o actualizar muchos productos con Excel'):
            self.assertNotIn(f'<h3>{h3}</h3>', html, h3)

    def test_quien_solo_maneja_ofertas_no_ve_paquetes_ni_productos(self):
        html = _render(ofertas=True, catalogo=True)
        for h3 in ('Ofertas y promociones', 'Crear una oferta', 'Cómo se aplican al vender'):
            self.assertIn(f'<h3>{h3}</h3>', html, h3)
        for h3 in ('Paquetes y combos', 'La lista de productos', 'Stock: cuánto tenés de cada cosa'):
            self.assertNotIn(f'<h3>{h3}</h3>', html, h3)
        # Sin Productos ni Stock, el "Dónde está" de arriba quedaría vacío.
        self.assertNotIn('<span class="manual-enum-lista"></span>', html)

    def test_quien_solo_ve_proveedores_no_ve_como_cargarlos_ni_eliminarlos(self):
        html = _render(proveedores=True, catalogo=True)
        self.assertIn('<h3>Proveedores</h3>', html)
        self.assertNotIn('<h3>Cargar un proveedor</h3>', html)
        self.assertNotIn('<h3>Eliminar un proveedor</h3>', html)
        self.assertNotIn('+ Nuevo proveedor.', html)

    def test_inventario_sin_ajustar_stock_no_explica_como_registrar_perdidas(self):
        html = _render(compras_crear=True, catalogo=True)
        self.assertIn('<h3>Inventario: lotes y vencimientos</h3>', html)
        self.assertIn('<h3>Fraccionar: armar paquetes con mercadería a granel</h3>', html)
        self.assertNotIn('<h3>Registrar una pérdida</h3>', html)
        self.assertNotIn('id="hs-inv-9"', html)

    def test_quien_solo_ve_pedidos_tiene_la_seccion_catalogo_con_pedidos(self):
        user = SimpleNamespace(is_superuser=False)
        with patch.object(views, 'chequear_permiso', side_effect=lambda u, c: c == 'ver_pedidos'):
            ver = views._secciones_manual_visibles(user)
        self.assertTrue(ver['catalogo'])
        html = _render(pedidos=True, catalogo=True)
        self.assertIn('id="seccion-catalogo"', html)
        self.assertIn('<h3>Pedidos que llegan del catálogo</h3>', html)
        self.assertNotIn('<h3>Catálogo online: la página que ven tus clientes</h3>', html)

    def test_herramientas_sin_permisos_no_explica_anotador_ni_factura_inicial(self):
        html = _render()
        self.assertIn('<h3>Contador de billetes y calculadora de vuelto</h3>', html)
        self.assertNotIn('<h3>Anotador</h3>', html)
        self.assertNotIn('Factura inicial: el stock', html)

    def test_con_todo_habilitado_no_falta_ninguna_seccion(self):
        html = render_to_string('core/manual.html', {'ver': defaultdict(lambda: True)})
        self.assertEqual(html.count('<section class="manual-section"'), 19)

    def test_superusuario_ve_todo(self):
        user = SimpleNamespace(is_superuser=True)
        with patch.object(views, 'chequear_permiso', return_value=True):
            ver = views._secciones_manual_visibles(user)
        self.assertTrue(all(ver.values()))

    def test_sin_ningun_permiso_todo_en_falso(self):
        user = SimpleNamespace(is_superuser=False)
        with patch.object(views, 'chequear_permiso', return_value=False):
            ver = views._secciones_manual_visibles(user)
        self.assertFalse(any(ver.values()))
