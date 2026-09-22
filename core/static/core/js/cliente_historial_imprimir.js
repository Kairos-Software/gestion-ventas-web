/**
 * cliente_historial_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Imprime el historial de ventas y pagos de cuota de un cliente en
 * una única tabla cronológica (fecha, descripción, medio de pago,
 * monto, saldo) — mismo patrón visual que cliente_deuda_total_
 * imprimir.js / cuentas_cobrar_imprimir.js.
 *
 * Expone: clienteHistorialImprimir(cliente, historial, ventanaPrevia)
 *   - historial: array como el que arma
 *     core.services_estadisticas.cliente_perfil.historial_cliente()
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _chiEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _chiFmtMoneda(v, moneda) {
    const codigo = ['ARS', 'USD', 'EUR'].includes(moneda) ? moneda : 'ARS';
    return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${codigo}`;
}

function _chiFecha(iso) {
    if (!iso) return '-';
    const [anio, mes, dia] = iso.slice(0, 10).split('-');
    return `${dia}/${mes}/${anio}`;
}

function _chiEmpresaHtml(emp) {
    const nombre = emp.nombre || emp.razon_social || '';
    const razon = emp.razon_social && emp.razon_social !== nombre ? emp.razon_social : '';
    const contacto = [emp.domicilio, emp.telefono ? `Tel: ${emp.telefono}` : '', emp.email]
        .filter(Boolean).map(_chiEsc).join(' · ');
    const fiscal = [emp.cuit ? `CUIT: ${emp.cuit}` : '', emp.condicion_iva]
        .filter(Boolean).map(_chiEsc).join(' · ');
    if (!emp.logo_url && !nombre && !contacto && !fiscal && !emp.eslogan) return '';
    return `<header class="chi-membrete">
        <div class="chi-marca">
            ${emp.logo_url ? `<img class="chi-logo" src="${_chiEsc(emp.logo_url)}" alt="Logo">` : ''}
            <div>
                ${nombre ? `<div class="chi-empresa-nombre">${_chiEsc(nombre)}</div>` : ''}
                ${emp.eslogan ? `<div class="chi-eslogan">${_chiEsc(emp.eslogan)}</div>` : ''}
            </div>
        </div>
        <div class="chi-empresa-datos">
            ${razon ? `<div>${_chiEsc(razon)}</div>` : ''}
            ${contacto ? `<div>${contacto}</div>` : ''}
            ${fiscal ? `<div>${fiscal}</div>` : ''}
        </div>
    </header>`;
}

function _chiClienteHtml(cliente) {
    const datos = [
        cliente.dni ? `DNI: ${cliente.dni}` : '',
        cliente.cuil ? `CUIL: ${cliente.cuil}` : '',
        cliente.cuit ? `CUIT: ${cliente.cuit}` : '',
        (!cliente.dni && !cliente.cuil && !cliente.cuit && cliente.documento) ? `Documento: ${cliente.documento}` : '',
        cliente.condicion_iva ? `IVA: ${cliente.condicion_iva}` : '',
        cliente.direccion ? `Domicilio: ${cliente.direccion}` : '',
        cliente.email ? `Email: ${cliente.email}` : '',
    ].filter(Boolean).map(_chiEsc).join(' · ');
    return `<section class="chi-cliente">
        <span>Cliente</span><strong>${_chiEsc(cliente.nombre)}</strong>
        ${datos ? `<div>${datos}</div>` : ''}
    </section>`;
}

/**
 * @param {object} cliente - {pk, nombre}
 * @param {object[]} historial - filas {fecha, tipo, descripcion, monto, saldo, medio_pago}
 * @param {Window} [ventanaPrevia]
 */
function clienteHistorialImprimir(cliente, historial, ventanaPrevia) {
    const emp = (typeof window !== 'undefined' && window.KAI_EMPRESA) || {};
    if (!historial || !historial.length) {
        if (ventanaPrevia) ventanaPrevia.close();
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('Este cliente todavía no tiene historial para imprimir.', 'warning');
        }
        return;
    }

    const filas = historial.map(f => `
        <tr>
            <td>${_chiFecha(f.fecha)}</td>
            <td>${_chiEsc(f.descripcion)}</td>
            <td>${_chiEsc(f.medio_pago || '-')}</td>
            <td class="chi-monto">${_chiFmtMoneda(f.monto, f.moneda)}</td>
            <td class="chi-monto">${f.saldo != null ? _chiFmtMoneda(f.saldo, f.moneda) : '—'}</td>
        </tr>`).join('');

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Historial — ${_chiEsc(cliente.nombre)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 800px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .chi-membrete { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid #1E6FA8; page-break-inside: avoid; }
    .chi-marca { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .chi-logo { display: block; max-width: 170px; max-height: 58px; object-fit: contain; }
    .chi-empresa-nombre { font-size: 1.05rem; font-weight: 700; }
    .chi-eslogan { margin-top: 2px; color: #40536A; font-size: .75rem; font-style: italic; }
    .chi-empresa-datos { max-width: 55%; color: #26364A; font-size: .75rem; line-height: 1.45; text-align: right; }
    .chi-cliente { margin: 0 0 18px; padding: 9px 12px; border: 1px solid #B7CEDC; background: #F7FAFC; font-size: .8125rem; line-height: 1.45; }
    .chi-cliente > span { margin-right: 8px; color: #1E6FA8; font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
    .chi-cliente div { margin-top: 3px; color: #40536A; font-size: .75rem; }
    .chi-subtitulo { color: #555; font-size: .875rem; margin: 0 0 20px; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .chi-monto { text-align: right; white-space: nowrap; }
    .chi-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } thead { display: table-header-group; } }
</style>
</head>
<body>
    ${_chiEmpresaHtml(emp)}
    <h1>Historial de ventas y pagos</h1>
    <p class="chi-subtitulo">Generado al ${new Date().toLocaleDateString('es-AR')} — ${historial.length} movimiento${historial.length === 1 ? '' : 's'}, ordenado de más reciente a más antiguo</p>
    ${_chiClienteHtml(cliente)}
    <table>
        <thead>
            <tr><th>Fecha</th><th>Descripción</th><th>Medio de pago</th><th class="chi-monto">Monto</th><th class="chi-monto">Saldo</th></tr>
        </thead>
        <tbody>${filas}</tbody>
    </table>
    <p class="chi-footer">Generado desde Kairos.</p>
    <script>window.onload = function () { setTimeout(function () { window.print(); }, 150); };</script>
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
