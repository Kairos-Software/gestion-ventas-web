/**
 * cuenta_corriente_recibo.js
 * ─────────────────────────────────────────────────────────────────
 * Recibo imprimible de un cobro por cuenta corriente: cuánto pagó el
 * cliente, a qué cuenta entró, y el desglose de a qué deudas se imputó.
 * Mismo patrón que cuentas_cobrar_imprimir.js (HTML en ventana nueva
 * que dispara el diálogo de impresión del navegador).
 *
 * Expone: ccReciboImprimir(cobro, clienteNombre, saldoDespues, ventanaPrevia)
 *   - cobro: objeto serializado por services_cuenta_corriente.resumen_cliente
 *     (fecha, monto, moneda, cuenta_nombre, numero_comprobante, notas,
 *      imputaciones: [{titulo, monto, cancelo}])
 *   - clienteNombre: string
 *   - saldoDespues: saldo total del cliente DESPUÉS de este cobro (string)
 *   - ventanaPrevia: window.open síncrono en el click (para no perder el gesto)
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _ccrEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _ccrMoneda(v, moneda) {
    return `$ ${parseFloat(v || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    })}${moneda && moneda !== 'ARS' ? ' ' + moneda : ''}`;
}

function _ccrFecha(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}/${m}/${y}`;
}

function ccReciboImprimir(cobro, clienteNombre, saldoDespues, ventanaPrevia) {
    const filas = (cobro.imputaciones || []).map(i => `
        <tr>
            <td>${_ccrEsc(i.titulo)}</td>
            <td class="ccr-monto">${_ccrMoneda(i.monto, cobro.moneda)}</td>
            <td>${i.cancelo ? 'Saldada' : 'Abonada en parte'}</td>
        </tr>`).join('');

    const anulado = cobro.estado === 'anulado';

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Recibo de cobro — ${_ccrEsc(clienteNombre)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 640px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .ccr-sub { color: #555; font-size: .875rem; margin: 0 0 20px; }
    .ccr-anulado { display: inline-block; background: #fee2e2; color: #b91c1c; border: 1px solid #b91c1c; border-radius: 4px; padding: 2px 10px; font-size: .8rem; font-weight: bold; margin-bottom: 14px; }
    .ccr-monto-grande {
        display: flex; align-items: baseline; justify-content: space-between;
        background: #FFF0E6; border: 1px solid #F26A1B; border-radius: 8px;
        padding: 14px 18px; margin-bottom: 20px; font-size: .9375rem;
    }
    .ccr-monto-grande strong { font-size: 1.5rem; color: #D45A0F; }
    .ccr-datos { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 20px; font-size: .875rem; }
    .ccr-datos div { display: flex; justify-content: space-between; border-bottom: 1px solid #eee; padding: 3px 0; }
    .ccr-datos span { color: #666; }
    h3 { font-size: .95rem; margin: 20px 0 8px; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .ccr-monto { text-align: right; white-space: nowrap; }
    .ccr-saldo { margin-top: 16px; font-size: .9375rem; display: flex; justify-content: space-between; border-top: 2px solid #333; padding-top: 8px; }
    .ccr-firma { margin-top: 48px; display: flex; justify-content: space-between; font-size: .8rem; color: #555; }
    .ccr-firma div { border-top: 1px solid #999; padding-top: 4px; width: 45%; text-align: center; }
    .ccr-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } }
</style>
</head>
<body>
    <h1>Recibo de cobro</h1>
    <p class="ccr-sub">${_ccrEsc(clienteNombre)} — ${_ccrFecha(cobro.fecha)}</p>
    ${anulado ? '<div class="ccr-anulado">COBRO ANULADO</div>' : ''}

    <div class="ccr-monto-grande">
        <span>Recibimos</span>
        <strong>${_ccrMoneda(cobro.monto, cobro.moneda)}</strong>
    </div>

    <div class="ccr-datos">
        ${cobro.cuenta_nombre ? `<div><span>Cuenta</span><strong>${_ccrEsc(cobro.cuenta_nombre)}</strong></div>` : ''}
        ${cobro.numero_comprobante ? `<div><span>N° de comprobante</span><strong>${_ccrEsc(cobro.numero_comprobante)}</strong></div>` : ''}
        ${cobro.notas ? `<div><span>Notas</span><strong>${_ccrEsc(cobro.notas)}</strong></div>` : ''}
    </div>

    ${filas ? `
    <h3>Se imputó a</h3>
    <table>
        <thead><tr><th>Deuda</th><th class="ccr-monto">Monto</th><th>Estado</th></tr></thead>
        <tbody>${filas}</tbody>
    </table>` : ''}

    <div class="ccr-saldo">
        <span>Saldo del cliente después de este cobro</span>
        <strong>${_ccrMoneda(saldoDespues, cobro.moneda)}</strong>
    </div>

    <div class="ccr-firma">
        <div>Firma del cliente</div>
        <div>Firma y sello</div>
    </div>

    <p class="ccr-footer">Generado desde Kairos.</p>
    <script>window.onload = function () { setTimeout(function () { window.print(); }, 150); };<\/script>
</body>
</html>`;

    const ventana = ventanaPrevia || window.open('', '_blank', 'width=760,height=920');
    if (!ventana) {
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio.', 'warning', 6000);
        }
        return;
    }
    ventana.document.write(html);
    ventana.document.close();
}
