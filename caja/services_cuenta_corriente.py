"""
caja/services_cuenta_corriente.py

Lógica de la pantalla "Cuenta corriente" — la vista por cliente del
saldo consolidado, cuando la instalación cobra en ese modo (ver
core.models.usa_cuenta_corriente).

No hay modelo nuevo de "cuenta corriente": el saldo de un cliente ES la
suma de los saldos de todas sus CuentaPorCobrar activas. Estas funciones
solo agregan y presentan esa información; el cobro (imputación FIFO) vive
en caja.models.registrar_cobro_cuenta_corriente.
"""

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from .models import (
    CuentaPorCobrar, CuotaCobro, CobroCuentaCorriente,
    EstadoDeuda, EstadoCuota, ModoCuotas,
)


def clientes_con_saldo(q=''):
    """
    Un renglón por cliente con deuda activa: saldo total, cantidad de
    deudas, fecha de la deuda más vieja, y si tiene alguna cuota vencida
    impaga (mora). Ordenado por saldo descendente.
    """
    hoy = timezone.localtime().date()

    qs = (
        CuentaPorCobrar.objects
        .filter(estado=EstadoDeuda.ACTIVA)
        .select_related('cliente')
    )
    if q:
        qs = qs.filter(
            Q(cliente__nombre__icontains=q) |
            Q(cliente__apellido__icontains=q) |
            Q(cliente__razon_social__icontains=q) |
            Q(cliente__nombre_comercial__icontains=q) |
            Q(cliente__dni__icontains=q) |
            Q(cliente__cuit__icontains=q)
        )

    # Cuotas vencidas impagas, por cliente — una query.
    en_mora = set(
        CuotaCobro.objects
        .filter(estado=EstadoCuota.PENDIENTE, fecha_vencimiento__lt=hoy,
                cuenta_por_cobrar__estado=EstadoDeuda.ACTIVA)
        .values_list('cuenta_por_cobrar__cliente_id', flat=True)
    )

    acum = {}
    for cxc in qs:
        saldo = cxc.saldo_pendiente
        if saldo <= 0:
            continue
        d = acum.get(cxc.cliente_id)
        if d is None:
            cli = cxc.cliente
            d = acum[cxc.cliente_id] = {
                'cliente_pk': cli.pk,
                'cliente_nombre': cli.get_nombre_display(),
                'doc': cli.dni or cli.cuit or cli.cuil or '',
                'codigo': cli.codigo or '',
                'saldo_total': Decimal('0'),
                'cant_deudas': 0,
                'deuda_mas_vieja': cxc.fecha_inicio,
                'en_mora': cxc.cliente_id in en_mora,
                'monedas': set(),
            }
        d['saldo_total'] += saldo
        d['cant_deudas'] += 1
        d['monedas'].add(cxc.moneda)
        if cxc.fecha_inicio < d['deuda_mas_vieja']:
            d['deuda_mas_vieja'] = cxc.fecha_inicio

    filas = sorted(acum.values(), key=lambda x: x['saldo_total'], reverse=True)
    for f in filas:
        f['saldo_total'] = str(f['saldo_total'])
        f['deuda_mas_vieja'] = f['deuda_mas_vieja'].isoformat()
        f['multi_moneda'] = len(f['monedas']) > 1
        del f['monedas']
    return filas


def resumen_cliente(cliente):
    """
    Detalle de la cuenta corriente de un cliente: saldo, sus deudas
    individuales (para poder entrar a cada una), el libro de movimientos
    con saldo corrido, el pagaré consolidado y los cobros de cuenta
    corriente ya registrados.
    """
    from core.services_estadisticas import cliente_perfil as stats

    # Más viejas primero — el mismo orden en que la cascada FIFO las va
    # a imputar (deudas_activas viene ordenada por -fecha_alta).
    deudas = sorted(stats.deudas_activas(cliente), key=lambda d: d['fecha_inicio'])
    historial = stats.historial_cliente(cliente)

    saldo_total = sum((Decimal(d['saldo_pendiente']) for d in deudas), Decimal('0'))

    cobros = [
        {
            'pk': c.pk,
            'fecha': c.fecha.isoformat(),
            'monto': str(c.monto),
            'moneda': c.moneda,
            'cuenta_nombre': c.cuenta.nombre if c.cuenta_id else '',
            'numero_comprobante': c.numero_comprobante,
            'notas': c.notas,
            'estado': c.estado,
            'saldo_posterior': str(c.saldo_posterior),
            'creado_por': str(c.creado_por) if c.creado_por else '',
            'fecha_alta': c.fecha_alta.isoformat(),
            'imputaciones': [
                {
                    'cuenta_por_cobrar_id': i['cuenta_por_cobrar_id'],
                    'titulo': i['titulo'],
                    'monto': str(i['monto']),
                    'cancelo': i['cancelo'],
                }
                for i in c.imputaciones
            ],
        }
        for c in (
            CobroCuentaCorriente.objects
            .filter(cliente=cliente)
            .select_related('cuenta', 'creado_por')
            .prefetch_related('cuotas_imputadas__cuenta_por_cobrar__pago_venta__venta')
        )
    ]

    tiene_cuotas_fijas = any(
        d['modo_cuotas'] == ModoCuotas.FIJAS and Decimal(d['saldo_pendiente']) > 0
        for d in deudas
    )

    return {
        'cliente_pk': cliente.pk,
        'cliente_nombre': cliente.get_nombre_display(),
        'saldo_total': str(saldo_total),
        'deudas': deudas,
        'historial': historial,
        'cobros': cobros,
        'tiene_cuotas_fijas': tiene_cuotas_fijas,
        'pagare': {
            'numero': cliente.numero_pagare,
            'foto_url': cliente.foto_pagare.url if cliente.foto_pagare else '',
        },
    }
