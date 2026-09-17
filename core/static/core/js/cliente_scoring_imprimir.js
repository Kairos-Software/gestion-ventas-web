/**
 * cliente_scoring_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Imprime el historial de scoring de un cliente: un resumen (mejor/
 * peor momento, cuántas veces subió/bajó) y una tabla cronológica
 * (fecha, score, banda, cambio, motivo principal) — mismo patrón
 * visual que cliente_deuda_total_imprimir.js / cliente_historial_
 * imprimir.js.
 *
 * Expone: clienteScoringImprimir(cliente, puntos, ventanaPrevia)
 *   - puntos: array como el que arma
 *     core.services_estadisticas.cliente_perfil.historial_scoring()
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _csiEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _csiFecha(iso) {
    if (!iso) return '-';
    const [anio, mes, dia] = iso.slice(0, 10).split('-');
    return `${dia}/${mes}/${anio}`;
}

function _csiEmpresaHtml(emp) {
    const nombre = emp.nombre || emp.razon_social || '';
    const razon = emp.razon_social && emp.razon_social !== nombre ? emp.razon_social : '';
    const contacto = [emp.domicilio, emp.telefono ? `Tel: ${emp.telefono}` : '', emp.email]
        .filter(Boolean).map(_csiEsc).join(' · ');
    const fiscal = [emp.cuit ? `CUIT: ${emp.cuit}` : '', emp.condicion_iva]
        .filter(Boolean).map(_csiEsc).join(' · ');
    if (!emp.logo_url && !nombre && !contacto && !fiscal && !emp.eslogan) return '';
    return `<header class="csi-membrete">
        <div class="csi-marca">
            ${emp.logo_url ? `<img class="csi-logo" src="${_csiEsc(emp.logo_url)}" alt="Logo">` : ''}
            <div>
                ${nombre ? `<div class="csi-empresa-nombre">${_csiEsc(nombre)}</div>` : ''}
                ${emp.eslogan ? `<div class="csi-eslogan">${_csiEsc(emp.eslogan)}</div>` : ''}
            </div>
        </div>
        <div class="csi-empresa-datos">
            ${razon ? `<div>${_csiEsc(razon)}</div>` : ''}
            ${contacto ? `<div>${contacto}</div>` : ''}
            ${fiscal ? `<div>${fiscal}</div>` : ''}
        </div>
    </header>`;
}

function _csiClienteHtml(cliente) {
    const datos = [
        cliente.dni ? `DNI: ${cliente.dni}` : '',
        cliente.cuil ? `CUIL: ${cliente.cuil}` : '',
        cliente.cuit ? `CUIT: ${cliente.cuit}` : '',
        (!cliente.dni && !cliente.cuil && !cliente.cuit && cliente.documento) ? `Documento: ${cliente.documento}` : '',
        cliente.condicion_iva ? `IVA: ${cliente.condicion_iva}` : '',
        cliente.direccion ? `Domicilio: ${cliente.direccion}` : '',
        cliente.email ? `Email: ${cliente.email}` : '',
    ].filter(Boolean).map(_csiEsc).join(' · ');
    return `<section class="csi-cliente">
        <span>Cliente</span><strong>${_csiEsc(cliente.nombre)}</strong>
        ${datos ? `<div>${datos}</div>` : ''}
    </section>`;
}

const _CSI_BANDA_COLOR = {
    excelente: '#15803d',
    bueno:     '#4d7c0f',
    regular:   '#b45309',
    riesgo:    '#c2410c',
    critico:   '#b91c1c',
};

// Mismo criterio que scoMotivoPrincipal() en estadisticas_cliente_scoring.js
// (duplicado a propósito: cada _imprimir.js de esta familia es autónomo,
// no depende de que otro script se haya cargado antes).
function _csiMotivoPrincipal(desglose) {
    const filas = (desglose || []).filter(d =>
        d.concepto !== 'Base' && !d.concepto.startsWith('Ajuste de rango') && d.puntos !== 0);
    if (!filas.length) return null;
    return filas.reduce((peor, d) => Math.abs(d.puntos) > Math.abs(peor.puntos) ? d : peor);
}

/**
 * @param {object} cliente - {pk, nombre}
 * @param {object[]} puntos - historial_scoring(cliente), orden ascendente por fecha
 * @param {Window} [ventanaPrevia]
 */
function clienteScoringImprimir(cliente, puntos, ventanaPrevia) {
    const emp = (typeof window !== 'undefined' && window.KAI_EMPRESA) || {};
    if (!puntos || !puntos.length) {
        if (ventanaPrevia) ventanaPrevia.close();
        if (typeof KaiToast !== 'undefined') {
            KaiToast.show('Este cliente todavía no tiene historial de scoring para imprimir.', 'warning');
        }
        return;
    }

    const mejor = puntos.reduce((a, b) => b.score >= a.score ? b : a);
    const peor = puntos.reduce((a, b) => b.score <= a.score ? b : a);
    let subidas = 0, bajadas = 0;
    for (let i = 1; i < puntos.length; i++) {
        const d = puntos[i].score - puntos[i - 1].score;
        if (d > 0) subidas++; else if (d < 0) bajadas++;
    }

    const filas = puntos.map((p, i) => {
        const previo = i > 0 ? puntos[i - 1] : null;
        const delta = previo ? p.score - previo.score : null;
        const motivo = _csiMotivoPrincipal(p.desglose);
        const deltaTexto = delta === null ? '—' : (delta > 0 ? `+${delta}` : `${delta}`);
        const deltaClase = delta > 0 ? 'csi-pos' : (delta < 0 ? 'csi-neg' : '');
        const etiqueta = p.es_actual ? ' <em>(vigente hoy, sin guardar aún)</em>'
            : (p.es_backfill ? ' <em>(estimado)</em>' : '');
        return `
        <tr>
            <td>${_csiFecha(p.fecha)}${etiqueta}</td>
            <td class="csi-num">${p.score}</td>
            <td><span class="csi-banda" style="color:${_CSI_BANDA_COLOR[p.banda] || '#333'}">${_csiEsc(p.banda_label)}</span></td>
            <td class="csi-num ${deltaClase}">${deltaTexto}</td>
            <td>${motivo ? `${_csiEsc(motivo.concepto)} (${motivo.puntos > 0 ? '+' : ''}${motivo.puntos})` : '—'}</td>
        </tr>`;
    }).join('');

    const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Historial de scoring — ${_csiEsc(cliente.nombre)}</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; padding: 32px; max-width: 800px; margin: 0 auto; }
    h1 { font-size: 1.25rem; margin: 0 0 4px; }
    .csi-membrete { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid #1E6FA8; page-break-inside: avoid; }
    .csi-marca { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .csi-logo { display: block; max-width: 170px; max-height: 58px; object-fit: contain; }
    .csi-empresa-nombre { font-size: 1.05rem; font-weight: 700; }
    .csi-eslogan { margin-top: 2px; color: #40536A; font-size: .75rem; font-style: italic; }
    .csi-empresa-datos { max-width: 55%; color: #26364A; font-size: .75rem; line-height: 1.45; text-align: right; }
    .csi-cliente { margin: 0 0 14px; padding: 9px 12px; border: 1px solid #B7CEDC; background: #F7FAFC; font-size: .8125rem; line-height: 1.45; }
    .csi-cliente > span { margin-right: 8px; color: #1E6FA8; font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
    .csi-cliente div { margin-top: 3px; color: #40536A; font-size: .75rem; }
    .csi-subtitulo { color: #555; font-size: .875rem; margin: 0 0 14px; }
    .csi-resumen { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0 0 20px; padding: 10px 14px; background: #f7f7f7; border-radius: 6px; font-size: .8125rem; }
    table { width: 100%; border-collapse: collapse; font-size: .8125rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f7f7f7; }
    .csi-num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
    .csi-pos { color: #15803d; font-weight: 700; }
    .csi-neg { color: #b91c1c; font-weight: 700; }
    .csi-banda { font-weight: 700; }
    .csi-footer { margin-top: 24px; font-size: .75rem; color: #888; }
    @media print { body { padding: 0; } thead { display: table-header-group; } }
</style>
</head>
<body>
    ${_csiEmpresaHtml(emp)}
    <h1>Historial de scoring</h1>
    <p class="csi-subtitulo">Generado al ${new Date().toLocaleDateString('es-AR')} — ${puntos.length} punto${puntos.length === 1 ? '' : 's'} registrado${puntos.length === 1 ? '' : 's'}, de más antiguo a más reciente</p>
    ${_csiClienteHtml(cliente)}
    <div class="csi-resumen">
        <span>Mejor momento: <strong>${mejor.score}</strong> (${_csiEsc(mejor.banda_label)}) el ${_csiFecha(mejor.fecha)}</span>
        <span>Peor momento: <strong>${peor.score}</strong> (${_csiEsc(peor.banda_label)}) el ${_csiFecha(peor.fecha)}</span>
        <span>Subió ${subidas} vez${subidas === 1 ? '' : 'es'}, bajó ${bajadas} vez${bajadas === 1 ? '' : 'es'}</span>
    </div>
    <table>
        <thead><tr><th>Fecha</th><th class="csi-num">Score</th><th>Banda</th><th class="csi-num">Cambio</th><th>Motivo principal</th></tr></thead>
        <tbody>${filas}</tbody>
    </table>
    <p class="csi-footer">Generado desde Kairos. Los puntos marcados "estimado" son una reconstrucción a partir del historial real de cuotas y cheques, no un registro hecho en el momento.</p>
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
