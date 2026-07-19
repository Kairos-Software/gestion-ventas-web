import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from caja.models import CuentaCaja, TipoCaja, TipoCuenta, Cheque, TipoCheque, EstadoCheque
from compras.models import Compra, ItemCompra, MedioPagoCompra
from core.models import Usuario
from productos.models import (
    CategoriaProducto, Producto, Oferta, TipoOferta, AplicacionOferta, Moneda,
)
from ventas.models import Venta, ItemVenta, MedioPago

PREFIJO = 'TEST - '


class Command(BaseCommand):
    help = (
        'Genera datos de prueba (productos, compras, ventas, deudas, '
        'cheques y una oferta) para poder probar los reportes/alertas de '
        'asistencia con información realista. Pensado solo para bases de '
        'desarrollo — todo lo que crea arranca con el prefijo "TEST - ".'
    )

    @property
    def hoy(self):
        return timezone.now().date()

    def handle(self, *args, **options):
        hoy = self.hoy
        admin = Usuario.objects.filter(is_superuser=True).first()
        if admin is None:
            self.stdout.write(self.style.ERROR('No hay ningún superusuario para atribuir las operaciones.'))
            return

        cuenta_efectivo = CuentaCaja.objects.filter(es_credito=False, activa=True, moneda=Moneda.ARS).first()
        if cuenta_efectivo is None:
            cuenta_efectivo = CuentaCaja.objects.create(
                nombre='Efectivo', tipo=TipoCuenta.EFECTIVO, moneda=Moneda.ARS, caja=TipoCaja.GRANDE,
            )
        cuenta_banco, _ = CuentaCaja.objects.get_or_create(
            nombre=f'{PREFIJO}Banco', caja=TipoCaja.GRANDE, moneda=Moneda.ARS,
            defaults={'tipo': TipoCuenta.BANCO, 'es_credito': False, 'activa': True},
        )
        cuenta_tarjeta, _ = CuentaCaja.objects.get_or_create(
            nombre=f'{PREFIJO}Tarjeta', caja=TipoCaja.GRANDE, moneda=Moneda.ARS,
            defaults={'tipo': TipoCuenta.OTRA, 'es_credito': True, 'dia_cierre': 10,
                      'dia_vencimiento': 20, 'activa': True},
        )

        categoria, _ = CategoriaProducto.objects.get_or_create(
            nombre=f'{PREFIJO}Almacén', defaults={'activo': True},
        )

        yogur = self._crear_producto(categoria, 'Yogur Cremoso 1L', Decimal('900'), perecedero=True)
        fiambre = self._crear_producto(categoria, 'Jamón Cocido x Kg', Decimal('4500'), perecedero=True)
        gaseosa = self._crear_producto(categoria, 'Gaseosa Cola 2L', Decimal('1800'))
        termo = self._crear_producto(categoria, 'Termo Acero 1L', Decimal('15000'))
        self.stdout.write(self.style.SUCCESS('Productos creados.'))

        # ── Compra: yogur (vence en 12 días) + fiambre (vence en 3 días)
        #    + gaseosa + termo, pagada con tarjeta de crédito en 3 cuotas
        #    empezando en 2 días → dispara la alerta de deuda próxima.
        self._crear_compra_credito(
            admin, cuenta_tarjeta, hoy,
            items=[
                (yogur, Decimal('60'), Decimal('600'), hoy + timedelta(days=12)),
                (fiambre, Decimal('50'), Decimal('3000'), hoy + timedelta(days=3)),
                (gaseosa, Decimal('300'), Decimal('1100'), None),
                (termo, Decimal('10'), Decimal('9000'), None),
            ],
            cuotas=3, dias_inicio_debito=2,
        )
        self.stdout.write(self.style.SUCCESS('Compra a crédito confirmada (genera deuda pendiente).'))

        # ── Compra anterior, pagada a crédito y ya con su primera cuota
        #    saldada hoy → dispara el reporte de "deuda pagada".
        deuda_vieja = self._crear_compra_credito(
            admin, cuenta_tarjeta, hoy - timedelta(days=50),
            items=[(gaseosa, Decimal('50'), Decimal('1050'), None)],
            cuotas=2, dias_inicio_debito=-48,
        )
        primera_cuota = deuda_vieja.cuotas.order_by('numero').first()
        if primera_cuota:
            primera_cuota.confirmar(cuenta_pk=cuenta_efectivo.pk, usuario=admin)
        self.stdout.write(self.style.SUCCESS('Cuota vieja marcada como pagada hoy.'))

        # ── Cheques de prueba ──
        Cheque.objects.get_or_create(
            numero_cheque=f'{PREFIJO}0001', defaults={
                'tipo': TipoCheque.A_COBRAR, 'monto': Decimal('50000'), 'moneda': Moneda.ARS,
                'fecha_emision': hoy, 'fecha_cobro': hoy + timedelta(days=5),
                'titular_librador': 'Cliente de prueba', 'estado': EstadoCheque.PENDIENTE,
            },
        )
        Cheque.objects.get_or_create(
            numero_cheque=f'{PREFIJO}0002', defaults={
                'tipo': TipoCheque.A_PAGAR, 'monto': Decimal('30000'), 'moneda': Moneda.ARS,
                'fecha_emision': hoy, 'fecha_cobro': hoy + timedelta(days=1),
                'cuenta_origen': cuenta_banco, 'estado': EstadoCheque.PENDIENTE,
            },
        )
        self.stdout.write(self.style.SUCCESS('Cheques de prueba creados.'))

        # ── Oferta sobre el yogur que está por vencer ──
        oferta, _ = Oferta.objects.get_or_create(
            nombre=f'{PREFIJO}Liquidación yogur', defaults={
                'tipo': TipoOferta.PORCENTAJE, 'porcentaje': Decimal('20'),
                'fecha_inicio': hoy, 'fecha_fin': hoy + timedelta(days=12),
                'aplicacion': AplicacionOferta.AUTOMATICA, 'activa': True,
            },
        )
        oferta.productos.add(yogur)
        self.stdout.write(self.style.SUCCESS('Oferta de liquidación creada.'))

        # ── Ventas de los últimos ~75 días (gaseosa y yogur venden bien;
        #    el termo NO se vende nunca → stock estancado) ──
        medios_variados = [
            (MedioPago.EFECTIVO, None),
            (MedioPago.TRANSFERENCIA, cuenta_banco.pk),
            (MedioPago.DEBITO, cuenta_banco.pk),
        ]
        cantidad_ventas = 0
        for dias_atras in range(75, -1, -3):
            fecha_venta = hoy - timedelta(days=dias_atras)
            producto, cantidad = random.choice([
                (gaseosa, random.randint(1, 5)),
                (yogur, random.randint(1, 8)),
                (fiambre, Decimal(random.randint(1, 3))),
            ])
            medio, cuenta_pk = random.choice(medios_variados)
            self._crear_venta_confirmada(admin, fecha_venta, producto, cantidad, medio, cuenta_pk)
            cantidad_ventas += 1

        self.stdout.write(self.style.SUCCESS(f'{cantidad_ventas} ventas confirmadas.'))
        self.stdout.write(self.style.SUCCESS(
            'Datos de prueba listos. El termo no se vendio nunca: va a '
            'aparecer en el reporte de stock estancado.'
        ))

    # ── helpers ──────────────────────────────────────────────────

    def _crear_producto(self, categoria, nombre, precio, perecedero=False):
        producto, creado = Producto.objects.get_or_create(
            nombre=f'{PREFIJO}{nombre}',
            defaults={
                'categoria': categoria, 'precio_venta': precio,
                'gestiona_stock': True, 'es_perecedero': perecedero,
                'estado': 'activo', 'publicado': True,
            },
        )
        return producto

    def _crear_compra_credito(self, admin, cuenta_tarjeta, fecha, items, cuotas, dias_inicio_debito):
        compra = Compra.objects.create(fecha=fecha, creado_por=admin)
        total = Decimal('0')
        for producto, cantidad, costo, fecha_vencimiento in items:
            ItemCompra.objects.create(
                compra=compra, producto=producto, cantidad=cantidad,
                costo_unitario=costo, fecha_vencimiento=fecha_vencimiento,
            )
            total += cantidad * costo

        compra.confirmar(medio_pago=MedioPagoCompra.CREDITO, pagos=[{
            'medio': MedioPagoCompra.CREDITO, 'monto': total, 'cuenta_pk': cuenta_tarjeta.pk,
            'cuotas': cuotas, 'interes_pct': 0,
            'fecha_inicio_debito': (self.hoy + timedelta(days=dias_inicio_debito)).isoformat(),
        }])

        from caja.models import Deuda
        return Deuda.objects.filter(pago_compra__compra=compra).first()

    def _crear_venta_confirmada(self, admin, fecha, producto, cantidad, medio, cuenta_pk):
        venta = Venta.objects.create(fecha=fecha, creado_por=admin)
        ItemVenta.objects.create(
            venta=venta, producto=producto, cantidad=cantidad,
            precio_unitario=producto.precio_venta,
        )
        pago = {'medio': medio, 'monto': cantidad * producto.precio_venta}
        if cuenta_pk:
            pago['cuenta_pk'] = cuenta_pk
        venta.confirmar(confirmado_por=admin, medio_pago=medio, pagos=[pago])
