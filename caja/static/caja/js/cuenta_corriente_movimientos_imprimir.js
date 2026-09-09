/**
 * cuenta_corriente_movimientos_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Extracto imprimible del libro de movimientos de la cuenta corriente
 * de un cliente: cada venta/deuda que le sumó saldo y cada pago que se
 * lo bajó, en orden, con el saldo que le quedaba después de cada uno.
 * Mismo patrón que cuenta_corriente_recibo.js (HTML en ventana nueva
 * que dispara el diálogo de impresión del navegador).
 *
 * Expone: ccMovimientosImprimir(clienteNombre, historial, formato, ventanaPrevia)
 *   - clienteNombre: string
 *   - historial: filas de
 *     core.services_estadisticas.cliente_perfil.historial_cliente
 *     [{fecha, descripcion, medio_pago, monto, saldo}], orden cronológico.
 *     El signo (suma / resta) se deduce de cómo se movió el saldo
 *     corrido, no del texto — así "Pago cuota…" también sale como resta.
 *   - formato: a4, termica80 o termica58
 *   - ventanaPrevia: opcional; mantiene compatibilidad con la firma anterior
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _ccmEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _ccmMoneda(v) {
    return `$ ${parseFloat(v || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    })}`;
}

function _ccmFecha(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}/${m}/${y}`;
}

function _ccmResolverSalida(formato, ventanaPrevia) {
    if (formato && typeof formato !== 'string') {
        return { formato: 'a4', ventana: formato };
    }
    const valor = ['a4', 'termica80', 'termica58'].includes(formato) ? formato : 'a4';
    return { formato: valor, ventana: ventanaPrevia || null };
}

function _ccmCssFormato(formato) {
    if (formato === 'a4') return '@page { size: A4; margin: 12mm; }';
    const ancho = formato === 'termica58' ? 58 : 80;
    const padding = formato === 'termica58' ? '2.5mm' : '3.5mm';
    const fuente = formato === 'termica58' ? '8.2pt' : '9pt';
    return `
        @page { size: ${ancho}mm auto; margin: 0; }
        html, body { width: ${ancho}mm; max-width: ${ancho}mm; margin: 0; }
        body { padding: ${padding}; font-size: ${fuente}; }
        h1 { font-size: 12pt; line-height: 1.25; }
        .ccm-sub { font-size: 8pt; line-height: 1.35; margin-bottom: 12px; }
        .ccm-saldo-actual { padding: 8px; margin-bottom: 12px; border: 1px solid #333; background: none; font-size: ${fuente}; }
        .ccm-saldo-actual strong { color: #111; font-size: 12pt; }
        table, tbody { display: block; width: 100%; }
        thead { display: none; }
        tr { display: block; padding: 5px 0; border-top: 1px dashed #777; page-break-inside: avoid; }
        td { display: flex; justify-content: space-between; gap: 8px; border: 0; padding: 1px 0; text-align: right; overflow-wrap: anywhere; }
        td::before { content: attr(data-label); color: #555; font-weight: normal; text-align: left; flex-shrink: 0; }
        td[data-label="Detalle"] { display: block; text-align: left; padding: 2px 0; }
        td[data-label="Detalle"]::before { display: block; margin-bottom: 1px; }
        .ccm-num { text-align: right; }
        .ccm-pago td { color: #111; }
        .ccm-pago td[data-label="Monto"] { color: #047857; }
        .ccm-totales { max-width: none; margin-top: 12px; font-size: ${fuente}; }
        .ccm-footer { margin-top: 14px; font-size: 7pt; text-align: center; }
    `;
}

function ccMovimientosImprimir(clienteNombre, historial, formato, ventanaPrevia) {
    const salida = _ccmResolverSalida(formato, ventanaPrevia);
    formato = salida.formato;
    ventanaPrevia = salida.ventana;
    const movs = Array.isArray(historial) ? historial : [];
    if (!movs.length) {
        if (ventanaPrevia) ventanaPrevia.close();
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('Este cliente todavía no tiene movimientos para imprimir.', 'warning');
        }
        return;
    }

    let saldoPrev = 0;
    let totalSuma = 0;
    let totalPago = 0;
    const filas = movs.map((f) => {
        const saldo = parseFloat(f.saldo || 0) || 0;
        const esPago = saldo - saldoPrev < -0.005;
        saldoPrev = saldo;
        const monto = parseFloat(f.monto || 0) || 0;
        if (esPago) totalPago += monto; else totalSuma += monto;
        return `
        <tr class="${esPago ? 'ccm-pago' : ''}">
            <td data-label="Fecha">${_ccmFecha(f.fecha)}</td>
            <td data-label="Detalle">${_ccmEsc(f.descripcion)}</td>
            <td data-label="Monto" class="ccm-num">${esPago ? '−' : '+'} ${_ccmMoneda(monto)}</td>
            <td data-label="Saldo" class="ccm-num ccm-saldo">${_ccmMoneda(f.saldo)}</td>
        </tr>`;
    }).join('');

    const saldoActual = _ccmMoneda(saldoPrev);
    const desde = _ccmFecha(movs[0].fecha);
    const hasta = _ccmFecha(movs[movs.length - 1].fecha);
    const rango = desde === hasta ? `el ${desde}` : `del ${desde} al ${hasta}`;

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Movimientos de cuenta corriente — ${_ccmEsc(clienteNombre)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 800px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .ccm-sub { color: #555; font-size: .875rem; margin: 0 0 20px; }
    .ccm-saldo-actual {
        display: flex; align-items: baseline; justify-content: space-between;
        background: #FFF0E6; border: 1px solid #F26A1B; border-radius: 8px;
        padding: 14px 18px; margin-bottom: 22px; font-size: .9375rem;
    }
    .ccm-saldo-actual strong { font-size: 1.5rem; color: #D45A0F; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .ccm-num { text-align: right; white-space: nowrap; }
    .ccm-saldo { font-weight: bold; }
    .ccm-pago td { color: #047857; }
    .ccm-totales { margin-top: 18px; display: grid; grid-template-columns: 1fr; gap: 4px; max-width: 320px; margin-left: auto; font-size: .875rem; }
    .ccm-totales div { display: flex; justify-content: space-between; border-bottom: 1px solid #eee; padding: 4px 0; }
    .ccm-totales span { color: #666; }
    .ccm-totales div:last-child { border-bottom: none; border-top: 2px solid #333; font-weight: bold; }
    .ccm-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } thead { display: table-header-group; } tr { page-break-inside: avoid; } }
    ${_ccmCssFormato(formato)}
</style>
</head>
<body>
    <h1>Movimientos de cuenta corriente</h1>
    <p class="ccm-sub">${_ccmEsc(clienteNombre)} — ${rango} · ${movs.length} movimiento${movs.length === 1 ? '' : 's'} · impreso el ${new Date().toLocaleDateString('es-AR')}</p>

    <div class="ccm-saldo-actual">
        <span>Saldo actual</span>
        <strong>${saldoActual}</strong>
    </div>

    <table>
        <thead>
            <tr><th>Fecha</th><th>Detalle</th><th class="ccm-num">Monto</th><th class="ccm-num">Saldo</th></tr>
        </thead>
        <tbody>${filas}</tbody>
    </table>

    <div class="ccm-totales">
        <div><span>Total que se le sumó</span><strong>${_ccmMoneda(totalSuma)}</strong></div>
        <div><span>Total que pagó</span><strong>${_ccmMoneda(totalPago)}</strong></div>
        <div><span>Saldo actual</span><strong>${saldoActual}</strong></div>
    </div>

    <p class="ccm-footer">Generado desde Kairos.</p>
    <script>window.onload = function () { setTimeout(function () { window.print(); }, 150); };<\/script>
</body>
</html>`;

    const anchoVentana = formato === 'a4' ? 820 : (formato === 'termica80' ? 440 : 360);
    const ventana = ventanaPrevia || window.open('', '_blank', `width=${anchoVentana},height=950`);
    if (!ventana) {
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio.', 'warning', 6000);
        }
        return;
    }
    ventana.document.write(html);
    ventana.document.close();
}
