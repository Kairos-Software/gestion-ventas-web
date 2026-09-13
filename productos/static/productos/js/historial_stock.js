/**
 * historial_stock.js
 * Página de historial unificado de movimientos de stock de un producto
 * (compras, facturas iniciales, ajustes, mermas, fraccionamientos,
 * ventas y devoluciones) — ver productos/services_historial.py.
 *
 * Requiere que el template defina PRODUCTO_PK y URLS.historial.
 */
'use strict';

let currentPage    = 1;
let currentFilters = {};
let lastData       = null;

const listaContainer          = document.getElementById('listaContainer');
const reconciliacionContainer = document.getElementById('reconciliacionContainer');
const paginacion               = document.getElementById('paginacion');
const btnAnterior               = document.getElementById('btnAnterior');
const btnSiguiente              = document.getElementById('btnSiguiente');
const pagInfo                   = document.getElementById('pagInfo');
const resumenBar                = document.getElementById('resumenBar');
const resumenTotal              = document.getElementById('resumenTotal');
const resumenPag                = document.getElementById('resumenPag');

const filtroQ             = document.getElementById('filtroQ');
const filtroCategoria     = document.getElementById('filtroCategoria');
const filtroEntradaSalida = document.getElementById('filtroEntradaSalida');
const filtroCombinacion   = document.getElementById('filtroCombinacion');  // null si el producto no tiene variantes
const filtroDesde         = document.getElementById('filtroDesde');
const filtroHasta         = document.getElementById('filtroHasta');
const btnFiltrar          = document.getElementById('btnFiltrar');
const btnLimpiar          = document.getElementById('btnLimpiar');

function fetchHistorial(page) {
    currentPage = page || 1;

    listaContainer.innerHTML =
        '<div class="loading-state"><span class="spinner"></span> Cargando movimientos…</div>';
    paginacion.style.display = 'none';
    resumenBar.style.display = 'none';

    const params = new URLSearchParams({ producto_pk: PRODUCTO_PK, page: currentPage });
    if (currentFilters.q)           params.set('q',              currentFilters.q);
    if (currentFilters.categoria)   params.set('categoria',      currentFilters.categoria);
    if (currentFilters.es_entrada)  params.set('es_entrada',     currentFilters.es_entrada);
    if (currentFilters.combinacion) params.set('combinacion_pk', currentFilters.combinacion);
    if (currentFilters.fecha_desde) params.set('fecha_desde',    currentFilters.fecha_desde);
    if (currentFilters.fecha_hasta) params.set('fecha_hasta',    currentFilters.fecha_hasta);

    fetch(`${URLS.historial}?${params.toString()}`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => {
            lastData = data;
            renderReconciliacion(data);
            renderLista(data);
        })
        .catch(() => {
            listaContainer.innerHTML =
                '<div class="empty-state"><p>Error al cargar el historial. Intentá de nuevo.</p></div>';
        });
}

function renderReconciliacion(data) {
    const diferencia = parseFloat(data.diferencia);
    const cuadra      = Math.abs(diferencia) < 0.001;

    let html = `
        <div class="mov-reconciliacion ${cuadra ? 'ok' : 'danger'}">
            <span>Stock actual: <strong>${data.stock_actual}</strong></span>
            <span>Según el historial: <strong>${data.stock_reconstruido}</strong></span>
            ${cuadra
                ? '<span class="mov-reconciliacion-tag">✓ cuadra exacto</span>'
                : `<span class="mov-reconciliacion-tag">⚠ diferencia de ${Math.abs(diferencia)}</span>`}
        </div>`;

    if (!cuadra) {
        html += `
        <div class="mov-reconciliacion-nota">
            Hay stock que no salió de ninguna compra, ajuste ni venta registrada en este historial
            — probablemente se cargó directo en la base (importación de datos, edición manual).
        </div>`;
    }

    reconciliacionContainer.innerHTML = html;
}

function renderLista(data) {
    resumenBar.style.display = 'flex';
    resumenTotal.textContent = data.total;
    resumenPag.textContent   = `${data.pagina} / ${data.paginas}`;

    if (!data.movimientos.length) {
        listaContainer.innerHTML =
            '<div class="empty-state"><p>No hay movimientos que coincidan con estos filtros.</p></div>';
        paginacion.style.display = 'none';
        return;
    }

    let html = '<div class="mov-list">';
    data.movimientos.forEach(m => {
        const signo      = m.es_entrada ? '+' : '−';
        const tituloHtml = m.origen_url
            ? `<a href="${m.origen_url}" target="_blank" rel="noopener">${m.origen_label}</a>`
            : m.origen_label;
        html += `
            <div class="mov-item">
                <div class="mov-dot ${m.es_entrada ? 'entrada' : 'salida'}">${signo}</div>
                <div class="mov-body">
                    <div class="mov-tipo">
                        ${tituloHtml}
                        ${m.activo ? '' : '<span class="mov-anulado">anulada</span>'}
                    </div>
                    <div class="mov-prod">
                        ${m.combinacion ? m.combinacion + ' · ' : ''}${m.detalle}
                    </div>
                </div>
                <div class="mov-right">
                    <div class="mov-qty ${m.es_entrada ? 'entrada' : 'salida'}">${signo}${m.cantidad}</div>
                    <div class="mov-meta">${m.usuario} · ${m.fecha}</div>
                </div>
            </div>`;
    });
    html += '</div>';
    listaContainer.innerHTML = html;

    paginacion.style.display = data.paginas > 1 ? 'flex' : 'none';
    pagInfo.textContent      = `Página ${data.pagina} de ${data.paginas}`;
    btnAnterior.disabled     = !data.tiene_anterior;
    btnSiguiente.disabled    = !data.tiene_siguiente;
}

/* ════════════════════════════════════════════════════════════════
   FILTROS
════════════════════════════════════════════════════════════════ */
function aplicarFiltros() {
    currentFilters = {
        q:           filtroQ.value.trim(),
        categoria:   filtroCategoria.value,
        es_entrada:  filtroEntradaSalida.value,
        combinacion: filtroCombinacion ? filtroCombinacion.value : '',
        fecha_desde: filtroDesde.value,
        fecha_hasta: filtroHasta.value,
    };
    fetchHistorial(1);
}

btnFiltrar.addEventListener('click', aplicarFiltros);
filtroQ.addEventListener('keydown', e => { if (e.key === 'Enter') aplicarFiltros(); });
[filtroCategoria, filtroEntradaSalida, filtroCombinacion, filtroDesde, filtroHasta]
    .filter(Boolean)
    .forEach(el => el.addEventListener('change', aplicarFiltros));

btnLimpiar.addEventListener('click', () => {
    filtroQ.value = '';
    filtroCategoria.value = '';
    filtroEntradaSalida.value = '';
    if (filtroCombinacion) filtroCombinacion.value = '';
    filtroDesde.value = '';
    filtroHasta.value = '';
    currentFilters = {};
    fetchHistorial(1);
});

btnAnterior.addEventListener('click',  () => { if (currentPage > 1) fetchHistorial(currentPage - 1); });
btnSiguiente.addEventListener('click', () => { if (lastData && lastData.tiene_siguiente) fetchHistorial(currentPage + 1); });

fetchHistorial(1);
