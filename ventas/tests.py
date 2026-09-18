"""
ventas/tests.py

Primer módulo de tests automatizados de este app — hasta ahora todo lo
relacionado a ARCA/devoluciones se probó a mano contra la base `claude-test`
(ver memoria de sesiones previas). Se enfoca en emitir_nota_credito() (Nota
de Crédito ARCA al registrar una devolución) y su integración en
RegistrarDevolucionAjax.

Mock necesario: core.services_arca.wsfe._post es el único punto que hace la
llamada HTTP real de WSFE — todo lo demás parsea texto con regex. Para no
depender de un segundo mock (WSAA), precargamos el cache de token
directamente en ConfiguracionArca (wsaa_token/wsaa_sign/wsaa_expira, ver
core/services_arca/wsaa.py:154-161) — así obtener_token() nunca intenta
pedir uno nuevo por red. 100% offline: no requiere ARCA_ENCRYPTION_KEY ni
certificado real (tiene_certificado() solo chequea que los campos no estén
vacíos, no los descifra).
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.utils import timezone

from core.models import AmbienteArca, CondicionIVA, ConfiguracionArca, DatosEmpresa, Usuario
from core.services_arca import facturacion, wsfe
from core.services_arca.tipos import CondicionIvaReceptor, DOC_TIPO_CONSUMIDOR_FINAL, DOC_TIPO_CUIT
from core.services_arca.wsaa import ArcaError

from .models import (
    ComprobanteArca, ConsumoLoteVenta, EstadoVenta, ItemVenta, NotaCreditoArca,
    TipoComprobante, Venta, registrar_devolucion,
)
from .views_devoluciones import RegistrarDevolucionAjax


def _fake_post(resultado='A', cae='11122233344455', ultimo_nro=0):
    """side_effect para mockear core.services_arca.wsfe._post — responde
    según el 2° argumento posicional (metodo), sin tocar la red ni el
    filesystem. resultado='R' simula un rechazo de ARCA."""
    def _post(config, metodo, cuerpo_xml):
        if metodo == 'FECompUltimoAutorizado':
            return f'<CbteNro>{ultimo_nro}</CbteNro>'
        if metodo == 'FECAESolicitar':
            if resultado == 'A':
                return (
                    '<FeDetResp><FECAEDetResponse><Resultado>A</Resultado></FECAEDetResponse></FeDetResp>'
                    f'<CAE>{cae}</CAE><CAEFchVto>20261231</CAEFchVto>'
                )
            return (
                '<FeDetResp><FECAEDetResponse><Resultado>R</Resultado>'
                '<Err><Code>10015</Code><Msg>Rechazado de prueba</Msg></Err>'
                '</FECAEDetResponse></FeDetResp>'
            )
        raise AssertionError(f'metodo inesperado: {metodo}')
    return _post


class NotaCreditoArcaTests(TestCase):

    def setUp(self):
        DatosEmpresa.objects.update_or_create(pk=1, defaults={
            'nombre_comercial': 'Test SA',
            'cuit': '20111111112',
            'condicion_iva': CondicionIVA.RESPONSABLE_INSCRIPTO,
        })
        ConfiguracionArca.objects.update_or_create(pk=1, defaults={
            'habilitado': True,
            'ambiente': AmbienteArca.TESTING,
            'punto_venta': 1,
            'certificado_pem': 'x',
            'clave_privada_enc': 'x',
            'wsaa_token': 'tok',
            'wsaa_sign': 'sign',
            'wsaa_expira': timezone.now() + timedelta(hours=1),
        })

    def _crear_venta_facturada(self, tipo_comprobante, cantidad=Decimal('2'),
                                precio_unitario=Decimal('1000'), alicuota='21',
                                descuento_pct=Decimal('0'), doc_tipo=DOC_TIPO_CONSUMIDOR_FINAL,
                                doc_nro='0',
                                condicion_iva_receptor_id=CondicionIvaReceptor.CONSUMIDOR_FINAL):
        """Arma una Venta CONFIRMADA con un ItemVenta + su ConsumoLoteVenta
        (lote=None: "vendida sin stock", camino ya soportado por
        registrar_devolucion — no hace falta armar un LoteCompra real para
        estos tests) y un ComprobanteArca ya emitido, lista para devolver y
        probar emitir_nota_credito()."""
        venta = Venta.objects.create(fecha=date.today(), estado=EstadoVenta.CONFIRMADA)
        item = ItemVenta.objects.create(
            venta=venta, cantidad=cantidad, precio_unitario=precio_unitario,
            alicuota_iva=alicuota, descuento_pct=descuento_pct,
            producto_nombre='Producto de prueba',
        )
        ConsumoLoteVenta.objects.create(
            item_venta=item, lote=None, cantidad=cantidad, lote_codigo_snapshot='SIN STOCK',
        )
        subtotal = item.subtotal
        if tipo_comprobante == TipoComprobante.FACTURA_C:
            importe_neto, importe_iva = subtotal, Decimal('0')
        else:
            importe_neto = round(subtotal / (1 + Decimal(alicuota) / 100), 2)
            importe_iva = subtotal - importe_neto
        venta.total = subtotal
        venta.save(update_fields=['total'])
        comprobante = ComprobanteArca.objects.create(
            venta=venta, tipo_comprobante=tipo_comprobante, punto_venta=1, numero=45,
            cae='99988877766655', cae_vencimiento=date.today() + timedelta(days=10),
            ambiente=AmbienteArca.TESTING, doc_tipo=doc_tipo, doc_nro=doc_nro,
            condicion_iva_receptor_id=condicion_iva_receptor_id,
            importe_total=subtotal, importe_neto=importe_neto, importe_iva=importe_iva,
        )
        return venta, item, comprobante

    @staticmethod
    def _items_data(item, cantidad, es_perdida=False, motivo_perdida=None):
        return [{'item_venta': item, 'cantidad': cantidad, 'es_perdida': es_perdida, 'motivo_perdida': motivo_perdida}]

    # ── 1. Devolución total ──────────────────────────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_devolucion_total_emite_nc_por_el_importe_facturado(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(TipoComprobante.FACTURA_B)
        mock_post.side_effect = _fake_post()

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, item.cantidad),
            descripcion='Devolución total', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc = facturacion.emitir_nota_credito(devolucion)

        self.assertIsNotNone(nc)
        self.assertEqual(nc.tipo_comprobante, TipoComprobante.NOTA_CREDITO_B)
        self.assertEqual(nc.importe_total, comprobante.importe_total)
        self.assertEqual(nc.comprobante_original, comprobante)

    # ── 2. Devolución parcial ─────────────────────────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_devolucion_parcial_emite_nc_proporcional(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(
            TipoComprobante.FACTURA_B, cantidad=Decimal('4'), precio_unitario=Decimal('1000'),
        )
        mock_post.side_effect = _fake_post()

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, Decimal('2')),
            descripcion='Devolución parcial (la mitad)', usuario=None, cuenta=None,
            monto=Decimal('0'), cotizacion=None,
        )
        nc = facturacion.emitir_nota_credito(devolucion)

        self.assertEqual(nc.importe_total, round(comprobante.importe_total / 2, 2))

    # ── 3. Venta sin comprobante ARCA ────────────────────────────────
    def test_venta_sin_comprobante_arca_no_dispara_nada(self):
        venta = Venta.objects.create(fecha=date.today(), estado=EstadoVenta.CONFIRMADA, total=Decimal('1000'))
        item = ItemVenta.objects.create(
            venta=venta, cantidad=Decimal('1'), precio_unitario=Decimal('1000'), alicuota_iva='21',
        )
        ConsumoLoteVenta.objects.create(item_venta=item, lote=None, cantidad=Decimal('1'), lote_codigo_snapshot='SIN STOCK')

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, Decimal('1')),
            descripcion='Venta nunca facturada ante ARCA', usuario=None, cuenta=None,
            monto=Decimal('0'), cotizacion=None,
        )

        with patch('core.services_arca.wsfe._post') as mock_post:
            nc = facturacion.emitir_nota_credito(devolucion)

        self.assertIsNone(nc)
        mock_post.assert_not_called()
        self.assertFalse(NotaCreditoArca.objects.exists())

    # ── 4. ARCA rechaza la NC ────────────────────────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_arca_rechaza_la_nc_pero_la_devolucion_queda_registrada(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(TipoComprobante.FACTURA_B)
        mock_post.side_effect = _fake_post(resultado='R')

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, item.cantidad),
            descripcion='NC que ARCA va a rechazar', usuario=None, cuenta=None,
            monto=Decimal('0'), cotizacion=None,
        )

        with self.assertRaises(ArcaError):
            facturacion.emitir_nota_credito(devolucion)

        # Lo que ya pasó (la devolución, sus ítems) no se deshace.
        self.assertTrue(devolucion.pk)
        self.assertEqual(devolucion.items.count(), 1)
        self.assertFalse(NotaCreditoArca.objects.exists())

    # ── 5. Dos devoluciones parciales sucesivas ──────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_dos_devoluciones_parciales_sucesivas_generan_dos_nc_sin_pasarse_del_total(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(
            TipoComprobante.FACTURA_B, cantidad=Decimal('4'), precio_unitario=Decimal('1000'),
        )
        mock_post.side_effect = _fake_post()

        dev1 = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, Decimal('1')),
            descripcion='Parcial 1', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc1 = facturacion.emitir_nota_credito(dev1)

        dev2 = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, Decimal('1')),
            descripcion='Parcial 2', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc2 = facturacion.emitir_nota_credito(dev2)

        self.assertNotEqual(nc1.pk, nc2.pk)
        self.assertLessEqual(nc1.importe_total + nc2.importe_total, comprobante.importe_total)

    # ── 6. Factura C → NC-C sin desglose de IVA ──────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_factura_c_nc_sin_desglose_de_iva(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(TipoComprobante.FACTURA_C)
        mock_post.side_effect = _fake_post()

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, item.cantidad),
            descripcion='Total, Factura C', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc = facturacion.emitir_nota_credito(devolucion)

        self.assertEqual(nc.tipo_comprobante, TipoComprobante.NOTA_CREDITO_C)
        self.assertEqual(nc.importe_iva, Decimal('0'))
        cuerpo_cae = next(c.args[2] for c in mock_post.call_args_list if c.args[1] == 'FECAESolicitar')
        self.assertNotIn('<ar:Iva>', cuerpo_cae)

    # ── 7. Factura A → NC-A con CbtesAsoc + Iva ──────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_factura_a_nc_incluye_cbtes_asoc_e_iva(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(
            TipoComprobante.FACTURA_A, doc_tipo=DOC_TIPO_CUIT, doc_nro='20111111112',
            condicion_iva_receptor_id=CondicionIvaReceptor.RESPONSABLE_INSCRIPTO,
        )
        mock_post.side_effect = _fake_post()

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, item.cantidad),
            descripcion='Total, Factura A', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc = facturacion.emitir_nota_credito(devolucion)

        self.assertEqual(nc.tipo_comprobante, TipoComprobante.NOTA_CREDITO_A)
        cuerpo_cae = next(c.args[2] for c in mock_post.call_args_list if c.args[1] == 'FECAESolicitar')
        self.assertIn('<ar:CbtesAsoc>', cuerpo_cae)
        self.assertIn(f'<ar:Tipo>{comprobante.tipo_comprobante}</ar:Tipo>', cuerpo_cae)
        self.assertIn(f'<ar:PtoVta>{comprobante.punto_venta}</ar:PtoVta>', cuerpo_cae)
        self.assertIn(f'<ar:Nro>{comprobante.numero}</ar:Nro>', cuerpo_cae)
        self.assertIn('<ar:Iva>', cuerpo_cae)

    # ── 8. Ítem es_perdida cuenta igual ──────────────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_item_es_perdida_igual_cuenta_para_la_nc(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(TipoComprobante.FACTURA_B)
        mock_post.side_effect = _fake_post()

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, item.cantidad, es_perdida=True, motivo_perdida='rotura'),
            descripcion='Llegó rota', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc = facturacion.emitir_nota_credito(devolucion)

        self.assertEqual(nc.importe_total, comprobante.importe_total)

    # ── 9. Idempotencia ───────────────────────────────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_emitir_nota_credito_es_idempotente(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(TipoComprobante.FACTURA_B)
        mock_post.side_effect = _fake_post()

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, item.cantidad),
            descripcion='Total', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc1 = facturacion.emitir_nota_credito(devolucion)
        llamadas_previas = mock_post.call_count

        devolucion.refresh_from_db()  # limpia el cache de relaciones para forzar una lectura real
        nc2 = facturacion.emitir_nota_credito(devolucion)

        self.assertEqual(nc1.pk, nc2.pk)
        self.assertEqual(mock_post.call_count, llamadas_previas)

    # ── 10. Regresión: sin cbtes_asoc, mismo comportamiento de siempre ──
    def test_solicitar_cae_sin_cbtes_asoc_no_cambia_el_comportamiento_existente(self):
        config = ConfiguracionArca.get_solo()
        with patch('core.services_arca.wsfe._post') as mock_post:
            mock_post.side_effect = _fake_post()
            wsfe.solicitar_cae(
                config, cuit='20111111112', tipo_comprobante=TipoComprobante.FACTURA_C,
                doc_tipo=DOC_TIPO_CONSUMIDOR_FINAL, doc_nro='0',
                condicion_iva_receptor_id=CondicionIvaReceptor.CONSUMIDOR_FINAL,
                importe_total=Decimal('1000'), importe_neto=Decimal('1000'), importe_iva=Decimal('0'),
            )
            cuerpo_cae = next(c.args[2] for c in mock_post.call_args_list if c.args[1] == 'FECAESolicitar')
        self.assertNotIn('CbtesAsoc', cuerpo_cae)

    # ── 11. Vista RegistrarDevolucionAjax ─────────────────────────────
    def _post_devolucion(self, venta, item, cantidad, resultado_arca='A'):
        factory = RequestFactory()
        body = {
            'venta_pk': venta.pk,
            'descripcion': 'Devolución vía AJAX',
            'monto': '0',
            'items': [{'item_venta_pk': item.pk, 'cantidad': str(cantidad), 'es_perdida': False}],
        }
        request = factory.post(
            '/ventas/devoluciones/registrar/', data=json.dumps(body), content_type='application/json',
        )
        # A diferencia de catalogo/tests.py (que usa SimpleNamespace), acá
        # hace falta un Usuario real: registrar_devolucion() lo persiste
        # como DevolucionVenta.creado_por (FK), no alcanza con un objeto
        # cualquiera con is_authenticated=True.
        request.user, _ = Usuario.objects.get_or_create(username='test-devoluciones')
        with patch('ventas.views_devoluciones.chequear_permiso', return_value=True), \
             patch('core.services_arca.wsfe._post', side_effect=_fake_post(resultado=resultado_arca)):
            return RegistrarDevolucionAjax.as_view()(request)

    def test_registrar_devolucion_ajax_devuelve_datos_de_nc_en_el_json(self):
        venta, item, comprobante = self._crear_venta_facturada(TipoComprobante.FACTURA_B)
        response = self._post_devolucion(venta, item, item.cantidad)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['ok'])
        self.assertIn('nota_credito_cae', data)
        self.assertIn('nota_credito_numero_display', data)
        self.assertNotIn('nota_credito_error', data)

    def test_registrar_devolucion_ajax_informa_error_de_nc_sin_fallar_la_devolucion(self):
        venta, item, comprobante = self._crear_venta_facturada(TipoComprobante.FACTURA_B)
        response = self._post_devolucion(venta, item, item.cantidad, resultado_arca='R')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['ok'])
        self.assertIn('nota_credito_error', data)
        self.assertNotIn('nota_credito_cae', data)

    # ── 12. Consumidor Final sin cliente vinculado ────────────────────
    @patch('core.services_arca.wsfe._post')
    def test_consumidor_final_sin_cliente_vinculado_emite_nc_igual(self, mock_post):
        venta, item, comprobante = self._crear_venta_facturada(
            TipoComprobante.FACTURA_B, doc_tipo=DOC_TIPO_CONSUMIDOR_FINAL, doc_nro='0',
            condicion_iva_receptor_id=CondicionIvaReceptor.CONSUMIDOR_FINAL,
        )
        self.assertIsNone(venta.cliente_unico)  # ningún ItemVenta tiene cliente cargado
        mock_post.side_effect = _fake_post()

        devolucion = registrar_devolucion(
            venta=venta, items_data=self._items_data(item, item.cantidad),
            descripcion='Consumidor Final', usuario=None, cuenta=None, monto=Decimal('0'), cotizacion=None,
        )
        nc = facturacion.emitir_nota_credito(devolucion)

        self.assertIsNotNone(nc)
        self.assertEqual(nc.doc_tipo, DOC_TIPO_CONSUMIDOR_FINAL)
        self.assertEqual(nc.doc_nro, '0')
