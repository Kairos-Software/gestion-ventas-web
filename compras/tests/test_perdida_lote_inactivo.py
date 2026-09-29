from decimal import Decimal

from django.test import TestCase

from compras.models import LoteCompra, registrar_perdida


class PerdidaDeLoteInactivoTests(TestCase):
    """Un lote inactivo es de una compra anulada: su stock ya salió del
    producto al anularla. Registrarle una pérdida lo descontaba otra vez."""

    def test_no_se_puede_registrar_perdida_de_un_lote_inactivo(self):
        lote = LoteCompra(codigo='LT-2026-00001', activo=False, cantidad_actual=Decimal('5'))
        with self.assertRaisesMessage(ValueError, 'ya no está activo'):
            registrar_perdida(lote=lote, cantidad=Decimal('2'), motivo='rotura')
