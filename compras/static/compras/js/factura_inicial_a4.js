/**
 * factura_inicial_a4.js
 * ─────────────────────────────────────────────────────────────────
 * Comprobante A4 de la herramienta "Factura inicial".
 *
 * En esta compra el negocio es el RECEPTOR:
 *   • EMISOR   = el proveedor (data.emisor)
 *   • RECEPTOR = mi empresa (data.receptor)
 *
 * Es un documento interno, sin CAE ni QR.
 *
 * Exporta: facturaInicialHtmlA4(data, { sinAutoImpresion }) → string
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _fiEsc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _fiNum(v) {
    const n = parseFloat(v);
    if (isNaN(n)) return String(v ?? '');
    return n.toLocaleString('es-AR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

function facturaInicialHtmlA4(data, opts = {}) {
    const c = data.comprobante || {};
    const em = data.emisor || {};
    const re = data.receptor || {};
    const tot = data.totales || {};
    const items = data.items || [];
    const pago = data.pago || {};
    const pagoLineas = pago.lineas || [];
    const tienePago = !!(pago.condicion || pagoLineas.length);
    const discrimina = !!c.discrimina_iva;
    const conDescuento = parseFloat(tot.descuento || '0') > 0.005;
    const autoImp = !opts.sinAutoImpresion;
    const numeroInterno = data.numero_interno || '';

    const dato = (label, val) => val ? `
        <div class="a4-dato">
            <span class="a4-dato-label">${_fiEsc(label)}</span>
            <span class="a4-dato-value">${_fiEsc(val)}</span>
        </div>` : '';

    const columnas = conDescuento
        ? `<col style="width:12%"><col style="width:35%"><col style="width:10%"><col style="width:16%"><col style="width:11%"><col style="width:16%">`
        : `<col style="width:14%"><col style="width:39%"><col style="width:11%"><col style="width:17%"><col style="width:19%">`;

    return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>${_fiEsc(c.titulo)}${c.letra ? ' ' + _fiEsc(c.letra) : ''}${c.numero ? ' — ' + _fiEsc(c.numero) : ''}</title>
<style>
    :root {
        --ink: #142235;
        --muted: #607086;
        --soft: #F5F7FA;
        --line: #DDE4EC;
        --line-strong: #AEB9C7;
        --brand: #F26A1B;
        --blue: #1E6FA8;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
        width: 210mm;
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 10pt;
        color: var(--ink);
        background: #fff;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }
    body { padding: 0 17mm 16mm; }

    .a4-topbar {
        height: 4pt;
        margin: 0 -17mm 18pt;
        background: linear-gradient(90deg, var(--brand) 0 24%, var(--ink) 24% 100%);
    }

    /* Encabezado */
    .a4-head {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 235pt;
        gap: 26pt;
        align-items: stretch;
        padding-bottom: 15pt;
        border-bottom: 1px solid var(--line);
    }
    .a4-kicker {
        font-size: 7pt;
        line-height: 1;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: .13em;
        color: var(--blue);
        margin-bottom: 7pt;
    }
    .a4-emisor-nombre {
        max-width: 330pt;
        font-size: 16pt;
        line-height: 1.15;
        font-weight: 800;
        letter-spacing: -.025em;
        margin-bottom: 8pt;
    }
    .a4-emisor-datos {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 3pt 14pt;
    }
    .a4-dato { min-width: 0; font-size: 8.2pt; line-height: 1.35; color: var(--muted); }
    .a4-dato-label { display: block; font-size: 6.6pt; font-weight: 800; text-transform: uppercase; letter-spacing: .055em; color: #8895A6; }
    .a4-dato-value { display: block; overflow-wrap: anywhere; color: var(--ink); }

    .a4-doc {
        display: grid;
        grid-template-columns: 58pt minmax(0, 1fr);
        gap: 12pt;
        padding-left: 17pt;
        border-left: 1px solid var(--line);
        align-content: start;
    }
    .a4-letra-box {
        width: 58pt;
        height: 58pt;
        border: 1.5px solid var(--ink);
        border-radius: 5pt;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .a4-letra { font-size: 29pt; font-weight: 850; line-height: .8; letter-spacing: -.04em; }
    .a4-letra-label { font-size: 5.8pt; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin-top: 5pt; }
    .a4-doc-copy { min-width: 0; padding-top: 1pt; text-align: right; }
    .a4-doc-orig { font-size: 6.8pt; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; color: var(--muted); }
    .a4-doc-titulo { font-size: 19pt; line-height: 1.05; font-weight: 850; letter-spacing: -.025em; text-transform: uppercase; margin-top: 4pt; }
    .a4-doc-numero { font-size: 12pt; line-height: 1.2; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--brand); margin-top: 5pt; overflow-wrap: anywhere; }
    .a4-doc-meta {
        grid-column: 1 / -1;
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 5pt 12pt;
        padding-top: 2pt;
    }
    .a4-doc-meta .a4-dato:last-child { text-align: right; }

    /* Receptor */
    .a4-receptor {
        display: grid;
        grid-template-columns: minmax(160pt, 1.3fr) minmax(0, 1fr);
        gap: 12pt 28pt;
        padding: 12pt 14pt;
        margin: 13pt 0 15pt;
        border: 1px solid var(--line);
        border-left: 3pt solid var(--blue);
        border-radius: 4pt;
        background: var(--soft);
    }
    .a4-receptor .a4-kicker { margin-bottom: 6pt; }
    .a4-receptor-nombre { font-size: 12pt; line-height: 1.25; font-weight: 800; }
    .a4-receptor-datos {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 5pt 15pt;
        align-content: end;
    }
    .a4-receptor-datos .a4-dato-domicilio { grid-column: 1 / -1; }

    /* Detalle */
    .a4-section-title {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 6pt;
    }
    .a4-section-title strong { font-size: 9pt; font-weight: 800; letter-spacing: .01em; }
    .a4-section-title span { font-size: 7.5pt; color: var(--muted); }
    .a4-table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-bottom: 13pt; font-size: 9pt; }
    .a4-table thead { display: table-header-group; }
    .a4-table thead th {
        padding: 6.5pt 7pt;
        border-top: 1.5px solid var(--ink);
        border-bottom: 1px solid var(--line-strong);
        background: var(--soft);
        color: #526176;
        font-size: 6.8pt;
        line-height: 1.2;
        font-weight: 800;
        text-align: left;
        text-transform: uppercase;
        letter-spacing: .075em;
    }
    .a4-table th.num, .a4-table td.num { text-align: right; }
    .a4-table td {
        padding: 8pt 7pt;
        border-bottom: 1px solid var(--line);
        vertical-align: top;
        overflow-wrap: anywhere;
    }
    .a4-table tbody tr { break-inside: avoid; page-break-inside: avoid; }
    .a4-table tbody tr:last-child td { border-bottom-color: var(--line-strong); }
    .a4-codigo { color: var(--muted); font-size: 8pt; font-variant-numeric: tabular-nums; }
    .a4-prod-nombre { font-weight: 700; line-height: 1.35; }
    .a4-prod-ref { display: block; font-size: 7.2pt; color: #8794A5; margin-top: 2.5pt; }
    .a4-cantidad, .a4-dinero { white-space: nowrap; font-variant-numeric: tabular-nums; }
    .a4-cantidad-valor { display: block; font-weight: 700; }
    .a4-cantidad-unidad { display: block; margin-top: 2pt; font-size: 7pt; color: var(--muted); }
    .a4-desc-badge { color: #1E7A52; font-weight: 700; white-space: nowrap; }

    /* Totales */
    .a4-summary { display: flex; justify-content: flex-end; margin-bottom: 16pt; break-inside: avoid; page-break-inside: avoid; }
    .a4-tot-box { width: 260pt; }
    .a4-tot-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 14pt;
        padding: 3pt 9pt;
        font-size: 8.8pt;
        color: var(--muted);
    }
    .a4-tot-row span:last-child { white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--ink); }
    .a4-tot-row.total {
        margin-top: 5pt;
        padding: 8pt 9pt 8pt 11pt;
        border: 1px solid var(--line);
        border-left: 3pt solid var(--brand);
        border-radius: 3pt;
        background: var(--soft);
        font-size: 13.5pt;
        font-weight: 850;
        color: var(--ink);
    }
    .a4-tot-row.total span:last-child { color: var(--brand); }

    /* Pago y observaciones */
    .a4-pago, .a4-obs { break-inside: avoid; page-break-inside: avoid; }
    .a4-pago {
        margin-bottom: 13pt;
        padding: 10pt 12pt;
        border: 1px solid var(--line);
        border-radius: 4pt;
    }
    .a4-pago-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12pt; margin-bottom: 7pt; }
    .a4-pago-head .a4-kicker { margin: 0; }
    .a4-pago-cond { font-size: 8.5pt; font-weight: 700; color: var(--ink); }
    .a4-pago-table { width: 100%; border-collapse: collapse; font-size: 8.5pt; }
    .a4-pago-table td { padding: 4pt 0; border-top: 1px solid #E9EDF2; vertical-align: top; }
    .a4-pago-table td:first-child { width: 28%; font-weight: 700; }
    .a4-pago-table td:nth-child(2) { color: var(--muted); padding-left: 12pt; }
    .a4-pago-table td:last-child { width: 25%; padding-left: 12pt; text-align: right; white-space: nowrap; font-weight: 700; font-variant-numeric: tabular-nums; }
    .a4-pago-nota { margin-top: 7pt; padding-top: 6pt; border-top: 1px solid #E9EDF2; font-size: 7.1pt; line-height: 1.4; color: #8794A5; }
    .a4-obs { margin-bottom: 13pt; padding: 10pt 12pt; background: var(--soft); border-left: 3pt solid var(--line-strong); color: var(--muted); font-size: 8.5pt; line-height: 1.45; white-space: pre-line; }
    .a4-obs strong { display: block; margin-bottom: 3pt; color: var(--ink); font-size: 7pt; text-transform: uppercase; letter-spacing: .08em; }

    /* Pie */
    .a4-footer {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 18pt;
        margin-top: 5pt;
        padding-top: 9pt;
        border-top: 1px solid var(--line);
        color: #8794A5;
        font-size: 7.2pt;
        line-height: 1.45;
        break-inside: avoid;
        page-break-inside: avoid;
    }
    .a4-aviso { max-width: 390pt; }
    .a4-aviso strong { color: var(--muted); }
    .a4-registro { flex: 0 0 auto; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }

    @media print {
        html, body { width: auto; }
        body { padding: 0 17mm 16mm; }
        .a4-topbar { margin: 0 -17mm 18pt; }
        @page { size: A4; margin: 12mm 0; }
    }
</style>
</head>
<body>

    <div class="a4-topbar"></div>

    <header class="a4-head">
        <div class="a4-emisor">
            <div class="a4-kicker">Proveedor · Emisor</div>
            <div class="a4-emisor-nombre">${_fiEsc(em.razon_social || 'Proveedor')}</div>
            <div class="a4-emisor-datos">
                ${dato('CUIT', em.cuit)}
                ${dato('Condición frente al IVA', em.condicion_iva)}
                ${dato('Domicilio', em.domicilio)}
                ${dato('Teléfono', em.telefono)}
                ${dato('Email', em.email)}
            </div>
        </div>

        <div class="a4-doc">
            <div class="a4-letra-box">
                <div class="a4-letra">${_fiEsc(c.letra || 'X')}</div>
                <div class="a4-letra-label">Comprobante</div>
            </div>
            <div class="a4-doc-copy">
                <div class="a4-doc-orig">Original</div>
                <div class="a4-doc-titulo">${_fiEsc(c.titulo || 'Comprobante')}</div>
                ${c.numero ? `<div class="a4-doc-numero">N.º ${_fiEsc(c.numero)}</div>` : ''}
            </div>
            <div class="a4-doc-meta">
                ${dato('Fecha de emisión', c.fecha)}
                ${dato('Registro interno', numeroInterno)}
            </div>
        </div>
    </header>

    <section class="a4-receptor">
        <div>
            <div class="a4-kicker">Datos del receptor</div>
            <div class="a4-receptor-nombre">${_fiEsc(re.razon_social || 'Mi empresa')}</div>
        </div>
        <div class="a4-receptor-datos">
            ${dato('CUIT', re.cuit)}
            ${dato('Condición frente al IVA', re.condicion_iva)}
            ${re.domicilio ? `<div class="a4-dato a4-dato-domicilio"><span class="a4-dato-label">Domicilio</span><span class="a4-dato-value">${_fiEsc(re.domicilio)}</span></div>` : ''}
        </div>
    </section>

    <div class="a4-section-title">
        <strong>Detalle de productos</strong>
        <span>${items.length} ${items.length === 1 ? 'ítem' : 'ítems'}</span>
    </div>

    <table class="a4-table">
        <colgroup>${columnas}</colgroup>
        <thead>
            <tr>
                <th>Código</th>
                <th>Descripción</th>
                <th class="num">Cantidad</th>
                <th class="num">Precio unit.</th>
                ${conDescuento ? '<th class="num">Desc.</th>' : ''}
                <th class="num">Importe</th>
            </tr>
        </thead>
        <tbody>
            ${items.map(it => `<tr>
                <td><span class="a4-codigo">${_fiEsc(it.codigo || '—')}</span></td>
                <td>
                    <div class="a4-prod-nombre">${_fiEsc(it.detalle)}</div>
                    ${it.referencia ? `<span class="a4-prod-ref">Referencia: ${_fiEsc(it.referencia)}</span>` : ''}
                </td>
                <td class="num a4-cantidad">
                    <span class="a4-cantidad-valor">${_fiEsc(it.cantidad)}</span>
                    ${it.unidad ? `<span class="a4-cantidad-unidad">${_fiEsc(it.unidad)}</span>` : ''}
                </td>
                <td class="num a4-dinero">$ ${_fiNum(it.precio_unitario)}</td>
                ${conDescuento ? `<td class="num">${it.descuento_pct ? `<span class="a4-desc-badge">−${_fiEsc(it.descuento_pct)}%</span>` : '—'}</td>` : ''}
                <td class="num a4-dinero"><strong>$ ${_fiNum(it.subtotal)}</strong></td>
            </tr>`).join('')}
        </tbody>
    </table>

    <div class="a4-summary">
        <div class="a4-tot-box">
            <div class="a4-tot-row"><span>Subtotal</span><span>$ ${_fiNum(tot.subtotal)}</span></div>
            ${conDescuento ? `<div class="a4-tot-row"><span>Descuentos</span><span>− $ ${_fiNum(tot.descuento)}</span></div>` : ''}
            ${discrimina ? `
                <div class="a4-tot-row"><span>Neto gravado</span><span>$ ${_fiNum(tot.neto)}</span></div>
                <div class="a4-tot-row"><span>IVA ${_fiEsc(String(c.alicuota_pct).replace('.', ','))}%</span><span>$ ${_fiNum(tot.iva)}</span></div>
            ` : ''}
            <div class="a4-tot-row total"><span>Total</span><span>$ ${_fiNum(tot.total)}</span></div>
        </div>
    </div>

    ${tienePago ? `
    <section class="a4-pago">
        <div class="a4-pago-head">
            <div class="a4-kicker">Condición de pago</div>
            ${pago.condicion ? `<div class="a4-pago-cond">${_fiEsc(pago.condicion)}</div>` : ''}
        </div>
        ${pagoLineas.length ? `<table class="a4-pago-table"><tbody>
            ${pagoLineas.map(l => `<tr>
                <td>${_fiEsc(l.medio_label || l.medio)}</td>
                <td>${_fiEsc(l.detalle || '')}</td>
                <td>${l.monto ? '$ ' + _fiNum(l.monto) : ''}</td>
            </tr>`).join('')}
        </tbody></table>` : ''}
        <div class="a4-pago-nota">Información declarativa del acuerdo con el proveedor. No genera una deuda ni un movimiento de caja.</div>
    </section>` : ''}

    ${data.observaciones ? `<div class="a4-obs"><strong>Observaciones</strong>${_fiEsc(data.observaciones)}</div>` : ''}

    <footer class="a4-footer">
        <div class="a4-aviso">${data.incluir_leyenda ? `
            <strong>Documento de uso interno, sin validez fiscal.</strong>
            Generado para registrar el stock inicial. No fue emitido ni autorizado por ARCA.
        ` : ''}</div>
        ${numeroInterno ? `<div class="a4-registro">Registro ${_fiEsc(numeroInterno)}</div>` : ''}
    </footer>

    ${autoImp ? `<script>
        window.addEventListener('load', function () { setTimeout(function () { window.print(); }, 150); });
        window.addEventListener('afterprint', function () { window.close(); });
    <\/script>` : ''}
</body>
</html>`;
}
