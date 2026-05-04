// historial_compras.js — Kai-Cart
(function () {
    'use strict';

    // ── Estado ─────────────────────────────────────────────────────────
    let currentPage    = 1;
    let currentFilters = {};
    let lastData       = null;

    // ── DOM ────────────────────────────────────────────────────────────
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

    // ── Helpers ────────────────────────────────────────────────────────

    function formatMoney(val) {
        const n = parseFloat(val);
        if (isNaN(n)) return val;
        return '$ ' + n.toLocaleString('es-AR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function iconExterna() {
        return `<svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <path d="M5 2H2C1.45 2 1 2.45 1 3V10C1 10.55 1.45 11 2 11H9C9.55 11 10 10.55 10 10V7"
                  stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <path d="M7 1H11V5" stroke="currentColor" stroke-width="1.4"
                  stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M11 1L5.5 6.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        </svg>`;
    }

    function buildItemsHTML(items) {
        if (!items || items.length === 0) {
            return '<p style="color:var(--text-muted);font-size:0.85rem;margin:0.5rem 0 0;">Sin ítems registrados.</p>';
        }

        const filas = items.map(item => {
            // Pasamos ?q= para que el listado abra ya filtrado por este producto/proveedor
            const urlProducto  = `${HISTORIAL_URLS.productos}?q=${encodeURIComponent(item.producto_nombre)}`;
            const productoLink = `
                <a href="${urlProducto}" target="_blank" rel="noopener" class="link-externo"
                   title="Buscar "${item.producto_nombre}" en catálogo">
                    ${item.producto_nombre} ${iconExterna()}
                </a>
                <span style="font-size:0.72rem;color:var(--text-muted);display:block;margin-top:1px;">
                    ${item.producto_cod}
                </span>`;

            const urlProveedor  = item.proveedor_pk
                ? `${HISTORIAL_URLS.proveedores}?q=${encodeURIComponent(item.proveedor)}`
                : null;
            const proveedorLink = urlProveedor
                ? `<a href="${urlProveedor}" target="_blank" rel="noopener"
                      class="link-externo" title="Buscar "${item.proveedor}" en proveedores">
                       ${item.proveedor} ${iconExterna()}
                   </a>`
                : `<span style="color:var(--text-muted);">—</span>`;

            const descuento = parseFloat(item.descuento_pct) > 0
                ? `<span class="descuento-tag">&nbsp;-${item.descuento_pct}%</span>` : '';

            return `
            <tr>
                <td>${productoLink}</td>
                <td>${proveedorLink}</td>
                <td style="text-align:right;">
                    ${parseFloat(item.cantidad).toLocaleString('es-AR')}
                </td>
                <td style="text-align:right;">
                    ${formatMoney(item.costo_unitario)}
                    <span class="moneda-badge">${item.moneda}</span>
                    ${descuento}
                </td>
                <td style="text-align:right;font-weight:600;">
                    ${formatMoney(item.subtotal)}
                </td>
                <td style="color:var(--text-muted);">${item.condicion_pago}</td>
                <td style="color:var(--text-muted);font-size:0.8rem;">
                    ${item.referencia || '—'}
                </td>
            </tr>`;
        }).join('');

        return `
        <table class="items-table">
            <thead>
                <tr>
                    <th>Producto</th>
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

    function buildCompraHTML(c) {
        const cabecera = `
        <div class="compra-cabecera">
            <span class="compra-numero">${c.numero}</span>
            <span class="compra-fecha">${c.fecha}</span>
            <span class="compra-notas">${c.notas || ''}</span>
            <span class="compra-total">${formatMoney(c.total)}</span>
            <span class="badge-estado ${c.estado}">${c.estado_label}</span>
            <svg class="compra-toggle" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>`;

        const detalle = `
        <div class="compra-detalle">
            <p class="detalle-titulo">
                ${c.items_count} ítem${c.items_count !== 1 ? 's' : ''}
            </p>
            ${buildItemsHTML(c.items)}
            <div class="detalle-footer">
                <span class="compra-notas-detalle">
                    ${c.notas ? '📝 ' + c.notas : ''}
                </span>
                <div class="detalle-footer-right">
                    <span style="color:var(--text-muted);font-size:0.82rem;">
                        Registrado por <strong>${c.creado_por}</strong>
                    </span>
                    <span style="color:var(--text-muted);">·</span>
                    <span style="font-size:0.875rem;color:var(--text-muted);">Total:</span>
                    <strong>${formatMoney(c.total)}</strong>
                </div>
            </div>
        </div>`;

        return `<div class="compra-row">${cabecera}${detalle}</div>`;
    }

    function renderLista(data) {
        lastData = data;

        if (!data.results || data.results.length === 0) {
            listaContainer.innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                    <path d="M3 3H5L6.68 12.39C6.77 12.83 7.16 13.14 7.61 13.14H15.5
                             C15.95 13.14 16.33 12.83 16.42 12.39L18 5H5"
                          stroke="currentColor" stroke-width="1.3"
                          stroke-linecap="round" stroke-linejoin="round"/>
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

        // Acordeón: toggle al hacer click en la cabecera
        listaContainer.querySelectorAll('.compra-cabecera').forEach(cab => {
            cab.addEventListener('click', () => {
                cab.closest('.compra-row').classList.toggle('open');
            });
        });

        // Paginación
        const totalPages = Math.ceil(data.total / data.page_size) || 1;
        pagInfo.textContent       = `Página ${data.page} de ${totalPages}`;
        btnAnterior.disabled      = !data.has_prev;
        btnSiguiente.disabled     = !data.has_next;
        paginacion.style.display  = data.total > data.page_size ? 'flex' : 'none';

        // Resumen
        resumenTotal.textContent = data.total;
        resumenPag.textContent   = `${data.page} / ${totalPages}`;
        resumenBar.style.display = 'flex';
    }

    // ── Fetch ──────────────────────────────────────────────────────────

    function fetchCompras(page) {
        currentPage = page || 1;

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
            .then(r => {
                if (!r.ok) throw new Error('Error de red');
                return r.json();
            })
            .then(data => renderLista(data))
            .catch(() => {
                listaContainer.innerHTML = `
                <div class="empty-state">
                    <p>Error al cargar las compras. Intentá de nuevo.</p>
                </div>`;
            });
    }

    // ── Eventos filtros ────────────────────────────────────────────────

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

    filtroQ.addEventListener('keydown', e => {
        if (e.key === 'Enter') aplicarFiltros();
    });

    btnLimpiar.addEventListener('click', () => {
        filtroQ.value      = '';
        filtroEstado.value = '';
        filtroDesde.value  = '';
        filtroHasta.value  = '';
        currentFilters     = {};
        fetchCompras(1);
    });

    btnAnterior.addEventListener('click',  () => { if (currentPage > 1)            fetchCompras(currentPage - 1); });
    btnSiguiente.addEventListener('click', () => { if (lastData && lastData.has_next) fetchCompras(currentPage + 1); });

    // ── Carga inicial ──────────────────────────────────────────────────
    fetchCompras(1);

})();