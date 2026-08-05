/**
 * cliente_historial_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Imprime el historial de ventas y pagos de cuota de un cliente en
 * una única tabla cronológica (fecha, descripción, medio de pago,
 * monto, saldo) — mismo patrón visual que cliente_deuda_total_
 * imprimir.js / cuentas_cobrar_imprimir.js.
 *
 * Expone: clienteHistorialImprimir(cliente, historial, ventanaPrevia)
 *   - historial: array como el que arma
 *     core.services_estadisticas.cliente_perfil.historial_cliente()
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _chiEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _chiFmtMoneda(v) {
    return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function _chiFecha(iso) {
    if (!iso) return '-';
    const [anio, mes, dia] = iso.slice(0, 10).split('-');
    return `${dia}/${mes}/${anio}`;
}

/**
 * @param {object} cliente - {pk, nombre}
 * @param {object[]} historial - filas {fecha, tipo, descripcion, monto, saldo, medio_pago}
 * @param {Window} [ventanaPrevia]
 */
function clienteHistorialImprimir(cliente, historial, ventanaPrevia) {
    if (!historial || !historial.length) {
        if (ventanaPrevia) ventanaPrevia.close();
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('Este cliente todavía no tiene historial para imprimir.', 'warning');
        }
        return;
    }

    const filas = historial.map(f => `
        <tr>
            <td>${_chiFecha(f.fecha)}</td>
            <td>${_chiEsc(f.descripcion)}</td>
            <td>${_chiEsc(f.medio_pago || '-')}</td>
            <td class="chi-monto">${_chiFmtMoneda(f.monto)}</td>
            <td class="chi-monto">${f.saldo != null ? _chiFmtMoneda(f.saldo) : '—'}</td>
        </tr>`).join('');

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Historial — ${_chiEsc(cliente.nombre)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 800px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .chi-subtitulo { color: #555; font-size: .875rem; margin: 0 0 20px; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .chi-monto { text-align: right; white-space: nowrap; }
    .chi-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } thead { display: table-header-group; } }
</style>
</head>
<body>
    <h1>Historial de ventas y pagos — ${_chiEsc(cliente.nombre)}</h1>
    <p class="chi-subtitulo">Generado al ${new Date().toLocaleDateString('es-AR')} — ${historial.length} movimiento${historial.length === 1 ? '' : 's'}, ordenado de más reciente a más antiguo</p>
    <table>
        <thead>
            <tr><th>Fecha</th><th>Descripción</th><th>Medio de pago</th><th class="chi-monto">Monto</th><th class="chi-monto">Saldo</th></tr>
        </thead>
        <tbody>${filas}</tbody>
    </table>
    <p class="chi-footer">Generado desde Kairos.</p>
    <script>window.onload = function () { setTimeout(function () { window.print(); }, 150); };</script>
</body>
</html>`;

    const ventana = ventanaPrevia || window.open('', '_blank', 'width=800,height=950');
    if (!ventana) {
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio e intentá de nuevo.', 'warning', 6000);
        }
        return;
    }
    ventana.document.write(html);
    ventana.document.close();
}
