/**
 * ticket_termica_80.js
 * ─────────────────────────────────────────────────────────────────
 * Generador de HTML para ticket de venta en impresora térmica 80mm.
 *
 * Características del formato:
 *   - Ancho fijo de 72mm (80mm de papel - ~4mm de márgenes c/lado)
 *   - Fuente monoespaciada para alinear columnas sin tablas complejas
 *   - Sin colores ni imágenes de fondo (las térmicas no los imprimen)
 *   - Logo en blanco/negro si existe (max 200px ancho)
 *   - Texto grande para el total (legibilidad en caja)
 *   - Sin @page margin grandes — la térmica come el papel desde arriba
 *
 * Exporta: ticketHtmlTermica80(data) → string HTML completo
 *
 * Estructura de `data`: igual que ticket_a4.js (ver ese archivo).
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

/**
 * Genera el HTML completo del ticket para impresora térmica 80mm.
 * @param {object} data
 * @returns {string}
 */
function ticketHtmlTermica80(data) {
    const emp   = data.empresa || {};
    const venta = data.venta   || {};
    const items = data.items   || [];
    const pagos = data.pagos   || [];

    // En 80mm con fuente monoespaciada ~9pt entran ~42 caracteres por línea
    const COLS = 42;

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Ticket 80mm — ${_esc(venta.numero)}</title>
    <style>
        /* ── Reset ── */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        /* ── Página ── */
        html, body {
            width: 72mm;
            font-family: 'Courier New', Courier, monospace;
            font-size: 9pt;
            color: #000;
            background: #fff;
        }
        body { padding: 3mm 2mm 8mm 2mm; }

        /* ── Elementos comunes ── */
        .t80-center { text-align: center; }
        .t80-right  { text-align: right; }
        .t80-bold   { font-weight: bold; }
        .t80-grande { font-size: 13pt; font-weight: bold; }
        .t80-peq    { font-size: 7.5pt; color: #333; }

        .t80-sep-doble  { border: none; border-top: 2px solid #000; margin: 4pt 0; }
        .t80-sep-simple { border: none; border-top: 1px dashed #000; margin: 3pt 0; }

        /* ── Cabecera ── */
        .t80-logo { max-width: 200px; max-height: 50px; display: block; margin: 0 auto 4pt; }
        .t80-empresa-nombre { font-size: 11pt; font-weight: bold; text-align: center; margin-bottom: 2pt; }
        .t80-empresa-dato   { font-size: 7.5pt; text-align: center; line-height: 1.5; }

        /* ── Info de venta ── */
        .t80-venta-num  { font-size: 9.5pt; font-weight: bold; text-align: center; margin: 3pt 0 1pt; }
        .t80-venta-meta { font-size: 7.5pt; text-align: center; color: #333; margin-bottom: 2pt; }

        /* ── Tabla de ítems (sin <table>, usa divs para control exacto de ancho) ── */
        .t80-items { width: 100%; margin: 3pt 0; }
        .t80-item  { margin-bottom: 4pt; }
        .t80-item-nombre  { font-weight: bold; font-size: 8.5pt; word-break: break-word; }
        .t80-item-detalle { font-size: 7pt; color: #444; }
        .t80-item-nums {
            display: flex;
            justify-content: space-between;
            font-size: 8.5pt;
            margin-top: 1pt;
        }
        .t80-item-cant  { flex: 0 0 auto; }
        .t80-item-sub   { flex: 0 0 auto; font-weight: bold; }

        /* ── Totales ── */
        .t80-totales { width: 100%; margin: 3pt 0; }
        .t80-total-row {
            display: flex;
            justify-content: space-between;
            font-size: 8.5pt;
            line-height: 1.7;
        }
        .t80-total-final {
            display: flex;
            justify-content: space-between;
            font-size: 14pt;
            font-weight: bold;
            margin-top: 2pt;
        }

        /* ── Pagos ── */
        .t80-pago-row {
            display: flex;
            justify-content: space-between;
            font-size: 8pt;
            line-height: 1.6;
        }

        /* ── Pie ── */
        .t80-footer {
            text-align: center;
            font-size: 7.5pt;
            color: #444;
            margin-top: 5pt;
            line-height: 1.6;
        }

        /* ── Print ── */
        @media print {
            html, body { width: auto; }
            body { padding: 0 2mm 8mm; }
            @page {
                size: 80mm auto;   /* alto automático = corte por contenido */
                margin: 2mm 0 0 0;
            }
        }
    </style>
</head>
<body>

    <!-- Logo -->
    ${emp.logo_url ? `<img class="t80-logo" src="${_esc(emp.logo_url)}" alt="Logo">` : ''}

    <!-- Empresa -->
    <div class="t80-empresa-nombre">${_esc(emp.nombre)}</div>
    ${emp.razon_social ? `<div class="t80-empresa-dato">${_esc(emp.razon_social)}</div>` : ''}
    ${emp.domicilio    ? `<div class="t80-empresa-dato">${_esc(emp.domicilio)}</div>`    : ''}
    ${emp.telefono     ? `<div class="t80-empresa-dato">Tel: ${_esc(emp.telefono)}</div>` : ''}
    ${emp.cuit         ? `<div class="t80-empresa-dato">CUIT: ${_esc(emp.cuit)}</div>`  : ''}
    ${emp.condicion_iva? `<div class="t80-empresa-dato">IVA: ${_esc(emp.condicion_iva)}</div>` : ''}

    <hr class="t80-sep-doble">

    <!-- Número y fecha -->
    <div class="t80-venta-num">TICKET ${_esc(venta.numero)}</div>
    <div class="t80-venta-meta">Fecha: ${_esc(venta.fecha)}</div>
    ${venta.confirmado_por ? `<div class="t80-venta-meta">Op: ${_esc(venta.confirmado_por)}</div>` : ''}

    <hr class="t80-sep-simple">

    <!-- Ítems -->
    <div class="t80-items">
        ${items.map(item => _t80Item(item)).join('')}
    </div>

    <hr class="t80-sep-doble">

    <!-- Totales -->
    <div class="t80-totales">
        <div class="t80-total-row">
            <span>Líneas:</span><span>${items.length}</span>
        </div>
        <div class="t80-total-final">
            <span>TOTAL</span>
            <span>$${_fmtNum(venta.total)}</span>
        </div>
    </div>

    <hr class="t80-sep-simple">

    <!-- Medios de pago -->
    ${_t80Pagos(pagos, venta)}

    <!-- Notas -->
    ${venta.notas ? `
    <hr class="t80-sep-simple">
    <div class="t80-peq" style="white-space:pre-line">${_esc(venta.notas)}</div>
    ` : ''}

    <!-- Pie -->
    <hr class="t80-sep-simple">
    <div class="t80-footer">
        Gracias por su compra.<br>
        ${emp.email ? _esc(emp.email) : ''}
    </div>

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

function _t80Item(item) {
    const detalle = [
        item.color   ? `Color: ${item.color}`     : '',
        item.cliente ? `Cli: ${item.cliente}`      : '',
    ].filter(Boolean).join(' · ');

    const desc = item.descuento_pct && item.descuento_pct !== '0.00'
        ? ` (-${item.descuento_pct}%)`
        : '';

    return `<div class="t80-item">
        <div class="t80-item-nombre">${_esc(item.nombre)}</div>
        ${detalle ? `<div class="t80-item-detalle">${_esc(detalle)}</div>` : ''}
        <div class="t80-item-nums">
            <span class="t80-item-cant">${_esc(String(item.cantidad))} x ${_esc(item.moneda)} ${_fmtNum(item.precio_unitario)}${desc}</span>
            <span class="t80-item-sub">${_esc(item.moneda)} ${_fmtNum(item.subtotal)}</span>
        </div>
    </div>`;
}

function _t80Pagos(pagos, venta) {
    if (pagos && pagos.length) {
        return pagos.map(p => `
        <div class="t80-pago-row">
            <span>${_esc(p.medio_display)}</span>
            <span>$${_fmtNum(p.monto)}</span>
        </div>`).join('');
    }
    if (venta.medio_pago_display) {
        return `<div class="t80-pago-row"><span>${_esc(venta.medio_pago_display)}</span><span></span></div>`;
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