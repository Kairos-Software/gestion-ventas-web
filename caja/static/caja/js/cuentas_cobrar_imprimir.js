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
    return `
        @page { size: ${ancho}mm auto; margin: 0; }
        html, body { width: ${ancho}mm; max-width: ${ancho}mm; margin: 0; }
        body { padding: ${padding}; font-size: ${fuente}; }
        h1 { font-size: 12pt; line-height: 1.25; }
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
    <h1>Cuenta por cobrar — ${_ciEsc(cxc.cliente_nombre || ('#' + cxc.pk))}</h1>
    <p class="ci-subtitulo">Estado de cuenta al ${new Date().toLocaleDateString('es-AR')}</p>
    ${cxc.es_carga_inicial ? '<div class="ci-badge">Carga inicial</div>' : ''}
    <div class="ci-resumen">
        ${cxc.numero_comprobante ? `<div><span>N° de comprobante</span><strong>${_ciEsc(cxc.numero_comprobante)}</strong></div>` : ''}
        <div><span>Cliente</span><strong>${_ciEsc(cxc.cliente_nombre)}</strong></div>
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
