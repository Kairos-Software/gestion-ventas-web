/**
 * compras.js
 * Lógica del carrito de compras — Nueva Compra
 *
 * Las URLs y el CSRF token se inyectan desde el template
 * a través de window.CMP_CONFIG antes de cargar este archivo.
 *
 * Esperado en el template:
 *   <script>
 *     window.CMP_CONFIG = {
 *       urlBuscarProducto: "{% url 'compras:buscar_producto' %}",
 *       urlBuscarProveedor: "{% url 'compras:buscar_proveedor' %}",
 *       urlConfirmar: "{% url 'compras:confirmar_compra' %}",
 *       csrfToken: "{{ csrf_token }}",
 *     };
 *   </script>
 */

'use strict';

/* ════════════════════════════════════════════════════════════════
   CONFIG  (inyectada desde el template)
════════════════════════════════════════════════════════════════ */
const CFG = window.CMP_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   ESTADO GLOBAL
════════════════════════════════════════════════════════════════ */
let carrito = [];
let _nextId  = 0;

/* ════════════════════════════════════════════════════════════════
   REFS DOM
════════════════════════════════════════════════════════════════ */
const searchInput    = document.getElementById('cmpSearchInput');
const searchDropdown = document.getElementById('cmpSearchDropdown');
const cartBody       = document.getElementById('cmpCartBody');
const cartEmpty      = document.getElementById('cmpCartEmpty');
const btnConfirmar   = document.getElementById('cmpBtnConfirmar');
const totalItemsEl   = document.getElementById('cmpTotalItems');
const totalMontoEl   = document.getElementById('cmpTotalMonto');
const badgeEl        = document.getElementById('cmpBadge');
const inputFecha     = document.getElementById('cmpFecha');
const inputNotas     = document.getElementById('cmpNotas');

/* ════════════════════════════════════════════════════════════════
   BUSCADOR DE PRODUCTOS
════════════════════════════════════════════════════════════════ */
let _searchTimer;

searchInput.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    const q = searchInput.value.trim();
    if (q.length < 1) { cerrarDropdownProd(); return; }
    _searchTimer = setTimeout(() => buscarProductos(q), 260);
});

searchInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') { cerrarDropdownProd(); searchInput.value = ''; }
});

document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
        cerrarDropdownProd();
    }
});

async function buscarProductos(q) {
    try {
        const res  = await fetch(`${CFG.urlBuscarProducto}?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        renderDropdownProductos(data.results || []);
    } catch {
        cerrarDropdownProd();
    }
}

function renderDropdownProductos(results) {
    if (!results.length) {
        searchDropdown.innerHTML = '<div class="cmp-dropdown-empty">Sin resultados para esa búsqueda</div>';
    } else {
        searchDropdown.innerHTML = results.map(p => {
            const stockBajo = parseFloat(p.stock_actual) <= parseFloat(p.stock_minimo || 0);
            return `
            <div class="cmp-dropdown-item"
                 data-pk="${p.pk}"
                 data-nombre="${_esc(p.nombre)}"
                 data-codigo="${_esc(p.codigo)}"
                 data-unidad="${_esc(p.unidad_medida)}"
                 data-categoria="${_esc(p.categoria)}"
                 data-marca="${_esc(p.marca)}"
                 data-stock="${_esc(p.stock_actual)}"
                 data-prov-pk="${p.proveedor_pk || ''}"
                 data-prov-nombre="${_esc(p.proveedor)}">

                <div class="cmp-dropdown-item-top">
                    <span class="cmp-dropdown-item-nombre">${_esc(p.nombre)}</span>
                    <span class="cmp-dropdown-item-codigo">${_esc(p.codigo)}</span>
                </div>

                <div class="cmp-dropdown-item-meta">
                    <span class="cmp-meta-chip">
                        <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                            <rect x="1" y="1" width="9" height="9" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
                            <path d="M3.5 5.5H7.5M5.5 3.5V7.5" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
                        </svg>
                        <strong>${_esc(p.unidad_medida)}</strong>
                    </span>
                    ${p.categoria ? `<span class="cmp-meta-chip">Cat: <strong>${_esc(p.categoria)}</strong></span>` : ''}
                    ${p.marca     ? `<span class="cmp-meta-chip">Marca: <strong>${_esc(p.marca)}</strong></span>` : ''}
                    <span class="cmp-meta-chip cmp-meta-chip--stock ${stockBajo ? 'bajo' : ''}">
                        <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                            <path d="M1 9L3.5 4L6 7L8 5L10 2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                        Stock: <strong>${parseFloat(p.stock_actual).toLocaleString('es-AR')}</strong>
                    </span>
                    ${p.proveedor ? `<span class="cmp-meta-chip">Prov: <strong>${_esc(p.proveedor)}</strong></span>` : ''}
                </div>
            </div>`;
        }).join('');

        searchDropdown.querySelectorAll('.cmp-dropdown-item').forEach(el => {
            el.addEventListener('click', () => agregarItem({ ...el.dataset }));
        });
    }
    searchDropdown.classList.add('open');
}

function cerrarDropdownProd() {
    searchDropdown.classList.remove('open');
    searchDropdown.innerHTML = '';
}

/* ════════════════════════════════════════════════════════════════
   CARRITO — agregar ítem
════════════════════════════════════════════════════════════════ */
function agregarItem(d) {
    const item = {
        id:               _nextId++,
        producto_pk:      d.pk,
        nombre:           d.nombre,
        codigo:           d.codigo,
        unidad:           d.unidad,
        proveedor_pk:     d['prov-pk'] || d.provPk || '',
        proveedor_nombre: d['prov-nombre'] || d.provNombre || '',
        cantidad:         1,
        costo:            0,
        moneda:           'ARS',
        descuento:        0,
        condicion:        'contado',
        referencia:       '',
    };
    carrito.push(item);
    cerrarDropdownProd();
    searchInput.value = '';
    renderCarrito();
}

/* ════════════════════════════════════════════════════════════════
   CARRITO — render
════════════════════════════════════════════════════════════════ */
function renderCarrito() {
    cartEmpty.style.display = carrito.length ? 'none' : 'flex';

    if (!carrito.length) {
        cartBody.innerHTML = '';
        actualizarTotales();
        actualizarBadge();
        return;
    }

    cartBody.innerHTML = carrito.map(item => `
        <tr data-id="${item.id}">

            <!-- Producto -->
            <td>
                <div class="cmp-prod-cell">
                    <span class="cmp-prod-nombre">${_esc(item.nombre)}</span>
                    <span class="cmp-prod-meta">${_esc(item.codigo)} · ${_esc(item.unidad)}</span>
                </div>
            </td>

            <!-- Proveedor autocomplete -->
            <td>
                <div class="cmp-prov-wrap">
                    <input type="text"
                           class="cmp-input-inline cmp-input-inline w-lg"
                           placeholder="Buscar proveedor…"
                           value="${_esc(item.proveedor_nombre)}"
                           autocomplete="off"
                           oninput="onProveedorInput(this, ${item.id})"
                           onblur="onProveedorBlur(this)">
                    <div class="cmp-prov-dropdown"></div>
                </div>
            </td>

            <!-- Cantidad -->
            <td>
                <input type="number" min="0.001" step="any"
                       class="cmp-input-inline w-xs"
                       value="${item.cantidad}"
                       onchange="updateItem(${item.id}, 'cantidad', this.value)">
            </td>

            <!-- Costo unitario -->
            <td>
                <input type="number" min="0" step="any"
                       class="cmp-input-inline w-sm"
                       value="${item.costo}"
                       onchange="updateItem(${item.id}, 'costo', this.value)">
            </td>

            <!-- Moneda -->
            <td>
                <select class="cmp-select-inline"
                        onchange="updateItem(${item.id}, 'moneda', this.value)">
                    <option value="ARS" ${item.moneda==='ARS'?'selected':''}>ARS</option>
                    <option value="USD" ${item.moneda==='USD'?'selected':''}>USD</option>
                    <option value="EUR" ${item.moneda==='EUR'?'selected':''}>EUR</option>
                </select>
            </td>

            <!-- Descuento -->
            <td>
                <input type="number" min="0" max="100" step="0.01"
                       class="cmp-input-inline w-xs"
                       value="${item.descuento}"
                       onchange="updateItem(${item.id}, 'descuento', this.value)">
            </td>

            <!-- Condición de pago -->
            <td>
                <select class="cmp-select-inline"
                        onchange="updateItem(${item.id}, 'condicion', this.value)">
                    <option value="contado"  ${item.condicion==='contado'?'selected':''}>Contado</option>
                    <option value="15"       ${item.condicion==='15'?'selected':''}>15 días</option>
                    <option value="30"       ${item.condicion==='30'?'selected':''}>30 días</option>
                    <option value="60"       ${item.condicion==='60'?'selected':''}>60 días</option>
                    <option value="90"       ${item.condicion==='90'?'selected':''}>90 días</option>
                    <option value="convenir" ${item.condicion==='convenir'?'selected':''}>A convenir</option>
                </select>
            </td>

            <!-- Referencia -->
            <td>
                <input type="text"
                       class="cmp-input-inline w-md"
                       placeholder="Nº remito / factura"
                       value="${_esc(item.referencia)}"
                       onchange="updateItem(${item.id}, 'referencia', this.value)">
            </td>

            <!-- Subtotal -->
            <td class="cmp-subtotal-cell" id="sub-${item.id}">
                ${fmtMoneda(calcSubtotal(item), item.moneda)}
            </td>

            <!-- Eliminar -->
            <td>
                <button class="cmp-btn-remove" onclick="eliminarItem(${item.id})" title="Quitar ítem">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                    </svg>
                </button>
            </td>
        </tr>
    `).join('');

    actualizarTotales();
    actualizarBadge();
}

/* ════════════════════════════════════════════════════════════════
   CARRITO — actualizar campo
════════════════════════════════════════════════════════════════ */
function updateItem(id, campo, valor) {
    const item = carrito.find(i => i.id === id);
    if (!item) return;

    if (['cantidad', 'costo', 'descuento'].includes(campo)) {
        item[campo] = parseFloat(valor) || 0;
    } else {
        item[campo] = valor;
    }

    // Actualizar solo la celda subtotal de esta fila
    const subEl = document.getElementById(`sub-${id}`);
    if (subEl) subEl.textContent = fmtMoneda(calcSubtotal(item), item.moneda);

    actualizarTotales();
}

function eliminarItem(id) {
    carrito = carrito.filter(i => i.id !== id);
    renderCarrito();
}

/* ════════════════════════════════════════════════════════════════
   PROVEEDOR — autocomplete por fila (dropdown fixed al body)
════════════════════════════════════════════════════════════════ */
const _provTimers = {};

// Dropdown global único, adjunto al body para escapar de overflow
let _provGlobalDropdown = null;
let _provActiveInput    = null;
let _provActiveItemId   = null;

function _getProvGlobalDropdown() {
    if (!_provGlobalDropdown) {
        _provGlobalDropdown = document.createElement('div');
        _provGlobalDropdown.className = 'cmp-prov-dropdown';
        _provGlobalDropdown.id = 'cmpProvGlobalDropdown';
        document.body.appendChild(_provGlobalDropdown);
    }
    return _provGlobalDropdown;
}

function _positionProvDropdown(input) {
    const dd   = _getProvGlobalDropdown();
    const rect = input.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const ddHeight   = Math.min(200, spaceBelow - 8);

    dd.style.position  = 'fixed';
    dd.style.left      = rect.left + 'px';
    dd.style.width     = Math.max(rect.width, 220) + 'px';
    dd.style.maxHeight = Math.max(ddHeight, 120) + 'px';
    dd.style.zIndex    = '9000';

    // Abrir hacia arriba si no hay espacio suficiente abajo
    if (spaceBelow < 120) {
        dd.style.top    = '';
        dd.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
    } else {
        dd.style.bottom = '';
        dd.style.top    = (rect.bottom + 4) + 'px';
    }
}

function _cerrarProvDropdown() {
    const dd = _getProvGlobalDropdown();
    dd.classList.remove('open');
    dd.innerHTML = '';
    _provActiveInput  = null;
    _provActiveItemId = null;
}

// Cerrar al hacer click fuera
document.addEventListener('mousedown', e => {
    if (_provActiveInput && !_provActiveInput.contains(e.target) && !_getProvGlobalDropdown().contains(e.target)) {
        _cerrarProvDropdown();
    }
});

// Reposicionar al hacer scroll o resize
window.addEventListener('scroll', () => { if (_provActiveInput) _positionProvDropdown(_provActiveInput); }, true);
window.addEventListener('resize', () => { if (_provActiveInput) _positionProvDropdown(_provActiveInput); });

function onProveedorInput(input, itemId) {
    const q = input.value.trim();
    clearTimeout(_provTimers[itemId]);

    _provActiveInput  = input;
    _provActiveItemId = itemId;

    // Limpiar pk al escribir
    updateItem(itemId, 'proveedor_pk',     '');
    updateItem(itemId, 'proveedor_nombre', input.value);

    const dd = _getProvGlobalDropdown();

    if (!q) { _cerrarProvDropdown(); return; }

    _provTimers[itemId] = setTimeout(async () => {
        try {
            const res  = await fetch(`${CFG.urlBuscarProveedor}?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            renderProvDropdown(dd, data.results || [], input, itemId);
        } catch {
            _cerrarProvDropdown();
        }
    }, 250);
}

function renderProvDropdown(dropdown, results, input, itemId) {
    if (!results.length) {
        dropdown.innerHTML = `<div class="cmp-prov-option" style="color:var(--text-muted);cursor:default">Sin resultados</div>`;
    } else {
        dropdown.innerHTML = results.map(p => `
            <div class="cmp-prov-option"
                 data-pk="${p.pk}"
                 data-nombre="${_esc(p.nombre)}"
                 data-cuit="${_esc(p.cuit)}">
                <div class="cmp-prov-option-nombre">${_esc(p.nombre)}</div>
                ${p.cuit ? `<div class="cmp-prov-option-meta">CUIT: ${_esc(p.cuit)}</div>` : ''}
            </div>
        `).join('');

        dropdown.querySelectorAll('.cmp-prov-option[data-pk]').forEach(el => {
            el.addEventListener('mousedown', e => {
                e.preventDefault();
                input.value = el.dataset.nombre;
                updateItem(itemId, 'proveedor_pk',     el.dataset.pk);
                updateItem(itemId, 'proveedor_nombre', el.dataset.nombre);
                _cerrarProvDropdown();
            });
        });
    }
    _positionProvDropdown(input);
    dropdown.classList.add('open');
}

function onProveedorBlur(input) {
    // El mousedown en una opción llama preventDefault, así que el blur
    // se dispara antes de que el click se procese — esperamos un tick.
    setTimeout(() => {
        if (_provActiveInput === input) _cerrarProvDropdown();
    }, 200);
}

/* ════════════════════════════════════════════════════════════════
   TOTALES  Y  BADGE
════════════════════════════════════════════════════════════════ */
function calcSubtotal(item) {
    const base = item.cantidad * item.costo;
    return item.descuento ? base * (1 - item.descuento / 100) : base;
}

function actualizarTotales() {
    const total = carrito.reduce((s, i) => s + calcSubtotal(i), 0);
    totalItemsEl.textContent = carrito.length;
    totalMontoEl.textContent = fmtPeso(total);
    btnConfirmar.disabled    = carrito.length === 0;
}

function actualizarBadge() {
    if (carrito.length) {
        badgeEl.textContent    = carrito.length;
        badgeEl.style.display  = 'inline-flex';
    } else {
        badgeEl.style.display  = 'none';
    }
}

/* ════════════════════════════════════════════════════════════════
   CONFIRMAR COMPRA
════════════════════════════════════════════════════════════════ */
btnConfirmar.addEventListener('click', async () => {
    const fecha = inputFecha.value;
    if (!fecha) { alert('Ingresá una fecha para la compra.'); return; }
    if (!carrito.length) return;

    const payload = {
        fecha: fecha,
        notas: inputNotas.value.trim(),
        items: carrito.map(i => ({
            producto_pk:    i.producto_pk,
            proveedor_pk:   i.proveedor_pk || null,
            cantidad:       i.cantidad,
            costo_unitario: i.costo,
            moneda:         i.moneda,
            descuento_pct:  i.descuento,
            condicion_pago: i.condicion,
            referencia:     i.referencia,
        })),
    };

    // Estado cargando
    btnConfirmar.disabled   = true;
    btnConfirmar.innerHTML  = `<svg class="cmp-spin" width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
    </svg> Guardando…`;

    try {
        const res  = await fetch(CFG.urlConfirmar, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
            body:    JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.ok) {
            mostrarToast(
                `Compra ${data.numero} confirmada`,
                `Total: ${fmtPeso(parseFloat(data.total))}`
            );
            carrito = [];
            inputNotas.value = '';
            renderCarrito();
        } else {
            alert('Error: ' + (data.error || 'No se pudo confirmar la compra.'));
        }
    } catch {
        alert('Error de conexión. Intentá de nuevo.');
    } finally {
        btnConfirmar.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
        </svg> Confirmar compra`;
        btnConfirmar.disabled = carrito.length === 0;
    }
});

/* ════════════════════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════════════════════ */
function mostrarToast(titulo, cuerpo) {
    const toast = document.getElementById('cmpToast');
    document.getElementById('cmpToastTitle').textContent = titulo;
    document.getElementById('cmpToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

/* ════════════════════════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════════════════════════ */
function fmtPeso(v) {
    return '$' + v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtMoneda(v, moneda) {
    const sym = { USD: 'U$S ', EUR: '€ ', ARS: '$' }[moneda] || '$';
    return sym + v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function _esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/* ════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */
renderCarrito();