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
 *              email, cuit, condicion_iva, logo_url },
 *   venta:   { numero, fecha, notas, total,
 *              confirmado_por, medio_pago_display },
 *   pagos:   [ { medio_display, monto }, ... ],
 *   items:   [ { nombre, codigo, color, cliente,
 *                cantidad, moneda, precio_unitario,
 *                descuento_pct, subtotal,
 *                condicion_pago_display }, ... ],
 *   comprobante_arca: { tipo_display, numero_display, cae,
 *                        cae_vencimiento, qrDataUrl } | null,
 * }
 *
 * Paleta: misma que el resto del sistema (core/static/core/css/base.css)
 * — naranja de marca #F26A1B, azul de marca #1E6FA8 — para que el
 * comprobante se sienta parte del mismo producto, no un documento aparte.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

/**
 * Genera el HTML completo del ticket en formato A4.
 * @param {object} data  Datos del ticket (ver estructura arriba)
 * @returns {string}     HTML completo listo para abrir en ventana nueva
 */
function ticketHtmlA4(data) {
    const emp   = data.empresa || {};
    const venta = data.venta   || {};
    const items = data.items   || [];
    const pagos = data.pagos   || [];
    const cbte  = data.comprobante_arca || null;

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
        body { padding: 0 22mm 20mm; }

        /* ── Barra superior de marca ── */
        .a4-topbar { height: 6pt; background: #F26A1B; margin: 0 -22mm 16pt; }

        /* ── Cabecera empresa ── */
        .a4-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            padding-bottom: 12pt;
            border-bottom: 1.5px solid #0D1B2A;
            margin-bottom: 14pt;
        }
        .a4-logo { max-height: 55px; max-width: 160px; object-fit: contain; margin-bottom: 4pt; display: block; }
        .a4-empresa-nombre { font-size: 15pt; font-weight: 700; margin-bottom: 4pt; letter-spacing: -.01em; }
        .a4-empresa-dato   { font-size: 8.5pt; color: #4A5568; margin: 1pt 0; }

        .a4-titulo-box { text-align: right; }
        .a4-ticket-titulo {
            display: inline-block;
            font-size: 11pt;
            font-weight: 700;
            letter-spacing: .02em;
            color: #fff;
            background: #1E6FA8;
            padding: 4pt 12pt;
            border-radius: 3pt;
        }
        .a4-titulo-box .a4-ticket-titulo.a4-titulo-simple {
            color: #4A5568;
            background: #F4F6F9;
        }
        .a4-ticket-numero {
            font-size: 12pt;
            font-weight: 700;
            font-variant-numeric: tabular-nums;
            margin-top: 6pt;
            color: #0D1B2A;
        }
        .a4-ticket-interno { font-size: 8pt; color: #8A9BB0; margin-top: 1pt; }

        /* ── Info de venta ── */
        .a4-venta-info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 12pt;
            padding: 8pt 10pt;
            background: #F4F6F9;
            border-radius: 4pt;
            font-size: 9pt;
        }
        .a4-venta-info span { color: #8A9BB0; }
        .a4-venta-info strong { color: #0D1B2A; font-weight: 600; }

        /* ── Medios de pago ── */
        .a4-pagos { display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 14pt; }
        .a4-pago-badge {
            display: inline-block;
            padding: 3pt 10pt;
            background: #E8F4FD;
            color: #1E6FA8;
            border-radius: 20pt;
            font-size: 8.5pt;
            font-weight: 600;
        }

        /* ── Tabla de ítems ── */
        .a4-table { width: 100%; border-collapse: collapse; margin-bottom: 14pt; font-size: 9.5pt; }
        .a4-table thead th {
            text-align: left;
            padding: 7pt 8pt;
            background: #1E6FA8;
            color: #fff;
            font-size: 7.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .05em;
        }
        .a4-table thead th:first-child { border-radius: 3pt 0 0 0; }
        .a4-table thead th:last-child  { border-radius: 0 3pt 0 0; text-align: right; }
        .a4-table th:not(:first-child) { text-align: right; }
        .a4-table td {
            padding: 7pt 8pt;
            border-bottom: 1px solid #E4EAF0;
            vertical-align: top;
        }
        .a4-table td:not(:first-child) { text-align: right; }
        .a4-table tbody tr:nth-child(even) { background: #FAFAFA; }
        .a4-table tbody tr:last-child td   { border-bottom: 1px solid #0D1B2A; }

        .a4-prod-nombre  { font-weight: 600; }
        .a4-prod-detalle { font-size: 8pt; color: #8A9BB0; margin-top: 2pt; }
        .a4-desc-badge   { color: #10B981; font-weight: 600; }

        /* ── Totales ── */
        .a4-totales { display: flex; justify-content: flex-end; margin-bottom: 16pt; }
        .a4-totales-tabla { width: 230pt; font-size: 9.5pt; }
        .a4-totales-tabla td { padding: 3pt 0; color: #4A5568; }
        .a4-totales-tabla td:last-child { text-align: right; font-weight: 600; color: #0D1B2A; }
        .a4-total-final td {
            border-top: 1.5px solid #0D1B2A;
            padding-top: 8pt;
            font-size: 15pt;
            font-weight: 800;
            color: #0D1B2A !important;
        }
        .a4-total-final td:last-child { color: #F26A1B !important; }

        /* ── Comprobante ARCA (CAE + QR) ── */
        .a4-comprobante {
            display: flex;
            align-items: center;
            gap: 14pt;
            margin-bottom: 14pt;
            padding: 10pt 14pt;
            background: #E8F4FD;
            border-left: 4pt solid #1E6FA8;
            border-radius: 4pt;
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
            border-top: 1px solid #E4EAF0;
            padding-top: 10pt;
            margin-top: 6pt;
        }

        /* ── Print ── */
        @media print {
            html, body { width: auto; }
            body { padding: 0 22mm 20mm; }
            .a4-topbar { margin: 0 -22mm 16pt; }
            @page { size: A4; margin: 14mm 0; }
        }
    </style>
</head>
<body>

    <div class="a4-topbar"></div>

    <!-- Cabecera empresa -->
    <div class="a4-header">
        <div>
            ${emp.logo_url ? `<img class="a4-logo" src="${_esc(emp.logo_url)}" alt="Logo">` : ''}
            <div class="a4-empresa-nombre">${_esc(emp.nombre)}</div>
            ${emp.razon_social ? `<div class="a4-empresa-dato">${_esc(emp.razon_social)}</div>` : ''}
            ${emp.domicilio    ? `<div class="a4-empresa-dato">${_esc(emp.domicilio)}</div>`    : ''}
            ${emp.telefono     ? `<div class="a4-empresa-dato">Tel: ${_esc(emp.telefono)}</div>` : ''}
            ${emp.email        ? `<div class="a4-empresa-dato">${_esc(emp.email)}</div>`        : ''}
            ${emp.cuit         ? `<div class="a4-empresa-dato">CUIT: ${_esc(emp.cuit)}</div>`  : ''}
            ${emp.condicion_iva? `<div class="a4-empresa-dato">IVA: ${_esc(emp.condicion_iva)}</div>` : ''}
        </div>
        <div class="a4-titulo-box">
            <span class="a4-ticket-titulo${cbte ? '' : ' a4-titulo-simple'}">${cbte ? _esc(cbte.tipo_display) : 'Ticket de Venta'}</span>
            <div class="a4-ticket-numero">${cbte ? _esc(cbte.numero_display) : _esc(venta.numero)}</div>
            ${cbte ? `<div class="a4-ticket-interno">Venta interna ${_esc(venta.numero)}</div>` : ''}
        </div>
    </div>

    <!-- Info de venta -->
    <div class="a4-venta-info">
        <span>Fecha: <strong>${_esc(venta.fecha)}</strong></span>
        ${venta.confirmado_por ? `<span>Operador: <strong>${_esc(venta.confirmado_por)}</strong></span>` : '<span></span>'}
    </div>

    <!-- Medios de pago -->
    ${_a4Pagos(pagos, venta)}

    <!-- Tabla de ítems -->
    <table class="a4-table">
        <thead>
            <tr>
                <th>Producto</th>
                <th>Cant.</th>
                <th>Precio unit.</th>
                <th>Desc.</th>
                <th>Subtotal</th>
            </tr>
        </thead>
        <tbody>
            ${items.map(item => _a4FilaItem(item)).join('')}
        </tbody>
    </table>

    <!-- Totales -->
    <div class="a4-totales">
        <table class="a4-totales-tabla">
            <tr>
                <td>Líneas</td>
                <td>${items.length}</td>
            </tr>
            <tr class="a4-total-final">
                <td>Total</td>
                <td>$${_fmtNum(venta.total)}</td>
            </tr>
        </table>
    </div>

    <!-- Comprobante ARCA (CAE + QR) -->
    ${_a4Comprobante(cbte)}

    <!-- Notas -->
    ${venta.notas ? `<div class="a4-notas">${_esc(venta.notas)}</div>` : ''}

    <!-- Pie -->
    <div class="a4-footer">Gracias por su compra.</div>

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
    <\/script>
</body>
</html>`;
}

/* ── Helpers internos ─────────────────────────────────────────── */

function _a4FilaItem(item) {
    const detalle = [
        item.marca   ? _esc(item.marca) : '',
        item.codigo  ? item.codigo : '',
        item.color   ? `Color: ${_esc(item.color)}`   : '',
        item.cliente ? `Cliente: ${_esc(item.cliente)}` : '',
        item.condicion_pago_display || '',
    ].filter(Boolean).join(' · ');

    return `<tr>
        <td>
            <div class="a4-prod-nombre">${_esc(item.nombre)}</div>
            ${detalle ? `<div class="a4-prod-detalle">${detalle}</div>` : ''}
        </td>
        <td>${_esc(String(item.cantidad))}</td>
        <td>${_esc(item.moneda)} ${_fmtNum(item.precio_unitario)}</td>
        <td>${item.descuento_pct && item.descuento_pct !== '0.00'
            ? `<span class="a4-desc-badge">-${_esc(String(item.descuento_pct))}%</span>`
            : '—'}</td>
        <td><strong>${_esc(item.moneda)} ${_fmtNum(item.subtotal)}</strong></td>
    </tr>`;
}

function _a4Comprobante(cbte) {
    if (!cbte) return '';
    return `<div class="a4-comprobante">
        ${cbte.qrDataUrl ? `<img class="a4-comprobante-qr" src="${cbte.qrDataUrl}" alt="QR AFIP">` : ''}
        <div class="a4-comprobante-datos">
            <div class="a4-comprobante-label">Comprobante autorizado por ARCA</div>
            <div>CAE: <b>${_esc(cbte.cae)}</b></div>
            <div>Vencimiento del CAE: <b>${_esc(cbte.cae_vencimiento)}</b></div>
        </div>
    </div>`;
}

function _a4Pagos(pagos, venta) {
    if (pagos && pagos.length) {
        const badges = pagos.map(p =>
            `<span class="a4-pago-badge">${_esc(p.medio_display)}: $${_fmtNum(p.monto)}</span>`
        ).join('');
        return `<div class="a4-pagos">${badges}</div>`;
    }
    if (venta.medio_pago_display) {
        return `<div class="a4-pagos">
            <span class="a4-pago-badge">${_esc(venta.medio_pago_display)}</span>
        </div>`;
    }
    return '';
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
