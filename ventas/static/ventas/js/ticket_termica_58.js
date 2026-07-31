/**
 * ticket_termica_58.js
 * ─────────────────────────────────────────────────────────────────
 * Generador de HTML para ticket de venta en impresora térmica 58mm.
 *
 * Ancho real: aunque el rollo es de 58mm, el cabezal de impresión de
 * la enorme mayoría de estas impresoras solo imprime ~48mm de ancho
 * (48mm / 384 dots a 203dpi es el estándar de la categoría "58mm").
 * Diseñar a 50mm+ hace que la columna derecha se corte en la
 * impresión real — por eso acá el contenido se arma a 48mm con
 * márgenes de 1.5mm a los costados, no a los 58mm nominales del papel.
 *
 * Diferencias respecto a ticket_termica_80.js:
 *   - Ancho útil ~45mm (más estrecho aún)
 *   - Fuente más pequeña (7.5pt base) para que entren más caracteres
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
    const emp     = data.empresa || {};
    const venta   = data.venta   || {};
    const items   = data.items   || [];
    const pagos   = data.pagos   || [];
    const cbte    = data.comprobante_arca || null;
    const cliente = data.cliente || null;

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
            width: 48mm;
            font-family: 'Courier New', Courier, monospace;
            font-size: 7.5pt;
            color: #000;
            background: #fff;
        }
        body { padding: 2mm 1.5mm 8mm 1.5mm; }

        /* ── Utilidades ── */
        /* Igual criterio que en el ticket de 80mm (ver ese archivo para
           el detalle): la térmica no tiene escala de grises real, así
           que ningún texto va en gris — todo negro puro, con más peso
           en el texto secundario para que el cabezal tenga suficiente
           densidad de tinta por carácter. Acá los tamaños se mantienen
           más chicos que en 80mm a propósito (ancho útil de solo 48mm),
           pero ninguno queda tan chico como para perder densidad. */
        .t58-center { text-align: center; }
        .t58-right  { text-align: right; }
        .t58-bold   { font-weight: bold; }
        .t58-peq    { font-size: 6.5pt; font-weight: 600; line-height: 1.4; }

        .t58-sep-doble  { border: none; border-top: 2px solid #000; margin: 3pt 0; }
        .t58-sep-simple { border: none; border-top: 1px dashed #000; margin: 2pt 0; }

        /* ── Cabecera empresa ── */
        .t58-logo {
            max-width: 130px;
            max-height: 46px;
            display: block;
            margin: 0 auto 3pt;
            filter: grayscale(1) contrast(1.6) brightness(1.05);
        }
        .t58-empresa-nombre { font-size: 9pt; font-weight: bold; text-align: center; }
        .t58-empresa-dato   { font-size: 6.5pt; font-weight: 600; text-align: center; line-height: 1.45; }
        .t58-empresa-datos-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1pt 3pt;
            font-size: 6.5pt;
            font-weight: 600;
            text-align: center;
            margin-bottom: 1pt;
        }

        /* ── Número de venta ── */
        .t58-venta-num  { font-size: 8pt; font-weight: bold; text-align: center; margin: 2pt 0 1pt; }
        .t58-venta-meta { font-size: 6.5pt; font-weight: 600; text-align: center; }

        /* ── Cliente ── */
        .t58-cliente-cf {
            font-size: 6.8pt; font-weight: bold; text-align: center;
            letter-spacing: .03em; margin: 2pt 0;
        }
        .t58-cliente { text-align: center; margin: 2pt 0; }
        .t58-cliente-nombre { font-weight: bold; font-size: 7pt; }

        /* ── Ítems ── */
        .t58-items { width: 100%; margin: 3pt 0; }
        .t58-item  { margin-bottom: 4pt; }
        .t58-item-nombre {
            font-weight: bold;
            font-size: 7pt;
            word-break: break-word;
            line-height: 1.3;
        }
        .t58-item-detalle { font-size: 6.2pt; font-weight: 600; }
        .t58-item-nums {
            display: flex;
            justify-content: space-between;
            font-size: 7pt;
            font-weight: 600;
            margin-top: 1pt;
            gap: 3pt;
        }

        /* ── Totales ── */
        .t58-total-row {
            display: flex;
            justify-content: space-between;
            font-size: 7pt;
            font-weight: 600;
            line-height: 1.7;
        }
        .t58-total-final {
            display: flex;
            justify-content: space-between;
            font-size: 12pt;
            font-weight: bold;
            margin-top: 2pt;
        }

        /* ── Pagos ── */
        .t58-pago-row {
            display: flex;
            justify-content: space-between;
            font-size: 6.5pt;
            font-weight: 600;
            line-height: 1.6;
        }

        /* ── Comprobante ARCA ── */
        .t58-comprobante {
            text-align: center;
            border: 1.5px solid #000;
            border-radius: 2pt;
            padding: 4pt 3pt;
            margin: 3pt 0;
        }
        .t58-comprobante-label {
            font-size: 6.2pt;
            font-weight: bold;
            letter-spacing: .04em;
            text-transform: uppercase;
            margin-bottom: 2pt;
        }

        /* ── Pie ── */
        .t58-footer {
            text-align: center;
            font-size: 6.5pt;
            font-weight: 600;
            margin-top: 4pt;
            line-height: 1.6;
        }

        /* ── Print ── */
        @media print {
            html, body { width: auto; }
            body { padding: 0 1.5mm 8mm; }
            @page {
                size: 58mm auto;
                margin: 1mm 1mm 0 1mm;
            }
        }
    </style>
</head>
<body>

    <!-- Logo -->
    ${emp.logo_url ? `<img class="t58-logo" src="${_esc(emp.logo_url)}" alt="">` : ''}

    <!-- Empresa -->
    <div class="t58-empresa-nombre">${_esc(emp.nombre)}</div>
    ${emp.razon_social ? `<div class="t58-empresa-dato">${_esc(emp.razon_social)}</div>` : ''}
    ${_t58EmpresaDatosGrid([
        emp.telefono      ? `Tel: ${emp.telefono}`      : null,
        emp.cuit          ? `CUIT: ${emp.cuit}`         : null,
        emp.condicion_iva ? `IVA: ${emp.condicion_iva}` : null,
        emp.domicilio     ? `Dom: ${emp.domicilio}`     : null,
    ])}

    <hr class="t58-sep-doble">

    <!-- Número y fecha -->
    <div class="t58-venta-num">${cbte ? _esc(cbte.tipo_display) + ' ' + _esc(cbte.numero_display) : _esc(venta.numero)}</div>
    <div class="t58-venta-meta">${_esc(venta.fecha_hora || venta.fecha)}</div>
    ${venta.confirmado_por ? `<div class="t58-venta-meta">Op: ${_esc(venta.confirmado_por)}</div>` : ''}

    <hr class="t58-sep-simple">

    <!-- Cliente -->
    ${_t58Cliente(cliente)}

    <hr class="t58-sep-simple">

    <!-- Ítems -->
    <div class="t58-items">
        ${items.map(item => _t58Item(item)).join('')}
    </div>

    <hr class="t58-sep-doble">

    <!-- Total -->
    ${_t58DesgloseIva(cbte)}
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

    <!-- Comprobante ARCA (CAE + QR) -->
    ${_t58Comprobante(cbte)}

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

// Igual idea que en 80mm (2 datos por línea), pero acá el ancho útil es
// de solo 48mm — un teléfono y un CUIT completos (con guiones) casi
// nunca entran juntos sin que uno se corte a la mitad. En vez de forzar
// el emparejado siempre, se intenta de a 2 y solo se arma la fila doble
// si el largo combinado entra en el ancho disponible a este tamaño de
// letra; si no entra, ese dato queda solo en su propia línea completa.
// Así, cuando los valores son cortos SÍ se ven 2 por línea (como en
// 80mm), y cuando no entran (el caso típico de teléfono+CUIT argentino)
// no se rompe ningún número.
const T58_GRID_MAX_CHARS = 34; // ajustado para 48mm de ancho a 6.5pt

function _t58EmpresaDatosGrid(campos) {
    const valores = campos.filter(Boolean);
    let html = '';
    let i = 0;
    while (i < valores.length) {
        const actual = valores[i];
        const siguiente = valores[i + 1];
        if (siguiente && (actual.length + siguiente.length) <= T58_GRID_MAX_CHARS) {
            html += `<div class="t58-empresa-datos-grid"><span>${_esc(actual)}</span><span>${_esc(siguiente)}</span></div>`;
            i += 2;
        } else {
            html += `<div class="t58-empresa-dato">${_esc(actual)}</div>`;
            i += 1;
        }
    }
    return html;
}

function _t58Cliente(cliente) {
    if (!cliente) {
        return `<div class="t58-cliente-cf">CONSUMIDOR FINAL</div>`;
    }
    return `<div class="t58-cliente">
        <div class="t58-cliente-nombre">Cliente: ${_esc(cliente.nombre)}</div>
        ${cliente.documento ? `<div class="t58-peq">${_esc(cliente.documento)}</div>` : ''}
        ${cliente.direccion ? `<div class="t58-peq">Dir: ${_esc(cliente.direccion)}</div>` : ''}
        ${cliente.telefono  ? `<div class="t58-peq">Tel: ${_esc(cliente.telefono)}</div>` : ''}
    </div>`;
}

function _t58Item(item) {
    const desc = item.descuento_pct && item.descuento_pct !== '0.00'
        ? ` -${item.descuento_pct}%`
        : '';
    // Código en la línea chica (no en el título) — hace falta para
    // identificar el producto ante una devolución, sin volver a cargar
    // de largo el nombre principal.
    const detalle = [
        item.codigo ? _esc(`Cód: ${item.codigo}`) : '',
        item.marca  ? _esc(item.marca)            : '',
        item.color  ? _esc(item.color)            : '',
    ].filter(Boolean).join(' · ');
    return `<div class="t58-item">
        <div class="t58-item-nombre">${_esc(item.nombre)}</div>
        ${detalle ? `<div class="t58-item-detalle">${detalle}</div>` : ''}
        <div class="t58-item-nums">
            <span class="t58-item-cant">${_esc(String(item.cantidad))}x ${_fmtNum(item.precio_unitario)}${desc}</span>
            <span><strong>${_fmtNum(item.subtotal)}</strong></span>
        </div>
    </div>`;
}

// Factura A/B discrimina IVA (tipo_comprobante: 1=A, 6=B, 11=C) — Factura C
// nunca lo mostró y sigue igual.
function _t58DesgloseIva(cbte) {
    if (!cbte || (cbte.tipo_comprobante !== 1 && cbte.tipo_comprobante !== 6)) return '';
    return `
        <div class="t58-total-row"><span>Neto gravado</span><span>$${_fmtNum(cbte.importe_neto)}</span></div>
        <div class="t58-total-row"><span>IVA</span><span>$${_fmtNum(cbte.importe_iva)}</span></div>
    `;
}

function _t58Comprobante(cbte) {
    if (!cbte) return '';
    return `<div class="t58-comprobante">
        <div class="t58-comprobante-label">Autorizado por ARCA</div>
        ${cbte.qrDataUrl ? `<img src="${cbte.qrDataUrl}" alt="QR AFIP" style="width:24mm; height:24mm; margin:2pt auto; display:block;">` : ''}
        <div class="t58-peq">CAE: <strong>${_esc(cbte.cae)}</strong></div>
        <div class="t58-peq">Vto: <strong>${_esc(cbte.cae_vencimiento)}</strong></div>
    </div>`;
}

function _t58PagoDetalle(p) {
    const partes = [];
    if (p.etiqueta_plan && Number(p.cantidad_pagos) > 1) partes.push(p.etiqueta_plan);
    if (p.recargo_monto && parseFloat(p.recargo_monto) > 0) partes.push(`+${p.recargo_pct}%`);
    return partes.length ? ` (${partes.join(', ')})` : '';
}

function _t58Pagos(pagos, venta) {
    if (pagos && pagos.length) {
        return pagos.map(p => {
            const tarjeta = p.tarjeta_nombre ? ` · ${_esc(p.tarjeta_nombre)}` : '';
            return `
        <div class="t58-pago-row">
            <span>${_esc(p.medio_display)}${tarjeta}${_t58PagoDetalle(p)}</span>
            <span>$${_fmtNum(p.monto)}</span>
        </div>`;
        }).join('');
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
