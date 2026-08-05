/**
 * cliente_deuda_total_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Genera un "estado de cuenta consolidado" imprimible con TODAS las
 * CuentaPorCobrar activas de un cliente juntas (total general arriba
 * + un bloque con su propia tabla de cuotas por cada una) — mismo
 * estilo visual y helpers que caja/static/caja/js/cuentas_cobrar_
 * imprimir.js, extendido a varias cuentas a la vez.
 *
 * Expone: clienteDeudaTotalImprimir(cliente, deudas, ventanaPrevia)
 *   - cliente: {pk, nombre}
 *   - deudas: array de objetos serializados igual que _serializar_cxc
 *     (con_cuotas=True) en caja/views_cuentas_cobrar.py
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _cdtEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _cdtFmtMoneda(v, moneda) {
    return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${moneda || ''}`.trim();
}

function _cdtEstadoLabel(c) {
    // Este texto lo lee el cliente, no el dueño — no le interesa si fue
    // por cheque, con qué cuenta, o si es carga inicial "que no afectó
    // caja" (jerga interna); solo le interesa si está pagada o no.
    if (c.estado === 'confirmada') return 'Pagada';
    if (c.estado === 'anulada') return 'Anulada';
    return 'Pendiente';
}

/**
 * @param {object} cliente - {pk, nombre}
 * @param {object[]} deudas - cuentas por cobrar activas, ya serializadas con cuotas
 * @param {Window} [ventanaPrevia] - ventana ya abierta con window.open síncrono en
 *   el click, para no perder el gesto del usuario (ver cxcImprimir).
 */
function clienteDeudaTotalImprimir(cliente, deudas, ventanaPrevia) {
    if (!deudas || !deudas.length) {
        if (ventanaPrevia) ventanaPrevia.close();
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('Este cliente no tiene deuda activa para imprimir.', 'warning');
        }
        return;
    }

    // Suma el saldo pendiente agrupado por moneda (una cuenta en USD y
    // otra en ARS no se pueden sumar en un solo número sin mentir).
    const totalesPorMoneda = {};
    deudas.forEach(d => {
        totalesPorMoneda[d.moneda] = (totalesPorMoneda[d.moneda] || 0) + parseFloat(d.saldo_pendiente || 0);
    });
    const totalGeneral = Object.entries(totalesPorMoneda)
        .map(([moneda, total]) => _cdtFmtMoneda(total, moneda)).join(' + ');

    const bloques = deudas.map(cxc => {
        const filasCuotas = (cxc.cuotas || []).map(c => `
            <tr>
                <td>${c.numero}</td>
                <td>${_cdtEsc(c.fecha_vencimiento)}</td>
                <td class="cdt-monto">${_cdtFmtMoneda(c.monto, cxc.moneda)}</td>
                <td>${_cdtEsc(_cdtEstadoLabel(c))}</td>
                <td>${c.fecha_confirmacion ? _cdtEsc(c.fecha_confirmacion.slice(0, 10)) : '-'}</td>
            </tr>`).join('');

        return `
        <div class="cdt-cuenta">
            <h2 class="cdt-cuenta-titulo">${_cdtEsc(cxc.titulo)}</h2>
            ${cxc.es_carga_inicial ? '<div class="cdt-badge">Carga inicial</div>' : ''}
            <div class="cdt-resumen">
                <div><span>Monto original</span><strong>${_cdtFmtMoneda(cxc.monto_original, cxc.moneda)}</strong></div>
                <div><span>Monto total</span><strong>${_cdtFmtMoneda(cxc.monto_total, cxc.moneda)}</strong></div>
                <div><span>Saldo pendiente</span><strong>${_cdtFmtMoneda(cxc.saldo_pendiente, cxc.moneda)}</strong></div>
                <div><span>Cuotas cobradas</span><strong>${cxc.cuotas_cobradas}/${cxc.cantidad_cuotas || '-'}</strong></div>
            </div>
            <table>
                <thead>
                    <tr><th>#</th><th>Vencimiento</th><th class="cdt-monto">Monto</th><th>Estado</th><th>Fecha de cobro</th></tr>
                </thead>
                <tbody>${filasCuotas}</tbody>
            </table>
        </div>`;
    }).join('');

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Deuda total — ${_cdtEsc(cliente.nombre)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 760px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .cdt-subtitulo { color: #555; font-size: .875rem; margin: 0 0 20px; }
    .cdt-total-general {
        display: flex; align-items: baseline; justify-content: space-between;
        background: #FFF0E6; border: 1px solid #F26A1B; border-radius: 8px;
        padding: 14px 18px; margin-bottom: 24px; font-size: .9375rem;
    }
    .cdt-total-general strong { font-size: 1.375rem; color: #D45A0F; }
    .cdt-cuenta { margin-bottom: 28px; padding-top: 16px; border-top: 2px solid #eee; }
    .cdt-cuenta:first-of-type { border-top: none; padding-top: 0; }
    .cdt-cuenta-titulo { font-size: 1rem; margin: 0 0 6px; }
    .cdt-badge { display: inline-block; background: #f3f0ff; color: #5b21b6; border-radius: 4px; padding: 2px 8px; font-size: .75rem; margin-bottom: 10px; }
    .cdt-resumen { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 14px; font-size: .875rem; }
    .cdt-resumen div { display: flex; justify-content: space-between; border-bottom: 1px solid #eee; padding: 3px 0; }
    .cdt-resumen span { color: #666; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .cdt-monto { text-align: right; }
    .cdt-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } .cdt-cuenta { page-break-inside: avoid; } }
</style>
</head>
<body>
    <h1>Deuda total — ${_cdtEsc(cliente.nombre)}</h1>
    <p class="cdt-subtitulo">Estado de cuenta consolidado al ${new Date().toLocaleDateString('es-AR')} — ${deudas.length} cuenta${deudas.length === 1 ? '' : 's'} por cobrar activa${deudas.length === 1 ? '' : 's'}</p>
    <div class="cdt-total-general">
        <span>Total adeudado</span>
        <strong>${totalGeneral}</strong>
    </div>
    ${bloques}
    <p class="cdt-footer">Generado desde Kairos.</p>
    <script>window.onload = function () { setTimeout(function () { window.print(); }, 150); };<\/script>
</body>
</html>`;

    const ventana = ventanaPrevia || window.open('', '_blank', 'width=800,height=950');
    if (!ventana) {
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio e intentá de nuevo.', 'warning', 6000);
        }
        return;
    }
    ventana.document.write(html);
    ventana.document.close();
}
