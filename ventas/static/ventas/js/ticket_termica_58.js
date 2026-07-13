/**
 * ticket_termica_58.js
 * ─────────────────────────────────────────────────────────────────
 * Generador de HTML para ticket de venta en impresora térmica 58mm.
 *
 * Diferencias respecto a ticket_termica_80.js:
 *   - Ancho útil ~50mm (más estrecho aún)
 *   - Fuente más pequeña (8pt base) para que entren más caracteres
 *   - Nombres de producto más cortos — se truncan con CSS
 *   - Total aún más destacado (es lo más importante en 58mm)
 *   - Sin columnas precio/cant en la misma línea si el nombre es largo
 *     (se pone en línea separada abajo del nombre)
 *
 * Exporta: ticketHtmlTermica58(data) → string HTML completo
 *
 * Estructura de `data`: igual que ticket_a4.js (ver ese archivo).
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

/**
 * Genera el HTML completo del ticket para impresora térmica 58mm.
 * @param {object} data
 * @returns {string}
 */
function ticketHtmlTermica58(data) {
    const emp   = data.empresa || {};
    const venta = data.venta   || {};
    const items = data.items   || [];
    const pagos = data.pagos   || [];

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Ticket 58mm — ${_esc(venta.numero)}</title>
    <style>
        /* ── Reset ── */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        /* ── Página ── */
        html, body {
            width: 50mm;
            font-family: 'Courier New', Courier, monospace;
            font-size: 8pt;
            color: #000;
            background: #fff;
        }
        body { padding: 2mm 1.5mm 8mm 1.5mm; }

        /* ── Utilidades ── */
        .t58-center { text-align: center; }
        .t58-right  { text-align: right; }
        .t58-bold   { font-weight: bold; }
        .t58-peq    { font-size: 6.5pt; color: #333; }

        .t58-sep-doble  { border: none; border-top: 2px solid #000; margin: 3pt 0; }
        .t58-sep-simple { border: none; border-top: 1px dashed #000; margin: 2pt 0; }

        /* ── Cabecera empresa ── */
        .t58-logo { max-width: 130px; max-height: 40px; display: block; margin: 0 auto 3pt; }
        .t58-empresa-nombre { font-size: 9.5pt; font-weight: bold; text-align: center; }
        .t58-empresa-dato   { font-size: 6.5pt; text-align: center; line-height: 1.5; }

        /* ── Número de venta ── */
        .t58-venta-num  { font-size: 8.5pt; font-weight: bold; text-align: center; margin: 2pt 0 1pt; }
        .t58-venta-meta { font-size: 6.5pt; text-align: center; color: #333; }

        /* ── Ítems ── */
        .t58-items { width: 100%; margin: 3pt 0; }
        .t58-item  { margin-bottom: 4pt; }
        .t58-item-nombre {
            font-weight: bold;
            font-size: 7.5pt;
            word-break: break-word;
            line-height: 1.3;
        }
        .t58-item-detalle { font-size: 6pt; color: #555; }
        .t58-item-nums {
            display: flex;
            justify-content: space-between;
            font-size: 7.5pt;
            margin-top: 1pt;
        }

        /* ── Totales ── */
        .t58-total-row {
            display: flex;
            justify-content: space-between;
            font-size: 7.5pt;
            line-height: 1.7;
        }
        .t58-total-final {
            display: flex;
            justify-content: space-between;
            font-size: 13pt;
            font-weight: bold;
            margin-top: 2pt;
        }

        /* ── Pagos ── */
        .t58-pago-row {
            display: flex;
            justify-content: space-between;
            font-size: 7pt;
            line-height: 1.6;
        }

        /* ── Pie ── */
        .t58-footer {
            text-align: center;
            font-size: 6.5pt;
            color: #555;
            margin-top: 4pt;
            line-height: 1.6;
        }

        /* ── Print ── */
        @media print {
            html, body { width: auto; }
            body { padding: 0 1.5mm 8mm; }
            @page {
                size: 58mm auto;
                margin: 1mm 0 0 0;
            }
        }
    </style>
</head>
<body>

    <!-- Logo -->
    ${emp.logo_url ? `<img class="t58-logo" src="${_esc(emp.logo_url)}" alt="">` : ''}

    <!-- Empresa -->
    <div class="t58-empresa-nombre">${_esc(emp.nombre)}</div>
    ${emp.domicilio ? `<div class="t58-empresa-dato">${_esc(emp.domicilio)}</div>` : ''}
    ${emp.telefono  ? `<div class="t58-empresa-dato">Tel: ${_esc(emp.telefono)}</div>` : ''}
    ${emp.cuit      ? `<div class="t58-empresa-dato">CUIT: ${_esc(emp.cuit)}</div>`  : ''}

    <hr class="t58-sep-doble">

    <!-- Número y fecha -->
    <div class="t58-venta-num">${_esc(venta.numero)}</div>
    <div class="t58-venta-meta">${_esc(venta.fecha)}</div>
    ${venta.confirmado_por ? `<div class="t58-venta-meta">Op: ${_esc(venta.confirmado_por)}</div>` : ''}

    <hr class="t58-sep-simple">

    <!-- Ítems -->
    <div class="t58-items">
        ${items.map(item => _t58Item(item)).join('')}
    </div>

    <hr class="t58-sep-doble">

    <!-- Total -->
    <div class="t58-total-final">
        <span>TOTAL</span>
        <span>$${_fmtNum(venta.total)}</span>
    </div>

    <hr class="t58-sep-simple">

    <!-- Medios de pago -->
    ${_t58Pagos(pagos, venta)}

    <!-- Notas (solo si caben — se truncan por CSS si son muy largas) -->
    ${venta.notas ? `
    <hr class="t58-sep-simple">
    <div class="t58-peq" style="white-space:pre-line;overflow:hidden;max-height:20mm">${_esc(venta.notas)}</div>
    ` : ''}

    <!-- Pie -->
    <hr class="t58-sep-simple">
    <div class="t58-footer">Gracias por su compra.</div>

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

function _t58Item(item) {
    const desc = item.descuento_pct && item.descuento_pct !== '0.00'
        ? ` -${item.descuento_pct}%`
        : '';
    return `<div class="t58-item">
        <div class="t58-item-nombre">${_esc(item.nombre)}</div>
        ${item.color ? `<div class="t58-item-detalle">${_esc(item.color)}</div>` : ''}
        <div class="t58-item-nums">
            <span>${_esc(String(item.cantidad))}x ${_fmtNum(item.precio_unitario)}${desc}</span>
            <span><strong>${_fmtNum(item.subtotal)}</strong></span>
        </div>
    </div>`;
}

function _t58Pagos(pagos, venta) {
    if (pagos && pagos.length) {
        return pagos.map(p => `
        <div class="t58-pago-row">
            <span>${_esc(p.medio_display)}</span>
            <span>$${_fmtNum(p.monto)}</span>
        </div>`).join('');
    }
    if (venta.medio_pago_display) {
        return `<div class="t58-pago-row"><span>${_esc(venta.medio_pago_display)}</span><span></span></div>`;
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