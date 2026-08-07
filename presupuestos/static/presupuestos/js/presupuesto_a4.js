/**
 * presupuesto_a4.js
 * ─────────────────────────────────────────────────────────────────
 * Generador de HTML para Presupuesto en formato A4 — clon de
 * ventas/static/ventas/js/ticket_a4.js sin el bloque ARCA/CAE/QR
 * (un presupuesto no es un comprobante fiscal) y sin forma de pago
 * (todavía no se vendió nada).
 *
 * Exporta: presupuestoHtmlA4(data) → string HTML completo
 * data = la respuesta JSON de Crear/ActualizarPresupuestoAjax o de
 * PresupuestoDatosAjax (ver presupuestos/views.py::_datos_impresion):
 * {
 *   empresa: { nombre, razon_social, domicilio, telefono, email, logo_url },
 *   presupuesto: { numero, fecha, notas, total },
 *   cliente_nombre: string,
 *   items: [ { nombre, cantidad, precio_unitario, descuento_pct, subtotal }, ... ],
 * }
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function presupuestoHtmlA4(data) {
    const emp = data.empresa || {};
    const pre = data.presupuesto || {};
    const items = data.items || [];

    return `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Presupuesto — ${_esc(pre.numero)}</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { width: 210mm; font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; color: #0D1B2A; background: #fff; }
        body { padding: 0 22mm 20mm; }

        .a4-topbar { height: 5pt; background: #F26A1B; margin: 0 -22mm 18pt; }

        .a4-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1.5rem; margin-bottom: 18pt; }
        .a4-logo { max-height: 50px; max-width: 150px; object-fit: contain; margin-bottom: 6pt; display: block; }
        .a4-empresa-nombre { font-size: 14pt; font-weight: 700; margin-bottom: 3pt; letter-spacing: -.01em; }
        .a4-empresa-dato   { font-size: 8.5pt; color: #4A5568; margin: 1pt 0; }

        .a4-titulo-box { text-align: right; flex: 0 0 auto; }
        .a4-ticket-titulo { font-size: 20pt; font-weight: 800; letter-spacing: -.01em; color: #0D1B2A; }
        .a4-ticket-numero { font-size: 11pt; font-weight: 700; font-variant-numeric: tabular-nums; color: #F26A1B; margin-top: 3pt; }
        .a4-ticket-fecha  { font-size: 8.5pt; color: #4A5568; margin-top: 6pt; }

        .a4-info-grid { display: flex; gap: 12pt; margin-bottom: 16pt; }
        .a4-info-box { flex: 1 1 0; background: #F4F6F9; border-radius: 5pt; padding: 9pt 12pt; }
        .a4-info-label { font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #1E6FA8; margin-bottom: 5pt; }
        .a4-info-nombre { font-size: 10pt; font-weight: 700; margin-bottom: 2pt; }
        .a4-info-dato   { font-size: 8.5pt; color: #4A5568; line-height: 1.5; }

        .a4-table { width: 100%; border-collapse: collapse; margin-bottom: 14pt; font-size: 9.5pt; }
        .a4-table thead th { text-align: left; padding: 6pt 8pt; border-bottom: 1.5px solid #0D1B2A; color: #0D1B2A; font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
        .a4-table th:not(:first-child) { text-align: right; }
        .a4-table td { padding: 7pt 8pt; border-bottom: 1px solid #E4EAF0; vertical-align: top; }
        .a4-table td:not(:first-child) { text-align: right; }
        .a4-table tbody tr:nth-child(even) { background: #FAFBFC; }
        .a4-table tbody tr:last-child td   { border-bottom: 1.5px solid #0D1B2A; }
        .a4-prod-nombre { font-weight: 600; }
        .a4-desc-badge  { color: #10B981; font-weight: 600; }

        .a4-totales { display: flex; justify-content: flex-end; margin-bottom: 16pt; }
        .a4-total-final-box {
            width: 230pt; display: flex; justify-content: space-between; align-items: baseline;
            border-top: 1.5px solid #0D1B2A; padding-top: 8pt; font-size: 15pt; font-weight: 800; color: #0D1B2A;
        }
        .a4-total-final-box span:last-child { color: #F26A1B; }

        .a4-notas { font-size: 9pt; color: #4A5568; padding: 8pt 10pt; background: #F4F6F9; border-left: 3px solid #CBD5E0; margin-bottom: 14pt; white-space: pre-line; }

        .a4-aviso {
            font-size: 8.5pt; color: #8A9BB0; text-align: center;
            border-top: 1px solid #E4EAF0; padding-top: 10pt; margin-top: 6pt; line-height: 1.5;
        }

        @media print {
            html, body { width: auto; }
            body { padding: 0 22mm 20mm; }
            .a4-topbar { margin: 0 -22mm 18pt; }
            @page { size: A4; margin: 14mm 0; }
        }
    </style>
</head>
<body>

    <div class="a4-topbar"></div>

    <div class="a4-header">
        <div>
            ${emp.logo_url ? `<img class="a4-logo" src="${_esc(emp.logo_url)}" alt="Logo">` : ''}
            <div class="a4-empresa-nombre">${_esc(emp.nombre)}</div>
            ${emp.razon_social ? `<div class="a4-empresa-dato">${_esc(emp.razon_social)}</div>` : ''}
            ${emp.domicilio    ? `<div class="a4-empresa-dato">${_esc(emp.domicilio)}</div>`    : ''}
            ${emp.telefono     ? `<div class="a4-empresa-dato">Tel: ${_esc(emp.telefono)}</div>` : ''}
            ${emp.email        ? `<div class="a4-empresa-dato">${_esc(emp.email)}</div>`        : ''}
        </div>
        <div class="a4-titulo-box">
            <div class="a4-ticket-titulo">Presupuesto</div>
            <div class="a4-ticket-numero">${_esc(pre.numero)}</div>
            <div class="a4-ticket-fecha">${_esc(pre.fecha)}</div>
        </div>
    </div>

    <div class="a4-info-grid">
        <div class="a4-info-box">
            <div class="a4-info-label">Para</div>
            <div class="a4-info-nombre">${data.cliente_nombre ? _esc(data.cliente_nombre) : 'Sin especificar'}</div>
        </div>
        <div class="a4-info-box">
            <div class="a4-info-label">Datos del presupuesto</div>
            <div class="a4-info-dato">Fecha de emisión: <strong style="color:#0D1B2A">${_esc(pre.fecha)}</strong></div>
            <div class="a4-info-dato">Líneas: <strong style="color:#0D1B2A">${items.length}</strong></div>
        </div>
    </div>

    <table class="a4-table">
        <thead>
            <tr><th>Producto</th><th>Cant.</th><th>Precio unit.</th><th>Desc.</th><th>Subtotal</th></tr>
        </thead>
        <tbody>
            ${items.map(item => `<tr>
                <td><div class="a4-prod-nombre">${_esc(item.nombre)}</div></td>
                <td>${_esc(String(item.cantidad))}</td>
                <td>$ ${_fmtNum(item.precio_unitario)}</td>
                <td>${item.descuento_pct && item.descuento_pct !== '0.00' ? `<span class="a4-desc-badge">-${_esc(String(item.descuento_pct))}%</span>` : '—'}</td>
                <td><strong>$ ${_fmtNum(item.subtotal)}</strong></td>
            </tr>`).join('')}
        </tbody>
    </table>

    <div class="a4-totales">
        <div style="width:230pt;">
            <div class="a4-total-final-box"><span>Total</span><span>$${_fmtNum(pre.total)}</span></div>
        </div>
    </div>

    ${pre.notas ? `<div class="a4-notas">${_esc(pre.notas)}</div>` : ''}

    <div class="a4-aviso">
        Documento sin valor fiscal — no es una factura ni un comprobante de venta.<br>
        Precios sujetos a confirmación de stock al momento de la compra.
    </div>

    <script>
        window.addEventListener('load', function () { setTimeout(function () { window.print(); }, 150); });
        window.addEventListener('afterprint', function () { window.close(); });
    <\/script>
</body>
</html>`;
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
