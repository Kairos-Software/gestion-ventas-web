from decimal import Decimal

from django.test import TestCase

from productos.models import (
    CombinacionVariante, CombinacionVarianteOpcion, OpcionVariante, Producto, Variante,
)


class CombinacionVarianteStrTests(TestCase):
    def test_str_muestra_las_opciones_sin_romper(self):
        remera = Producto.objects.create(nombre='Remera', precio_venta=Decimal('9000'),
                                         gestiona_variantes=True)
        color = Variante.objects.create(nombre='Color')
        rojo = OpcionVariante.objects.create(variante=color, nombre='Rojo')
        comb = CombinacionVariante.objects.create(producto=remera)
        CombinacionVarianteOpcion.objects.create(combinacion=comb, opcion=rojo)
        comb.descripcion_combinacion = ''
        self.assertEqual(str(comb), f'{remera.codigo} — Color: Rojo')
