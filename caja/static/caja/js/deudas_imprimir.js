/**
 * deudas_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Genera un "estado de cuenta" imprimible de una Deuda (encabezado +
 * tabla de cuotas con su estado real) y lo abre en una ventana nueva
 * que dispara el diálogo de impresión del navegador — mismo mecanismo
 * que ventas/static/ventas/js/ticket_imprimir.js, sin necesidad de
 * varios formatos: acá alcanza con una sola hoja tipo A4.
 *
 * Expone: deudaImprimir(deuda) — llamada desde deudas.js.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _diEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _diFmtMoneda(v, moneda) {
    return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${moneda || ''}`.trim();
}

function _diEstadoLabel(c) {
    // Este texto lo lee quien recibe el comprobante (proveedor/acreedor),
    // no nosotros — no le interesa con qué cuenta pagamos ni si es carga
    // inicial "que no afectó caja" (jerga interna); solo si está pagada o no.
    if (c.estado === 'confirmada') return 'Pagada';
    if (c.estado === 'anulada') return 'Anulada';
    return 'Pendiente';
}

/**
 * @param {object} deuda
 * @param {Window} [ventanaPrevia] - Ventana ya abierta (window.open llamado
 *   de forma síncrona en el click, antes de cualquier `await`) para no
 *   perder el gesto del usuario y que el navegador no bloquee el popup.
 *   Si no se pasa, la abre acá mismo (caso de uso sin async de por medio).
 */
function deudaImprimir(deuda, ventanaPrevia) {
    const cuentaLabel = deuda.tipo === 'compra_credito' ? 'Tarjeta' : 'Cuenta acreditada';
    const cuentaValor = deuda.tipo === 'compra_credito'
        ? (deuda.cuenta_tarjeta_nombre || '-')
        : (deuda.cuenta_acreditacion_nombre || '-');

    const filasCuotas = (deuda.cuotas || []).map(c => `
        <tr>
            <td>${c.numero}</td>
            <td>${_diEsc(c.fecha_vencimiento)}</td>
            <td class="di-monto">${_diFmtMoneda(c.monto, deuda.moneda)}</td>
            <td>${_diEsc(_diEstadoLabel(c))}</td>
            <td>${c.fecha_confirmacion ? _diEsc(c.fecha_confirmacion.slice(0, 10)) : '-'}</td>
        </tr>`).join('');

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Deuda — ${_diEsc(deuda.descripcion || deuda.compra_numero || ('#' + deuda.pk))}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 720px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .di-subtitulo { color: #555; font-size: .875rem; margin: 0 0 20px; }
    .di-resumen { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 20px; font-size: .875rem; }
    .di-resumen div { display: flex; justify-content: space-between; border-bottom: 1px solid #eee; padding: 3px 0; }
    .di-resumen span { color: #666; }
    .di-badge { display: inline-block; background: #f3f0ff; color: #5b21b6; border-radius: 4px; padding: 2px 8px; font-size: .75rem; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .di-monto { text-align: right; }
    .di-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } }
</style>
</head>
<body>
    <h1>${_diEsc(deuda.tipo_display)} — ${_diEsc(deuda.descripcion || deuda.compra_numero || ('#' + deuda.pk))}</h1>
    <p class="di-subtitulo">Estado de cuenta al ${new Date().toLocaleDateString('es-AR')}</p>
    ${deuda.es_carga_inicial ? '<div class="di-badge">Carga inicial</div>' : ''}
    <div class="di-resumen">
        ${deuda.numero_comprobante ? `<div><span>N° de comprobante</span><strong>${_diEsc(deuda.numero_comprobante)}</strong></div>` : ''}
        <div><span>${cuentaLabel}</span><strong>${_diEsc(cuentaValor)}</strong></div>
        <div><span>Monto original</span><strong>${_diFmtMoneda(deuda.monto_original, deuda.moneda)}</strong></div>
        <div><span>Interés</span><strong>${_diEsc(deuda.porcentaje_interes)}%</strong></div>
        <div><span>Monto total</span><strong>${_diFmtMoneda(deuda.monto_total, deuda.moneda)}</strong></div>
        <div><span>Saldo pendiente</span><strong>${_diFmtMoneda(deuda.saldo_pendiente, deuda.moneda)}</strong></div>
        <div><span>Cuotas pagadas</span><strong>${deuda.cuotas_pagadas}/${deuda.cantidad_cuotas}</strong></div>
        <div><span>Estado</span><strong>${_diEsc(deuda.estado_display)}</strong></div>
    </div>
    <table>
        <thead>
            <tr><th>#</th><th>Vencimiento</th><th class="di-monto">Monto</th><th>Estado</th><th>Fecha de pago</th></tr>
        </thead>
        <tbody>${filasCuotas}</tbody>
    </table>
    <p class="di-footer">Generado desde Kairos.</p>
    <script>window.onload = function () { setTimeout(function () { window.print(); }, 150); };</script>
</body>
</html>`;

    const ventana = ventanaPrevia || window.open('', '_blank', 'width=800,height=950');
    if (!ventana) {
        KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio e intentá de nuevo.', 'warning', 6000);
        return;
    }
    ventana.document.write(html);
    ventana.document.close();
}
