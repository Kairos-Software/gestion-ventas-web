/**
 * nueva_venta.js
 * ────────────────────────────────────────────────────────────────
 * Esta página es SOLO para cargar productos al carrito: buscar,
 * agregar, definir cantidad, cliente, color, precio, descuento,
 * condición de pago y referencia por ítem.
 *
 * NO se elige fecha, NO se elige medio de pago, NO se confirma la
 * venta acá. Al hacer click en "Continuar al detalle" se guarda el
 * carrito como BORRADOR y se redirige a detalle_venta, que es donde
 * viven: fecha, medios de pago (múltiples), preview/impresión del
 * ticket, confirmar venta o volver atrás a editar el carrito.
 * ────────────────────────────────────────────────────────────────
 */
'use strict';

const CFG = window.VTA_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   ESTADO
════════════════════════════════════════════════════════════════ */
let carrito      = [];
let nextId       = 0;
let cliTimers    = {};
let cliGlobalDD  = null;
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
function _totalCarrito() {
    return carrito.reduce((s, i) => s + _calcSub(i), 0);
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
   BUSCADOR DE PRODUCTOS
════════════════════════════════════════════════════════════════ */
let searchTimer;

searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    if (q.length < 1) { searchDropdown.classList.remove('open'); searchDropdown.innerHTML = ''; return; }
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
                    const precioLabel  = p.precio_venta !== null && p.precio_venta !== undefined
                        ? `<span class="vta-meta-chip vta-meta-chip--precio">Precio: <strong>${_fmtPeso(p.precio_venta)}</strong></span>`
                        : `<span class="vta-meta-chip vta-meta-chip--sin-precio">Sin precio</span>`;
                    return `
                    <div class="vta-dropdown-item"
                         data-pk="${p.pk}" data-nombre="${_esc(p.nombre)}" data-codigo="${_esc(p.codigo)}"
                         data-unidad="${_esc(p.unidad_medida || '')}" data-tiene-colores="${tieneColores ? '1' : '0'}"
                         data-precio="${p.precio_venta !== null && p.precio_venta !== undefined ? p.precio_venta : ''}"
                         data-moneda="${p.moneda || 'ARS'}" ${coloresAttr}>
                        <div class="vta-dropdown-item-top">
                            <span class="vta-dropdown-item-nombre">${_esc(p.nombre)}</span>
                            <span class="vta-dropdown-item-codigo">${_esc(p.codigo)}</span>
                        </div>
                        <div class="vta-dropdown-item-meta">
                            <span class="vta-meta-chip">Stock: <strong>${parseFloat(p.stock_actual || 0).toLocaleString('es-AR')}</strong></span>
                            ${precioLabel}
                            ${tieneColores ? `<span class="vta-meta-chip vta-meta-chip--colores"><strong>${p.colores.length} color${p.colores.length !== 1 ? 'es' : ''}</strong></span>` : ''}
                        </div>
                    </div>`;
                }).join('');
                searchDropdown.querySelectorAll('.vta-dropdown-item').forEach(el => {
                    el.addEventListener('click', () => {
                        let colores = [];
                        if (el.dataset.colores) {
                            try { colores = JSON.parse(decodeURIComponent(escape(atob(el.dataset.colores)))); } catch { colores = []; }
                        }
                        _agregarItem(el.dataset, colores);
                        searchDropdown.classList.remove('open');
                        searchDropdown.innerHTML = '';
                        searchInput.value = '';
                    });
                });
            }
            searchDropdown.classList.add('open');
        } catch { searchDropdown.classList.remove('open'); }
    }, 260);
});

searchInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') { searchDropdown.classList.remove('open'); searchInput.value = ''; }
});
document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target))
        searchDropdown.classList.remove('open');
});

/* ════════════════════════════════════════════════════════════════
   AGREGAR ÍTEM AL CARRITO
   ──────────────────────────────────────────────────────────────
   Si el producto tiene colores, la cantidad arranca en 0 y se
   autocompleta a medida que se distribuyen los colores (no es
   editable a mano — ver _renderCarrito).
   Si NO tiene colores, la cantidad arranca en 1 y es editable.
════════════════════════════════════════════════════════════════ */
function _agregarItem(dataset, colores) {
    const tieneColores = dataset.tieneColores === '1';
    const precio = dataset.precio !== '' ? parseFloat(dataset.precio) : 0;
    const item = {
        id:             nextId++,
        producto_pk:    dataset.pk,
        nombre:         dataset.nombre,
        codigo:         dataset.codigo,
        unidad:         dataset.unidad || '',
        cliente_pk:     '',
        cliente_nombre: '',
        tiene_colores:  tieneColores,
        colores_lista:  colores,
        colores_dist:   tieneColores ? Object.fromEntries(colores.map(c => [c.pk, 0])) : {},
        cantidad:       tieneColores ? 0 : 1,
        precio_unitario: precio,
        moneda:         dataset.moneda || 'ARS',
        descuento:      0,
        condicion:      'contado',
        referencia:     '',
    };
    carrito.push(item);
    _renderCarrito();
    _actualizarBtnContinuar();
}

/* ════════════════════════════════════════════════════════════════
   RENDER CARRITO
════════════════════════════════════════════════════════════════ */
function _renderCarrito() {
    if (!carrito.length) {
        cartEmpty.style.display  = 'flex';
        cartBody.innerHTML       = '';
        cartFooter.style.display = 'none';
        if (badge) { badge.textContent = '0'; badge.style.display = 'none'; }
        _actualizarTotales();
        return;
    }

    cartEmpty.style.display  = 'none';
    cartFooter.style.display = 'flex';
    if (badge) { badge.textContent = carrito.length; badge.style.display = 'inline-flex'; }

    const MONEDAS    = ['ARS', 'USD', 'EUR'];
    const CONDICIONES = [
        { v: 'contado', l: 'Contado' },
        { v: 'cuenta_corriente', l: 'Cta. Cte.' },
        { v: 'credito', l: 'Crédito' },
    ];

    cartBody.innerHTML = carrito.map(item => {
        const sub = _calcSub(item);

        const colorPanel = item.tiene_colores ? `
        <tr class="vta-row-colores" data-item-id="${item.id}">
            <td colspan="10">
                <div class="vta-colores-panel">
                    <div class="vta-colores-panel-header">
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <circle cx="6" cy="6" r="4.5" stroke="currentColor" stroke-width="1.2"/>
                            <circle cx="6" cy="6" r="1.8" fill="currentColor"/>
                        </svg>
                        Distribuir por color
                        <span class="vta-colores-panel-resumen ok" id="colRes_${item.id}">
                            Total: ${_totalColoresDist(item).toLocaleString('es-AR')}
                        </span>
                    </div>
                    <div class="vta-colores-chips">
                        ${item.colores_lista.map(c => `
                        <div class="vta-color-chip">
                            ${c.codigo_hex ? `<span class="vta-color-swatch" style="background:${_esc(c.codigo_hex)}"></span>` : ''}
                            <span class="vta-color-chip-nombre">${_esc(c.nombre)}</span>
                            <span class="vta-color-chip-stock">(${parseFloat(c.stock_actual || 0).toLocaleString('es-AR')})</span>
                            <input type="number" class="vta-input-inline w-xs vta-color-qty"
                                   min="0" step="1" style="width:65px"
                                   value="${parseFloat(item.colores_dist[c.pk] || 0)}"
                                   data-item-id="${item.id}" data-color-pk="${c.pk}">
                        </div>`).join('')}
                    </div>
                </div>
            </td>
        </tr>` : '';

        return `
        <tr data-item-id="${item.id}">
            <td>
                <div class="vta-prod-cell">
                    <span class="vta-prod-nombre">${_esc(item.nombre)}</span>
                    <span class="vta-prod-meta">${_esc(item.codigo)}
                        ${item.tiene_colores ? `<span class="vta-prod-badge-colores">
                            <svg width="9" height="9" viewBox="0 0 10 10" fill="none">
                                <circle cx="5" cy="5" r="3.5" stroke="currentColor" stroke-width="1.2"/>
                            </svg>
                            ${item.colores_lista.length} colores
                        </span>` : ''}
                    </span>
                </div>
            </td>
            <td>
                <input type="text" class="vta-input-inline vta-cli-input"
                       placeholder="Sin cliente" value="${_esc(item.cliente_nombre)}"
                       data-item-id="${item.id}" autocomplete="off">
            </td>
            <td>
                ${item.tiene_colores
                    ? `<input type="number" class="vta-input-inline w-xs" value="${item.cantidad}"
                              data-item-id="${item.id}" data-cantidad-auto="1" readonly
                              title="Se calcula automáticamente según los colores distribuidos">`
                    : `<input type="number" class="vta-input-inline w-xs" min="0.001" step="0.001"
                              value="${item.cantidad}" data-campo="cantidad" data-item-id="${item.id}">`
                }
            </td>
            <td>
                <input type="number" class="vta-input-inline w-sm" min="0" step="0.01"
                       value="${item.precio_unitario}" data-campo="precio_unitario" data-item-id="${item.id}">
            </td>
            <td>
                <select class="vta-select-inline w-xs" data-campo="moneda" data-item-id="${item.id}">
                    ${MONEDAS.map(m => `<option value="${m}" ${item.moneda === m ? 'selected' : ''}>${m}</option>`).join('')}
                </select>
            </td>
            <td>
                <input type="number" class="vta-input-inline w-xs" min="0" max="100" step="0.1"
                       value="${item.descuento}" data-campo="descuento" data-item-id="${item.id}">
            </td>
            <td>
                <select class="vta-select-inline w-md" data-campo="condicion" data-item-id="${item.id}">
                    ${CONDICIONES.map(c => `<option value="${c.v}" ${item.condicion === c.v ? 'selected' : ''}>${c.l}</option>`).join('')}
                </select>
            </td>
            <td>
                <input type="text" class="vta-input-inline w-md" placeholder="Nº factura / ref."
                       value="${_esc(item.referencia)}" data-campo="referencia" data-item-id="${item.id}">
            </td>
            <td class="vta-subtotal-cell">${_fmt(sub, item.moneda)}</td>
            <td>
                <button class="vta-btn-remove" data-remove="${item.id}" title="Quitar">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                    </svg>
                </button>
            </td>
        </tr>
        ${colorPanel}`;
    }).join('');

    // Inputs de campos simples (no incluye el de cantidad cuando tiene colores, porque ese es readonly)
    cartBody.querySelectorAll('[data-campo][data-item-id]').forEach(el => {
        el.addEventListener('input', () => {
            const id    = parseInt(el.dataset.itemId, 10);
            const campo = el.dataset.campo;
            const item  = carrito.find(i => i.id === id);
            if (!item) return;
            item[campo] = el.value;
            if (['cantidad', 'precio_unitario', 'descuento'].includes(campo)) {
                const tr = el.closest('tr');
                tr && (tr.querySelector('.vta-subtotal-cell').textContent = _fmt(_calcSub(item), item.moneda));
            }
            _actualizarTotales();
            if (campo === 'cantidad') _actualizarBtnContinuar();
        });
    });

    // Distribución de colores → autocompleta el campo "Cantidad" general
    cartBody.querySelectorAll('.vta-color-qty').forEach(el => {
        el.addEventListener('input', () => {
            const id      = parseInt(el.dataset.itemId, 10);
            const colorPk = el.dataset.colorPk;
            const item    = carrito.find(i => i.id === id);
            if (!item) return;

            item.colores_dist[colorPk] = parseFloat(el.value) || 0;

            // ── Autocompletar cantidad general = suma de todos los colores ──
            const total = _totalColoresDist(item);
            item.cantidad = total;

            const resumen = document.getElementById(`colRes_${id}`);
            if (resumen) resumen.textContent = `Total: ${total.toLocaleString('es-AR')}`;

            // Actualizar el input de cantidad (readonly) y el subtotal de la fila
            const tr = cartBody.querySelector(`tr[data-item-id="${id}"]:not(.vta-row-colores)`);
            if (tr) {
                const cantidadInput = tr.querySelector('[data-cantidad-auto]');
                if (cantidadInput) cantidadInput.value = total;
                const subtotalCell = tr.querySelector('.vta-subtotal-cell');
                if (subtotalCell) subtotalCell.textContent = _fmt(_calcSub(item), item.moneda);
            }

            _actualizarTotales();
            _actualizarBtnContinuar();
        });
    });

    // Quitar ítem
    cartBody.querySelectorAll('[data-remove]').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = parseInt(btn.dataset.remove, 10);
            carrito = carrito.filter(i => i.id !== id);
            _renderCarrito();
            _actualizarBtnContinuar();
        });
    });

    // Cliente autocomplete
    cartBody.querySelectorAll('.vta-cli-input').forEach(input => {
        input.addEventListener('input',  () => _onCliInput(input));
        input.addEventListener('blur',   () => _onCliBlur(input));
        input.addEventListener('focus',  () => { if (input.value.trim()) _onCliInput(input); });
    });

    _actualizarTotales();
    _actualizarBtnContinuar();
}

/* ════════════════════════════════════════════════════════════════
   TOTALES Y ESTADO DEL BOTÓN
════════════════════════════════════════════════════════════════ */
function _actualizarTotales() {
    const total = _totalCarrito();
    if (totalItemsEl) totalItemsEl.textContent = carrito.length;
    if (totalMontoEl) totalMontoEl.textContent  = _fmtPeso(total);
    if (badge) badge.textContent = carrito.length;
}

function _actualizarBtnContinuar() {
    if (!btnContinuar) return;
    const hayItems = carrito.length > 0;
    // Si tiene colores pero la cantidad autocompletada quedó en 0, no deja avanzar
    const hayPendiente = carrito.some(i => i.tiene_colores && (parseFloat(i.cantidad) || 0) <= 0);
    btnContinuar.disabled = !hayItems || hayPendiente;
}

/* ════════════════════════════════════════════════════════════════
   CLIENTE — AUTOCOMPLETE
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
    dd.classList.remove('open'); dd.innerHTML = '';
    cliActiveInput = null; cliActiveItemId = null;
}
function _posCliDD(input) {
    const dd = _getCliDD(), rect = input.getBoundingClientRect(), below = window.innerHeight - rect.bottom;
    dd.style.cssText = `position:fixed;left:${rect.left}px;width:${Math.max(rect.width, 220)}px;max-height:${Math.min(200, Math.max(below - 8, 120))}px;z-index:9000;${below < 120 ? `bottom:${window.innerHeight - rect.top + 4}px;top:auto;` : `top:${rect.bottom + 4}px;bottom:auto;`}`;
}
function _onCliInput(input) {
    const itemId = parseInt(input.dataset.itemId, 10);
    cliActiveInput = input; cliActiveItemId = itemId;
    const item = carrito.find(i => i.id === itemId);
    if (item) { item.cliente_pk = ''; item.cliente_nombre = input.value; }
    clearTimeout(cliTimers[itemId]);
    const dd = _getCliDD(), q = input.value.trim();
    if (!q) { _cerrarCliDD(); return; }
    cliTimers[itemId] = setTimeout(async () => {
        try {
            const res = await fetch(`${CFG.urlBuscarCliente}?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            const results = data.results || [];
            dd.innerHTML = results.length
                ? results.map(p => `<div class="vta-cli-option" data-pk="${p.pk}" data-nombre="${_esc(p.nombre)}">
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
            _posCliDD(input); dd.classList.add('open');
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
   CONTINUAR AL DETALLE — guarda borrador y redirige
   ──────────────────────────────────────────────────────────────
   Acá NO se confirma la venta. Solo se guarda como borrador y se
   redirige a detalle_venta, donde se completa fecha, medio(s) de
   pago, y se confirma (o se vuelve atrás a editar el carrito).
════════════════════════════════════════════════════════════════ */
function _buildItemsPayload() {
    const payload = [];
    for (const item of carrito) {
        if (item.tiene_colores) {
            for (const [colorPk, cant] of Object.entries(item.colores_dist)) {
                const cantidad = parseFloat(cant) || 0;
                if (cantidad <= 0) continue;
                payload.push({
                    producto_pk:     item.producto_pk,
                    cliente_pk:      item.cliente_pk || null,
                    color_pk:        parseInt(colorPk, 10),
                    cantidad,
                    precio_unitario: parseFloat(item.precio_unitario) || 0,
                    moneda:          item.moneda,
                    descuento_pct:   parseFloat(item.descuento) || 0,
                    condicion_pago:  item.condicion,
                    referencia:      item.referencia,
                });
            }
        } else {
            payload.push({
                producto_pk:     item.producto_pk,
                cliente_pk:      item.cliente_pk || null,
                color_pk:        null,
                cantidad:        parseFloat(item.cantidad) || 0,
                precio_unitario: parseFloat(item.precio_unitario) || 0,
                moneda:          item.moneda,
                descuento_pct:   parseFloat(item.descuento) || 0,
                condicion_pago:  item.condicion,
                referencia:      item.referencia,
            });
        }
    }
    return payload;
}

if (btnContinuar) {
    btnContinuar.addEventListener('click', async () => {
        if (!carrito.length) return;

        const sinDistribuir = carrito.filter(i => i.tiene_colores && (parseFloat(i.cantidad) || 0) <= 0);
        if (sinDistribuir.length) {
            _toast('Colores sin distribuir', `Asigná cantidad a los colores de: ${sinDistribuir.map(i => i.nombre).join(', ')}`);
            return;
        }

        btnContinuar.disabled  = true;
        btnContinuar.innerHTML = `<svg class="vta-spin" width="15" height="15" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Guardando…`;

        try {
            const res  = await fetch(CFG.urlGuardarBorrador, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                body:    JSON.stringify({ items: _buildItemsPayload() }),
            });
            const data = await res.json();

            if (data.ok) {
                window.location.href = CFG.urlDetalle + data.pk + '/';
            } else {
                _toast('Error', data.error || 'No se pudo guardar el borrador.');
                btnContinuar.disabled  = false;
                btnContinuar.innerHTML = `<svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                    <path d="M3 7.5H12M8.5 3.5L12.5 7.5L8.5 11.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg> Continuar al detalle`;
            }
        } catch {
            _toast('Error de conexión', 'Intentá de nuevo.');
            btnContinuar.disabled  = false;
            btnContinuar.innerHTML = `<svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                <path d="M3 7.5H12M8.5 3.5L12.5 7.5L8.5 11.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg> Continuar al detalle`;
        }
    });
}