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
 * }
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

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Ticket A4 — ${_esc(venta.numero)}</title>
    <style>
        /* ── Reset ── */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        /* ── Página ── */
        html, body {
            width: 210mm;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11pt;
            color: #111;
            background: #fff;
        }
        body { padding: 20mm 22mm; }

        /* ── Cabecera empresa ── */
        .a4-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            padding-bottom: 10pt;
            border-bottom: 2px solid #111;
            margin-bottom: 12pt;
        }
        .a4-logo { max-height: 55px; max-width: 160px; object-fit: contain; }
        .a4-empresa-nombre { font-size: 15pt; font-weight: 700; margin-bottom: 3pt; }
        .a4-empresa-dato   { font-size: 9pt; color: #555; margin: 1pt 0; }

        /* ── Info de venta ── */
        .a4-venta-info {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 14pt;
        }
        .a4-ticket-titulo {
            font-size: 14pt;
            font-weight: 800;
            letter-spacing: -.01em;
        }
        .a4-ticket-numero { font-size: 11pt; color: #555; margin-top: 2pt; }
        .a4-venta-meta    { text-align: right; font-size: 9.5pt; color: #555; line-height: 1.6; }

        /* ── Tabla de ítems ── */
        .a4-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 14pt;
            font-size: 9.5pt;
        }
        .a4-table th {
            text-align: left;
            padding: 5pt 6pt;
            border-bottom: 1.5px solid #111;
            font-size: 8pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .04em;
            color: #444;
        }
        .a4-table th:not(:first-child) { text-align: right; }
        .a4-table td {
            padding: 5pt 6pt;
            border-bottom: 1px solid #e5e5e5;
            vertical-align: top;
        }
        .a4-table td:not(:first-child) { text-align: right; }
        .a4-table tr:last-child td     { border-bottom: none; }

        .a4-prod-nombre  { font-weight: 600; }
        .a4-prod-detalle { font-size: 8pt; color: #777; margin-top: 2pt; }
        .a4-desc-badge   { color: #16a34a; font-size: 8pt; }

        /* ── Totales ── */
        .a4-totales {
            display: flex;
            justify-content: flex-end;
            margin-bottom: 14pt;
        }
        .a4-totales-tabla { width: 220pt; font-size: 9.5pt; }
        .a4-totales-tabla td { padding: 3pt 0; }
        .a4-totales-tabla td:last-child { text-align: right; font-weight: 600; }
        .a4-total-final td {
            border-top: 2px solid #111;
            padding-top: 6pt;
            font-size: 12pt;
            font-weight: 800;
        }

        /* ── Medios de pago ── */
        .a4-pagos {
            display: flex;
            gap: .6rem;
            flex-wrap: wrap;
            margin-bottom: 14pt;
        }
        .a4-pago-badge {
            display: inline-block;
            padding: 2pt 8pt;
            border: 1px solid #ccc;
            border-radius: 20pt;
            font-size: 8.5pt;
            color: #444;
        }

        /* ── Notas ── */
        .a4-notas {
            font-size: 9pt;
            color: #555;
            padding: 6pt 9pt;
            border-left: 3px solid #e5e5e5;
            margin-bottom: 14pt;
            white-space: pre-line;
        }

        /* ── Pie ── */
        .a4-footer {
            text-align: center;
            font-size: 8.5pt;
            color: #888;
            border-top: 1px solid #ddd;
            padding-top: 8pt;
            margin-top: 14pt;
        }

        /* ── Print ── */
        @media print {
            html, body { width: auto; }
            body { padding: 0; }
            @page { size: A4; margin: 18mm 20mm; }
        }
    </style>
</head>
<body>

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
        <div style="text-align:right">
            <div class="a4-ticket-titulo">Ticket de Venta</div>
            <div class="a4-ticket-numero">${_esc(venta.numero)}</div>
        </div>
    </div>

    <!-- Info de venta -->
    <div class="a4-venta-info">
        <div></div>
        <div class="a4-venta-meta">
            <div>Fecha: <strong>${_esc(venta.fecha)}</strong></div>
            ${venta.confirmado_por ? `<div>Operador: ${_esc(venta.confirmado_por)}</div>` : ''}
        </div>
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
                <td style="color:#555">Líneas</td>
                <td>${items.length}</td>
            </tr>
            <tr class="a4-total-final">
                <td>Total</td>
                <td>$${_fmtNum(venta.total)}</td>
            </tr>
        </table>
    </div>

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
            ? `<span class="a4-desc-badge">${_esc(String(item.descuento_pct))}%</span>`
            : '—'}</td>
        <td><strong>${_esc(item.moneda)} ${_fmtNum(item.subtotal)}</strong></td>
    </tr>`;
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