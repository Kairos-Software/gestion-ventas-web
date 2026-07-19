/**
 * nueva_compra.js
 * Módulo del carrito para crear una nueva compra.
 *
 * Cada resultado que devuelve el buscador (?q=) ya es una UNIDAD
 * AGREGABLE resuelta: un producto sin variantes, o una variante puntual
 * de un producto con variantes. Un clic (o un escaneo exacto) agrega
 * directo una fila al carrito — ya no existe la distribución manual
 * por combinación.
 *
 * Requiere window.CMP_CONFIG con:
 *   urlBuscarProducto  — GET ?q=
 *   urlBuscarProveedor — GET ?q=
 *   urlGuardarBorrador — POST JSON
 *   urlDetalle         — base URL para redirigir (se le concatena el pk)
 *   csrfToken
 */
'use strict';

const CFG = window.CMP_CONFIG || {};

// Si venimos de "Editar carrito" (?editar=<pk>), el backend precarga los
// ítems de ese borrador en un <script type="application/json"> aparte
// (vía json_script de Django) — misma técnica segura que en detalle_compra.
(() => {
    const el = document.getElementById('cmpItemsData');
    CFG.itemsIniciales = el ? JSON.parse(el.textContent) : [];
})();

/* ════════════════════════════════════════════════════════════════
   ESTADO
════════════════════════════════════════════════════════════════ */
let carrito      = [];   // [{ id, producto_pk, combinacion_pk, nombre,
                         //    producto_nombre, variante_desc, codigo,
                         //    codigo_barras, unidad, es_perecedero,
                         //    proveedor_pk, proveedor_nombre,
                         //    cantidad, costo, moneda, descuento,
                         //    condicion, referencia, fecha_vencimiento }]
let nextId       = 0;
let provTimers   = {};
let provGlobalDD = null;
let provActiveInput  = null;
let provActiveItemId = null;
let _lastResults = [];   // últimos resultados del buscador (para leer por índice)

/* ════════════════════════════════════════════════════════════════
   DOM
════════════════════════════════════════════════════════════════ */
const searchInput    = document.getElementById('cmpSearchInput');
const searchDropdown = document.getElementById('cmpSearchDropdown');
const cartBody       = document.getElementById('cmpCartBody');
const cartEmpty      = document.getElementById('cmpCartEmpty');
const cartFooter     = document.getElementById('cmpCartFooter');
const btnContinuar   = document.getElementById('cmpBtnContinuar');
const badge          = document.getElementById('cmpBadge');
const totalItemsEl   = document.getElementById('cmpTotalItems');
const totalMontoEl   = document.getElementById('cmpTotalMonto');

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
    const base = (parseFloat(item.cantidad) || 0) * (parseFloat(item.costo) || 0);
    return item.descuento ? base * (1 - parseFloat(item.descuento) / 100) : base;
}

/* ════════════════════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════════════════════ */
function _toast(titulo, cuerpo) {
    const toast = document.getElementById('cmpToast');
    document.getElementById('cmpToastTitle').textContent = titulo;
    document.getElementById('cmpToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

/* ════════════════════════════════════════════════════════════════
   BUSCADOR DE PRODUCTOS — autocomplete / escaneo
════════════════════════════════════════════════════════════════ */
let searchTimer;

/**
 * Ejecuta la búsqueda y decide qué hacer con los resultados.
 * `forzarAgregado`: true cuando el disparo viene de un Enter (típico
 * de un lector de código de barras) — en ese caso, si hay UN solo
 * resultado, se agrega directo aunque el backend no lo haya marcado
 * como match_exacto (red de seguridad ante espacios/formatos raros).
 */
async function _ejecutarBusqueda(q, { forzarAgregado = false } = {}) {
    if (!q) {
        searchDropdown.classList.remove('open');
        searchDropdown.innerHTML = '';
        return;
    }
    try {
        const res     = await fetch(`${CFG.urlBuscarProducto}?q=${encodeURIComponent(q)}`);
        const data    = await res.json();
        const results = data.results || [];
        _lastResults  = results;

        // ── Match exacto único (escaneo) → agregar directo, sin dropdown ──
        const debeAgregarDirecto =
            (results.length === 1 && results[0].match_exacto) ||
            (forzarAgregado && results.length === 1);

        if (debeAgregarDirecto) {
            _agregarItem(results[0]);
            searchDropdown.classList.remove('open');
            searchDropdown.innerHTML = '';
            searchInput.value = '';
            return;
        }

        if (!results.length) {
            searchDropdown.innerHTML = forzarAgregado
                ? '<div class="cmp-dropdown-empty">No se encontró ningún producto con ese código.</div>'
                : '<div class="cmp-dropdown-empty">Sin resultados</div>';
        } else {
            searchDropdown.innerHTML = results.map((r, idx) => `
                <div class="cmp-dropdown-item" data-idx="${idx}">
                    <div class="cmp-dropdown-item-top">
                        <span class="cmp-dropdown-item-nombre">${_esc(r.producto_nombre)}</span>
                        <span class="cmp-dropdown-item-codigo">${_esc(r.codigo)}</span>
                    </div>
                    <div class="cmp-dropdown-item-meta">
                        <span class="cmp-meta-chip cmp-meta-chip--stock${parseFloat(r.stock_actual || 0) <= 0 ? ' cmp-meta-chip--stock-vacio' : ''}">
                            <span class="cmp-meta-label">Stock</span>
                            <strong>${parseFloat(r.stock_actual || 0).toLocaleString('es-AR')}</strong>
                        </span>
                        ${r.proveedor ? `<span class="cmp-meta-chip cmp-meta-chip--prov">
                            <span class="cmp-meta-label">Prov.</span>
                            <strong>${_esc(r.proveedor)}</strong>
                        </span>` : ''}
                        ${r.variante_desc ? `<span class="cmp-meta-chip cmp-meta-chip--variante">
                            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                <rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                                <circle cx="3" cy="3" r="1" fill="currentColor"/>
                            </svg>
                            <strong>${_esc(r.variante_desc)}</strong>
                        </span>` : ''}
                    </div>
                </div>`
            ).join('');

            searchDropdown.querySelectorAll('.cmp-dropdown-item[data-idx]').forEach(el => {
                el.addEventListener('click', () => {
                    const fila = _lastResults[parseInt(el.dataset.idx, 10)];
                    if (fila) _agregarItem(fila);
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
}

searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    if (q.length < 1) {
        searchDropdown.classList.remove('open');
        searchDropdown.innerHTML = '';
        return;
    }
    searchTimer = setTimeout(() => _ejecutarBusqueda(q), 260);
});

searchInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        searchDropdown.classList.remove('open');
        searchInput.value = '';
        return;
    }
    if (e.key === 'Enter') {
        // Clave para el lector de código de barras: la mayoría termina
        // el escaneo mandando un Enter. Bloqueamos cualquier submit de
        // formulario que ese Enter pudiera disparar, cancelamos el
        // debounce pendiente, y buscamos/agregamos ya mismo.
        e.preventDefault();
        clearTimeout(searchTimer);
        const q = searchInput.value.trim();
        if (q) _ejecutarBusqueda(q, { forzarAgregado: true });
    }
});

document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
        searchDropdown.classList.remove('open');
    }
});

/* ════════════════════════════════════════════════════════════════
   AGREGAR ÍTEM AL CARRITO
   `fila` es un resultado del buscador: ya identifica exactamente
   producto_pk + combinacion_pk (o combinacion_pk: null si no aplica).
════════════════════════════════════════════════════════════════ */
function _agregarItem(fila) {
    // Si ya existe la misma unidad (mismo producto + misma variante), solo suma cantidad
    const existente = carrito.find(i =>
        String(i.producto_pk) === String(fila.producto_pk) &&
        (i.combinacion_pk || null) === (fila.combinacion_pk || null)
    );
    if (existente) {
        existente.cantidad = (parseFloat(existente.cantidad) || 0) + 1;
        _renderCarrito();
        _actualizarTotales();
        _toast('Cantidad actualizada', fila.nombre);
        return;
    }

    carrito.push({
        id:               nextId++,
        producto_pk:      fila.producto_pk,
        combinacion_pk:   fila.combinacion_pk || null,
        nombre:           fila.nombre,
        producto_nombre:  fila.producto_nombre,
        variante_desc:    fila.variante_desc || '',
        codigo:           fila.codigo || '',
        codigo_barras:    fila.codigo_barras || '',
        unidad:           fila.unidad_medida || '',
        es_perecedero:    !!fila.es_perecedero,
        proveedor_pk:     fila.proveedor_pk || '',
        proveedor_nombre: fila.proveedor || '',
        cantidad:         1,
        costo:            0,
        moneda:           'ARS',
        descuento:        0,
        lista_descuento_nombre: '',
        condicion:        'contado',
        referencia:       '',
        fecha_vencimiento: '',
    });

    _renderCarrito();
    _actualizarTotales();
    _toast('Producto agregado', fila.nombre);
}

function _selectListaDescuento(item) {
    const listas = CFG.listasDescuento || [];
    if (!listas.length) {
        return `<span class="cmp-lista-vacia" title="No hay listas de descuento creadas">—</span>`;
    }
    const opciones = listas.map(l => `
        <option value="${_esc(l.nombre)}" data-pct="${l.porcentaje}" ${item.lista_descuento_nombre === l.nombre ? 'selected' : ''}>
            ${_esc(l.nombre)} (${l.porcentaje}%)
        </option>`).join('');
    return `
        <select class="cmp-select-inline cmp-field-input w-sm" data-item-id="${item.id}" data-campo="lista_descuento"
                title="Aplicar % de una lista de descuento">
            <option value="">— Manual —</option>
            ${opciones}
        </select>`;
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
        const sub = _calcSub(item);

        return `
        <tr data-item-id="${item.id}" class="cmp-row-main">
            <td>
                <div class="cmp-prod-cell">
                    <span class="cmp-prod-nombre">${_esc(item.producto_nombre)}</span>
                    <span class="cmp-prod-meta">${_esc(item.codigo)}</span>
                    ${item.variante_desc
                        ? `<span class="cmp-prod-badge-colores">
                               <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                   <rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                                   <circle cx="3" cy="3" r="1" fill="currentColor"/>
                               </svg>
                               ${_esc(item.variante_desc)}
                           </span>` : ''}
                </div>
            </td>
            <td>
                <div class="cmp-prov-wrap">
                    <input type="text"
                           class="cmp-input-inline w-lg cmp-prov-input"
                           placeholder="Buscar proveedor…"
                           value="${_esc(item.proveedor_nombre)}"
                           autocomplete="off"
                           data-item-id="${item.id}">
                </div>
            </td>
            <td>
                <input type="number" min="0.001" step="any"
                       class="cmp-input-inline w-xs cmp-field-input"
                       value="${item.cantidad}"
                       data-item-id="${item.id}" data-campo="cantidad">
            </td>
            <td>
                <input type="number" min="0" step="any"
                       class="cmp-input-inline w-sm cmp-field-input"
                       value="${item.costo}"
                       data-item-id="${item.id}" data-campo="costo">
            </td>
            <td>
                <input type="number" min="0" max="100" step="0.01"
                       class="cmp-input-inline w-xs cmp-field-input"
                       value="${item.descuento}"
                       data-item-id="${item.id}" data-campo="descuento">
            </td>
            <td>${_selectListaDescuento(item)}</td>
            <td>
                <select class="cmp-select-inline cmp-field-input"
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
                       class="cmp-input-inline w-md cmp-field-input"
                       placeholder="Nº remito / factura"
                       value="${_esc(item.referencia)}"
                       data-item-id="${item.id}" data-campo="referencia">
            </td>
            <td>
                ${item.es_perecedero
                    ? `<input type="date"
                           class="cmp-input-inline w-md cmp-field-input${!item.fecha_vencimiento ? ' cmp-input-required-empty' : ''}"
                           value="${item.fecha_vencimiento || ''}"
                           data-item-id="${item.id}" data-campo="fecha_vencimiento"
                           title="Requerido: este producto es perecedero">`
                    : `<span class="cmp-td-na" title="Este producto no es perecedero">— No aplica —</span>`
                }
            </td>
            <td class="cmp-subtotal-cell" id="cmpSub_${item.id}">
                ${_fmt(sub, item.moneda)}
            </td>
            <td>
                <button class="cmp-btn-remove cmp-btn-quitar" data-item-id="${item.id}" title="Quitar">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                    </svg>
                </button>
            </td>
        </tr>`;
    }).join('');

    _bindCartBodyEvents();
    _actualizarBtnContinuar();
}

/* ════════════════════════════════════════════════════════════════
   BIND EVENTOS TBODY
════════════════════════════════════════════════════════════════ */
function _bindCartBodyEvents() {
    // Campos editables
    cartBody.querySelectorAll('.cmp-field-input').forEach(el => {
        el.addEventListener('change', () =>
            _updateField(parseInt(el.dataset.itemId, 10), el.dataset.campo, el.value));
    });

    // Quitar ítem
    cartBody.querySelectorAll('.cmp-btn-quitar').forEach(btn => {
        btn.addEventListener('click', () => {
            carrito = carrito.filter(i => i.id !== parseInt(btn.dataset.itemId, 10));
            _renderCarrito();
            _actualizarTotales();
        });
    });

    // Proveedor autocomplete
    cartBody.querySelectorAll('.cmp-prov-input').forEach(input => {
        input.addEventListener('input', () => _onProvInput(input));
        input.addEventListener('blur',  () => _onProvBlur(input));
    });
}

/* ════════════════════════════════════════════════════════════════
   ACTUALIZAR CAMPO DE UN ÍTEM
════════════════════════════════════════════════════════════════ */
function _updateField(id, campo, valor) {
    const item = carrito.find(i => i.id === id);
    if (!item) return;

    if (campo === 'lista_descuento') {
        item.lista_descuento_nombre = valor;
        if (valor) {
            const lista = (CFG.listasDescuento || []).find(l => l.nombre === valor);
            if (lista) item.descuento = parseFloat(lista.porcentaje) || 0;
            const inputDesc = cartBody.querySelector(`input[data-item-id="${id}"][data-campo="descuento"]`);
            if (inputDesc) inputDesc.value = item.descuento;
        }
    } else if (['cantidad', 'costo', 'descuento'].includes(campo)) {
        item[campo] = parseFloat(valor) || 0;
        if (campo === 'descuento' && item.lista_descuento_nombre) {
            item.lista_descuento_nombre = '';
            const selLista = cartBody.querySelector(`select[data-item-id="${id}"][data-campo="lista_descuento"]`);
            if (selLista) selLista.value = '';
        }
    } else {
        item[campo] = valor;
    }

    // Actualizar subtotal en la celda
    const subEl = document.getElementById(`cmpSub_${id}`);
    if (subEl) subEl.textContent = _fmt(_calcSub(item), item.moneda);

    // Quitar el aviso visual de "falta fecha" apenas se completa
    if (campo === 'fecha_vencimiento') {
        const inputEl = cartBody.querySelector(`input[data-item-id="${id}"][data-campo="fecha_vencimiento"]`);
        if (inputEl) inputEl.classList.toggle('cmp-input-required-empty', !valor);
    }

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
    btnContinuar.disabled = carrito.length === 0;
}

/* ════════════════════════════════════════════════════════════════
   PROVEEDOR — AUTOCOMPLETE GLOBAL (posicionado con fixed)
════════════════════════════════════════════════════════════════ */
function _getProvDD() {
    if (!provGlobalDD) {
        provGlobalDD = document.createElement('div');
        provGlobalDD.className = 'cmp-prov-dropdown';
        document.body.appendChild(provGlobalDD);
    }
    return provGlobalDD;
}

function _cerrarProvDD() {
    const dd = _getProvDD();
    dd.classList.remove('open');
    dd.innerHTML = '';
    provActiveInput  = null;
    provActiveItemId = null;
}

function _posProvDD(input) {
    const dd   = _getProvDD();
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

function _onProvInput(input) {
    const itemId = parseInt(input.dataset.itemId, 10);
    provActiveInput  = input;
    provActiveItemId = itemId;

    // Limpiar pk mientras escribe
    const item = carrito.find(i => i.id === itemId);
    if (item) { item.proveedor_pk = ''; item.proveedor_nombre = input.value; }

    clearTimeout(provTimers[itemId]);
    const dd = _getProvDD();
    const q  = input.value.trim();
    if (!q) { _cerrarProvDD(); return; }

    provTimers[itemId] = setTimeout(async () => {
        try {
            const res     = await fetch(`${CFG.urlBuscarProveedor}?q=${encodeURIComponent(q)}`);
            const data    = await res.json();
            const results = data.results || [];
            dd.innerHTML  = results.length
                ? results.map(p => `
                    <div class="cmp-prov-option" data-pk="${p.pk}" data-nombre="${_esc(p.nombre)}">
                        <div class="cmp-prov-option-nombre">${_esc(p.nombre)}</div>
                        ${p.cuit ? `<div class="cmp-prov-option-meta">CUIT: ${_esc(p.cuit)}</div>` : ''}
                    </div>`).join('')
                : `<div class="cmp-prov-option" style="color:var(--text-muted);cursor:default">Sin resultados</div>`;

            dd.querySelectorAll('.cmp-prov-option[data-pk]').forEach(el => {
                el.addEventListener('mousedown', e => {
                    e.preventDefault();
                    input.value = el.dataset.nombre;
                    const it = carrito.find(i => i.id === itemId);
                    if (it) { it.proveedor_pk = el.dataset.pk; it.proveedor_nombre = el.dataset.nombre; }
                    _cerrarProvDD();
                });
            });
            _posProvDD(input);
            dd.classList.add('open');
        } catch { _cerrarProvDD(); }
    }, 250);
}

function _onProvBlur(input) {
    setTimeout(() => { if (provActiveInput === input) _cerrarProvDD(); }, 200);
}

document.addEventListener('mousedown', e => {
    if (provGlobalDD && !provGlobalDD.contains(e.target)) _cerrarProvDD();
});

/* ════════════════════════════════════════════════════════════════
   GUARDAR BORRADOR Y NAVEGAR AL DETALLE
════════════════════════════════════════════════════════════════ */
if (btnContinuar) {
    btnContinuar.addEventListener('click', async () => {
        if (!carrito.length) return;

        const pendientesVencimiento = carrito.filter(i => i.es_perecedero && !i.fecha_vencimiento);
        if (pendientesVencimiento.length) {
            _toast(
                'Falta la fecha de vencimiento',
                `Estos productos son perecederos y necesitan fecha: ${pendientesVencimiento.map(i => i.nombre).join(', ')}`
            );
            return;
        }

        btnContinuar.disabled  = true;
        btnContinuar.innerHTML = `<svg class="cmp-spin" width="15" height="15" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Guardando…`;

        // Cada ítem del carrito ya es una unidad resuelta (producto o
        // producto+variante) — se envía tal cual, sin expandir nada.
        const itemsPayload = carrito.map(item => ({
            producto_pk:       item.producto_pk,
            proveedor_pk:      item.proveedor_pk || null,
            combinacion_pk:    item.combinacion_pk || null,
            cantidad:          item.cantidad,
            costo_unitario:    item.costo,
            moneda:            item.moneda,
            descuento_pct:     item.descuento,
            lista_descuento_nombre: item.lista_descuento_nombre || '',
            condicion_pago:    item.condicion,
            referencia:        item.referencia,
            fecha_vencimiento: item.fecha_vencimiento || null,
        }));

        // Modo edición (?editar=<pk>): actualiza el borrador existente.
        // Modo normal: crea un borrador nuevo.
        const editando = !!CFG.editingPk;
        const url      = editando ? CFG.urlActualizarBorrador : CFG.urlGuardarBorrador;
        const body     = editando
            ? { compra_pk: CFG.editingPk, items: itemsPayload }
            : { items: itemsPayload };

        try {
            const res  = await fetch(url, {
                method:  'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken':  CFG.csrfToken,
                },
                body: JSON.stringify(body),
            });
            const data = await res.json();

            if (data.ok) {
                // Redirigir al detalle del borrador (nuevo o el mismo que editábamos)
                const pkDestino = editando ? CFG.editingPk : data.pk;
                window.location.href = CFG.urlDetalle + pkDestino + '/';
            } else {
                _toast('Error al guardar', data.error || 'No se pudo guardar el borrador.');
                btnContinuar.disabled  = false;
                btnContinuar.innerHTML = `<svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                    <path d="M3 7.5H12M8.5 3.5L12.5 7.5L8.5 11.5" stroke="currentColor" stroke-width="1.6"
                          stroke-linecap="round" stroke-linejoin="round"/>
                </svg> Continuar al detalle`;
            }
        } catch {
            _toast('Error de conexión', 'Intentá de nuevo.');
            btnContinuar.disabled  = false;
            btnContinuar.innerHTML = `<svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                <path d="M3 7.5H12M8.5 3.5L12.5 7.5L8.5 11.5" stroke="currentColor" stroke-width="1.6"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg> Continuar al detalle`;
        }
    });
}

/* ════════════════════════════════════════════════════════════════
   INIT — precarga del carrito si venimos en modo edición,
   estado inicial correcto + foco automático en el buscador
════════════════════════════════════════════════════════════════ */
if (CFG.itemsIniciales && CFG.itemsIniciales.length) {
    carrito = CFG.itemsIniciales.map((it, idx) => ({
        id:               idx,
        producto_pk:      it.producto_pk,
        combinacion_pk:   it.combinacion_pk || null,
        nombre:           it.nombre,
        producto_nombre:  it.producto_nombre,
        variante_desc:    it.variante_desc || '',
        codigo:           it.codigo || '',
        unidad:           '',
        es_perecedero:    !!it.es_perecedero,
        proveedor_pk:     it.proveedor_pk || '',
        proveedor_nombre: it.proveedor || '',
        cantidad:         parseFloat(it.cantidad) || 0,
        costo:            parseFloat(it.costo) || 0,
        moneda:           it.moneda || 'ARS',
        descuento:        parseFloat(it.descuento) || 0,
        lista_descuento_nombre: it.lista_descuento_nombre || '',
        condicion:        it.condicion || 'contado',
        referencia:       it.referencia || '',
        fecha_vencimiento: it.fecha_vencimiento || '',
    }));
    nextId = carrito.length;
}
_renderCarrito();
_actualizarTotales();
searchInput.focus();