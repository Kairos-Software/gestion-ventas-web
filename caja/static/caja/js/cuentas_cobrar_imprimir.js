/**
 * cuentas_cobrar_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Genera un "estado de cuenta" imprimible de una CuentaPorCobrar
 * (encabezado + tabla de cuotas con su estado real + documentos
 * adjuntos) y lo abre en una ventana nueva que dispara el diálogo de
 * impresión del navegador — mirror de caja/static/caja/js/deudas_
 * imprimir.js, en espejo (cobro, no pago) y con la sección de
 * documentos agregada (más relevante acá por el caso de carga inicial).
 *
 * Expone: cxcImprimir(cxc, formato, ventanaPrevia) — formatos: a4,
 * termica80 o termica58. La firma anterior (cxc, ventana) sigue válida.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _ciEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _ciFmtMoneda(v, moneda) {
    return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${moneda || ''}`.trim();
}

function _ciEstadoLabel(c) {
    // Este texto lo lee el cliente, no el dueño — no le interesa si fue
    // por cheque, con qué cuenta, o si es carga inicial "que no afectó
    // caja" (jerga interna); solo le interesa si está pagada o no.
    if (c.estado === 'confirmada') return 'Pagada';
    if (c.estado === 'anulada') return 'Anulada';
    return 'Pendiente';
}

function _ciEmpresaHtml(emp) {
    const nombre = emp.nombre || emp.razon_social || '';
    const razon = emp.razon_social && emp.razon_social !== nombre ? emp.razon_social : '';
    const contacto = [emp.domicilio, emp.telefono ? `Tel: ${emp.telefono}` : '', emp.email]
        .filter(Boolean).map(_ciEsc).join(' · ');
    const fiscal = [emp.cuit ? `CUIT: ${emp.cuit}` : '', emp.condicion_iva]
        .filter(Boolean).map(_ciEsc).join(' · ');
    if (!emp.logo_url && !nombre && !contacto && !fiscal && !emp.eslogan) return '';
    return `<header class="ci-membrete">
        <div class="ci-marca">
            ${emp.logo_url ? `<img class="ci-logo" src="${_ciEsc(emp.logo_url)}" alt="Logo">` : ''}
            <div>
                ${nombre ? `<div class="ci-empresa-nombre">${_ciEsc(nombre)}</div>` : ''}
                ${emp.eslogan ? `<div class="ci-eslogan">${_ciEsc(emp.eslogan)}</div>` : ''}
            </div>
        </div>
        <div class="ci-empresa-datos">
            ${razon ? `<div>${_ciEsc(razon)}</div>` : ''}
            ${contacto ? `<div>${contacto}</div>` : ''}
            ${fiscal ? `<div>${fiscal}</div>` : ''}
        </div>
    </header>`;
}

function _ciClienteHtml(cxc) {
    const datos = [
        cxc.cliente_codigo ? `Código: ${cxc.cliente_codigo}` : '',
        cxc.cliente_documento ? `Documento: ${cxc.cliente_documento}` : '',
        cxc.cliente_condicion_iva ? `IVA: ${cxc.cliente_condicion_iva}` : '',
        cxc.cliente_direccion ? `Domicilio: ${cxc.cliente_direccion}` : '',
        cxc.cliente_email ? `Email: ${cxc.cliente_email}` : '',
    ].filter(Boolean).map(_ciEsc).join(' · ');
    return `<section class="ci-cliente">
        <span>Cliente</span><strong>${_ciEsc(cxc.cliente_nombre || '—')}</strong>
        ${datos ? `<div>${datos}</div>` : ''}
    </section>`;
}

function _ciResolverSalida(formato, ventanaPrevia) {
    if (formato && typeof formato !== 'string') {
        return { formato: 'a4', ventana: formato };
    }
    const valor = ['a4', 'termica80', 'termica58'].includes(formato) ? formato : 'a4';
    return { formato: valor, ventana: ventanaPrevia || null };
}

function _ciCssFormato(formato) {
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
        .ci-membrete { display: block; margin-bottom: 12px; padding-bottom: 9px; text-align: center; }
        .ci-marca { display: block; }
        .ci-logo { max-width: ${logoAncho}; max-height: ${logoAlto}; margin: 0 auto 5px; }
        .ci-empresa-nombre { font-size: 10pt; }
        .ci-eslogan, .ci-empresa-datos { max-width: none; margin-top: 2px; font-size: 7pt; line-height: 1.35; text-align: center; overflow-wrap: anywhere; }
        .ci-cliente { margin-bottom: 10px; padding: 7px; font-size: ${fuente}; overflow-wrap: anywhere; }
        .ci-cliente > span { display: block; margin: 0 0 2px; }
        .ci-cliente div { font-size: 7pt; }
        .ci-subtitulo { font-size: 8pt; margin-bottom: 12px; }
        .ci-resumen { grid-template-columns: 1fr; gap: 0; margin-bottom: 12px; font-size: ${fuente}; }
        .ci-resumen div { gap: 8px; padding: 3px 0; }
        .ci-resumen strong { text-align: right; overflow-wrap: anywhere; }
        .ci-badge { margin-bottom: 8px; }
        table, tbody { display: block; width: 100%; }
        thead { display: none; }
        tr { display: block; padding: 5px 0; border-top: 1px dashed #777; page-break-inside: avoid; }
        td { display: flex; justify-content: space-between; gap: 8px; border: 0; padding: 1px 0; text-align: right; }
        td::before { content: attr(data-label); color: #555; font-weight: normal; text-align: left; }
        .ci-monto { text-align: right; font-weight: bold; }
        .ci-subtitulo-seccion { font-size: 9pt; margin-top: 14px; }
        .ci-docs { padding-left: 15px; font-size: 7.5pt; overflow-wrap: anywhere; }
        .ci-footer { margin-top: 14px; font-size: 7pt; text-align: center; }
    `;
}

/**
 * @param {object} cxc
 * @param {'a4'|'termica80'|'termica58'} [formato]
 * @param {Window} [ventanaPrevia] - Ventana ya abierta (window.open llamado
 *   de forma síncrona en el click, antes de cualquier `await`) para no
 *   perder el gesto del usuario y que el navegador no bloquee el popup.
 *   Si no se pasa, la abre acá mismo (caso de uso sin async de por medio).
 */
function cxcImprimir(cxc, formato, ventanaPrevia) {
    const emp = (typeof window !== 'undefined' && window.KAI_EMPRESA) || {};
    const salida = _ciResolverSalida(formato, ventanaPrevia);
    formato = salida.formato;
    ventanaPrevia = salida.ventana;
    const filasCuotas = (cxc.cuotas || []).map(c => `
        <tr>
            <td data-label="Cuota">${c.numero}</td>
            <td data-label="Vencimiento">${_ciEsc(c.fecha_vencimiento)}</td>
            <td data-label="Monto" class="ci-monto">${_ciFmtMoneda(c.monto, cxc.moneda)}</td>
            <td data-label="Estado">${_ciEsc(_ciEstadoLabel(c))}</td>
            <td data-label="Fecha de cobro">${c.fecha_confirmacion ? _ciEsc(c.fecha_confirmacion.slice(0, 10)) : '-'}</td>
        </tr>`).join('');

    const documentos = cxc.documentos || [];
    const seccionDocumentos = documentos.length ? `
    <h3 class="ci-subtitulo-seccion">Documentos adjuntos</h3>
    <ul class="ci-docs">
        ${documentos.map(doc => `<li>${_ciEsc(doc.tipo_label)}: ${_ciEsc(doc.nombre)}${doc.descripcion ? ' — ' + _ciEsc(doc.descripcion) : ''} (${_ciEsc(doc.subido_el)})</li>`).join('')}
    </ul>` : '';

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Cuenta por cobrar — ${_ciEsc(cxc.cliente_nombre || ('#' + cxc.pk))}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 720px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .ci-membrete { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid #1E6FA8; page-break-inside: avoid; }
    .ci-marca { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .ci-logo { display: block; max-width: 170px; max-height: 58px; object-fit: contain; }
    .ci-empresa-nombre { font-size: 1.05rem; font-weight: 700; }
    .ci-eslogan { margin-top: 2px; color: #40536A; font-size: .75rem; font-style: italic; }
    .ci-empresa-datos { max-width: 55%; color: #26364A; font-size: .75rem; line-height: 1.45; text-align: right; }
    .ci-cliente { margin: 0 0 18px; padding: 9px 12px; border: 1px solid #B7CEDC; background: #F7FAFC; font-size: .8125rem; line-height: 1.45; }
    .ci-cliente > span { margin-right: 8px; color: #1E6FA8; font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
    .ci-cliente div { margin-top: 3px; color: #40536A; font-size: .75rem; }
    .ci-subtitulo { color: #555; font-size: .875rem; margin: 0 0 20px; }
    .ci-resumen { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 20px; font-size: .875rem; }
    .ci-resumen div { display: flex; justify-content: space-between; border-bottom: 1px solid #eee; padding: 3px 0; }
    .ci-resumen span { color: #666; }
    .ci-badge { display: inline-block; background: #f3f0ff; color: #5b21b6; border-radius: 4px; padding: 2px 8px; font-size: .75rem; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .ci-monto { text-align: right; }
    .ci-subtitulo-seccion { font-size: 0.95rem; margin: 20px 0 8px; }
    .ci-docs { font-size: .8125rem; padding-left: 20px; margin: 0; }
    .ci-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } }
    ${_ciCssFormato(formato)}
</style>
</head>
<body>
    ${_ciEmpresaHtml(emp)}
    <h1>Cuenta por cobrar</h1>
    <p class="ci-subtitulo">Estado de cuenta al ${new Date().toLocaleDateString('es-AR')}</p>
    ${_ciClienteHtml(cxc)}
    ${cxc.es_carga_inicial ? '<div class="ci-badge">Carga inicial</div>' : ''}
    <div class="ci-resumen">
        ${cxc.numero_comprobante ? `<div><span>N° de comprobante</span><strong>${_ciEsc(cxc.numero_comprobante)}</strong></div>` : ''}
        ${cxc.venta_numero ? `<div><span>Venta</span><strong>${_ciEsc(cxc.venta_numero)}</strong></div>` : ''}
        <div><span>Monto original</span><strong>${_ciFmtMoneda(cxc.monto_original, cxc.moneda)}</strong></div>
        <div><span>Interés</span><strong>${_ciEsc(cxc.porcentaje_interes)}%</strong></div>
        <div><span>Monto total</span><strong>${_ciFmtMoneda(cxc.monto_total, cxc.moneda)}</strong></div>
        <div><span>Saldo pendiente</span><strong>${_ciFmtMoneda(cxc.saldo_pendiente, cxc.moneda)}</strong></div>
        <div><span>Cuotas cobradas</span><strong>${cxc.cuotas_cobradas}/${cxc.cantidad_cuotas || '-'}</strong></div>
        <div><span>Estado</span><strong>${_ciEsc(cxc.estado_display)}</strong></div>
    </div>
    <table>
        <thead>
            <tr><th>#</th><th>Vencimiento</th><th class="ci-monto">Monto</th><th>Estado</th><th>Fecha de cobro</th></tr>
        </thead>
        <tbody>${filasCuotas}</tbody>
    </table>
    ${seccionDocumentos}
    <p class="ci-footer">Generado desde Kairos.</p>
    <script>window.onload = function () { setTimeout(function () { window.print(); }, 150); };</script>
</body>
</html>`;

    const anchoVentana = formato === 'a4' ? 800 : (formato === 'termica80' ? 440 : 360);
    const ventana = ventanaPrevia || window.open('', '_blank', `width=${anchoVentana},height=950`);
    if (!ventana) {
        KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio e intentá de nuevo.', 'warning', 6000);
        return;
    }
    ventana.document.write(html);
    ventana.document.close();
}
