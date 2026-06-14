/**
 * nueva_venta.js
 * Módulo del carrito para crear una nueva venta.
 *
 * Requiere window.VTA_CONFIG con:
 *   urlBuscarProducto  — GET ?q=
 *   urlBuscarCliente   — GET ?q=
 *   urlGuardarBorrador — POST JSON
 *   urlDetalle         — base URL para redirigir (se le concatena el pk)
 *   csrfToken
 */
'use strict';

const CFG = window.VTA_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   ESTADO
════════════════════════════════════════════════════════════════ */
let carrito      = [];   // [{ id, producto_pk, nombre, codigo, unidad,
                         //    cliente_pk, cliente_nombre,
                         //    tiene_colores, colores_lista, colores_dist,
                         //    cantidad, precio_unitario, moneda, descuento,
                         //    condicion, referencia }]
let nextId       = 0;
let cliTimers   = {};
let cliGlobalDD = null;
let cliActiveInput  = null;
let cliActiveItemId = null;

/* ════════════════════════════════════════════════════════════════
   DOM
════════════════════════════════════════════════════════════════ */
const searchInput    = document.getElementById('vtaSearchInput');
const searchDropdown = document.getElementById('vtaSearchDropdown');
const cartBody       = document.getElementById('vtaCartBody');
const cartEmpty      = document.getElementById('vtaCartEmpty');
const cartFooter     = document.getElementById('vtaCartFooter');
const btnContinuar   = document.getElementById('vtaBtnContinuar');
const badge          = document.getElementById('vtaBadge');
const totalItemsEl   = document.getElementById('vtaTotalItems');
const totalMontoEl   = document.getElementById('vtaTotalMonto');

/* ════════════════════════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════════════════════════ */
function _esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _fmt(v, moneda) {
    const sym = { USD: 'U$S ', EUR: '€ ', ARS: '$ ' }[moneda] || '$ ';
    return sym + parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function _fmtPeso(v) {
    return '$ ' + parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function _calcSub(item) {
    const base = (parseFloat(item.cantidad) || 0) * (parseFloat(item.precio_unitario) || 0);
    return item.descuento ? base * (1 - parseFloat(item.descuento) / 100) : base;
}

function _totalColoresDist(item) {
    return Object.values(item.colores_dist).reduce((s, v) => s + (parseFloat(v) || 0), 0);
}

function _coloresValidos(item) {
    if (!item.tiene_colores) return true;
    return Math.abs(_totalColoresDist(item) - (parseFloat(item.cantidad) || 0)) < 0.001;
}

/* ════════════════════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════════════════════ */
function _toast(titulo, cuerpo) {
    const toast = document.getElementById('vtaToast');
    document.getElementById('vtaToastTitle').textContent = titulo;
    document.getElementById('vtaToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

/* ════════════════════════════════════════════════════════════════
   BUSCADOR DE PRODUCTOS — autocomplete
════════════════════════════════════════════════════════════════ */
let searchTimer;

searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    if (q.length < 1) {
        searchDropdown.classList.remove('open');
        searchDropdown.innerHTML = '';
        return;
    }
    searchTimer = setTimeout(async () => {
        try {
            const res     = await fetch(`${CFG.urlBuscarProducto}?q=${encodeURIComponent(q)}`);
            const data    = await res.json();
            const results = data.results || [];

            if (!results.length) {
                searchDropdown.innerHTML = '<div class="vta-dropdown-empty">Sin resultados</div>';
            } else {
                searchDropdown.innerHTML = results.map(p => {
                    const tieneColores = p.tiene_variantes_color && p.colores && p.colores.length > 0;
                    const coloresAttr  = tieneColores
                        ? `data-colores="${_esc(btoa(unescape(encodeURIComponent(JSON.stringify(p.colores)))))}"` : '';

                    // ── Precio: mostrar en el chip si está cargado ─────────
                    const precioLabel = p.precio_venta !== null && p.precio_venta !== undefined
                        ? `<span class="vta-meta-chip vta-meta-chip--precio">
                               Precio: <strong>${_fmtPeso(p.precio_venta)}</strong>
                           </span>`
                        : `<span class="vta-meta-chip vta-meta-chip--sin-precio">Sin precio</span>`;

                    return `
                    <div class="vta-dropdown-item"
                         data-pk="${p.pk}"
                         data-nombre="${_esc(p.nombre)}"
                         data-codigo="${_esc(p.codigo)}"
                         data-unidad="${_esc(p.unidad_medida || '')}"
                         data-cli-pk="${p.cliente_pk || ''}"
                         data-cli-nombre="${_esc(p.cliente || '')}"
                         data-tiene-colores="${tieneColores ? '1' : '0'}"
                         data-precio="${p.precio_venta !== null && p.precio_venta !== undefined ? p.precio_venta : ''}"
                         data-moneda="${p.moneda || 'ARS'}"
                         ${coloresAttr}>
                        <div class="vta-dropdown-item-top">
                            <span class="vta-dropdown-item-nombre">${_esc(p.nombre)}</span>
                            <span class="vta-dropdown-item-codigo">${_esc(p.codigo)}</span>
                        </div>
                        <div class="vta-dropdown-item-meta">
                            <span class="vta-meta-chip">Stock: <strong>${parseFloat(p.stock_actual || 0).toLocaleString('es-AR')}</strong></span>
                            ${precioLabel}
                            ${tieneColores ? `<span class="vta-meta-chip vta-meta-chip--colores">
                                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                    <circle cx="5" cy="5" r="3.5" stroke="currentColor" stroke-width="1.2"/>
                                    <circle cx="5" cy="5" r="1.2" fill="currentColor"/>
                                </svg>
                                <strong>${p.colores.length} color${p.colores.length !== 1 ? 'es' : ''}</strong>
                            </span>` : ''}
                        </div>
                    </div>`;
                }).join('');

                searchDropdown.querySelectorAll('.vta-dropdown-item').forEach(el => {
                    el.addEventListener('click', () => {
                        let colores = [];
                        if (el.dataset.colores) {
                            try { colores = JSON.parse(decodeURIComponent(escape(atob(el.dataset.colores)))); }
                            catch { colores = []; }
                        }
                        _agregarItem(el.dataset, colores);
                        searchDropdown.classList.remove('open');
                        searchDropdown.innerHTML = '';
                        searchInput.value = '';
                    });
                });
            }
            searchDropdown.classList.add('open');
        } catch {
            searchDropdown.classList.remove('open');
        }
    }, 260);
});

searchInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        searchDropdown.classList.remove('open');
        searchInput.value = '';
    }
});

document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
        searchDropdown.classList.remove('open');
    }
});

/* ════════════════════════════════════════════════════════════════
   AGREGAR ÍTEM AL CARRITO
════════════════════════════════════════════════════════════════ */
function _agregarItem(d, colores) {
    // dataset convierte data-tiene-colores → tieneColores (camelCase automático)
    const tieneColores = (d['tieneColores'] === '1' || d['tiene-colores'] === '1') && colores && colores.length > 0;

    // ── Precio del producto (puede ser vacío si no está cargado) ──
    const precioProducto = d.precio !== undefined && d.precio !== ''
        ? parseFloat(d.precio)
        : 0;
    const monedaProducto = d.moneda || 'ARS';

    // Si ya existe el producto (sin colores), solo incrementa cantidad
    if (!tieneColores) {
        const existente = carrito.find(i => String(i.producto_pk) === String(d.pk) && !i.tiene_colores);
        if (existente) {
            existente.cantidad++;
            _renderCarrito();
            _actualizarTotales();
            return;
        }
    }

    carrito.push({
        id:               nextId++,
        producto_pk:      d.pk,
        nombre:           d.nombre,
        codigo:           d.codigo || '',
        unidad:           d.unidad || '',
        cliente_pk:       d['cli-pk'] || '',
        cliente_nombre:   d['cli-nombre'] || '',
        tiene_colores:    tieneColores,
        colores_lista:    tieneColores ? colores : [],
        colores_dist:     tieneColores ? Object.fromEntries(colores.map(c => [c.pk, 0])) : {},
        cantidad:         tieneColores ? 0 : 1,
        // ── Se autocompleta con el precio cargado en el producto ──
        // Si el producto no tiene precio (null), queda en 0 para ingreso manual.
        precio_unitario:  precioProducto,
        moneda:           monedaProducto,
        descuento:        0,
        condicion:        'contado',
        referencia:       '',
    });

    _renderCarrito();
    _actualizarTotales();
    _toast('Producto agregado', d.nombre);
}

/* ════════════════════════════════════════════════════════════════
   RENDER CARRITO
════════════════════════════════════════════════════════════════ */
function _renderCarrito() {
    if (!carrito.length) {
        cartBody.innerHTML  = '';
        cartEmpty.style.display  = 'flex';
        cartFooter.style.display = 'none';
        if (badge) badge.style.display = 'none';
        return;
    }

    cartEmpty.style.display  = 'none';
    cartFooter.style.display = 'flex';
    if (badge) { badge.textContent = carrito.length; badge.style.display = 'inline-flex'; }

    cartBody.innerHTML = carrito.map(item => {
        const sub          = _calcSub(item);
        const colorWarning = item.tiene_colores && !_coloresValidos(item)
            ? `<span class="vta-color-warning" title="Distribuí todos los colores">
                   <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                       <circle cx="6" cy="6" r="5" stroke="currentColor" stroke-width="1.3"/>
                       <path d="M6 4V6.5M6 8H6.01" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                   </svg>
               </span>` : '';

        const filaColores = item.tiene_colores ? _renderFilaColores(item) : '';

        return `
        <tr data-item-id="${item.id}" class="vta-row-main">
            <td>
                <div class="vta-prod-cell">
                    <span class="vta-prod-nombre">${_esc(item.nombre)}</span>
                    <span class="vta-prod-meta">${_esc(item.codigo)}</span>
                    ${item.tiene_colores
                        ? `<span class="vta-prod-badge-colores">
                               <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                   <circle cx="5" cy="5" r="3.5" stroke="currentColor" stroke-width="1.2"/>
                                   <circle cx="5" cy="5" r="1.2" fill="currentColor"/>
                               </svg>
                               Por color
                           </span>` : ''}
                </div>
            </td>
            <td>
                <div class="vta-cli-wrap">
                    <input type="text"
                           class="vta-input-inline w-lg vta-cli-input"
                           placeholder="Buscar cliente…"
                           value="${_esc(item.cliente_nombre)}"
                           autocomplete="off"
                           data-item-id="${item.id}">
                </div>
            </td>
            <td>
                <input type="number" min="0.001" step="any"
                       class="vta-input-inline w-xs vta-field-input"
                       value="${item.cantidad}"
                       data-item-id="${item.id}" data-campo="cantidad"
                       ${item.tiene_colores ? 'readonly title="Se calcula automáticamente desde la distribución"' : ''}>
                ${colorWarning}
            </td>
            <td>
                <input type="number" min="0" step="any"
                       class="vta-input-inline w-sm vta-field-input"
                       value="${item.precio_unitario}"
                       data-item-id="${item.id}" data-campo="precio_unitario">
            </td>
            <td>
                <select class="vta-select-inline vta-field-input"
                        data-item-id="${item.id}" data-campo="moneda">
                    <option value="ARS" ${item.moneda === 'ARS' ? 'selected' : ''}>ARS</option>
                    <option value="USD" ${item.moneda === 'USD' ? 'selected' : ''}>USD</option>
                    <option value="EUR" ${item.moneda === 'EUR' ? 'selected' : ''}>EUR</option>
                </select>
            </td>
            <td>
                <input type="number" min="0" max="100" step="0.01"
                       class="vta-input-inline w-xs vta-field-input"
                       value="${item.descuento}"
                       data-item-id="${item.id}" data-campo="descuento">
            </td>
            <td>
                <select class="vta-select-inline vta-field-input"
                        data-item-id="${item.id}" data-campo="condicion">
                    <option value="contado"  ${item.condicion === 'contado'  ? 'selected' : ''}>Contado</option>
                    <option value="15"       ${item.condicion === '15'       ? 'selected' : ''}>15 días</option>
                    <option value="30"       ${item.condicion === '30'       ? 'selected' : ''}>30 días</option>
                    <option value="60"       ${item.condicion === '60'       ? 'selected' : ''}>60 días</option>
                    <option value="90"       ${item.condicion === '90'       ? 'selected' : ''}>90 días</option>
                    <option value="convenir" ${item.condicion === 'convenir' ? 'selected' : ''}>A convenir</option>
                </select>
            </td>
            <td>
                <input type="text"
                       class="vta-input-inline w-md vta-field-input"
                       placeholder="Nº factura"
                       value="${_esc(item.referencia)}"
                       data-item-id="${item.id}" data-campo="referencia">
            </td>
            <td class="vta-subtotal-cell" id="vtaSub_${item.id}">
                ${_fmt(sub, item.moneda)}
            </td>
            <td>
                <button class="vta-btn-remove vta-btn-quitar" data-item-id="${item.id}" title="Quitar">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                    </svg>
                </button>
            </td>
        </tr>
        ${filaColores}`;
    }).join('');

    _bindCartBodyEvents();
    _actualizarBtnContinuar();
}

/* ════════════════════════════════════════════════════════════════
   FILA DE COLORES
════════════════════════════════════════════════════════════════ */
function _renderFilaColores(item) {
    const totalAsignado = _totalColoresDist(item);
    const totalItem     = parseFloat(item.cantidad) || 0;
    const ok            = Math.abs(totalAsignado - totalItem) < 0.001;

    const chips = item.colores_lista.map(c => {
        const val    = item.colores_dist[c.pk] || 0;
        const swatch = c.codigo_hex
            ? `<span class="vta-color-swatch" style="background:${_esc(c.codigo_hex)}"></span>` : '';
        return `
        <div class="vta-color-chip">
            ${swatch}
            <span class="vta-color-chip-nombre">${_esc(c.nombre)}</span>
            <span class="vta-color-chip-stock">(stock: ${parseFloat(c.stock_actual || 0).toLocaleString('es-AR')})</span>
            <input type="number" min="0" step="any"
                   class="vta-input-inline w-xs vta-color-qty"
                   value="${val}"
                   data-item-id="${item.id}"
                   data-color-pk="${c.pk}">
        </div>`;
    }).join('');

    return `
    <tr class="vta-row-colores" data-color-row="${item.id}">
        <td colspan="10">
            <div class="vta-colores-panel">
                <div class="vta-colores-panel-header">
                    <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                        <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" stroke-width="1.3"/>
                        <circle cx="6.5" cy="6.5" r="2" fill="currentColor"/>
                    </svg>
                    <span>Distribuir por color</span>
                    <span class="vta-colores-panel-resumen ${ok ? 'ok' : 'error'}"
                          id="vtaColRes_${item.id}">
                        ${ok
                            ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                   <path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                               </svg> Distribución completa`
                            : `Asignado: <strong>${totalAsignado.toLocaleString('es-AR')}</strong> / Total: <strong>${totalItem.toLocaleString('es-AR')}</strong>`
                        }
                    </span>
                </div>
                <div class="vta-colores-chips">${chips}</div>
            </div>
        </td>
    </tr>`;
}

function _actualizarFilaColores(itemId) {
    const item = carrito.find(i => i.id === itemId);
    if (!item || !item.tiene_colores) return;

    const filaVieja = cartBody.querySelector(`tr[data-color-row="${itemId}"]`);
    const nuevaHTML = _renderFilaColores(item);
    if (filaVieja) {
        filaVieja.outerHTML = nuevaHTML;
    } else {
        const filaMain = cartBody.querySelector(`tr[data-item-id="${itemId}"]`);
        if (filaMain) filaMain.insertAdjacentHTML('afterend', nuevaHTML);
    }

    // Re-bind inputs de color de la fila nueva
    cartBody.querySelectorAll(`.vta-color-qty[data-item-id="${itemId}"]`).forEach(input => {
        input.addEventListener('change', () =>
            _updateColorDist(parseInt(input.dataset.itemId, 10), input.dataset.colorPk, input.value));
    });
}

/* ════════════════════════════════════════════════════════════════
   BIND EVENTOS TBODY
════════════════════════════════════════════════════════════════ */
function _bindCartBodyEvents() {
    // Campos editables
    cartBody.querySelectorAll('.vta-field-input').forEach(el => {
        el.addEventListener('change', () =>
            _updateField(parseInt(el.dataset.itemId, 10), el.dataset.campo, el.value));
    });

    // Distribución de colores
    cartBody.querySelectorAll('.vta-color-qty').forEach(input => {
        input.addEventListener('change', () =>
            _updateColorDist(parseInt(input.dataset.itemId, 10), input.dataset.colorPk, input.value));
    });

    // Quitar ítem
    cartBody.querySelectorAll('.vta-btn-quitar').forEach(btn => {
        btn.addEventListener('click', () => {
            carrito = carrito.filter(i => i.id !== parseInt(btn.dataset.itemId, 10));
            _renderCarrito();
            _actualizarTotales();
        });
    });

    // Cliente autocomplete
    cartBody.querySelectorAll('.vta-cli-input').forEach(input => {
        input.addEventListener('input', () => _onCliInput(input));
        input.addEventListener('blur',  () => _onCliBlur(input));
    });
}

/* ════════════════════════════════════════════════════════════════
   ACTUALIZAR CAMPO DE UN ÍTEM
════════════════════════════════════════════════════════════════ */
function _updateField(id, campo, valor) {
    const item = carrito.find(i => i.id === id);
    if (!item) return;

    if (['cantidad', 'precio_unitario', 'descuento'].includes(campo)) {
        item[campo] = parseFloat(valor) || 0;
    } else {
        item[campo] = valor;
    }

    // Actualizar subtotal en la celda
    const subEl = document.getElementById(`vtaSub_${id}`);
    if (subEl) subEl.textContent = _fmt(_calcSub(item), item.moneda);

    // Si cambia la cantidad en un item con colores, actualizar resumen
    if (campo === 'cantidad' && item.tiene_colores) {
        const resEl = document.getElementById(`vtaColRes_${id}`);
        if (resEl) {
            const ta = _totalColoresDist(item), ti = parseFloat(item.cantidad) || 0;
            const ok = Math.abs(ta - ti) < 0.001;
            resEl.className = `vta-colores-panel-resumen ${ok ? 'ok' : 'error'}`;
            resEl.innerHTML = ok
                ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg> Distribución completa`
                : `Asignado: <strong>${ta.toLocaleString('es-AR')}</strong> / Total: <strong>${ti.toLocaleString('es-AR')}</strong>`;
        }
    }

    _actualizarTotales();
    _actualizarBtnContinuar();
}

/* ════════════════════════════════════════════════════════════════
   DISTRIBUCIÓN DE COLORES
════════════════════════════════════════════════════════════════ */
function _updateColorDist(itemId, colorPk, valor) {
    const item = carrito.find(i => i.id === itemId);
    if (!item) return;

    item.colores_dist[colorPk] = parseFloat(valor) || 0;
    const totalAsignado = _totalColoresDist(item);
    item.cantidad = totalAsignado;

    // Actualizar input de cantidad (readonly)
    const mainRow = cartBody.querySelector(`tr[data-item-id="${itemId}"]`);
    if (mainRow) {
        const cantInput = mainRow.querySelector('input[data-campo="cantidad"]');
        if (cantInput) cantInput.value = totalAsignado;
        mainRow.querySelector('.vta-color-warning')?.remove();
    }

    // Actualizar resumen distribución
    const resEl = document.getElementById(`vtaColRes_${itemId}`);
    const totalItem = parseFloat(item.cantidad) || 0;
    const ok = Math.abs(totalAsignado - totalItem) < 0.001;
    if (resEl) {
        resEl.className = `vta-colores-panel-resumen ${ok ? 'ok' : 'error'}`;
        resEl.innerHTML = ok
            ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                   <path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
               </svg> Distribución completa`
            : `Asignado: <strong>${totalAsignado.toLocaleString('es-AR')}</strong> / Total: <strong>${totalItem.toLocaleString('es-AR')}</strong>`;
    }

    // Actualizar subtotal
    const subEl = document.getElementById(`vtaSub_${itemId}`);
    if (subEl) subEl.textContent = _fmt(_calcSub(item), item.moneda);

    _actualizarTotales();
    _actualizarBtnContinuar();
}

/* ════════════════════════════════════════════════════════════════
   TOTALES Y BADGE
════════════════════════════════════════════════════════════════ */
function _actualizarTotales() {
    const total = carrito.reduce((s, i) => s + _calcSub(i), 0);
    if (totalItemsEl) totalItemsEl.textContent = carrito.length;
    if (totalMontoEl) totalMontoEl.textContent = _fmtPeso(total);
    if (badge) badge.textContent = carrito.length;
}

function _actualizarBtnContinuar() {
    if (!btnContinuar) return;
    const hayItems    = carrito.length > 0;
    const hayInvalido = carrito.some(i => i.tiene_colores && !_coloresValidos(i));
    btnContinuar.disabled = !hayItems || hayInvalido;
}

/* ════════════════════════════════════════════════════════════════
   CLIENTE — AUTOCOMPLETE GLOBAL (posicionado con fixed)
════════════════════════════════════════════════════════════════ */
function _getCliDD() {
    if (!cliGlobalDD) {
        cliGlobalDD = document.createElement('div');
        cliGlobalDD.className = 'vta-cli-dropdown';
        document.body.appendChild(cliGlobalDD);
    }
    return cliGlobalDD;
}

function _cerrarCliDD() {
    const dd = _getCliDD();
    dd.classList.remove('open');
    dd.innerHTML = '';
    cliActiveInput  = null;
    cliActiveItemId = null;
}

function _posCliDD(input) {
    const dd   = _getCliDD();
    const rect = input.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom;
    dd.style.cssText = `
        position:fixed;
        left:${rect.left}px;
        width:${Math.max(rect.width, 220)}px;
        max-height:${Math.min(200, Math.max(below - 8, 120))}px;
        z-index:9000;
        ${below < 120
            ? `bottom:${window.innerHeight - rect.top + 4}px; top:auto;`
            : `top:${rect.bottom + 4}px; bottom:auto;`}`;
}

function _onCliInput(input) {
    const itemId = parseInt(input.dataset.itemId, 10);
    cliActiveInput  = input;
    cliActiveItemId = itemId;

    // Limpiar pk mientras escribe
    const item = carrito.find(i => i.id === itemId);
    if (item) { item.cliente_pk = ''; item.cliente_nombre = input.value; }

    clearTimeout(cliTimers[itemId]);
    const dd = _getCliDD();
    const q  = input.value.trim();
    if (!q) { _cerrarCliDD(); return; }

    cliTimers[itemId] = setTimeout(async () => {
        try {
            const res     = await fetch(`${CFG.urlBuscarCliente}?q=${encodeURIComponent(q)}`);
            const data    = await res.json();
            const results = data.results || [];
            dd.innerHTML  = results.length
                ? results.map(p => `
                    <div class="vta-cli-option" data-pk="${p.pk}" data-nombre="${_esc(p.nombre)}">
                        <div class="vta-cli-option-nombre">${_esc(p.nombre)}</div>
                        ${p.codigo ? `<div class="vta-cli-option-meta">Código: ${_esc(p.codigo)}</div>` : ''}
                    </div>`).join('')
                : `<div class="vta-cli-option" style="color:var(--text-muted);cursor:default">Sin resultados</div>`;

            dd.querySelectorAll('.vta-cli-option[data-pk]').forEach(el => {
                el.addEventListener('mousedown', e => {
                    e.preventDefault();
                    input.value = el.dataset.nombre;
                    const it = carrito.find(i => i.id === itemId);
                    if (it) { it.cliente_pk = el.dataset.pk; it.cliente_nombre = el.dataset.nombre; }
                    _cerrarCliDD();
                });
            });
            _posCliDD(input);
            dd.classList.add('open');
        } catch { _cerrarCliDD(); }
    }, 250);
}

function _onCliBlur(input) {
    setTimeout(() => { if (cliActiveInput === input) _cerrarCliDD(); }, 200);
}

document.addEventListener('mousedown', e => {
    if (cliGlobalDD && !cliGlobalDD.contains(e.target)) _cerrarCliDD();
});

/* ════════════════════════════════════════════════════════════════
   GUARDAR BORRADOR Y NAVEGAR AL DETALLE
════════════════════════════════════════════════════════════════ */
if (btnContinuar) {
    btnContinuar.addEventListener('click', async () => {
        if (!carrito.length) return;

        const pendientes = carrito.filter(i => i.tiene_colores && !_coloresValidos(i));
        if (pendientes.length) {
            _toast(
                'Colores incompletos',
                `Distribuí todos los colores antes de continuar: ${pendientes.map(i => i.nombre).join(', ')}`
            );
            return;
        }

        btnContinuar.disabled  = true;
        btnContinuar.innerHTML = `<svg class="vta-spin" width="15" height="15" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Guardando…`;

        // Expandir colores → 1 item por color con cantidad > 0
        const itemsPayload = [];
        for (const item of carrito) {
            if (item.tiene_colores) {
                for (const [colorPk, cant] of Object.entries(item.colores_dist)) {
                    const cantidad = parseFloat(cant) || 0;
                    if (cantidad <= 0) continue;
                    itemsPayload.push({
                        producto_pk:     item.producto_pk,
                        cliente_pk:      item.cliente_pk || null,
                        color_pk:        parseInt(colorPk, 10),
                        cantidad,
                        precio_unitario: item.precio_unitario,
                        moneda:          item.moneda,
                        descuento_pct:   item.descuento,
                        condicion_pago:  item.condicion,
                        referencia:      item.referencia,
                    });
                }
            } else {
                itemsPayload.push({
                    producto_pk:     item.producto_pk,
                    cliente_pk:      item.cliente_pk || null,
                    color_pk:        null,
                    cantidad:        item.cantidad,
                    precio_unitario: item.precio_unitario,
                    moneda:          item.moneda,
                    descuento_pct:   item.descuento,
                    condicion_pago:  item.condicion,
                    referencia:      item.referencia,
                });
            }
        }

        try {
            const res  = await fetch(CFG.urlGuardarBorrador, {
                method:  'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken':  CFG.csrfToken,
                },
                body: JSON.stringify({ items: itemsPayload }),
            });
            const data = await res.json();

            if (data.ok) {
                window.location.href = CFG.urlDetalle + data.pk;
            } else {
                _toast('Error', data.error || 'No se pudo guardar el borrador');
                btnContinuar.disabled = false;
                btnContinuar.innerHTML = `
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M3 7.5H12M8.5 3.5L12.5 7.5L8.5 11.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    Continuar al detalle`;
            }
        } catch (e) {
            _toast('Error', 'Error de red al guardar');
            btnContinuar.disabled = false;
            btnContinuar.innerHTML = `
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                    <path d="M3 7.5H12M8.5 3.5L12.5 7.5L8.5 11.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Continuar al detalle`;
        }
    });
}