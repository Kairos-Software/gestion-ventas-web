/**
 * ticket_a4.js
 * ─────────────────────────────────────────────────────────────────
 * Generador de HTML para ticket de venta en formato A4.
 * Pensado para impresoras láser, inkjet o "Guardar como PDF".
 *
 * Exporta: ticketHtmlA4(data) → string HTML completo
 *
 * El parámetro `data` es el objeto window.TICKET_DATA definido
 * en el template detalle_venta.html. Estructura esperada:
 * {
 *   empresa: { nombre, razon_social, domicilio, telefono,
 *              email, cuit, condicion_iva, ingresos_brutos,
 *              fecha_inicio_actividades, eslogan, logo_url },
 *   venta:   { numero, fecha, fecha_hora, notas, total,
 *              confirmado_por, medio_pago_display,
 *              condicion_venta_display, descuento_global_pct,
 *              oferta_global_nombre },
 *   cliente: { nombre, documento, condicion_iva, telefono, direccion } | null,
 *   pagos:   [ { medio_display, monto }, ... ],
 *   items:   [ { nombre, codigo, unidad_medida, color, cliente,
 *                cantidad, moneda, precio_unitario,
 *                descuento_pct, subtotal,
 *                condicion_pago_display }, ... ],
 *   comprobante_arca: { tipo_display, tipo_comprobante, numero_display, cae,
 *                        cae_vencimiento, qrDataUrl } | null,
 * }
 *
 * Nota de cumplimiento (sep 2026): un cliente institucional (organismo
 * público) rechazó una factura nuestra por faltarle datos exigidos en el
 * modelo visual oficial de ARCA — CUIT/condición de IVA del RECEPTOR,
 * condición de venta, Ingresos Brutos y fecha de inicio de actividades del
 * emisor. Todos esos datos ya existían en la base (Cliente.cuit/cond_iva,
 * Venta.medio_pago) salvo ingresos_brutos/fecha_inicio_actividades, que se
 * cargan una sola vez en Configuración → Datos de la empresa. Este archivo
 * es la única fuente de verdad del layout — lo reusa ticket_pdf.js tal cual.
 *
 * Layout (ronda 2, mismo mes): el usuario trajo un mockup con la estructura
 * clásica de ARCA (recuadro "C / COD. 011" con línea divisoria, Datos del
 * cliente / Datos de la operación separados, Forma de pago y Totales lado a
 * lado, pie oficial "Comprobante Autorizado" + Pág. 1/1). Se replicó esa
 * estructura manteniendo la paleta propia (no la del mockup) — ver charla:
 * lo que había rechazado ARCA era el DATO faltante, no el color.
 *
 * Paleta: misma que el resto del sistema (core/static/core/css/base.css)
 * — naranja de marca #F26A1B, azul de marca #1E6FA8 — para que el
 * comprobante se sienta parte del mismo producto, no un documento aparte.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

const A4_ICON_PIN   = '<path d="M12 21s7-7.58 7-12a7 7 0 1 0-14 0c0 4.42 7 12 7 12z"/><circle cx="12" cy="9" r="2.3"/>';
const A4_ICON_PHONE = '<path d="M4 4h4l2 5-2.3 1.4a11 11 0 0 0 5 5L14 13l5 2v4a2 2 0 0 1-2 2A15 15 0 0 1 2 6a2 2 0 0 1 2-2z"/>';
const A4_ICON_MAIL  = '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>';

/**
 * Genera el HTML completo del ticket en formato A4.
 * @param {object} data  Datos del ticket (ver estructura arriba)
 * @param {object} [opts]
 * @param {boolean} [opts.sinAutoImpresion]  No incluir el <script> que
 *   dispara window.print() al cargar. Lo usa ticket_pdf.js, que
 *   rasteriza este HTML en un iframe oculto para armar el PDF.
 * @returns {string}     HTML completo listo para abrir en ventana nueva
 */
function ticketHtmlA4(data, opts) {
    const sinAutoImpresion = !!(opts && opts.sinAutoImpresion);
    const emp     = data.empresa || {};
    const venta   = data.venta   || {};
    const items   = data.items   || [];
    const pagos   = data.pagos   || [];
    const cbte    = data.comprobante_arca || null;
    const cliente = data.cliente || null;

    const letra = cbte ? String(cbte.tipo_display || '').trim().slice(-1) : '';
    const cod   = cbte ? String(cbte.tipo_comprobante).padStart(3, '0') : '';

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>${cbte ? _esc(cbte.tipo_display) : 'Ticket'} — ${_esc(venta.numero)}</title>
    <style>
        /* ── Reset ── */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        /* ── Página ── */
        html, body {
            width: 210mm;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10.5pt;
            color: #0D1B2A;
            background: #fff;
        }
        body { padding: 9mm 10mm 13mm; }

        /* ── Barra superior de marca ── */
        .a4-topbar { display: none; }

        /* ── Cabecera: emisor | tipo de comprobante | datos del comprobante ── */
        .a4-header2 {
            display: flex;
            align-items: stretch;
            gap: 0;
            min-height: 115pt;
            margin-bottom: 9pt;
            padding: 10pt 12pt;
            border: 1px solid #86AFC8;
        }
        .a4-header2-col { flex: 1 1 0; }
        .a4-header2-comprobante { text-align: right; }
        .a4-header2-divider {
            flex: 0 0 auto;
            width: 82pt;
            padding: 0 10pt;
            border-right: 1px solid #86AFC8;
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }
        .a4-tipo-box {
            flex: 0 0 auto;
            border: 1.5px solid #1E6FA8;
            width: 52pt;
            text-align: center;
            padding: 4pt 0 5pt;
        }
        .a4-tipo-letra { font-size: 26pt; font-weight: 800; line-height: 1; }
        .a4-tipo-cod   { font-size: 6.5pt; font-weight: 700; letter-spacing: .03em; color: #4A5568; margin-top: 2pt; }

        .a4-logo { max-height: 46px; max-width: 155px; object-fit: contain; margin-bottom: 6pt; display: block; }
        .a4-header2-comprobante .a4-logo { margin-left: auto; }
        .a4-empresa-nombre { font-size: 14pt; font-weight: 700; margin-bottom: 3pt; letter-spacing: -.01em; }
        .a4-empresa-dato   { font-size: 8.5pt; color: #4A5568; margin: 1pt 0; }
        .a4-empresa-contacto { margin: 5pt 0; }
        .a4-contacto-row { display: flex; align-items: flex-start; gap: 5pt; margin: 2pt 0; }
        .a4-contacto-row svg { flex: 0 0 auto; margin-top: 1pt; }
        .a4-contacto-row .a4-empresa-dato { margin: 0; }

        .a4-original-label {
            font-size: 7.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .12em;
            color: #8A9BB0;
            margin-bottom: 4pt;
        }
        .a4-ticket-titulo {
            font-size: 20pt;
            font-weight: 800;
            letter-spacing: -.01em;
            color: #0D1B2A;
        }
        .a4-ticket-titulo.a4-titulo-simple { color: #4A5568; }
        .a4-ticket-numero-grande {
            font-size: 13pt;
            font-weight: 800;
            font-variant-numeric: tabular-nums;
            color: #F26A1B;
            margin-top: 4pt;
        }
        .a4-meta-list { margin-top: 8pt; }
        .a4-meta-row { font-size: 8.5pt; color: #4A5568; margin: 2pt 0; }
        .a4-meta-row strong { color: #0D1B2A; font-weight: 700; }

        /* ── Bloques de info (cliente / operación) ── */
        .a4-info-grid {
            display: flex;
            gap: 0;
            margin-bottom: 9pt;
            border: 1px solid #86AFC8;
        }
        .a4-info-box {
            flex: 1 1 0;
            background: #fff;
            padding: 8pt 12pt;
        }
        .a4-info-box + .a4-info-box { border-left: 1px solid #86AFC8; }
        .a4-info-label {
            font-size: 7.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            color: #1E6FA8;
            margin-bottom: 5pt;
        }
        .a4-info-nombre { font-size: 10pt; font-weight: 700; margin-bottom: 2pt; }
        .a4-info-dato   { font-size: 8.5pt; color: #4A5568; line-height: 1.5; }

        /* ── Tabla de ítems ── */
        .a4-table { width: 100%; border-collapse: collapse; margin-bottom: 9pt; font-size: 8.2pt; table-layout: fixed; border: 1px solid #86AFC8; }
        .a4-table thead th {
            text-align: left;
            padding: 6pt 6pt;
            border: 1px solid #86AFC8;
            background: #EAF3F8;
            color: #0D1B2A;
            font-size: 7pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .04em;
        }
        .a4-table th:not(:nth-child(1)):not(:nth-child(2)) { text-align: right; }
        .a4-table td {
            padding: 6pt 6pt;
            border-right: 1px solid #B7CEDC;
            border-bottom: 1px solid #B7CEDC;
            vertical-align: top;
            word-wrap: break-word;
        }
        .a4-table td:not(:nth-child(1)):not(:nth-child(2)) { text-align: right; }
        .a4-table td:nth-child(n+3) { white-space: nowrap; }
        .a4-table tbody tr:last-child td { border-bottom: 0; }
        .a4-table--formal tbody tr:last-child td { height: 37mm; }
        .a4-table tr,
        .a4-resumen,
        .a4-leyenda-fiscal,
        .a4-comprobante,
        .a4-arca-oficial { break-inside: avoid; page-break-inside: avoid; }

        .a4-table col.a4-col-codigo  { width: 9%; }
        .a4-table col.a4-col-nombre  { width: 23%; }
        .a4-table col.a4-col-cant    { width: 7%; }
        .a4-table col.a4-col-unidad  { width: 11%; }
        .a4-table col.a4-col-precio  { width: 14%; }
        .a4-table col.a4-col-bonifp  { width: 9%; }
        .a4-table col.a4-col-bonifm  { width: 13%; }
        .a4-table col.a4-col-subtotal{ width: 14%; }

        .a4-prod-nombre  { font-weight: 600; }
        .a4-prod-detalle { font-size: 7.5pt; color: #8A9BB0; margin-top: 2pt; }

        /* ── Forma de pago + Totales, lado a lado ── */
        .a4-resumen {
            display: flex;
            border: 1px solid #86AFC8;
            margin-bottom: 9pt;
            overflow: hidden;
        }
        .a4-resumen-pago   { flex: 1 1 0; padding: 10pt 14pt; background: #fff; }
        .a4-resumen-totales{ flex: 1 1 0; padding: 10pt 14pt; border-left: 1px solid #86AFC8; }
        .a4-pagos { display: flex; gap: .5rem; flex-wrap: wrap; }
        .a4-pago-badge {
            display: inline-block;
            padding: 3pt 10pt;
            background: #EAF3F8;
            border: 0;
            color: #1E6FA8;
            border-radius: 20pt;
            font-size: 8.5pt;
            font-weight: 600;
        }
        .a4-desglose-iva-row {
            display: flex; justify-content: space-between;
            font-size: 9pt; color: #5B6B82; padding: 1.5pt 0;
        }
        .a4-transparencia-title {
            margin: 4pt 0 2pt;
            font-size: 7pt;
            font-weight: 700;
            line-height: 1.3;
            color: #1E6FA8;
            text-transform: uppercase;
        }
        .a4-transparencia {
            margin-top: 8pt;
            padding-top: 5pt;
            border-top: 1px solid #B7CEDC;
        }
        .a4-transparencia-row {
            display: flex;
            justify-content: space-between;
            gap: 8pt;
            font-size: 8pt;
            color: #4A5568;
            padding: 1pt 0;
        }
        .a4-total-final-row {
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
        .a4-total-final-row span:last-child { color: #F26A1B; }

        /* ── Comprobante ARCA (CAE + QR) ── */
        .a4-comprobante {
            display: flex;
            align-items: center;
            gap: 14pt;
            margin-bottom: 9pt;
            padding: 10pt 14pt;
            background: #fff;
            border: 1px solid #86AFC8;
            border-left: 4pt solid #1E6FA8;
        }
        .a4-comprobante-qr { width: 68pt; height: 68pt; flex: 0 0 auto; background: #fff; padding: 3pt; border-radius: 2pt; }
        .a4-comprobante-datos { font-size: 8.5pt; color: #0D1B2A; line-height: 1.4; }
        .a4-comprobante-label {
            font-size: 7.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .05em;
            color: #1E6FA8;
            margin-bottom: 4pt;
        }
        .a4-comprobante-datos b { font-variant-numeric: tabular-nums; }
        .a4-leyenda-fiscal {
            margin-bottom: 9pt;
            padding: 6pt 9pt;
            border: 1px solid #86AFC8;
            font-size: 7.5pt;
            line-height: 1.4;
            color: #4A5568;
        }

        /* ── Pie oficial ARCA ── */
        .a4-arca-oficial {
            display: flex;
            align-items: center;
            gap: 14pt;
            padding-top: 10pt;
            margin-bottom: 10pt;
            border-top: 1px solid #E4EAF0;
            font-size: 8pt;
            color: #4A5568;
        }
        .a4-arca-marca { flex: 0 0 auto; text-align: center; }
        .a4-arca-wordmark { font-size: 13pt; font-weight: 800; letter-spacing: .02em; color: #0D1B2A; }
        .a4-arca-caption { font-size: 6pt; text-transform: uppercase; letter-spacing: .03em; color: #8A9BB0; margin-top: 1pt; line-height: 1.3; }
        .a4-arca-texto { flex: 1 1 0; }
        .a4-arca-disclaimer { font-style: italic; font-size: 7.5pt; color: #8A9BB0; margin-top: 2pt; }
        .a4-arca-pagina { flex: 0 0 auto; font-weight: 600; }

        /* ── Notas ── */
        .a4-notas {
            font-size: 9pt;
            color: #4A5568;
            padding: 8pt 10pt;
            background: #F4F6F9;
            border-left: 3px solid #CBD5E0;
            margin-bottom: 14pt;
            white-space: pre-line;
        }

        /* ── Pie ── */
        .a4-footer {
            text-align: center;
            font-size: 8.5pt;
            color: #8A9BB0;
            padding-top: 4pt;
        }
        .a4-footer-eslogan {
            font-style: italic;
            font-family: 'Brush Script MT', 'Segoe Script', cursive;
            color: #1E6FA8;
            font-size: 12pt;
            margin-top: 4pt;
        }

        /* ── Print ── */
        @media print {
            html, body { width: auto; }
            body { padding: 0; }
            @page { size: A4; margin: 9mm 10mm 13mm; }
        }
    </style>
</head>
<body>

    <div class="a4-topbar"></div>

    <!-- Cabecera: emisor | tipo de comprobante | datos del comprobante -->
    <div class="a4-header2">
        <div class="a4-header2-col a4-header2-emisor">
            ${emp.logo_url ? `<img class="a4-logo" src="${_esc(emp.logo_url)}" alt="Logo">` : ''}
            <div class="a4-empresa-nombre">${_esc(emp.nombre)}</div>
            ${emp.razon_social ? `<div class="a4-empresa-dato">${_esc(emp.razon_social)}</div>` : ''}
            <div class="a4-empresa-contacto">
                ${emp.domicilio ? _a4ContactoRow(A4_ICON_PIN, emp.domicilio) : ''}
                ${emp.telefono  ? _a4ContactoRow(A4_ICON_PHONE, `Tel: ${emp.telefono}`) : ''}
                ${emp.email     ? _a4ContactoRow(A4_ICON_MAIL, emp.email) : ''}
            </div>
            ${emp.cuit          ? `<div class="a4-empresa-dato">CUIT: ${_esc(emp.cuit)}</div>` : ''}
            ${(cbte || emp.ingresos_brutos) ? `<div class="a4-empresa-dato">Ingresos Brutos: ${_esc(emp.ingresos_brutos || '—')}</div>` : ''}
            ${emp.condicion_iva ? `<div class="a4-empresa-dato">Condición frente al IVA: ${_esc(emp.condicion_iva)}</div>` : ''}
        </div>
        ${cbte ? `
        <div class="a4-header2-divider">
            <div class="a4-tipo-box">
                <div class="a4-tipo-letra">${_esc(letra)}</div>
                <div class="a4-tipo-cod">COD. ${_esc(cod)}</div>
            </div>
        </div>` : ''}
        <div class="a4-header2-col a4-header2-comprobante">
            ${cbte ? '<div class="a4-original-label">Original</div>' : ''}
            <div class="a4-ticket-titulo${cbte ? '' : ' a4-titulo-simple'}">${cbte ? _esc(cbte.tipo_display) : 'Ticket de Venta'}</div>
            <div class="a4-ticket-numero-grande">${cbte ? _esc(cbte.numero_display) : _esc(venta.numero)}</div>
            <div class="a4-meta-list">${_a4MetaComprobante(cbte, venta, emp)}</div>
        </div>
    </div>

    <!-- Datos del cliente + datos de la operación -->
    <div class="a4-info-grid">
        <div class="a4-info-box">
            <div class="a4-info-label">Datos del cliente</div>
            ${_a4Cliente(cliente, cbte)}
        </div>
        <div class="a4-info-box">
            <div class="a4-info-label">Datos de la operación</div>
            <div class="a4-info-dato">Fecha y hora: <strong style="color:#0D1B2A">${_esc(venta.fecha_hora || venta.fecha)}</strong></div>
            ${venta.confirmado_por ? `<div class="a4-info-dato">Atendido por: <strong style="color:#0D1B2A">${_esc(venta.confirmado_por)}</strong></div>` : ''}
            <div class="a4-info-dato">Condición de venta: <strong style="color:#0D1B2A">${_esc(venta.condicion_venta_display || 'Contado')}</strong></div>
        </div>
    </div>

    <!-- Tabla de ítems -->
    <table class="a4-table${items.length <= 4 ? ' a4-table--formal' : ''}">
        <colgroup>
            <col class="a4-col-codigo"><col class="a4-col-nombre"><col class="a4-col-cant">
            <col class="a4-col-unidad"><col class="a4-col-precio"><col class="a4-col-bonifp">
            <col class="a4-col-bonifm"><col class="a4-col-subtotal">
        </colgroup>
        <thead>
            <tr>
                <th>Código</th>
                <th>Producto / Servicio</th>
                <th>Cant.</th>
                <th>U. Medida</th>
                <th>Precio unit.</th>
                <th>% Bonif.</th>
                <th>Imp. Bonif.</th>
                <th>Subtotal</th>
            </tr>
        </thead>
        <tbody>
            ${items.map(item => _a4FilaItem(item, !!cbte)).join('')}
        </tbody>
    </table>

    <!-- Forma de pago + Totales, lado a lado -->
    <div class="a4-resumen">
        <div class="a4-resumen-pago">
            <div class="a4-info-label">Forma de pago</div>
            <div class="a4-pagos">${_a4PagosContenido(pagos, venta)}</div>
            ${_a4Transparencia(cbte)}
        </div>
        <div class="a4-resumen-totales">
            ${_a4Totales(cbte, items, venta)}
            <div class="a4-total-final-row">
                <span>Importe Total</span>
                <span>$${_fmtNum(cbte ? cbte.importe_total : venta.total)}</span>
            </div>
        </div>
    </div>

    ${_a4LeyendaReceptor(cbte)}

    <!-- Comprobante ARCA (CAE + QR) -->
    ${_a4Comprobante(cbte)}

    <!-- Pie oficial ARCA -->
    ${cbte ? `
    <div class="a4-arca-oficial">
        <div class="a4-arca-marca">
            <div class="a4-arca-wordmark">ARCA</div>
            <div class="a4-arca-caption">Agencia de Recaudación<br>y Control Aduanero</div>
        </div>
        <div class="a4-arca-texto">
            <strong>Comprobante Autorizado</strong>
            <div class="a4-arca-disclaimer">Esta Agencia no se responsabiliza por los datos ingresados en el detalle de la operación.</div>
        </div>
        ${items.length <= 8 ? '<div class="a4-arca-pagina">Pág. 1/1</div>' : ''}
    </div>` : ''}

    <!-- Notas -->
    ${venta.notas ? `<div class="a4-notas">${_esc(venta.notas)}</div>` : ''}

    <!-- Pie -->
    <div class="a4-footer">
        Gracias por su compra.
        ${emp.eslogan ? `<div class="a4-footer-eslogan">${_esc(emp.eslogan)}</div>` : ''}
    </div>
${sinAutoImpresion ? '' : `
    <script>
        window.addEventListener('load', function () {
            // La herramienta de impresión del navegador ES la vista previa
            // (ahí se ve el papel real y las impresoras conectadas) — no
            // hace falta ninguna vista previa propia en HTML.
            setTimeout(function () { window.print(); }, 150);
        });
        // Cerrar la ventana recién cuando el usuario termina con el
        // diálogo de impresión (imprime o cancela) — nunca antes.
        window.addEventListener('afterprint', function () { window.close(); });
    <\/script>`}
</body>
</html>`;
}

/* ── Helpers internos ─────────────────────────────────────────── */

function _a4ContactoRow(iconPath, texto) {
    return `<div class="a4-contacto-row">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#8A9BB0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${iconPath}</svg>
        <div class="a4-empresa-dato">${_esc(texto)}</div>
    </div>`;
}

// Lista de renglones a la derecha del número grande. Sin comprobante_arca
// (ticket informal) no hay nada de esto — solo aplica al comprobante fiscal.
function _a4MetaComprobante(cbte, venta, emp) {
    if (!cbte) return '';
    const partes = String(cbte.numero_display || '').split('-');
    const pv  = partes[0] || '';
    const nro = partes[1] || '';
    const filas = [
        `Fecha de Emisión: <strong>${_esc(venta.fecha)}</strong>`,
        `Punto de Venta: <strong>${_esc(pv)}</strong>`,
        `Comp. Nro: <strong>${_esc(nro)}</strong>`,
    ];
    filas.push(`Fecha de Inicio de Actividades: <strong>${_esc(emp.fecha_inicio_actividades || '—')}</strong>`);
    return filas.map(f => `<div class="a4-meta-row">${f}</div>`).join('');
}

// Si hay comprobante_arca, su doc/condición de IVA de receptor son el
// snapshot que efectivamente se declaró ante ARCA para ESTE comprobante
// (ver ComprobanteArca.doc_receptor_display/condicion_iva_receptor_display)
// — se prioriza sobre el dato actual del cliente, que puede haber cambiado
// desde que se facturó. Sin comprobante (ticket informal) se usa el dato
// vigente del cliente. Siempre se muestran las 4 filas (con "—" si falta
// el dato), igual que el modelo visual oficial de ARCA — nunca se ocultan.
function _a4Cliente(cliente, cbte) {
    const documento    = (cbte && cbte.receptor_documento)     || (cliente && cliente.documento)    || '';
    const condicionIva = (cbte && cbte.receptor_condicion_iva) || (cliente && cliente.condicion_iva) || (cliente ? '' : 'Consumidor Final');
    const direccion    = (cliente && cliente.direccion) || '';
    const esConsumidorFinal = String(condicionIva).toLocaleLowerCase('es').includes('consumidor final');
    let nombre = cliente ? cliente.nombre : 'Consumidor Final';
    if (esConsumidorFinal && String(nombre).toLocaleLowerCase('es').includes('consumidor final')) {
        nombre = 'A Consumidor Final';
    }
    return `
        <div class="a4-info-nombre">${_esc(nombre)}</div>
        <div class="a4-info-dato">${documento ? _esc(documento) : 'CUIT: —'}</div>
        <div class="a4-info-dato">Condición frente al IVA: ${_esc(condicionIva || '—')}</div>
        <div class="a4-info-dato">Domicilio: ${direccion ? _esc(direccion) : '—'}</div>
    `;
}

// Importe de la bonificación en pesos: la diferencia entre lo que hubiera
// costado la línea sin descuento y su subtotal real (ya neto del %).
function _a4ImporteBonif(item) {
    const bruto = parseFloat(item.cantidad) * parseFloat(item.precio_unitario);
    const bonif = bruto - parseFloat(item.subtotal);
    return bonif > 0.005 ? bonif : 0;
}

function _a4FilaItem(item, esOficial) {
    // "Cliente: X" por ítem es un dato interno (ventas repartidas entre
    // varias personas de un mismo grupo/terreno) — no corresponde en un
    // comprobante fiscal oficial, donde el receptor ya es uno solo y va
    // arriba en "Datos del cliente". Se sigue mostrando en el ticket
    // informal (sin comprobante_arca), que es donde tiene sentido.
    const detalle = [
        item.marca ? _esc(item.marca) : '',
        item.color ? `Color: ${_esc(item.color)}` : '',
        (!esOficial && item.cliente) ? `Cliente: ${_esc(item.cliente)}` : '',
    ].filter(Boolean).join(' · ');

    const tieneBonif = item.descuento_pct && parseFloat(item.descuento_pct) > 0;
    const bonif = _a4ImporteBonif(item);

    return `<tr>
        <td>${_esc(item.codigo || '—')}</td>
        <td>
            <div class="a4-prod-nombre">${_esc(item.nombre)}</div>
            ${detalle ? `<div class="a4-prod-detalle">${detalle}</div>` : ''}
        </td>
        <td>${_esc(String(item.cantidad))}</td>
        <td>${_esc(item.unidad_medida || 'unidades')}</td>
        <td>$ ${_fmtNum(item.precio_unitario)}</td>
        <td>${tieneBonif ? `${_esc(String(item.descuento_pct)).replace('.', ',')}%` : '0,00'}</td>
        <td>${bonif ? `$${_fmtNum(bonif)}` : '0,00'}</td>
        <td><strong>$ ${_fmtNum(item.subtotal)}</strong></td>
    </tr>`;
}

// Factura A/B discrimina IVA (el receptor Responsable Inscripto lo necesita
// para tomarse crédito fiscal) — Factura C nunca lo hizo y sigue igual.
// tipo_comprobante: 1=A, 6=B, 11=C (core/services_arca/tipos.py / ventas/models.py TipoComprobante).
// "Importe Otros Tributos" siempre da $0,00 — el sistema no modela ningún
// tributo aparte del IVA — pero el modelo visual oficial de ARCA igual
// exige mostrar la línea, no alcanza con omitirla. No incluye la línea de
// Total: eso se arma aparte en _a4-total-final-row (mismo valor para
// ticket informal o comprobante fiscal).
function _a4Totales(cbte, items, venta) {
    const subtotal = items.reduce((acc, it) => acc + parseFloat(it.subtotal || 0), 0);
    const totalDocumento = parseFloat((cbte && cbte.importe_total) || venta.total || 0);
    const descuentoGlobal = Math.max(0, subtotal - totalDocumento);
    const etiquetaDescuento = venta.oferta_global_nombre
        ? `Bonificación global · ${_esc(venta.oferta_global_nombre)}`
        : `Bonificación global${parseFloat(venta.descuento_global_pct || 0) > 0 ? ` (${_fmtPct(venta.descuento_global_pct)}%)` : ''}`;
    const filasComunes = `
        <div class="a4-desglose-iva-row"><span>Subtotal</span><span>$${_fmtNum(subtotal)}</span></div>
        ${descuentoGlobal > 0.005 ? `<div class="a4-desglose-iva-row"><span>${etiquetaDescuento}</span><span>− $${_fmtNum(descuentoGlobal)}</span></div>` : ''}
    `;

    if (!cbte) return filasComunes;
    if (cbte.tipo_comprobante === 1 || cbte.tipo_comprobante === 6) {
        const esFacturaB = cbte.tipo_comprobante === 6;
        return `
            ${filasComunes}
            <div class="a4-desglose-iva-row"><span>Neto gravado</span><span>$${_fmtNum(cbte.importe_neto)}</span></div>
            ${esFacturaB ? '' : `<div class="a4-desglose-iva-row"><span>IVA</span><span>$${_fmtNum(cbte.importe_iva)}</span></div>
            <div class="a4-desglose-iva-row"><span>Importe Otros Tributos</span><span>$0,00</span></div>`}
        `;
    }
    return `
        ${filasComunes}
        <div class="a4-desglose-iva-row"><span>Importe Otros Tributos</span><span>$0,00</span></div>
    `;
}

function _a4Transparencia(cbte) {
    if (!cbte || cbte.tipo_comprobante !== 6) return '';
    return `<div class="a4-transparencia">
        <div class="a4-transparencia-title">Régimen de Transparencia Fiscal al Consumidor (Ley 27.743)</div>
        <div class="a4-transparencia-row"><span>IVA contenido</span><span>$${_fmtNum(cbte.importe_iva)}</span></div>
        <div class="a4-transparencia-row"><span>Otros Impuestos Nacionales Indirectos</span><span>$0,00</span></div>
    </div>`;
}

function _a4LeyendaReceptor(cbte) {
    if (!cbte || cbte.tipo_comprobante !== 1) return '';
    const condicion = String(cbte.receptor_condicion_iva || '').toLocaleLowerCase('es');
    if (!condicion.includes('monotribut')) return '';
    return `<div class="a4-leyenda-fiscal">El crédito fiscal discriminado en el presente comprobante solo podrá ser computado a efectos del Régimen de Sostenimiento e Inclusión Fiscal para Pequeños Contribuyentes de la Ley N.º 27.618.</div>`;
}

function _a4Comprobante(cbte) {
    if (!cbte) return '';
    return `<div class="a4-comprobante">
        ${cbte.qrDataUrl ? `<img class="a4-comprobante-qr" src="${_esc(cbte.qrDataUrl)}" alt="QR ARCA">` : ''}
        <div class="a4-comprobante-datos">
            <div class="a4-comprobante-label">Comprobante autorizado por ARCA</div>
            <div>CAE: <b>${_esc(cbte.cae)}</b></div>
            <div>Vencimiento del CAE: <b>${_esc(cbte.cae_vencimiento)}</b></div>
        </div>
    </div>`;
}

function _a4PagoDetalle(p) {
    const partes = [];
    if (p.etiqueta_plan && Number(p.cantidad_pagos) > 1) partes.push(_esc(p.etiqueta_plan));
    if (p.recargo_monto && parseFloat(p.recargo_monto) > 0) partes.push(`recargo ${p.recargo_pct}% ($${_fmtNum(p.recargo_monto)})`);
    return partes.length ? ` (${partes.join(' — ')})` : '';
}

/** Lo que se muestra en la forma de pago del ticket = lo que cubre la venta
 *  (base + recargo), SIN el redondeo/diferencia — eso no va en el
 *  comprobante del cliente, solo en el detalle interno. */
function _a4MontoPago(p) {
    return parseFloat(p.monto || 0) - parseFloat(p.redondeo_monto || 0);
}

// Devuelve solo el contenido (badges) de "Forma de pago" — el contenedor
// con el título ya lo arma el layout de _a4-resumen-pago en ticketHtmlA4.
function _a4PagosContenido(pagos, venta) {
    if (pagos && pagos.length) {
        const visibles = pagos.filter(p => _a4MontoPago(p) > 0.005);
        const badges = visibles.map(p => {
            const tarjeta = p.tarjeta_nombre ? ` · ${_esc(p.tarjeta_nombre)}` : '';
            return `<span class="a4-pago-badge">${_esc(p.medio_display)}${tarjeta}${_a4PagoDetalle(p)}: $${_fmtNum(_a4MontoPago(p))}</span>`;
        }).join('');
        if (badges) return badges;
    }
    if (venta.medio_pago_display) {
        return `<span class="a4-pago-badge">${_esc(venta.medio_pago_display)}</span>`;
    }
    return '—';
}

function _esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _fmtNum(val) {
    const n = parseFloat(val);
    if (isNaN(n)) return String(val ?? '');
    return n.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function _fmtPct(val) {
    const n = parseFloat(val);
    if (isNaN(n)) return String(val ?? '');
    return n.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}
