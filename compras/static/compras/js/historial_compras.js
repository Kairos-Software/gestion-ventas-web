/**
 * historial_compras.js
 * Módulo principal del historial de compras.
 * Orquesta fetch, render de lista, acordeón y acciones simples (anular/eliminar).
 *
 * Depende de (cargar en este orden):
 *   1. historial_utils.js
 *   2. historial_docs.js
 *   3. historial_editor.js
 *   4. historial_compras.js  ← este archivo
 */
'use strict';

/* ════════════════════════════════════════════════════════════════
   ESTADO
════════════════════════════════════════════════════════════════ */
let currentPage    = 1;
let currentFilters = {};
let lastData       = null;

window._currentPage = currentPage; // usado por historial_editor.js al cancelar/guardar

/* ════════════════════════════════════════════════════════════════
   DOM
════════════════════════════════════════════════════════════════ */
const listaContainer = document.getElementById('listaContainer');
const paginacion     = document.getElementById('paginacion');
const btnAnterior    = document.getElementById('btnAnterior');
const btnSiguiente   = document.getElementById('btnSiguiente');
const pagInfo        = document.getElementById('pagInfo');
const resumenBar     = document.getElementById('resumenBar');
const resumenTotal   = document.getElementById('resumenTotal');
const resumenPag     = document.getElementById('resumenPag');

const filtroQ        = document.getElementById('filtroQ');
const filtroEstado   = document.getElementById('filtroEstado');
const filtroDesde    = document.getElementById('filtroDesde');
const filtroHasta    = document.getElementById('filtroHasta');
const btnFiltrar     = document.getElementById('btnFiltrar');
const btnLimpiar     = document.getElementById('btnLimpiar');

/* ════════════════════════════════════════════════════════════════
   ACCIONES SIMPLES
════════════════════════════════════════════════════════════════ */
function accionAnular(pk, numero) {
    abrirModal({
        icon: `<svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                   <circle cx="14" cy="14" r="12" stroke="var(--warning)" stroke-width="1.6"/>
                   <path d="M14 8V15" stroke="var(--warning)" stroke-width="1.8" stroke-linecap="round"/>
                   <circle cx="14" cy="19" r="1.2" fill="var(--warning)"/>
               </svg>`,
        title:        `Anular ${numero}`,
        body:         'Esta compra está confirmada. Al anularla se revertirá el stock de todos sus ítems. Luego podrás editarla y volver a confirmarla.',
        confirmLabel: 'Sí, anular',
        confirmClass: 'modal-btn-warning',
        onConfirm: () => {
            postAccion(
                HISTORIAL_URLS.anular,
                { pk },
                () => { mostrarToastExito(`Compra ${numero} anulada. Stock revertido.`); fetchCompras(currentPage); },
                msg => mostrarToastError(msg)
            );
        },
    });
}

function accionEliminar(pk, numero, revierteStock) {
    abrirModal({
        icon: `<svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                   <circle cx="14" cy="14" r="12" stroke="var(--danger)" stroke-width="1.6"/>
                   <path d="M9 9L19 19M19 9L9 19" stroke="var(--danger)" stroke-width="1.8" stroke-linecap="round"/>
               </svg>`,
        title:        `Eliminar ${numero}`,
        body:         '¿Estás seguro? Esta acción no se puede deshacer.',
        warning:      revierteStock
            ? 'Esta compra está confirmada. Al eliminarla se revertirá el stock de todos sus ítems.'
            : null,
        confirmLabel: 'Sí, eliminar',
        confirmClass: 'modal-btn-danger',
        onConfirm: () => {
            postAccion(
                HISTORIAL_URLS.eliminar,
                { pk },
                (data) => {
                    const msg = data.stock_revertido
                        ? `Compra ${numero} eliminada. Stock revertido.`
                        : `Compra ${numero} eliminada.`;
                    mostrarToastExito(msg);
                    fetchCompras(currentPage);
                },
                msg => mostrarToastError(msg)
            );
        },
    });
}

/* ════════════════════════════════════════════════════════════════
   BUILD HTML — vista de solo lectura
════════════════════════════════════════════════════════════════ */
function buildItemsHTML(items) {
    if (!items || !items.length) {
        return '<p style="color:var(--text-muted);font-size:0.85rem;margin:0.5rem 0 0;">Sin ítems registrados.</p>';
    }

    const filas = items.map(item => {
        const urlProducto  = `${HISTORIAL_URLS.productos}?q=${encodeURIComponent(item.producto_nombre)}`;
        const productoLink = `
            <a href="${urlProducto}" target="_blank" rel="noopener" class="link-externo">
                ${_esc(item.producto_display)} ${iconExterna()}
            </a>
            <span style="font-size:0.72rem;color:var(--text-muted);display:block;margin-top:1px;">
                ${_esc(item.producto_cod)}
            </span>`;

        // Combinación de variantes
        let combinacionCell;
        if (item.tiene_combinacion) {
            combinacionCell = `<span class="combinacion-badge">${_esc(item.combinacion_descripcion)}</span>`;
        } else {
            combinacionCell = `<span style="color:var(--text-muted);font-size:0.8rem;">—</span>`;
        }

        const urlProveedor  = item.proveedor_pk
            ? `${HISTORIAL_URLS.proveedores}?q=${encodeURIComponent(item.proveedor)}` : null;
        const proveedorCell = urlProveedor
            ? `<a href="${urlProveedor}" target="_blank" rel="noopener" class="link-externo">
                   ${_esc(item.proveedor)} ${iconExterna()}
               </a>`
            : `<span style="color:var(--text-muted);">${_esc(item.proveedor) || '—'}</span>`;

        const descuento = parseFloat(item.descuento_pct) > 0
            ? `<span class="descuento-tag">&nbsp;-${item.descuento_pct}%</span>` : '';

        return `
        <tr>
            <td>${productoLink}</td>
            <td>${combinacionCell}</td>
            <td>${proveedorCell}</td>
            <td style="text-align:right;">${parseFloat(item.cantidad).toLocaleString('es-AR')}</td>
            <td style="text-align:right;">
                ${formatMoney(item.costo_unitario)}
                <span class="moneda-badge">${_esc(item.moneda)}</span>
                ${descuento}
            </td>
            <td style="text-align:right;font-weight:600;">${formatMoney(item.subtotal)}</td>
            <td style="color:var(--text-muted);">${_esc(item.condicion_pago)}</td>
            <td style="color:var(--text-muted);font-size:0.8rem;">${_esc(item.referencia) || '—'}</td>
        </tr>`;
    }).join('');

    return `
    <table class="items-table">
        <thead>
            <tr>
                <th>Producto</th>
                <th>Combinación</th>
                <th>Proveedor</th>
                <th style="text-align:right;">Cantidad</th>
                <th style="text-align:right;">Costo unit.</th>
                <th style="text-align:right;">Subtotal</th>
                <th>Cond. pago</th>
                <th>Referencia</th>
            </tr>
        </thead>
        <tbody>${filas}</tbody>
    </table>`;
}

function buildAccionesHTML(c) {
    const btns = [];

    if (c.puede_anular) {
        btns.push(`
            <button class="btn-accion btn-accion--warning"
                    data-accion="anular" data-pk="${c.pk}" data-numero="${_esc(c.numero)}">
                ${iconAnular()} Anular
            </button>`);
    }
    if (c.puede_editar) {
        btns.push(`
            <button class="btn-accion btn-accion--blue"
                    data-accion="editar" data-pk="${c.pk}" data-numero="${_esc(c.numero)}">
                ${iconEditar()} Editar
            </button>`);
    }
    if (c.puede_eliminar) {
        btns.push(`
            <button class="btn-accion btn-accion--danger"
                    data-accion="eliminar" data-pk="${c.pk}" data-numero="${_esc(c.numero)}"
                    data-revierte="${c.eliminar_revierte_stock ? '1' : '0'}">
                ${iconEliminar()} Eliminar
            </button>`);
    }

    return btns.length
        ? `<div class="acciones-compra">${btns.join('')}</div>`
        : '';
}

function buildCompraHTML(c) {
    return `
    <div class="compra-row" data-pk="${c.pk}">
        <div class="compra-cabecera">
            <span class="compra-numero">${_esc(c.numero)}</span>
            <span class="compra-fecha">${_esc(c.fecha)}</span>
            <span class="compra-notas">${_esc(c.notas || '')}</span>
            <span class="compra-total">${formatMoney(c.total)}</span>
            <span class="badge-estado ${c.estado}">${_esc(c.estado_label)}</span>
            <svg class="compra-toggle" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="compra-detalle">
            <p class="detalle-titulo">
                ${c.items_count} ítem${c.items_count !== 1 ? 's' : ''}
            </p>
            ${buildItemsHTML(c.items)}
            <div class="detalle-footer">
                <span class="compra-notas-detalle">${c.notas ? '📝 ' + _esc(c.notas) : ''}</span>
                <div class="detalle-footer-right">
                    <span style="color:var(--text-muted);font-size:0.82rem;">
                        Registrado por <strong>${_esc(c.creado_por)}</strong>
                    </span>
                    <span style="color:var(--text-muted);">·</span>
                    <span style="font-size:0.875rem;color:var(--text-muted);">Total:</span>
                    <strong>${formatMoney(c.total)}</strong>
                </div>
            </div>
            ${buildDocumentosReadOnly(c)}
            ${buildAccionesHTML(c)}
        </div>
    </div>`;
}

/* ════════════════════════════════════════════════════════════════
   RENDER
════════════════════════════════════════════════════════════════ */
function renderLista(data) {
    lastData = data;

    if (!data.results || !data.results.length) {
        listaContainer.innerHTML = `
        <div class="empty-state">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                <path d="M3 3H5L6.68 12.39C6.77 12.83 7.16 13.14 7.61 13.14H15.5
                         C15.95 13.14 16.33 12.83 16.42 12.39L18 5H5"
                      stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                <circle cx="8.5" cy="18" r="1.5" stroke="currentColor" stroke-width="1.3"/>
                <circle cx="15.5" cy="18" r="1.5" stroke="currentColor" stroke-width="1.3"/>
            </svg>
            <p>No se encontraron compras con los filtros aplicados.</p>
        </div>`;
        paginacion.style.display = 'none';
        resumenBar.style.display = 'none';
        return;
    }

    listaContainer.innerHTML = `
    <div class="compras-lista">
        ${data.results.map(buildCompraHTML).join('')}
    </div>`;

    // Acordeón
    listaContainer.querySelectorAll('.compra-cabecera').forEach(cab => {
        cab.addEventListener('click', e => {
            // No colapsar si se hizo click en un botón de acción
            if (e.target.closest('.btn-accion')) return;
            cab.closest('.compra-row').classList.toggle('open');
        });
    });

    // Botones de acción
    listaContainer.querySelectorAll('.btn-accion').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            const accion   = btn.dataset.accion;
            const pk       = parseInt(btn.dataset.pk, 10);
            const numero   = btn.dataset.numero;
            const revierte = btn.dataset.revierte === '1';

            if (accion === 'anular')   accionAnular(pk, numero);
            if (accion === 'eliminar') accionEliminar(pk, numero, revierte);
            if (accion === 'editar') {
                const compraData = (lastData.results || []).find(c => c.pk === pk);
                if (compraData) accionEditar(pk, compraData, listaContainer);
            }
        });
    });

    // Paginación
    const totalPages             = Math.ceil(data.total / data.page_size) || 1;
    pagInfo.textContent          = `Página ${data.page} de ${totalPages}`;
    btnAnterior.disabled         = !data.has_prev;
    btnSiguiente.disabled        = !data.has_next;
    paginacion.style.display     = data.total > data.page_size ? 'flex' : 'none';

    // Resumen
    resumenTotal.textContent     = data.total;
    resumenPag.textContent       = `${data.page} / ${totalPages}`;
    resumenBar.style.display     = 'flex';
}

/* ════════════════════════════════════════════════════════════════
   FETCH
════════════════════════════════════════════════════════════════ */
function fetchCompras(page) {
    currentPage             = page || 1;
    window._currentPage     = currentPage;

    listaContainer.innerHTML = `
    <div class="loading-state">
        <span class="spinner"></span> Cargando…
    </div>`;
    paginacion.style.display = 'none';
    resumenBar.style.display = 'none';

    const params = new URLSearchParams({ page: currentPage });
    if (currentFilters.q)           params.set('q',           currentFilters.q);
    if (currentFilters.estado)      params.set('estado',      currentFilters.estado);
    if (currentFilters.fecha_desde) params.set('fecha_desde', currentFilters.fecha_desde);
    if (currentFilters.fecha_hasta) params.set('fecha_hasta', currentFilters.fecha_hasta);

    fetch(`${HISTORIAL_URLS.listar}?${params.toString()}`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => renderLista(data))
        .catch(() => {
            listaContainer.innerHTML = `
            <div class="empty-state"><p>Error al cargar las compras. Intentá de nuevo.</p></div>`;
        });
}

/* ════════════════════════════════════════════════════════════════
   FILTROS
════════════════════════════════════════════════════════════════ */
function aplicarFiltros() {
    currentFilters = {
        q:           filtroQ.value.trim(),
        estado:      filtroEstado.value,
        fecha_desde: filtroDesde.value,
        fecha_hasta: filtroHasta.value,
    };
    fetchCompras(1);
}

btnFiltrar.addEventListener('click', aplicarFiltros);
filtroQ.addEventListener('keydown', e => { if (e.key === 'Enter') aplicarFiltros(); });
btnLimpiar.addEventListener('click', () => {
    filtroQ.value = filtroEstado.value = filtroDesde.value = filtroHasta.value = '';
    currentFilters = {};
    fetchCompras(1);
});

btnAnterior.addEventListener('click',  () => { if (currentPage > 1)              fetchCompras(currentPage - 1); });
btnSiguiente.addEventListener('click', () => { if (lastData && lastData.has_next) fetchCompras(currentPage + 1); });

/* ════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */
fetchCompras(1);