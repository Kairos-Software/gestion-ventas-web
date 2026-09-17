/**
 * cuenta_corriente_movimientos_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Extracto imprimible del libro de movimientos de la cuenta corriente
 * de un cliente: cada venta/deuda que le sumó saldo y cada pago que se
 * lo bajó, en orden, con el saldo que le quedaba después de cada uno.
 * Mismo patrón que cuenta_corriente_recibo.js (HTML en ventana nueva
 * que dispara el diálogo de impresión del navegador).
 *
 * Expone: ccMovimientosImprimir(cliente, historial, formato, ventanaPrevia)
 *   - cliente: objeto identificatorio; por compatibilidad acepta un nombre
 *     como string.
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

function _ccmEmpresaHtml(emp) {
    const nombre = emp.nombre || emp.razon_social || '';
    const razon = emp.razon_social && emp.razon_social !== nombre ? emp.razon_social : '';
    const contacto = [emp.domicilio, emp.telefono ? `Tel: ${emp.telefono}` : '', emp.email]
        .filter(Boolean).map(_ccmEsc).join(' · ');
    const fiscal = [emp.cuit ? `CUIT: ${emp.cuit}` : '', emp.condicion_iva]
        .filter(Boolean).map(_ccmEsc).join(' · ');
    if (!emp.logo_url && !nombre && !contacto && !fiscal && !emp.eslogan) return '';
    return `<header class="ccm-membrete">
        <div class="ccm-marca">
            ${emp.logo_url ? `<img class="ccm-logo" src="${_ccmEsc(emp.logo_url)}" alt="Logo">` : ''}
            <div>
                ${nombre ? `<div class="ccm-empresa-nombre">${_ccmEsc(nombre)}</div>` : ''}
                ${emp.eslogan ? `<div class="ccm-eslogan">${_ccmEsc(emp.eslogan)}</div>` : ''}
            </div>
        </div>
        <div class="ccm-empresa-datos">
            ${razon ? `<div>${_ccmEsc(razon)}</div>` : ''}
            ${contacto ? `<div>${contacto}</div>` : ''}
            ${fiscal ? `<div>${fiscal}</div>` : ''}
        </div>
    </header>`;
}

function _ccmClienteHtml(cliente) {
    const datos = [
        cliente.dni ? `DNI: ${cliente.dni}` : '',
        cliente.cuil ? `CUIL: ${cliente.cuil}` : '',
        cliente.cuit ? `CUIT: ${cliente.cuit}` : '',
        cliente.condicion_iva ? `IVA: ${cliente.condicion_iva}` : '',
        cliente.direccion ? `Domicilio: ${cliente.direccion}` : '',
        cliente.email ? `Email: ${cliente.email}` : '',
    ].filter(Boolean).map(_ccmEsc).join(' · ');
    return `<section class="ccm-cliente">
        <span>Cliente</span><strong>${_ccmEsc(cliente.nombre || '—')}</strong>
        ${datos ? `<div>${datos}</div>` : ''}
    </section>`;
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
    const logoAncho = formato === 'termica58' ? '34mm' : '44mm';
    const logoAlto = formato === 'termica58' ? '13mm' : '16mm';
    return `
        @page { size: ${ancho}mm auto; margin: 0; }
        html, body { width: ${ancho}mm; max-width: ${ancho}mm; margin: 0; }
        body { padding: ${padding}; font-size: ${fuente}; }
        h1 { font-size: 12pt; line-height: 1.25; }
        .ccm-membrete { display: block; margin-bottom: 12px; padding-bottom: 9px; text-align: center; }
        .ccm-marca { display: block; }
        .ccm-logo { max-width: ${logoAncho}; max-height: ${logoAlto}; margin: 0 auto 5px; }
        .ccm-empresa-nombre { font-size: 10pt; }
        .ccm-eslogan, .ccm-empresa-datos { max-width: none; margin-top: 2px; font-size: 7pt; line-height: 1.35; text-align: center; overflow-wrap: anywhere; }
        .ccm-cliente { margin-bottom: 10px; padding: 7px; font-size: ${fuente}; overflow-wrap: anywhere; }
        .ccm-cliente > span { display: block; margin: 0 0 2px; }
        .ccm-cliente div { font-size: 7pt; }
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
    const emp = (typeof window !== 'undefined' && window.KAI_EMPRESA) || {};
    const clienteBase = (clienteNombre && typeof clienteNombre === 'object')
        ? clienteNombre
        : { nombre: clienteNombre || '' };
    const cliente = {
        ...clienteBase,
        nombre: clienteBase.nombre || clienteBase.cliente_nombre || '',
    };
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
<title>Movimientos de cuenta corriente — ${_ccmEsc(cliente.nombre)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 800px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .ccm-membrete { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid #1E6FA8; page-break-inside: avoid; }
    .ccm-marca { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .ccm-logo { display: block; max-width: 170px; max-height: 58px; object-fit: contain; }
    .ccm-empresa-nombre { font-size: 1.05rem; font-weight: 700; }
    .ccm-eslogan { margin-top: 2px; color: #40536A; font-size: .75rem; font-style: italic; }
    .ccm-empresa-datos { max-width: 55%; color: #26364A; font-size: .75rem; line-height: 1.45; text-align: right; }
    .ccm-cliente { margin: 0 0 18px; padding: 9px 12px; border: 1px solid #B7CEDC; background: #F7FAFC; font-size: .8125rem; line-height: 1.45; }
    .ccm-cliente > span { margin-right: 8px; color: #1E6FA8; font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
    .ccm-cliente div { margin-top: 3px; color: #40536A; font-size: .75rem; }
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
    ${_ccmEmpresaHtml(emp)}
    <h1>Movimientos de cuenta corriente</h1>
    <p class="ccm-sub">${rango} · ${movs.length} movimiento${movs.length === 1 ? '' : 's'} · impreso el ${new Date().toLocaleDateString('es-AR')}</p>
    ${_ccmClienteHtml(cliente)}

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
