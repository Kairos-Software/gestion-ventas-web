/**
 * historial_ventas.js — listado, filtros, auditoría y acciones de venta.
 * Los tickets (ver / imprimir) viven en detalle_venta.html — desde aquí
 * se accede a ellos con el botón "Ver detalle" de cada fila.
 */
'use strict';

let currentPage    = 1;
let currentFilters = {};
let lastData       = null;
window._currentPage = currentPage;

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
const filtroMedioPago= document.getElementById('filtroMedioPago');
const filtroDesde    = document.getElementById('filtroDesde');
const filtroHasta    = document.getElementById('filtroHasta');
const btnFiltrar     = document.getElementById('btnFiltrar');
const btnLimpiar     = document.getElementById('btnLimpiar');

/* ════════════════════════════════════════════════════════════════
   MEDIO DE PAGO
════════════════════════════════════════════════════════════════ */
const MEDIO_PAGO_CLASES = {
    efectivo:      'mp--efectivo',
    transferencia: 'mp--transferencia',
    debito:        'mp--debito',
    credito:       'mp--credito',
    qr:            'mp--qr',
};
function buildMedioPagoBadge(medioPago, medioPagoLabel, medioPagoIcon) {
    const cls = MEDIO_PAGO_CLASES[medioPago] || '';
    return `<span class="mp-badge ${cls}">${_esc(medioPagoIcon)} ${_esc(medioPagoLabel)}</span>`;
}

/** Si la venta tiene pagos divididos (c.pagos), muestra un badge por
 *  cada uno con su monto. Si no, cae al badge único de siempre. */
function buildMediosPagoHTML(c) {
    if (c.pagos && c.pagos.length) {
        return c.pagos.map(p => {
            const cls = MEDIO_PAGO_CLASES[p.medio] || '';
            return `<span class="mp-badge ${cls}">${_esc(p.medio_label)}: ${formatMoney(p.monto)}</span>`;
        }).join(' ');
    }
    return buildMedioPagoBadge(c.medio_pago, c.medio_pago_label, c.medio_pago_icon);
}

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
        body:         'Esta venta está confirmada. Al anularla se revertirá el stock de todos sus ítems. Luego podrás editarla y volver a confirmarla.',
        confirmLabel: 'Sí, anular',
        confirmClass: 'modal-btn-warning',
        onConfirm: () => {
            postAccion(
                HISTORIAL_URLS.anular,
                { pk },
                () => { mostrarToastExito(`Venta ${numero} anulada. Stock revertido.`); fetchVentas(currentPage); },
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
        warning:      revierteStock ? 'Esta venta está confirmada. Al eliminarla se revertirá el stock de todos sus ítems.' : null,
        confirmLabel: 'Sí, eliminar',
        confirmClass: 'modal-btn-danger',
        onConfirm: () => {
            postAccion(
                HISTORIAL_URLS.eliminar,
                { pk },
                (data) => {
                    mostrarToastExito(data.stock_revertido ? `Venta ${numero} eliminada. Stock revertido.` : `Venta ${numero} eliminada.`);
                    fetchVentas(currentPage);
                },
                msg => mostrarToastError(msg)
            );
        },
    });
}

/* ════════════════════════════════════════════════════════════════
   BUILD HTML — ítems (solo lectura)
════════════════════════════════════════════════════════════════ */
function buildItemsHTML(items) {
    if (!items || !items.length) return '<p style="color:var(--text-muted);font-size:0.85rem;margin:0.5rem 0 0;">Sin ítems registrados.</p>';

    const filas = items.map(item => {
        const urlProducto  = `${HISTORIAL_URLS.productos}?q=${encodeURIComponent(item.producto_nombre)}`;
        const productoLink = `
            <a href="${urlProducto}" target="_blank" rel="noopener" class="link-externo">
                ${_esc(item.producto_display)} ${iconExterna()}
            </a>
            <span style="font-size:0.72rem;color:var(--text-muted);display:block;margin-top:1px;">${_esc(item.producto_cod)}</span>`;

        let colorCell;
        if (item.tiene_color) {
            const swatch = item.color_hex
                ? `<span class="vta-color-swatch" style="background:${_esc(item.color_hex)};width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle;border:1px solid rgba(0,0,0,.15);"></span>` : '';
            colorCell = `<span class="color-badge">${swatch}${_esc(item.color_nombre)}</span>`;
        } else {
            colorCell = `<span style="color:var(--text-muted);font-size:0.8rem;">—</span>`;
        }

        const urlCliente  = item.cliente_pk ? `${HISTORIAL_URLS.clientes}?q=${encodeURIComponent(item.cliente)}` : null;
        const clienteCell = urlCliente
            ? `<a href="${urlCliente}" target="_blank" rel="noopener" class="link-externo">${_esc(item.cliente)} ${iconExterna()}</a>`
            : `<span style="color:var(--text-muted);">${_esc(item.cliente) || '—'}</span>`;

        const descuento = parseFloat(item.descuento_pct) > 0 ? `<span class="descuento-tag">&nbsp;-${item.descuento_pct}%</span>` : '';

        return `
        <tr>
            <td>${productoLink}</td>
            <td>${colorCell}</td>
            <td>${clienteCell}</td>
            <td style="text-align:right;">${parseFloat(item.cantidad).toLocaleString('es-AR')}</td>
            <td style="text-align:right;">${formatMoney(item.precio_unitario)}<span class="moneda-badge">${_esc(item.moneda)}</span>${descuento}</td>
            <td style="text-align:right;font-weight:600;">${formatMoney(item.subtotal)}</td>
            <td style="color:var(--text-muted);">${_esc(item.condicion_pago)}</td>
            <td style="color:var(--text-muted);font-size:0.8rem;">${_esc(item.referencia) || '—'}</td>
        </tr>`;
    }).join('');

    return `
    <table class="items-table">
        <thead>
            <tr>
                <th>Producto</th><th>Color</th><th>Cliente</th>
                <th style="text-align:right;">Cantidad</th><th style="text-align:right;">Precio unit.</th>
                <th style="text-align:right;">Subtotal</th><th>Cond. pago</th><th>Referencia</th>
            </tr>
        </thead>
        <tbody>${filas}</tbody>
    </table>`;
}

/* ════════════════════════════════════════════════════════════════
   BUILD HTML — auditoría inline en el detalle
════════════════════════════════════════════════════════════════ */
function buildAuditoriaHTML(c) {
    const filas = [];

    if (c.confirmado_por) {
        filas.push(`
        <div class="hist-audit-row">
            <span class="hist-audit-label">Confirmado por</span>
            <span class="hist-audit-val">${_esc(c.confirmado_por)}</span>
            ${c.fecha_confirmacion ? `<span class="hist-audit-fecha">${_esc(c.fecha_confirmacion)}</span>` : ''}
        </div>`);
    }
    if (c.anulado_por) {
        filas.push(`
        <div class="hist-audit-row hist-audit-row--anulada">
            <span class="hist-audit-label">Anulado por</span>
            <span class="hist-audit-val">${_esc(c.anulado_por)}</span>
            ${c.fecha_anulacion ? `<span class="hist-audit-fecha">${_esc(c.fecha_anulacion)}</span>` : ''}
        </div>`);
    }
    if (c.editado_por) {
        filas.push(`
        <div class="hist-audit-row hist-audit-row--editada">
            <span class="hist-audit-label">Editado por</span>
            <span class="hist-audit-val">${_esc(c.editado_por)}</span>
            ${c.fecha_edicion ? `<span class="hist-audit-fecha">${_esc(c.fecha_edicion)}</span>` : ''}
        </div>`);
    }

    if (!filas.length) return '';

    return `
    <div class="hist-auditoria">
        <div class="hist-auditoria-title">Auditoría</div>
        ${filas.join('')}
    </div>`;
}

/* ════════════════════════════════════════════════════════════════
   BUILD HTML — botones de acción (anular / editar / eliminar)
════════════════════════════════════════════════════════════════ */
function buildAccionesHTML(c) {
    const btns = [];

    // Ver detalle siempre disponible: la URL persiste y muestra el estado
    // actual de la venta (confirmada / anulada / editada), a diferencia
    // del flujo viejo donde la URL del borrador se volvía inútil.
    btns.push(`
        <a href="${HISTORIAL_URLS.detalleVenta.replace('/0/', '/' + c.pk + '/')}"
           class="btn-accion btn-accion--ghost" target="_blank" rel="noopener">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="3" stroke="currentColor" stroke-width="1.3"/>
                <path d="M1.5 8C3 4.5 5.5 2.5 8 2.5S13 4.5 14.5 8C13 11.5 10.5 13.5 8 13.5S3 11.5 1.5 8Z" stroke="currentColor" stroke-width="1.3"/>
            </svg>
            Ver detalle
        </a>`);

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

    return btns.length ? `<div class="acciones-venta">${btns.join('')}</div>` : '';
}

/* ════════════════════════════════════════════════════════════════
   BUILD HTML — fila de venta completa
════════════════════════════════════════════════════════════════ */
function buildVentaHTML(c) {
    const esPagoDividido = c.pagos && c.pagos.length > 1;
    const medioBadgeCabecera = esPagoDividido
        ? `<span class="mp-badge mp--dividido">💱 Pago dividido (${c.pagos.length})</span>`
        : buildMedioPagoBadge(c.medio_pago, c.medio_pago_label, c.medio_pago_icon);
    const mediosBadgeDetalle = buildMediosPagoHTML(c);

    // Línea de usuario en la cabecera: "por admin"
    const porUsuario = c.confirmado_por && c.confirmado_por !== '—'
        ? `<span class="venta-por-usuario">por ${_esc(c.confirmado_por)}</span>`
        : '';

    return `
    <div class="venta-row" data-pk="${c.pk}">
        <div class="venta-cabecera">
            <span class="venta-numero">${_esc(c.numero)}</span>
            <span class="venta-fecha">${_esc(c.fecha)}</span>
            <span class="venta-notas">${_esc(c.notas || '')}</span>
            ${porUsuario}
            ${medioBadgeCabecera}
            <span class="venta-total">${formatMoney(c.total)}</span>
            <span class="badge-estado ${c.estado}">${_esc(c.estado_label)}</span>
            <svg class="venta-toggle" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="venta-detalle">
            <p class="detalle-titulo">${c.items_count} ítem${c.items_count !== 1 ? 's' : ''}</p>
            ${buildItemsHTML(c.items)}
            <div class="detalle-footer">
                <span class="venta-notas-detalle">${c.notas ? '📝 ' + _esc(c.notas) : ''}</span>
                <div class="detalle-footer-right">
                    ${mediosBadgeDetalle}
                    ${c.confirmado_por && c.confirmado_por !== '—'
                        ? `<span style="color:var(--text-muted);font-size:0.82rem;">Registrado por <strong>${_esc(c.confirmado_por)}</strong></span><span style="color:var(--text-muted);">·</span>`
                        : ''}
                    <span style="font-size:0.875rem;color:var(--text-muted);">Total:</span>
                    <strong>${formatMoney(c.total)}</strong>
                </div>
            </div>
            ${buildAuditoriaHTML(c)}
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
                <path d="M3 3H5L6.68 12.39C6.77 12.83 7.16 13.14 7.61 13.14H15.5C15.95 13.14 16.33 12.83 16.42 12.39L18 5H5"
                      stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                <circle cx="8.5" cy="18" r="1.5" stroke="currentColor" stroke-width="1.3"/>
                <circle cx="15.5" cy="18" r="1.5" stroke="currentColor" stroke-width="1.3"/>
            </svg>
            <p>No se encontraron ventas con los filtros aplicados.</p>
        </div>`;
        paginacion.style.display = 'none';
        resumenBar.style.display = 'none';
        return;
    }

    listaContainer.innerHTML = `<div class="ventas-lista">${data.results.map(buildVentaHTML).join('')}</div>`;

    // Acordeón
    listaContainer.querySelectorAll('.venta-cabecera').forEach(cab => {
        cab.addEventListener('click', e => {
            if (e.target.closest('.btn-accion') || e.target.closest('.hist-ticket-btn')) return;
            cab.closest('.venta-row').classList.toggle('open');
        });
    });

    // Botones de acción (anular / editar / eliminar)
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
                const ventaData = (lastData.results || []).find(c => c.pk === pk);
                if (ventaData) accionEditar(pk, ventaData, listaContainer);
            }
        });
    });

    // Paginación
    const totalPages         = Math.ceil(data.total / data.page_size) || 1;
    pagInfo.textContent      = `Página ${data.page} de ${totalPages}`;
    btnAnterior.disabled     = !data.has_prev;
    btnSiguiente.disabled    = !data.has_next;
    paginacion.style.display = data.total > data.page_size ? 'flex' : 'none';

    resumenTotal.textContent = data.total;
    resumenPag.textContent   = `${data.page} / ${totalPages}`;
    resumenBar.style.display = 'flex';
}

/* ════════════════════════════════════════════════════════════════
   FETCH
════════════════════════════════════════════════════════════════ */
function fetchVentas(page) {
    currentPage         = page || 1;
    window._currentPage = currentPage;

    listaContainer.innerHTML = `<div class="loading-state"><span class="spinner"></span> Cargando…</div>`;
    paginacion.style.display = 'none';
    resumenBar.style.display = 'none';

    const params = new URLSearchParams({ page: currentPage });
    if (currentFilters.q)           params.set('q',           currentFilters.q);
    if (currentFilters.estado)      params.set('estado',      currentFilters.estado);
    if (currentFilters.medio_pago)  params.set('medio_pago',  currentFilters.medio_pago);
    if (currentFilters.fecha_desde) params.set('fecha_desde', currentFilters.fecha_desde);
    if (currentFilters.fecha_hasta) params.set('fecha_hasta', currentFilters.fecha_hasta);

    fetch(`${HISTORIAL_URLS.listar}?${params.toString()}`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => renderLista(data))
        .catch(() => {
            listaContainer.innerHTML = `<div class="empty-state"><p>Error al cargar las ventas. Intentá de nuevo.</p></div>`;
        });
}

/* ════════════════════════════════════════════════════════════════
   FILTROS
════════════════════════════════════════════════════════════════ */
function aplicarFiltros() {
    currentFilters = {
        q:           filtroQ       ? filtroQ.value.trim()     : '',
        estado:      filtroEstado  ? filtroEstado.value        : '',
        medio_pago:  filtroMedioPago ? filtroMedioPago.value   : '',
        fecha_desde: filtroDesde   ? filtroDesde.value         : '',
        fecha_hasta: filtroHasta   ? filtroHasta.value         : '',
    };
    fetchVentas(1);
}

btnFiltrar.addEventListener('click', aplicarFiltros);
filtroQ.addEventListener('keydown', e => { if (e.key === 'Enter') aplicarFiltros(); });
btnLimpiar.addEventListener('click', () => {
    if (filtroQ)          filtroQ.value          = '';
    if (filtroEstado)     filtroEstado.value      = '';
    if (filtroMedioPago)  filtroMedioPago.value   = '';
    if (filtroDesde)      filtroDesde.value       = '';
    if (filtroHasta)      filtroHasta.value       = '';
    currentFilters = {};
    fetchVentas(1);
});

btnAnterior.addEventListener('click',  () => { if (currentPage > 1)              fetchVentas(currentPage - 1); });
btnSiguiente.addEventListener('click', () => { if (lastData && lastData.has_next) fetchVentas(currentPage + 1); });

fetchVentas(1);