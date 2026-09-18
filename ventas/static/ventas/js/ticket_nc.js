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
            <div class="nc-meta">Fecha: ${_esc(_ncFechaHoy())}</div>
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
 * @param {number} anchoMm  72 (rollo 80mm) o 48 (rollo 58mm).
 * @param {object} [opts]
 * @param {boolean} [opts.sinAutoImpresion]  Ver ncHtmlA4.
 */
function _ncHtmlTermica(data, anchoMm, opts) {
    const esDuplicado = !!(opts && opts.duplicado);
    const sinAutoImpresion = !!(opts && opts.sinAutoImpresion);
    const { emp } = _ncEmpresaYCliente();
    const items = data.items || [];
    const nc = data.nc || null;

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Nota de Crédito — ${nc ? _esc(nc.numero_display) : ''}</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            width: ${anchoMm}mm;
            font-family: 'Courier New', Courier, monospace;
            font-size: 9pt;
            color: #000;
            background: #fff;
        }
        body { padding: 3mm 2mm 8mm 2mm; }
        .nct-center { text-align: center; }
        .nct-bold   { font-weight: bold; }
        .nct-grande { font-size: 13pt; font-weight: bold; }
        .nct-peq    { font-size: 8pt; font-weight: 600; }
        .nct-sep-doble  { border: none; border-top: 2px solid #000; margin: 4pt 0; }
        .nct-sep-simple { border: none; border-top: 1px dashed #000; margin: 3pt 0; }
        .nct-row { display: flex; justify-content: space-between; gap: 4pt; }
        @media print {
            html, body { width: auto; }
            body { padding: 0; }
            @page { size: ${anchoMm}mm auto; margin: 0; }
        }
    </style>
</head>
<body>
    <div class="nct-center nct-bold">${_esc(emp.nombre)}</div>
    ${emp.cuit ? `<div class="nct-center nct-peq">CUIT: ${_esc(emp.cuit)}</div>` : ''}
    <hr class="nct-sep-doble">
    <div class="nct-center nct-bold">${nc ? _esc(nc.tipo_display).toUpperCase() : 'NOTA DE CRÉDITO'}</div>
    <div class="nct-center">${nc ? _esc(nc.numero_display) : ''}</div>
    <div class="nct-center nct-peq">${esDuplicado ? 'DUPLICADO' : 'ORIGINAL'}</div>
    <hr class="nct-sep-simple">
    <div class="nct-peq">Corrige: ${_esc(data.comprobante_original_display)}</div>
    <hr class="nct-sep-simple">
    ${items.map(it => `
    <div>${_esc(it.nombre)}</div>
    <div class="nct-row nct-peq"><span>${_esc(it.cantidad)} x $${_fmtNum(it.precio_unitario)}</span><span>$${_fmtNum(it.subtotal)}</span></div>
    `).join('')}
    <hr class="nct-sep-simple">
    ${_ncTotalesFilasTexto(nc)}
    <div class="nct-row nct-grande"><span>TOTAL</span><span>$${_fmtNum(nc ? nc.importe_total : 0)}</span></div>
    <hr class="nct-sep-doble">
    ${nc ? `
    <div class="nct-center nct-peq">CAE: ${_esc(nc.cae)}</div>
    <div class="nct-center nct-peq">Vto. CAE: ${_esc(nc.cae_vencimiento)}</div>
    ` : ''}
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

function ncHtmlTermica80(data, opts) { return _ncHtmlTermica(data, 72, opts); }
function ncHtmlTermica58(data, opts) { return _ncHtmlTermica(data, 48, opts); }

function _ncFechaHoy() {
    return new Date().toLocaleDateString('es-AR');
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

function _ncTotalesFilasTexto(nc) {
    if (!nc || !nc.iva_grupos || !nc.iva_grupos.length) return '';
    const filasIva = nc.iva_grupos.map(g => `<div class="nct-row nct-peq"><span>IVA ${_esc(g.alicuota)}%</span><span>$${_fmtNum(g.iva)}</span></div>`).join('');
    return `<div class="nct-row nct-peq"><span>Neto gravado</span><span>$${_fmtNum(nc.importe_neto)}</span></div>${filasIva}`;
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
