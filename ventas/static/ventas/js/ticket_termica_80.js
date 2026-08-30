/**
 * ticket_termica_80.js
 * ─────────────────────────────────────────────────────────────────
 * Generador de HTML para ticket de venta en impresora térmica 80mm.
 *
 * Características del formato:
 *   - Ancho fijo de 72mm (80mm de papel - márgenes reales del cabezal
 *     de impresión, que en esta categoría imprime ~72mm/576 dots a
 *     203dpi aunque el rollo mida 80mm — mismo criterio que 58mm/48mm
 *     en ticket_termica_58.js)
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
 * @param {object} [opts]
 * @param {boolean} [opts.sinAutoImpresion]  No incluir el <script> que
 *   dispara window.print() al cargar (lo usa ticket_pdf.js).
 * @returns {string}
 */
function ticketHtmlTermica80(data, opts) {
    const sinAutoImpresion = !!(opts && opts.sinAutoImpresion);
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
        /* Las térmicas no manejan grises reales (no hay escala de grises
           en el cabezal, solo punto quemado o no) — cualquier texto en
           gris claro sale como puntos salteados, ilegible en tamaños
           chicos. Todo el texto del ticket va en negro puro (#000, ya
           sea heredado del body o explícito) y ningún tamaño baja de
           8pt, así el cabezal siempre tiene suficiente densidad de tinta
           por carácter para no "cortar" letras. */
        .t80-peq    { font-size: 8pt; font-weight: 600; }

        .t80-sep-doble  { border: none; border-top: 2px solid #000; margin: 4pt 0; }
        .t80-sep-simple { border: none; border-top: 1px dashed #000; margin: 3pt 0; }

        /* ── Cabecera ── */
        /* Igual que con el texto: la térmica no tiene escala de grises
           real, así que cualquier zona intermedia del logo (antialiasing,
           semitonos) sale como puntos salteados = "borroso". El filtro
           empuja todo a blanco/negro puro (sin grises intermedios) y el
           tamaño más grande le da más superficie física por detalle para
           que el punteado del cabezal térmico lo resuelva mejor. Si el
           archivo de origen es de muy baja resolución esto ayuda pero no
           hace milagros — en ese caso conviene subir un logo más grande
           en Configuración. */
        .t80-logo {
            max-width: 260px;
            max-height: 90px;
            display: block;
            margin: 0 auto 4pt;
            filter: grayscale(1) contrast(1.6) brightness(1.05);
        }
        .t80-empresa-nombre { font-size: 11pt; font-weight: bold; text-align: center; margin-bottom: 2pt; }
        .t80-empresa-dato   { font-size: 8pt; font-weight: 600; text-align: center; line-height: 1.5; }
        .t80-empresa-datos-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1pt 4pt;
            font-size: 8pt;
            font-weight: 600;
            text-align: center;
            margin-bottom: 1pt;
        }

        /* ── Info de venta ── */
        .t80-venta-num  { font-size: 9.5pt; font-weight: bold; text-align: center; margin: 3pt 0 1pt; }
        .t80-venta-meta { font-size: 8pt; font-weight: 600; text-align: center; margin-bottom: 2pt; }

        /* ── Cliente ── */
        .t80-cliente-cf {
            font-size: 8pt; font-weight: bold; text-align: center;
            letter-spacing: .04em; margin: 3pt 0;
        }
        .t80-cliente { text-align: center; margin: 3pt 0; }
        .t80-cliente-nombre { font-weight: bold; font-size: 8.5pt; }
        .t80-cliente-dato   { font-size: 8pt; font-weight: 600; line-height: 1.5; }

        /* ── Tabla de ítems (sin <table>, usa divs para control exacto de ancho) ── */
        .t80-items { width: 100%; margin: 3pt 0; }
        .t80-item  { margin-bottom: 4pt; }
        .t80-item-nombre  { font-weight: bold; font-size: 8.5pt; word-break: break-word; }
        .t80-item-detalle { font-size: 8pt; font-weight: 600; }
        .t80-item-nums {
            display: flex;
            justify-content: space-between;
            font-size: 8.5pt;
            margin-top: 1pt;
        }
        .t80-item-cant  { flex: 0 0 auto; font-weight: 600; }
        .t80-item-sub   { flex: 0 0 auto; font-weight: bold; }

        /* ── Totales ── */
        .t80-totales { width: 100%; margin: 3pt 0; }
        .t80-total-row {
            display: flex;
            justify-content: space-between;
            font-size: 8.5pt;
            font-weight: 600;
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
            font-weight: 600;
            line-height: 1.6;
        }

        /* ── Comprobante ARCA ── */
        .t80-comprobante {
            text-align: center;
            border: 1.5px solid #000;
            border-radius: 2pt;
            padding: 5pt 4pt;
            margin: 4pt 0;
        }
        .t80-comprobante-label {
            font-size: 8pt;
            font-weight: bold;
            letter-spacing: .06em;
            text-transform: uppercase;
            margin-bottom: 3pt;
        }

        /* ── Pie ── */
        .t80-footer {
            text-align: center;
            font-size: 8pt;
            font-weight: 600;
            margin-top: 5pt;
            line-height: 1.6;
        }

        /* ── Print ── */
        @media print {
            html, body { width: auto; }
            body { padding: 0 2mm 8mm; }
            @page {
                size: 80mm auto;   /* alto automático = corte por contenido */
                margin: 2mm 1mm 0 1mm;
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
    ${_t80EmpresaDatosGrid([
        emp.telefono      ? `Tel: ${emp.telefono}`       : null,
        emp.cuit          ? `CUIT: ${emp.cuit}`          : null,
        emp.condicion_iva ? `IVA: ${emp.condicion_iva}`  : null,
        emp.domicilio     ? `Dom: ${emp.domicilio}`      : null,
    ])}

    <hr class="t80-sep-doble">

    <!-- Número y fecha -->
    <div class="t80-venta-num">${cbte ? _esc(cbte.tipo_display) + ' ' + _esc(cbte.numero_display) : 'TICKET ' + _esc(venta.numero)}</div>
    <div class="t80-venta-meta">Fecha: ${_esc(venta.fecha_hora || venta.fecha)}</div>
    ${venta.confirmado_por ? `<div class="t80-venta-meta">Op: ${_esc(venta.confirmado_por)}</div>` : ''}

    <hr class="t80-sep-simple">

    <!-- Cliente -->
    ${_t80Cliente(cliente)}

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
        ${_t80DesgloseIva(cbte)}
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

    <!-- Comprobante ARCA (CAE + QR) -->
    ${_t80Comprobante(cbte)}

    <!-- Pie -->
    <hr class="t80-sep-simple">
    <div class="t80-footer">
        Gracias por su compra.<br>
        ${emp.email ? _esc(emp.email) : ''}
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

// Arma los datos de la empresa de a pares por fila (Tel+CUIT, IVA+Dom.)
// para ahorrar espacio vertical — si sobra uno solo (cantidad impar),
// ese queda en su propia línea completa en vez de a la mitad vacío.
function _t80EmpresaDatosGrid(campos) {
    const valores = campos.filter(Boolean);
    let html = '';
    for (let i = 0; i < valores.length; i += 2) {
        if (i + 1 < valores.length) {
            html += `<div class="t80-empresa-datos-grid"><span>${_esc(valores[i])}</span><span>${_esc(valores[i + 1])}</span></div>`;
        } else {
            html += `<div class="t80-empresa-dato">${_esc(valores[i])}</div>`;
        }
    }
    return html;
}

// El cliente se muestra UNA sola vez acá (con etiquetas claras) — los
// ítems ya no repiten "Cli: X" en cada línea, no aporta nada si todo el
// ticket es de un mismo cliente.
function _t80Cliente(cliente) {
    if (!cliente) {
        return `<div class="t80-cliente-cf">CONSUMIDOR FINAL</div>`;
    }
    return `<div class="t80-cliente">
        <div class="t80-cliente-nombre">Cliente: ${_esc(cliente.nombre)}</div>
        ${cliente.documento ? `<div class="t80-cliente-dato">${_esc(cliente.documento)}</div>` : ''}
        ${cliente.direccion ? `<div class="t80-cliente-dato">Dirección: ${_esc(cliente.direccion)}</div>` : ''}
        ${cliente.telefono  ? `<div class="t80-cliente-dato">Tel: ${_esc(cliente.telefono)}</div>` : ''}
    </div>`;
}

function _t80Item(item) {
    // El código va en la línea chica, no en el título del ítem — hace
    // falta para identificar el producto exacto ante una devolución,
    // pero mezclado en el nombre principal es lo que hacía la línea
    // larga y confusa de leer.
    const detalle = [
        item.codigo ? `Cód: ${item.codigo}`    : '',
        item.marca  ? item.marca               : '',
        item.color  ? `Color: ${item.color}`   : '',
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

// Factura A/B discrimina IVA (tipo_comprobante: 1=A, 6=B, 11=C) — Factura C
// nunca lo mostró y sigue igual.
function _t80DesgloseIva(cbte) {
    if (!cbte || (cbte.tipo_comprobante !== 1 && cbte.tipo_comprobante !== 6)) return '';
    return `
        <div class="t80-total-row"><span>Neto gravado</span><span>$${_fmtNum(cbte.importe_neto)}</span></div>
        <div class="t80-total-row"><span>IVA</span><span>$${_fmtNum(cbte.importe_iva)}</span></div>
    `;
}

function _t80Comprobante(cbte) {
    if (!cbte) return '';
    return `<div class="t80-comprobante">
        <div class="t80-comprobante-label">Comprobante autorizado por ARCA</div>
        ${cbte.qrDataUrl ? `<img src="${cbte.qrDataUrl}" alt="QR AFIP" style="width:32mm; height:32mm; margin:2pt auto; display:block;">` : ''}
        <div class="t80-peq">CAE: <strong>${_esc(cbte.cae)}</strong></div>
        <div class="t80-peq">Vto. CAE: <strong>${_esc(cbte.cae_vencimiento)}</strong></div>
    </div>`;
}

function _t80PagoDetalle(p) {
    const partes = [];
    if (p.etiqueta_plan && Number(p.cantidad_pagos) > 1) partes.push(p.etiqueta_plan);
    if (p.recargo_monto && parseFloat(p.recargo_monto) > 0) partes.push(`+${p.recargo_pct}%`);
    return partes.length ? ` (${partes.join(', ')})` : '';
}

function _t80Pagos(pagos, venta) {
    if (pagos && pagos.length) {
        return pagos.map(p => {
            const tarjeta = p.tarjeta_nombre ? ` · ${_esc(p.tarjeta_nombre)}` : '';
            return `
        <div class="t80-pago-row">
            <span>${_esc(p.medio_display)}${tarjeta}${_t80PagoDetalle(p)}</span>
            <span>$${_fmtNum(p.monto)}</span>
        </div>`;
        }).join('');
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
