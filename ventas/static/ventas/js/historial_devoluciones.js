/**
 * historial_devoluciones.js — listado centralizado de devoluciones de
 * venta (de cualquier venta). Cada fila lleva al detalle de la venta
 * original con un click. No hay acciones acá (una devolución no se
 * edita ni se anula, ver ventas.models.registrar_devolucion).
 */
'use strict';

function _esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let currentPage    = 1;
let currentFilters = {};
let lastData       = null;

const listaContainer = document.getElementById('listaContainer');
const paginacion     = document.getElementById('paginacion');
const btnAnterior    = document.getElementById('btnAnterior');
const btnSiguiente   = document.getElementById('btnSiguiente');
const pagInfo        = document.getElementById('pagInfo');
const resumenBar     = document.getElementById('resumenBar');
const resumenTotal   = document.getElementById('resumenTotal');
const resumenPag     = document.getElementById('resumenPag');
const filtroQ        = document.getElementById('filtroQ');
const filtroDesde    = document.getElementById('filtroDesde');
const filtroHasta    = document.getElementById('filtroHasta');
const btnFiltrar     = document.getElementById('btnFiltrar');
const btnLimpiar     = document.getElementById('btnLimpiar');

function urlDetalleVenta(pk) {
    return HISTORIAL_DEV_URLS.detalleVenta.replace('/0/', `/${pk}/`);
}

function buildDevolucionHTML(d) {
    const itemsHtml = (d.items || []).map(it => `
        <div class="dev-item-line">
            · ${it.cantidad} × ${_esc(it.producto_nombre)}${it.combinacion_desc ? ' — ' + _esc(it.combinacion_desc) : ''}${it.es_perdida ? '<span class="perdida-tag">(pérdida)</span>' : ''}
        </div>
    `).join('');

    const montoHtml = parseFloat(d.monto) > 0
        ? `<span class="dev-monto">$${parseFloat(d.monto).toLocaleString('es-AR', { minimumFractionDigits: 2 })}</span>`
        : `<span style="color:var(--text-muted);font-size:.8rem">Sin reembolso</span>`;

    return `
    <div class="dev-row">
        <div class="dev-row-top">
            <div>
                <span class="dev-numero">${_esc(d.numero)}</span>
                <span class="dev-fecha">${_esc(d.fecha)}</span>
            </div>
            ${montoHtml}
        </div>
        <div class="dev-descripcion">${_esc(d.descripcion)}</div>
        <div class="dev-items">${itemsHtml}</div>
        <div class="dev-footer">
            <span>Venta: <a class="link-externo" href="${urlDetalleVenta(d.venta_pk)}" target="_blank" rel="noopener">${_esc(d.venta_numero)}</a></span>
            <span>${d.cuenta ? `Cuenta: ${_esc(d.cuenta)} (${_esc(d.moneda)})` : ''}${d.creado_por ? ` · ${_esc(d.creado_por)}` : ''}</span>
        </div>
    </div>`;
}

function renderLista(data) {
    lastData = data;

    if (!data.results.length) {
        listaContainer.innerHTML = `<div class="empty-state"><p>No se encontraron devoluciones.</p></div>`;
        paginacion.style.display = 'none';
        resumenBar.style.display = 'none';
        return;
    }

    listaContainer.innerHTML = `<div class="ventas-lista">${data.results.map(buildDevolucionHTML).join('')}</div>`;

    resumenBar.style.display = 'flex';
    resumenTotal.textContent = data.total;
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    resumenPag.textContent = `${data.page} / ${totalPages}`;

    paginacion.style.display = 'flex';
    pagInfo.textContent = `Página ${data.page} de ${totalPages}`;
    btnAnterior.disabled = !data.has_prev;
    btnSiguiente.disabled = !data.has_next;
}

function fetchDevoluciones(page) {
    currentPage = page || 1;

    listaContainer.innerHTML = `<div class="loading-state"><span class="spinner"></span> Cargando…</div>`;
    paginacion.style.display = 'none';
    resumenBar.style.display = 'none';

    const params = new URLSearchParams({ page: currentPage });
    if (currentFilters.q)           params.set('q', currentFilters.q);
    if (currentFilters.fecha_desde) params.set('fecha_desde', currentFilters.fecha_desde);
    if (currentFilters.fecha_hasta) params.set('fecha_hasta', currentFilters.fecha_hasta);

    fetch(`${HISTORIAL_DEV_URLS.listar}?${params.toString()}`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => renderLista(data))
        .catch(() => {
            listaContainer.innerHTML = `<div class="empty-state"><p>Error al cargar las devoluciones. Intentá de nuevo.</p></div>`;
        });
}

function aplicarFiltros() {
    currentFilters = {
        q:           filtroQ     ? filtroQ.value.trim() : '',
        fecha_desde: filtroDesde ? filtroDesde.value    : '',
        fecha_hasta: filtroHasta ? filtroHasta.value    : '',
    };
    fetchDevoluciones(1);
}

btnFiltrar.addEventListener('click', aplicarFiltros);
filtroQ.addEventListener('keydown', e => { if (e.key === 'Enter') aplicarFiltros(); });
btnLimpiar.addEventListener('click', () => {
    if (filtroQ)     filtroQ.value = '';
    if (filtroDesde) filtroDesde.value = '';
    if (filtroHasta) filtroHasta.value = '';
    currentFilters = {};
    fetchDevoluciones(1);
});

btnAnterior.addEventListener('click',  () => { if (currentPage > 1) fetchDevoluciones(currentPage - 1); });
btnSiguiente.addEventListener('click', () => { if (lastData && lastData.has_next) fetchDevoluciones(currentPage + 1); });

fetchDevoluciones(1);
