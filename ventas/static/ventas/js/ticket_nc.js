/**
 * ticket_nc.js
 * ─────────────────────────────────────────────────────────────────
 * Generador de HTML para imprimir una Nota de Crédito ARCA como
 * documento propio — mismo nivel que una factura (selector de formato,
 * ítems devueltos, IVA discriminado si corresponde, CAE, QR), pero
 * mucho más corto que un ticket de venta completo: no lleva desglose
 * de pagos/recargos, solo lo que hace falta para justificar el crédito.
 *
 * Exporta: ncHtmlA4(data), ncHtmlTermica80(data), ncHtmlTermica58(data)
 *   → string HTML completo cada una.
 *
 * El parámetro `data` es UNA ENTRADA de window.NC_DATA (definido en
 * _detalle_venta_datos.html), no todo el array:
 * {
 *   devolucion_pk: 123,
 *   comprobante_original_display: "Factura B 0003-00000045",
 *   items: [ { nombre, cantidad, precio_unitario, subtotal }, ... ],
 *   nc: { tipo_display, tipo_comprobante, numero_display, cae,
 *         cae_vencimiento, importe_total, importe_neto, importe_iva,
 *         receptor_documento, receptor_condicion_iva, iva_grupos,
 *         qrDataUrl } | null,
 * }
 *
 * Reusa _esc()/_fmtNum() de ticket_a4.js (cargado antes en el template)
 * — no se duplican acá. Los datos de la empresa/cliente se leen de
 * window.TICKET_DATA (misma página, ya cargado) — no hace falta
 * duplicarlos en cada entrada de NC_DATA.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _ncEmpresaYCliente() {
    const td = window.TICKET_DATA || {};
    return { emp: td.empresa || {}, cliente: td.cliente || null };
}

/**
 * Genera el HTML completo de la Nota de Crédito en formato A4.
 * @param {object} data  Una entrada de window.NC_DATA.
 * @param {object} [opts]
 * @param {boolean} [opts.duplicado]  Aclara "Duplicado" en vez de
 *   "Original" — mismo comprobante ya emitido, solo cambia esa leyenda.
 * @param {boolean} [opts.sinAutoImpresion]  No incluir el <script> que
 *   dispara window.print() solo — lo usa ticket_pdf.js, que rasteriza
 *   este HTML en un iframe oculto (nunca se muestra ni se imprime).
 * @returns {string}
 */
function ncHtmlA4(data, opts) {
    const esDuplicado = !!(opts && opts.duplicado);
    const sinAutoImpresion = !!(opts && opts.sinAutoImpresion);
    const { emp, cliente } = _ncEmpresaYCliente();
    const items = data.items || [];
    const nc = data.nc || null;
    const letra = nc ? String(nc.tipo_display || '').trim().slice(-1) : '';
    const cod = nc ? String(nc.tipo_comprobante).padStart(3, '0') : '';

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>${nc ? _esc(nc.tipo_display) : 'Nota de Crédito'} — ${nc ? _esc(nc.numero_display) : ''}</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        html, body {
            width: 210mm;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10.5pt;
            color: #0D1B2A;
            background: #fff;
        }
        body { padding: 9mm 10mm 13mm; }

        .nc-header {
            display: flex;
            align-items: stretch;
            gap: 0;
            margin-bottom: 9pt;
            padding: 10pt 12pt;
            border: 1px solid #86AFC8;
        }
        .nc-header-col { flex: 1 1 0; }
        .nc-header-comprobante { text-align: right; }
        .nc-header-divider {
            flex: 0 0 auto;
            width: 82pt;
            padding: 0 10pt;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .nc-tipo-box {
            width: 100%;
            text-align: center;
            border: 1.5px solid #0D1B2A;
            padding: 4pt 0;
        }
        .nc-tipo-letra { font-size: 24pt; font-weight: 800; line-height: 1; }
        .nc-tipo-cod { font-size: 6.5pt; font-weight: 700; margin-top: 2pt; }

        .nc-empresa-nombre { font-size: 13pt; font-weight: 800; color: #1E6FA8; }
        .nc-empresa-dato { font-size: 8.5pt; color: #26364A; margin-top: 2pt; }

        .nc-original-label { font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #26364A; }
        .nc-titulo { font-size: 14pt; font-weight: 800; color: #0D1B2A; margin-top: 2pt; }
        .nc-numero-grande { font-size: 13pt; font-weight: 700; color: #1E6FA8; margin-top: 2pt; font-variant-numeric: tabular-nums; }
        .nc-meta { font-size: 8.5pt; color: #26364A; margin-top: 6pt; line-height: 1.5; }

        .nc-corrige {
            margin-bottom: 9pt;
            padding: 8pt 12pt;
            background: #F4F6F9;
            border-left: 4pt solid #F26A1B;
            font-size: 9.5pt;
            color: #26364A;
        }
        .nc-corrige b { color: #0D1B2A; }

        .nc-info-box {
            margin-bottom: 9pt;
            padding: 8pt 12pt;
            border: 1px solid #86AFC8;
        }
        .nc-info-label {
            font-size: 7.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .05em;
            color: #1E6FA8;
            margin-bottom: 4pt;
        }
        .nc-info-dato { font-size: 9pt; color: #26364A; }

        table.nc-table { width: 100%; border-collapse: collapse; margin-bottom: 9pt; font-size: 9pt; }
        table.nc-table th {
            text-align: left;
            font-size: 7.5pt;
            text-transform: uppercase;
            letter-spacing: .04em;
            color: #1E6FA8;
            border-bottom: 1.5px solid #0D1B2A;
            padding: 4pt 6pt;
        }
        table.nc-table td { padding: 4pt 6pt; border-bottom: 1px solid #D8E2EA; }
        table.nc-table td.nc-num { text-align: right; font-variant-numeric: tabular-nums; }

        .nc-totales { display: flex; justify-content: flex-end; margin-bottom: 9pt; }
        .nc-totales-box { min-width: 220pt; }
        .nc-totales-row { display: flex; justify-content: space-between; font-size: 9pt; color: #26364A; padding: 1.5pt 0; }
        .nc-total-final-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            border-top: 1.5px solid #0D1B2A;
            margin-top: 6pt;
            padding-top: 6pt;
            font-size: 13pt;
            font-weight: 800;
            color: #0D1B2A;
        }
        .nc-total-final-row span:last-child { color: #F26A1B; }

        .nc-comprobante {
            display: flex;
            align-items: center;
            gap: 12pt;
            margin-bottom: 9pt;
            padding: 8pt 12pt;
            background: #fff;
            border: 1px solid #86AFC8;
            border-left: 4pt solid #1E6FA8;
        }
        .nc-comprobante-qr { width: 60pt; height: 60pt; flex: 0 0 auto; background: #fff; padding: 2pt; }
        .nc-comprobante-datos { font-size: 8.5pt; color: #0D1B2A; line-height: 1.4; }
        .nc-comprobante-label {
            font-size: 7.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .05em;
            color: #1E6FA8;
            margin-bottom: 4pt;
        }
        .nc-comprobante-datos b { font-variant-numeric: tabular-nums; }

        .nc-arca-oficial {
            display: flex;
            align-items: center;
            gap: 12pt;
            padding: 8pt 2pt 0;
            border-top: 1.5px solid #1E6FA8;
            font-size: 8pt;
            color: #26364A;
        }
        .nc-arca-wordmark { flex: 0 0 auto; font-size: 17pt; font-weight: 800; letter-spacing: -.02em; color: #172842; }
        .nc-arca-separador { align-self: stretch; width: 1px; min-height: 25pt; margin: 0 7pt; background: #1E6FA8; }
        .nc-arca-disclaimer { font-style: italic; font-size: 7.5pt; color: #40536A; margin-top: 2pt; }

        @media print {
            html, body { width: auto; }
            body { padding: 0; }
            @page { size: A4; margin: 9mm 10mm 13mm; }
        }
    </style>
</head>
<body>

    <div class="nc-header">
        <div class="nc-header-col">
            <div class="nc-empresa-nombre">${_esc(emp.nombre)}</div>
            ${emp.razon_social ? `<div class="nc-empresa-dato">${_esc(emp.razon_social)}</div>` : ''}
            ${emp.domicilio ? `<div class="nc-empresa-dato">${_esc(emp.domicilio)}</div>` : ''}
            ${emp.cuit ? `<div class="nc-empresa-dato">CUIT: ${_esc(emp.cuit)}</div>` : ''}
            ${emp.condicion_iva ? `<div class="nc-empresa-dato">Condición frente al IVA: ${_esc(emp.condicion_iva)}</div>` : ''}
        </div>
        ${nc ? `
        <div class="nc-header-divider">
            <div class="nc-tipo-box">
                <div class="nc-tipo-letra">${_esc(letra)}</div>
                <div class="nc-tipo-cod">COD. ${_esc(cod)}</div>
            </div>
        </div>` : ''}
        <div class="nc-header-col nc-header-comprobante">
            <div class="nc-original-label">${esDuplicado ? 'Duplicado' : 'Original'}</div>
            <div class="nc-titulo">${nc ? _esc(nc.tipo_display) : 'Nota de Crédito'}</div>
            <div class="nc-numero-grande">${nc ? _esc(nc.numero_display) : ''}</div>
            <div class="nc-meta">Fecha: ${_esc(_ncFechaDocumento(data))}</div>
        </div>
    </div>

    <div class="nc-corrige">
        Corrige: <b>${_esc(data.comprobante_original_display)}</b>
    </div>

    <div class="nc-info-box">
        <div class="nc-info-label">Datos del cliente</div>
        <div class="nc-info-dato">${_ncClienteTexto(cliente, nc)}</div>
    </div>

    <table class="nc-table">
        <thead>
            <tr><th>Producto</th><th>Cantidad</th><th>Precio unit.</th><th>Subtotal</th></tr>
        </thead>
        <tbody>
            ${items.map(it => `<tr>
                <td>${_esc(it.nombre)}</td>
                <td class="nc-num">${_esc(it.cantidad)}</td>
                <td class="nc-num">$${_fmtNum(it.precio_unitario)}</td>
                <td class="nc-num">$${_fmtNum(it.subtotal)}</td>
            </tr>`).join('')}
        </tbody>
    </table>

    <div class="nc-totales">
        <div class="nc-totales-box">
            ${_ncTotalesFilas(nc)}
            <div class="nc-total-final-row">
                <span>Total acreditado</span>
                <span>$${_fmtNum(nc ? nc.importe_total : 0)}</span>
            </div>
        </div>
    </div>

    ${_ncComprobanteBox(nc)}

    ${nc ? `
    <div class="nc-arca-oficial">
        <div class="nc-arca-wordmark">ARCA</div>
        <div class="nc-arca-separador"></div>
        <div>
            <strong>Comprobante Autorizado</strong>
            <div class="nc-arca-disclaimer">Esta Agencia no se responsabiliza por los datos ingresados en el detalle de la operación.</div>
        </div>
    </div>` : ''}

${sinAutoImpresion ? '' : `
    <script>
        window.addEventListener('load', function () {
            setTimeout(function () { window.print(); }, 150);
        });
        window.addEventListener('afterprint', function () { window.close(); });
    </script>
`}
</body>
</html>`;
}

/**
 * Genera el HTML de la Nota de Crédito para impresora térmica (80mm o
 * 58mm) — mismo criterio visual que ticket_termica_80.js/58.js: fuente
 * monoespaciada, sin colores, texto grande para el total.
 * @param {object} data  Una entrada de window.NC_DATA.
 * @param {number} papelMm  Ancho nominal del rollo: 80 o 58 mm.
 * @param {number} contenidoMm  Ancho imprimible real: 72 o 48 mm.
 * @param {string} formato  Sufijo CSS del formato: "80" o "58".
 * @param {object} [opts]
 * @param {boolean} [opts.sinAutoImpresion]  Ver ncHtmlA4.
 */
function _ncHtmlTermica(data, papelMm, contenidoMm, formato, opts) {
    const esDuplicado = !!(opts && opts.duplicado);
    const sinAutoImpresion = !!(opts && opts.sinAutoImpresion);
    const { emp, cliente } = _ncEmpresaYCliente();
    const items = data.items || [];
    const nc = data.nc || null;
    const letra = nc ? String(nc.tipo_display || '').trim().slice(-1) : '';
    const cod = nc ? String(nc.tipo_comprobante).padStart(3, '0') : '';
    const es58 = formato === '58';
    const prefijo = `nct${formato}`;

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Nota de Crédito ${papelMm}mm — ${nc ? _esc(nc.numero_display) : ''}</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            width: ${contenidoMm}mm;
            font-family: 'Courier New', Courier, monospace;
            font-size: ${es58 ? '7.5pt' : '9pt'};
            color: #000;
            background: #fff;
        }
        body { padding: ${es58 ? '2mm 1.5mm 8mm' : '3mm 2mm 8mm'}; }
        .${prefijo}-center { text-align: center; }
        .${prefijo}-bold { font-weight: bold; }
        .${prefijo}-peq { font-size: ${es58 ? '6.5pt' : '8pt'}; font-weight: 600; line-height: 1.45; }
        .${prefijo}-logo {
            display: block;
            max-width: ${es58 ? '150px' : '260px'};
            max-height: ${es58 ? '58px' : '90px'};
            margin: 0 auto 3pt;
            filter: grayscale(1) contrast(1.6) brightness(1.05);
        }
        .${prefijo}-empresa { font-size: ${es58 ? '8.5pt' : '11pt'}; font-weight: bold; text-align: center; margin-bottom: 2pt; }
        .${prefijo}-empresa-dato { font-size: ${es58 ? '6.3pt' : '8pt'}; font-weight: 600; text-align: center; line-height: 1.45; overflow-wrap: anywhere; }
        .${prefijo}-sep-doble { border: 0; border-top: 2px solid #000; margin: 4pt 0; }
        .${prefijo}-sep-simple { border: 0; border-top: 1px dashed #000; margin: 3pt 0; }
        .${prefijo}-doc-head { display: flex; align-items: center; justify-content: center; gap: ${es58 ? '5pt' : '8pt'}; padding: 3pt 0; }
        .${prefijo}-doc-letter { min-width: ${es58 ? '21pt' : '25pt'}; padding: 2pt; border: 1.5px solid #000; font-size: ${es58 ? '13pt' : '15pt'}; font-weight: bold; line-height: 1; text-align: center; }
        .${prefijo}-doc-letter small { display: block; margin-top: 2pt; font-size: ${es58 ? '5pt' : '5.8pt'}; line-height: 1.1; }
        .${prefijo}-original { font-size: ${es58 ? '5.8pt' : '6.5pt'}; font-weight: bold; letter-spacing: .08em; text-align: center; text-transform: uppercase; }
        .${prefijo}-titulo { font-size: ${es58 ? '8pt' : '9.5pt'}; font-weight: bold; text-align: center; margin-top: 2pt; }
        .${prefijo}-meta { font-size: ${es58 ? '6.5pt' : '8pt'}; font-weight: 600; text-align: center; line-height: 1.45; }
        .${prefijo}-seccion { font-size: ${es58 ? '6.3pt' : '7.5pt'}; font-weight: bold; letter-spacing: .05em; text-transform: uppercase; margin: 3pt 0 2pt; }
        .${prefijo}-cliente { text-align: center; margin: 2pt 0; overflow-wrap: anywhere; }
        .${prefijo}-cliente-nombre { font-size: ${es58 ? '7pt' : '8.5pt'}; font-weight: bold; }
        .${prefijo}-corrige { border: 1px solid #000; padding: 3pt; margin: 3pt 0; font-size: ${es58 ? '6.3pt' : '8pt'}; font-weight: 600; line-height: 1.4; overflow-wrap: anywhere; }
        .${prefijo}-items-head { display: flex; justify-content: space-between; border-bottom: 1px solid #000; padding-bottom: 2pt; margin-bottom: 4pt; font-size: ${es58 ? '6pt' : '7pt'}; font-weight: bold; text-transform: uppercase; }
        .${prefijo}-item { margin-bottom: ${es58 ? '3pt' : '4pt'}; page-break-inside: avoid; }
        .${prefijo}-item-nombre { font-size: ${es58 ? '7pt' : '8.5pt'}; font-weight: bold; overflow-wrap: anywhere; }
        .${prefijo}-row { display: flex; justify-content: space-between; align-items: baseline; gap: 3pt; }
        .${prefijo}-item-detalle { font-size: ${es58 ? '6.3pt' : '8pt'}; font-weight: 600; margin-top: 1pt; }
        .${prefijo}-total-row { display: flex; justify-content: space-between; gap: 3pt; font-size: ${es58 ? '6.6pt' : '8.5pt'}; font-weight: 600; line-height: 1.65; }
        .${prefijo}-total { display: flex; justify-content: space-between; gap: 3pt; margin-top: 2pt; font-size: ${es58 ? '11.5pt' : '14pt'}; font-weight: bold; }
        .${prefijo}-fiscal { border: 1.5px solid #000; padding: ${es58 ? '4pt 3pt' : '5pt 4pt'}; margin: 4pt 0; text-align: ${es58 ? 'center' : 'left'}; page-break-inside: avoid; }
        .${prefijo}-fiscal-label { font-size: ${es58 ? '6.2pt' : '8pt'}; font-weight: bold; letter-spacing: .04em; text-transform: uppercase; text-align: center; margin-bottom: 3pt; }
        .${prefijo}-fiscal-contenido { display: ${es58 ? 'block' : 'flex'}; align-items: center; gap: 6pt; }
        .${prefijo}-qr { display: block; width: ${es58 ? '24mm' : '25mm'}; height: ${es58 ? '24mm' : '25mm'}; margin: ${es58 ? '2pt auto' : '0'}; flex: 0 0 auto; image-rendering: crisp-edges; }
        .${prefijo}-fiscal-datos { flex: 1 1 0; overflow-wrap: anywhere; }
        .${prefijo}-arca { text-align: center; font-size: ${es58 ? '6pt' : '7.2pt'}; font-weight: 600; line-height: 1.35; margin-top: 4pt; }
        .${prefijo}-arca strong { display: block; font-size: ${es58 ? '9pt' : '11pt'}; letter-spacing: .04em; }
        @media print {
            html, body { width: auto; }
            body { padding: 0 ${es58 ? '1.5mm' : '2mm'} 8mm; }
            @page { size: ${papelMm}mm auto; margin: ${es58 ? '1mm 1mm 0' : '2mm 1mm 0'}; }
        }
    </style>
</head>
<body>
    ${emp.logo_url ? `<img class="${prefijo}-logo" src="${_esc(emp.logo_url)}" alt="Logo">` : ''}
    <div class="${prefijo}-empresa">${_esc(emp.nombre)}</div>
    ${emp.razon_social ? `<div class="${prefijo}-empresa-dato">${_esc(emp.razon_social)}</div>` : ''}
    ${emp.domicilio ? `<div class="${prefijo}-empresa-dato">Dom: ${_esc(emp.domicilio)}</div>` : ''}
    ${emp.cuit ? `<div class="${prefijo}-empresa-dato">CUIT: ${_esc(emp.cuit)}</div>` : ''}
    ${emp.condicion_iva ? `<div class="${prefijo}-empresa-dato">IVA: ${_esc(emp.condicion_iva)}</div>` : ''}
    ${(nc || emp.ingresos_brutos) ? `<div class="${prefijo}-empresa-dato">IIBB: ${_esc(emp.ingresos_brutos || '—')}</div>` : ''}
    ${(nc || emp.fecha_inicio_actividades) ? `<div class="${prefijo}-empresa-dato">Inicio act.: ${_esc(emp.fecha_inicio_actividades || '—')}</div>` : ''}

    <hr class="${prefijo}-sep-doble">
    <div class="${prefijo}-doc-head">
        ${nc ? `<div class="${prefijo}-doc-letter">${_esc(letra)}<small>COD. ${_esc(cod)}</small></div>` : ''}
        <div>
            <div class="${prefijo}-original">${esDuplicado ? 'Duplicado' : 'Original'}</div>
            <div class="${prefijo}-titulo">${nc ? _esc(nc.tipo_display).toUpperCase() : 'NOTA DE CRÉDITO'}</div>
            <div class="${prefijo}-titulo">${nc ? _esc(nc.numero_display) : ''}</div>
        </div>
    </div>
    <div class="${prefijo}-meta">Fecha: ${_esc(_ncFechaDocumento(data))}</div>

    <div class="${prefijo}-corrige"><strong>Comprobante asociado</strong><br>${_esc(data.comprobante_original_display || '—')}</div>

    <div class="${prefijo}-seccion">Datos del cliente</div>
    ${_ncClienteTermica(cliente, nc, prefijo)}

    <hr class="${prefijo}-sep-simple">
    <div class="${prefijo}-items-head"><span>Producto / servicio</span><span>Subtotal</span></div>
    ${items.map(it => `<div class="${prefijo}-item">
        <div class="${prefijo}-item-nombre">${_esc(it.nombre)}</div>
        <div class="${prefijo}-row ${prefijo}-item-detalle">
            <span>${_esc(_ncCantidadDisplay(it.cantidad))} x $ ${_fmtNum(it.precio_unitario)}</span>
            <strong>$ ${_fmtNum(it.subtotal)}</strong>
        </div>
    </div>`).join('')}

    <hr class="${prefijo}-sep-doble">
    ${_ncTotalesFilasTermica(nc, prefijo, items)}
    <div class="${prefijo}-total"><span>TOTAL</span><span>$${_fmtNum(nc ? nc.importe_total : 0)}</span></div>
    ${_ncLeyendaReceptorTermica(nc, prefijo)}

    ${_ncComprobanteTermica(nc, prefijo)}
    ${nc ? `<div class="${prefijo}-arca"><strong>ARCA</strong>Comprobante autorizado<br>Esta Agencia no se responsabiliza por los datos ingresados en el detalle de la operación.</div>` : ''}
${sinAutoImpresion ? '' : `
    <script>
        window.addEventListener('load', function () {
            setTimeout(function () { window.print(); }, 150);
        });
        window.addEventListener('afterprint', function () { window.close(); });
    <\/script>
`}
</body>
</html>`;
}

function ncHtmlTermica80(data, opts) { return _ncHtmlTermica(data, 80, 72, '80', opts); }
function ncHtmlTermica58(data, opts) { return _ncHtmlTermica(data, 58, 48, '58', opts); }

function _ncFechaDocumento(data) {
    return (data && (data.fecha_hora || data.fecha)) || new Date().toLocaleDateString('es-AR');
}

function _ncClienteTexto(cliente, nc) {
    if (nc && nc.receptor_documento) {
        return `${cliente && cliente.nombre ? _esc(cliente.nombre) + ' — ' : ''}${_esc(nc.receptor_documento)}${nc.receptor_condicion_iva ? ' — ' + _esc(nc.receptor_condicion_iva) : ''}`;
    }
    return 'Consumidor Final';
}

function _ncTotalesFilas(nc) {
    if (!nc || !nc.iva_grupos || !nc.iva_grupos.length) return '';
    const filasIva = nc.iva_grupos.map(g => `<div class="nc-totales-row"><span>IVA ${_esc(g.alicuota)}%</span><span>$${_fmtNum(g.iva)}</span></div>`).join('');
    return `<div class="nc-totales-row"><span>Neto gravado</span><span>$${_fmtNum(nc.importe_neto)}</span></div>${filasIva}`;
}

function _ncTotalesFilasTermica(nc, prefijo, items) {
    const subtotal = (items || []).reduce((acc, item) => acc + (parseFloat(item.subtotal || 0) || 0), 0);
    const totalDocumento = parseFloat((nc && nc.importe_total) || 0) || 0;
    const bonificacion = Math.max(0, subtotal - totalDocumento);
    let html = `<div class="${prefijo}-total-row"><span>Subtotal</span><span>$${_fmtNum(subtotal)}</span></div>`;
    if (bonificacion > 0.005) {
        html += `<div class="${prefijo}-total-row"><span>Bonificación</span><span>− $${_fmtNum(bonificacion)}</span></div>`;
    }
    if (!nc || !nc.iva_grupos || !nc.iva_grupos.length) return html;
    const esNotaCreditoB = nc.tipo_comprobante === 8;
    const filasIva = nc.iva_grupos.map(g => `<div class="${prefijo}-total-row"><span>${esNotaCreditoB ? 'IVA contenido' : 'IVA'} ${_esc(g.alicuota)}%</span><span>$${_fmtNum(g.iva)}</span></div>`).join('');
    return `${html}<div class="${prefijo}-total-row"><span>Neto gravado</span><span>$${_fmtNum(nc.importe_neto)}</span></div>${esNotaCreditoB ? `<div class="${prefijo}-seccion">Transparencia fiscal · Ley 27.743</div>` : ''}${filasIva}<div class="${prefijo}-total-row"><span>${esNotaCreditoB ? 'Otros imp. nac.' : 'Otros tributos'}</span><span>$0,00</span></div>`;
}

function _ncClienteTermica(cliente, nc, prefijo) {
    const nombre = cliente && cliente.nombre ? cliente.nombre : 'A CONSUMIDOR FINAL';
    const documento = (nc && nc.receptor_documento) || (cliente && cliente.documento) || '';
    const condicionIva = (nc && nc.receptor_condicion_iva) || (cliente && cliente.condicion_iva) || 'Consumidor Final';
    const domicilio = cliente && cliente.direccion ? cliente.direccion : '—';
    return `<div class="${prefijo}-cliente">
        <div class="${prefijo}-cliente-nombre">${_esc(nombre)}</div>
        <div class="${prefijo}-peq">${documento ? _esc(documento) : 'CUIT: —'}</div>
        <div class="${prefijo}-peq">IVA: ${_esc(condicionIva)}</div>
        <div class="${prefijo}-peq">Dom: ${_esc(domicilio)}</div>
    </div>`;
}

function _ncCantidadDisplay(valor) {
    const numero = parseFloat(valor);
    if (Number.isNaN(numero)) return String(valor == null ? '' : valor);
    return numero.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 3 });
}

function _ncLeyendaReceptorTermica(nc, prefijo) {
    if (!nc || nc.tipo_comprobante !== 3) return '';
    const condicion = String(nc.receptor_condicion_iva || '').toLocaleLowerCase('es');
    if (!condicion.includes('monotribut')) return '';
    return `<div class="${prefijo}-corrige">El crédito fiscal discriminado en el presente comprobante solo podrá ser computado a efectos del Régimen de Sostenimiento e Inclusión Fiscal para Pequeños Contribuyentes de la Ley N.º 27.618.</div>`;
}

function _ncComprobanteTermica(nc, prefijo) {
    if (!nc) return '';
    return `<div class="${prefijo}-fiscal">
        <div class="${prefijo}-fiscal-label">Comprobante autorizado por ARCA</div>
        <div class="${prefijo}-fiscal-contenido">
            ${nc.qrDataUrl ? `<img class="${prefijo}-qr" src="${_esc(nc.qrDataUrl)}" alt="QR ARCA">` : ''}
            <div class="${prefijo}-fiscal-datos">
                <div class="${prefijo}-peq">CAE: <strong>${_esc(nc.cae)}</strong></div>
                <div class="${prefijo}-peq">Vto. CAE: <strong>${_esc(nc.cae_vencimiento)}</strong></div>
            </div>
        </div>
    </div>`;
}

function _ncComprobanteBox(nc) {
    if (!nc) return '';
    return `<div class="nc-comprobante">
        ${nc.qrDataUrl ? `<img class="nc-comprobante-qr" src="${_esc(nc.qrDataUrl)}" alt="QR ARCA">` : ''}
        <div class="nc-comprobante-datos">
            <div class="nc-comprobante-label">Comprobante autorizado por ARCA</div>
            <div>CAE: <b>${_esc(nc.cae)}</b></div>
            <div>Vencimiento del CAE: <b>${_esc(nc.cae_vencimiento)}</b></div>
        </div>
    </div>`;
}
