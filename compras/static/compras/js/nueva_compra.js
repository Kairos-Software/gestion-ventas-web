/**
 * nueva_compra.js
 * Una sola pantalla para crear una compra: carrito a la izquierda +
 * panel de proveedor / comprobante / IVA / forma de pago a la derecha
 * (mismo diseño que Nueva Venta y Factura inicial).
 *
 * Cada resultado del buscador (?q=) ya es una UNIDAD AGREGABLE resuelta
 * (producto simple o variante puntual). Un clic / escaneo agrega una
 * fila al carrito, ARRIBA de todo. Con muchos ítems aparece un filtro +
 * ventana de 10 filas con "Mostrar más / todos".
 *
 * "Confirmar compra" NO navega a otra página: guarda el borrador
 * (guardar_borrador / actualizar_borrador) y lo confirma
 * (confirmar_compra) en dos requests encadenados, y muestra el estado
 * "confirmada" en el mismo panel (como Nueva Venta).
 *
 * Requiere window.CMP_CONFIG (ver nueva_compra.html): urlBuscarProducto,
 * urlBuscarProveedor, urlGuardarBorrador, urlActualizarBorrador,
 * urlConfirmar, urlDetalle, urlHistorial, urlDeudas, urlNuevaCompra,
 * editingPk, hoy, csrfToken, listasDescuento, cuentas, tarjetas,
 * cuentaPrincipalPk, editPrefill.
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
let _lastResults = [];   // últimos resultados del buscador (para leer por índice)

/* Ventana del carrito — en compras largas no renderizamos todo de una:
   se muestran las primeras N filas (el ítem recién agregado entra arriba
   de todo) y el resto queda detrás de "Mostrar más" o del filtro. */
const CMP_CARRITO_LIMITE = 10;   // filas visibles antes de "Mostrar más"
const CMP_FILTRO_DESDE   = 10;   // a partir de cuántos ítems aparece el filtro
let _carritoLimite  = CMP_CARRITO_LIMITE;
let _carritoVerTodo = false;
let _carritoFiltro  = '';

// Proveedor de la compra — uno solo para todos los ítems (no por producto):
// una compra es un pedido a UN proveedor. Vive en el panel de la derecha
// (ver _bindProveedorPanel).
let compraProveedor = { pk: null, nombre: '' };
let provSearchTimer;

// pk del borrador ya guardado en esta sesión. En modo ?editar= arranca
// con editingPk; si no, se llena en el primer intento de confirmar (para
// que un 2do intento actualice ese borrador en vez de crear otro).
let _borradorPk = CFG.editingPk || null;
let _confirmada = false;

/* ════════════════════════════════════════════════════════════════
   DOM
════════════════════════════════════════════════════════════════ */
const searchInput    = document.getElementById('cmpSearchInput');
const searchDropdown = document.getElementById('cmpSearchDropdown');
const cartBody       = document.getElementById('cmpCartBody');
const cartEmpty      = document.getElementById('cmpCartEmpty');
const cartFooter     = document.getElementById('cmpCartFooter');
const cartCount      = document.getElementById('cmpCartCount');
const cartFilter     = document.getElementById('cmpCartFilter');
const cartFilterInput = document.getElementById('cmpCartFilterInput');
const cartFilterClear = document.getElementById('cmpCartFilterClear');
const cartMore       = document.getElementById('cmpCartMore');
const badge          = document.getElementById('cmpBadge');
const totalMontoEl   = document.getElementById('cmpTotalMonto');

// Panel
const panelHint      = document.getElementById('cmpPanelHint');
const cobroForm      = document.getElementById('cmpCobroForm');
const cobroConfirmada = document.getElementById('cmpCobroConfirmada');
const inTipoDoc      = document.getElementById('cmpTipoDoc');
const inFecha        = document.getElementById('cmpFecha');
const inNumComp      = document.getElementById('cmpNumComp');
const inAlicuota     = document.getElementById('cmpAlicuota');
const inIvaIncluido  = document.getElementById('cmpIvaIncluido');
const inNotas        = document.getElementById('cmpNotas');
const ivaSection     = document.getElementById('cmpIvaSection');
const pagoLineasEl   = document.getElementById('cmpPagoLineas');
const pagoResumenEl  = document.getElementById('cmpPagoResumen');
const btnConfirmar   = document.getElementById('cmpBtnConfirmar');
const btnCancelar    = document.getElementById('cmpBtnCancelar');

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
                        ${r.codigo_proveedor ? `<span class="cmp-meta-chip cmp-meta-chip--prov">
                            <span class="cmp-meta-label">Cód. prov.</span>
                            <strong>${_esc(r.codigo_proveedor)}</strong>
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
    _filtroLimpiar();   // que el ítem que se agrega quede siempre a la vista

    // Si ya existe la misma unidad (mismo producto + misma variante), solo suma
    // cantidad y la fila sube arriba de todo (mismo criterio que el alta nueva).
    const idxExistente = carrito.findIndex(i =>
        String(i.producto_pk) === String(fila.producto_pk) &&
        (i.combinacion_pk || null) === (fila.combinacion_pk || null)
    );
    if (idxExistente !== -1) {
        const existente = carrito[idxExistente];
        existente.cantidad = (parseFloat(existente.cantidad) || 0) + 1;
        if (idxExistente > 0) {
            carrito.splice(idxExistente, 1);
            carrito.unshift(existente);
        }
        _renderCarrito();
        _actualizarTotales();
        _toast('Cantidad actualizada', fila.nombre);
        return;
    }

    // Si todavía no se eligió proveedor, el primer producto agregado
    // "sugiere" el suyo (su proveedor habitual) en el panel de la derecha
    // — se puede cambiar ahí, y se propaga a todos los ítems.
    if (!compraProveedor.pk && !carrito.length && fila.proveedor_pk) {
        compraProveedor = { pk: fila.proveedor_pk, nombre: fila.proveedor || '' };
        const provInput = document.getElementById('cmpProvInput');
        const provClear = document.getElementById('cmpProvClear');
        if (provInput) provInput.value = compraProveedor.nombre;
        if (provClear) provClear.style.display = 'inline-flex';
    }

    carrito.unshift({
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
        proveedor_pk:     compraProveedor.pk || '',
        proveedor_nombre: compraProveedor.nombre || '',
        cantidad:         1,
        // Prellenado con el último costo vigente del producto (última
        // compra real, costo de referencia activado, o ajuste manual de
        // stock) — el usuario lo puede editar igual antes de confirmar.
        costo:            parseFloat(fila.costo_actual) || 0,
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
    if (!listas.length) return '';   // sin listas creadas → el campo no aparece
    const opciones = listas.map(l => `
        <option value="${_esc(l.nombre)}" data-pct="${l.porcentaje}" ${item.lista_descuento_nombre === l.nombre ? 'selected' : ''}>
            ${_esc(l.nombre)} (${l.porcentaje}%)
        </option>`).join('');
    return `
        <div class="cmp-cart-field">
            <label>Lista</label>
            <select class="cmp-field-input" data-item-id="${item.id}" data-campo="lista_descuento"
                    title="Aplicar % de una lista de descuento">
                <option value="">— Manual —</option>
                ${opciones}
            </select>
        </div>`;
}

/* ════════════════════════════════════════════════════════════════
   FILTRO DE ÍTEMS YA AGREGADOS (para compras largas)
════════════════════════════════════════════════════════════════ */
function _filtroLimpiar() {
    _carritoFiltro = '';
    if (cartFilterInput) cartFilterInput.value = '';
    if (cartFilterClear) cartFilterClear.hidden = true;
}
if (cartFilterInput) {
    cartFilterInput.addEventListener('input', () => {
        _carritoFiltro = cartFilterInput.value;
        if (cartFilterClear) cartFilterClear.hidden = !cartFilterInput.value;
        _renderCarrito();
    });
}
if (cartFilterClear) {
    cartFilterClear.addEventListener('click', () => {
        _filtroLimpiar();
        _renderCarrito();
        if (cartFilterInput) cartFilterInput.focus();
    });
}

/* ════════════════════════════════════════════════════════════════
   RENDER CARRITO — filas tipo tarjeta + ventana "mostrar más"
════════════════════════════════════════════════════════════════ */
function _renderCarrito() {
    if (!carrito.length) {
        cartBody.innerHTML  = '';
        cartEmpty.style.display  = 'flex';
        cartFooter.style.display = 'none';
        if (cartCount)  cartCount.textContent = '0 ítems';
        if (cartFilter) cartFilter.hidden = true;
        if (cartMore)   cartMore.hidden = true;
        if (badge) badge.style.display = 'none';
        _actualizarEstadoConfirmar();
        return;
    }

    cartEmpty.style.display  = 'none';
    cartFooter.style.display = 'flex';
    if (cartCount) cartCount.textContent = `${carrito.length} ${carrito.length === 1 ? 'ítem' : 'ítems'}`;
    if (badge) { badge.textContent = carrito.length; badge.style.display = 'inline-flex'; }

    // ── Ventana visible: filtro / "mostrar más" ──
    if (cartFilter) cartFilter.hidden = carrito.length < CMP_FILTRO_DESDE;
    const _filtro    = _carritoFiltro.trim().toLowerCase();
    const _hayFiltro = !!_filtro && !!cartFilter && !cartFilter.hidden;
    let _visibles, _truncado = 0;
    if (_hayFiltro) {
        _visibles = carrito.filter(i =>
            (i.producto_nombre || '').toLowerCase().includes(_filtro) ||
            (i.codigo || '').toLowerCase().includes(_filtro));
    } else if (_carritoVerTodo || carrito.length <= _carritoLimite) {
        _visibles = carrito;
    } else {
        _visibles = carrito.slice(0, _carritoLimite);
        _truncado = carrito.length - _visibles.length;
    }

    cartBody.innerHTML = _visibles.map(item => {
        const base    = (parseFloat(item.cantidad) || 0) * (parseFloat(item.costo) || 0);
        const sub     = _calcSub(item);
        const conDesc = item.descuento && sub !== base;
        return `
        <div class="cmp-cart-row" data-item-id="${item.id}">
            <div class="cmp-cart-row-top">
                <div class="cmp-cart-row-name">
                    <b>${_esc(item.producto_nombre)}</b>
                    <span>${_esc(item.codigo)}${item.unidad ? ' · ' + _esc(item.unidad) : ''}</span>
                    ${item.variante_desc ? `<span class="cmp-cart-row-variante">
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                            <rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                            <circle cx="3" cy="3" r="1" fill="currentColor"/>
                        </svg>${_esc(item.variante_desc)}</span>` : ''}
                </div>
                <button class="cmp-cart-row-x" data-quitar="${item.id}" title="Quitar" aria-label="Quitar">
                    <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                        <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                    </svg>
                </button>
            </div>
            <div class="cmp-cart-row-grid">
                <div class="cmp-cart-field">
                    <label>Cantidad</label>
                    <input type="number" min="0.001" step="any" value="${item.cantidad}"
                           class="cmp-field-input" data-item-id="${item.id}" data-campo="cantidad">
                </div>
                <div class="cmp-cart-field">
                    <label>Costo unit.</label>
                    <input type="number" min="0" step="any" value="${item.costo}"
                           class="cmp-field-input" data-item-id="${item.id}" data-campo="costo">
                </div>
                <div class="cmp-cart-field">
                    <label>Desc. %</label>
                    <input type="number" min="0" max="100" step="0.01" value="${item.descuento}"
                           class="cmp-field-input" data-item-id="${item.id}" data-campo="descuento">
                </div>
                ${_selectListaDescuento(item)}
                ${item.es_perecedero ? `
                <div class="cmp-cart-field">
                    <label>Vencimiento *</label>
                    <input type="date" value="${_esc(item.fecha_vencimiento || '')}"
                           class="cmp-field-input${!item.fecha_vencimiento ? ' cmp-input-required-empty' : ''}"
                           data-item-id="${item.id}" data-campo="fecha_vencimiento"
                           title="Requerido: este producto es perecedero">
                </div>` : ''}
                <div class="cmp-cart-field full">
                    <label>Referencia (opcional)</label>
                    <input type="text" value="${_esc(item.referencia || '')}"
                           class="cmp-field-input" data-item-id="${item.id}" data-campo="referencia"
                           placeholder="N° de remito, lote, nota…">
                </div>
            </div>
            <div class="cmp-cart-row-sub">
                <span>${_esc(String(item.cantidad))} × ${_fmt(item.costo, item.moneda)}</span>
                <strong id="cmpSub_${item.id}">${conDesc ? `<s>${_fmt(base, item.moneda)}</s>` : ''}${_fmt(sub, item.moneda)}</strong>
            </div>
        </div>`;
    }).join('');

    _bindCartBodyEvents();
    _renderCartMore({ hayFiltro: _hayFiltro, filtro: _filtro, mostrados: _visibles.length, truncado: _truncado });
    _actualizarEstadoConfirmar();
}

function _renderCartMore({ hayFiltro, filtro, mostrados, truncado }) {
    if (!cartMore) return;
    if (hayFiltro) {
        cartMore.hidden = false;
        cartMore.className = 'cmp-cart-more cmp-cart-more--filtro';
        cartMore.innerHTML = mostrados
            ? `<span><strong>${mostrados}</strong> de ${carrito.length} ítems coinciden</span>
               <span class="cmp-cart-more-btns"><button type="button" data-cart-accion="limpiar-filtro">Quitar filtro</button></span>`
            : `<span>Ningún ítem coincide con «${_esc(filtro)}»</span>
               <span class="cmp-cart-more-btns"><button type="button" data-cart-accion="limpiar-filtro">Ver todos</button></span>`;
    } else if (truncado > 0) {
        const paso = Math.min(CMP_CARRITO_LIMITE, truncado);
        cartMore.hidden = false;
        cartMore.className = 'cmp-cart-more';
        cartMore.innerHTML = `
            <span>Mostrando <strong>${mostrados}</strong> de ${carrito.length} ítems</span>
            <span class="cmp-cart-more-btns">
                <button type="button" data-cart-accion="mas">Mostrar ${paso} más</button>
                <button type="button" data-cart-accion="todos">Mostrar todos</button>
            </span>`;
    } else {
        cartMore.hidden = true;
        cartMore.innerHTML = '';
        return;
    }
    cartMore.querySelectorAll('[data-cart-accion]').forEach(b => {
        b.addEventListener('click', () => {
            const a = b.dataset.cartAccion;
            if (a === 'mas') _carritoLimite += CMP_CARRITO_LIMITE;
            else if (a === 'todos') _carritoVerTodo = true;
            else if (a === 'limpiar-filtro') _filtroLimpiar();
            _renderCarrito();
        });
    });
}

/* ════════════════════════════════════════════════════════════════
   BIND EVENTOS DE LAS FILAS
════════════════════════════════════════════════════════════════ */
function _bindCartBodyEvents() {
    // Campos editables
    cartBody.querySelectorAll('.cmp-field-input').forEach(el => {
        el.addEventListener('change', () =>
            _updateField(parseInt(el.dataset.itemId, 10), el.dataset.campo, el.value));
    });

    // Quitar ítem
    cartBody.querySelectorAll('[data-quitar]').forEach(btn => {
        btn.addEventListener('click', () => {
            carrito = carrito.filter(i => i.id !== parseInt(btn.dataset.quitar, 10));
            _renderCarrito();
            _actualizarTotales();
        });
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

    // Actualizar el pie de la fila (subtotal + "cantidad × costo")
    const fila = cartBody.querySelector(`.cmp-cart-row[data-item-id="${id}"]`);
    if (fila) {
        const base = (parseFloat(item.cantidad) || 0) * (parseFloat(item.costo) || 0);
        const sub  = _calcSub(item);
        const conDesc = item.descuento && sub !== base;
        const subEl = fila.querySelector(`#cmpSub_${id}`);
        if (subEl) subEl.innerHTML = (conDesc ? `<s>${_fmt(base, item.moneda)}</s>` : '') + _fmt(sub, item.moneda);
        const lineaEl = fila.querySelector('.cmp-cart-row-sub span');
        if (lineaEl) lineaEl.textContent = `${item.cantidad} × ${_fmt(item.costo, item.moneda)}`;
    }

    // Quitar el aviso visual de "falta fecha" apenas se completa
    if (campo === 'fecha_vencimiento') {
        const inputEl = cartBody.querySelector(`input[data-item-id="${id}"][data-campo="fecha_vencimiento"]`);
        if (inputEl) inputEl.classList.toggle('cmp-input-required-empty', !valor);
    }

    _actualizarTotales();
    _actualizarEstadoConfirmar();
}

/* ════════════════════════════════════════════════════════════════
   TOTALES DEL CARRITO + REFRESCO DEL PANEL
════════════════════════════════════════════════════════════════ */
function _actualizarTotales() {
    const subtotal = carrito.reduce((s, i) => s + _calcSub(i), 0);
    if (totalMontoEl) totalMontoEl.textContent = _fmtPeso(subtotal);
    if (cartCount)    cartCount.textContent = `${carrito.length} ${carrito.length === 1 ? 'ítem' : 'ítems'}`;
    if (badge) badge.textContent = carrito.length;
    _recalcularPanel();
}

function _round2(n) { return Math.round((parseFloat(n) || 0) * 100) / 100; }

/* El panel se recalcula en vivo cada vez que cambia el carrito o un
   campo del comprobante/IVA — sin re-renderizar las líneas de pago
   (eso robaría el foco a un input a medio tipear). */
function _recalcularPanel() {
    _actualizarIvaUI();
    // Un único medio sin tocar sigue al total; si el usuario ya editó el
    // monto (o hay más de una línea), no se pisa nada.
    if (cobroState.lineas.length === 1 && cobroState.lineas[0].autofill) {
        const nuevo = _round2(_ivaTotales().total);
        if (cobroState.lineas[0].monto !== nuevo) {
            cobroState.lineas[0].monto = nuevo;
            const inp = pagoLineasEl.querySelector('[data-campo="monto"]');
            if (inp && document.activeElement !== inp) inp.value = nuevo > 0 ? nuevo : '';
        }
    }
    _pagoResumen();
    _actualizarEstadoConfirmar();
}

/* ════════════════════════════════════════════════════════════════
   PROVEEDOR — buscador en el panel (widget .vta-cli-* como el
   "Cliente" de Nueva Venta / el proveedor de Factura inicial).
════════════════════════════════════════════════════════════════ */
function _sincronizarProveedorEnCarrito() {
    carrito.forEach(item => {
        item.proveedor_pk     = compraProveedor.pk || '';
        item.proveedor_nombre = compraProveedor.nombre || '';
    });
}

function _bindProveedorPanel() {
    const input    = document.getElementById('cmpProvInput');
    const dropdown = document.getElementById('cmpProvDropdown');
    const clear    = document.getElementById('cmpProvClear');
    if (!input || !dropdown || !clear) return;

    input.value = compraProveedor.nombre || '';
    clear.style.display = compraProveedor.pk ? 'inline-flex' : 'none';

    input.addEventListener('input', () => {
        clearTimeout(provSearchTimer);
        const q = input.value.trim();
        compraProveedor = { pk: null, nombre: '' };
        clear.style.display = 'none';
        _sincronizarProveedorEnCarrito();
        if (!q) { dropdown.classList.remove('open'); dropdown.innerHTML = ''; return; }
        provSearchTimer = setTimeout(async () => {
            try {
                const res  = await fetch(`${CFG.urlBuscarProveedor}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (input.value.trim() !== q) return;
                const results = data.results || [];
                dropdown.innerHTML = results.length
                    ? results.map((p, i) => `<div class="vta-cli-option" data-idx="${i}">
                        <div class="vta-cli-option-top">
                            <span>${_esc(p.nombre)}</span>
                            ${p.cuit ? `<span class="vta-dropdown-item-codigo">${_esc(p.cuit)}</span>` : ''}
                        </div></div>`).join('')
                    : '<div class="vta-dropdown-empty">Sin resultados</div>';
                dropdown.querySelectorAll('.vta-cli-option[data-idx]').forEach(el => {
                    el.addEventListener('mousedown', e => {
                        e.preventDefault();
                        const p = results[parseInt(el.dataset.idx, 10)];
                        if (!p) return;
                        compraProveedor = { pk: String(p.pk), nombre: p.nombre };
                        input.value = p.nombre;
                        clear.style.display = 'inline-flex';
                        dropdown.classList.remove('open'); dropdown.innerHTML = '';
                        _sincronizarProveedorEnCarrito();
                    });
                });
                dropdown.classList.add('open');
            } catch { /* silencioso */ }
        }, 260);
    });

    clear.addEventListener('click', () => {
        compraProveedor = { pk: null, nombre: '' };
        input.value = '';
        clear.style.display = 'none';
        _sincronizarProveedorEnCarrito();
        input.focus();
    });

    document.addEventListener('mousedown', e => {
        if (!dropdown.contains(e.target) && e.target !== input) dropdown.classList.remove('open');
    });
}

/* ════════════════════════════════════════════════════════════════
   IVA — solo cuenta si el comprobante es Factura. Mismo criterio que
   Compra.calcular_total() en el backend.
════════════════════════════════════════════════════════════════ */
function _ivaTotales() {
    const subtotal  = carrito.reduce((s, i) => s + _calcSub(i), 0);
    const esFactura = inTipoDoc.value === 'factura';
    const alic      = esFactura ? (parseFloat(inAlicuota.value) || 0) : 0;
    const incluido  = inIvaIncluido.checked;
    if (!esFactura || !alic) return { subtotal, neto: null, iva: null, total: subtotal, esFactura };
    if (incluido) {
        const neto = subtotal / (1 + alic / 100);
        return { subtotal, neto, iva: subtotal - neto, total: subtotal, esFactura };
    }
    const total = subtotal * (1 + alic / 100);
    return { subtotal, neto: subtotal, iva: total - subtotal, total, esFactura };
}

function _actualizarIvaUI() {
    const esFactura = inTipoDoc.value === 'factura';
    if (ivaSection) ivaSection.style.display = esFactura ? '' : 'none';
    const t = _ivaTotales();
    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setTxt('cmpTotSubtotal', _fmtPeso(t.subtotal));
    const netoRow = document.getElementById('cmpTotNetoRow');
    const ivaRow  = document.getElementById('cmpTotIvaRow');
    const hayIva  = esFactura && t.neto != null;
    if (netoRow) netoRow.style.display = hayIva ? '' : 'none';
    if (ivaRow)  ivaRow.style.display  = hayIva ? '' : 'none';
    if (hayIva) {
        setTxt('cmpTotNeto', _fmtPeso(t.neto));
        setTxt('cmpTotIva', _fmtPeso(t.iva));
        setTxt('cmpTotIvaPct', (parseFloat(inAlicuota.value) || 0).toString().replace('.', ','));
    }
}

/* ════════════════════════════════════════════════════════════════
   FORMA DE PAGO — botonera de medios (mismo lenguaje que Nueva Venta)
   + cuenta real de la que sale la plata + plan de cuotas (crédito /
   cheque) + cotización si la cuenta no es en pesos.
════════════════════════════════════════════════════════════════ */
const cobroState = { lineas: [], nextId: 0 };

const _MEDIO_ICONOS = {
    efectivo:      '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="2" y="5" width="16" height="10" rx="1.5" stroke="currentColor" stroke-width="1.4"/><circle cx="10" cy="10" r="2.2" stroke="currentColor" stroke-width="1.4"/></svg>',
    transferencia: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 7.5h10M11 4.5l3 3-3 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 12.5H6M9 15.5l-3-3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    debito:        '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="2.5" y="4.5" width="15" height="11" rx="1.8" stroke="currentColor" stroke-width="1.4"/><path d="M2.5 8.5h15" stroke="currentColor" stroke-width="1.4"/></svg>',
    qr:            '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="3" y="3" width="6" height="6" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="11" y="3" width="6" height="6" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="3" y="11" width="6" height="6" rx="1" stroke="currentColor" stroke-width="1.4"/><path d="M11 11h3v3M17 11.5V17h-5.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    credito:       '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="2.5" y="4.5" width="15" height="11" rx="1.8" stroke="currentColor" stroke-width="1.4"/><path d="M2.5 8.5h15" stroke="currentColor" stroke-width="1.4"/><path d="M5 12h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    cheque:        '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="3" y="3.5" width="14" height="13" rx="1.6" stroke="currentColor" stroke-width="1.4"/><path d="M6 8h8M6 11h8M6 14h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
};
const _MEDIOS = [
    { v: 'efectivo',      label: 'Efectivo' },
    { v: 'transferencia', label: 'Transferencia', corto: 'Transf.' },
    { v: 'debito',        label: 'Débito' },
    { v: 'qr',            label: 'QR' },
    { v: 'credito',       label: 'Crédito' },
    { v: 'cheque',        label: 'Cheque' },
];

function _cuentas()  { return CFG.cuentas || []; }
function _tarjetas() { return CFG.tarjetas || []; }
function _esTarjeta(pk) { return _tarjetas().some(t => String(t.pk) === String(pk)); }
function _cuentaEfectivo() { return _cuentas().find(c => c.nombre === 'Efectivo' && c.moneda === 'ARS'); }
function _cuentaInfo(pk) { return _cuentas().concat(_tarjetas()).find(c => String(c.pk) === String(pk)); }
function _cuentasParaMedio(medio) {
    if (medio === 'credito') return _tarjetas();
    if (medio === 'cheque')  return _cuentas().filter(c => c.tipo === 'banco');
    if (medio === 'efectivo') return [_cuentaEfectivo()].filter(Boolean);
    // transferencia / débito / qr → cualquier cuenta real menos las de "Efectivo"
    return _cuentas().filter(c => c.nombre !== 'Efectivo');
}
function _usaPlanCuotas(l) { return l.medio === 'credito' || l.medio === 'cheque'; }
function _montoArsLinea(l) {
    const info = _cuentaInfo(l.cuenta);
    if (info && info.moneda !== 'ARS') return (parseFloat(l.monto) || 0) * (parseFloat(l.cotizacion) || 0);
    return parseFloat(l.monto) || 0;
}
function _interesLinea(l) {
    if (!_usaPlanCuotas(l)) return 0;
    return (parseFloat(l.monto) || 0) * (parseFloat(l.interesPct) || 0) / 100;
}

function _aplicarMedio(l, medio) {
    l.medio = medio;
    l.cuenta = ''; l.cotizacion = '';
    l.modoCuotas = 'fijas'; l.cuotas = ''; l.interesPct = ''; l.fechaInicioDebito = '';
    if (medio === 'efectivo') {
        const e = _cuentaEfectivo();
        l.cuenta = e ? String(e.pk) : '';
    } else {
        const posibles = _cuentasParaMedio(medio);
        const enLista = pk => posibles.some(c => String(c.pk) === String(pk));
        if (CFG.cuentaPrincipalPk && enLista(CFG.cuentaPrincipalPk)) l.cuenta = String(CFG.cuentaPrincipalPk);
        else if (posibles.length === 1) l.cuenta = String(posibles[0].pk);
        if (medio === 'cheque' && !l.fechaInicioDebito) l.fechaInicioDebito = CFG.hoy || '';
    }
    _pagoRenderLineas();
}

function _pagoBotonera(l, idx) {
    return _MEDIOS.map((m, i) => `
        <button type="button" class="vdt-medio-tab${m.v === l.medio ? ' is-active' : ''}"
                data-medio-btn="${m.v}" data-i="${idx}" aria-pressed="${m.v === l.medio}"
                title="${m.label} (tecla ${i + 1})">
            <span class="vdt-medio-tab-num" aria-hidden="true">${i + 1}</span>
            ${_MEDIO_ICONOS[m.v] || ''}
            <span>${m.corto || m.label}</span>
        </button>`).join('');
}

function _cuentaSelectHTML(l, idx) {
    if (l.medio === 'efectivo') return `<div class="cmp-pago-efectivo">Efectivo — caja grande</div>`;
    const posibles = _cuentasParaMedio(l.medio);
    if (!posibles.length) {
        const que = l.medio === 'credito' ? 'tarjetas de crédito' : l.medio === 'cheque' ? 'cuentas bancarias (chequera)' : 'cuentas';
        return `<div class="cmp-pago-sin-cuenta">No hay ${que} cargadas. Creá una en Configuración → Cuentas de caja.</div>`;
    }
    return `<select class="vdt-pago-select" data-campo="cuenta" data-i="${idx}">
        <option value="">— Elegí ${l.medio === 'credito' ? 'tarjeta' : 'cuenta'} —</option>
        ${posibles.map(c => `<option value="${c.pk}" ${String(c.pk) === String(l.cuenta) ? 'selected' : ''}>${_esc(c.nombre)}${c.titular ? ' · ' + _esc(c.titular) : ''}${c.terminada_en ? ' ··' + _esc(c.terminada_en) : ''} (${c.moneda})</option>`).join('')}
    </select>`;
}

function _pagoRenderLineas() {
    if (!pagoLineasEl) return;
    if (!cobroState.lineas.length) {
        pagoLineasEl.innerHTML = `<p class="cmp-pago-vacio">Sin medios de pago. Usá el botón de abajo para agregar.</p>`;
        _pagoResumen(); _actualizarEstadoConfirmar();
        return;
    }
    pagoLineasEl.innerHTML = cobroState.lineas.map((l, idx) => {
        const info = _cuentaInfo(l.cuenta);
        const foranea = info && info.moneda !== 'ARS';
        const plan = _usaPlanCuotas(l);
        return `
    <div class="vdt-pago-linea-wrap" data-i="${idx}">
        <div class="vdt-medio-tabs" role="group" aria-label="Medio de pago">${_pagoBotonera(l, idx)}</div>
        <div class="vdt-pago-linea">
            ${_cuentaSelectHTML(l, idx)}
            <input type="number" class="vdt-pago-monto" min="0" step="0.01" placeholder="Monto"
                   value="${l.monto > 0 ? l.monto : ''}" data-campo="monto" data-i="${idx}">
            <button class="vdt-pago-btn-quitar" type="button" data-quitar="${idx}" title="Quitar">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
        </div>
        ${foranea ? `<div class="vdt-pago-linea-cuenta">
            <input type="number" class="vdt-pago-cotizacion" min="0.0001" step="0.0001"
                   placeholder="Cotización ($ por 1 ${_esc(info.moneda)})" value="${l.cotizacion || ''}"
                   data-campo="cotizacion" data-i="${idx}">
            ${l.cotizacion ? `<span class="vdt-pago-equivalente">≈ ${_fmtPeso(_montoArsLinea(l))}</span>` : ''}
        </div>` : ''}
        ${plan ? `
        <label class="vdt-credito-modo-row">
            <span class="vdt-pago-credito-label">Cuotas libres</span>
            <span class="toggle-switch">
                <input type="checkbox" data-campo="modoCuotas" data-i="${idx}" ${l.modoCuotas === 'libre' ? 'checked' : ''}>
                <span class="toggle-track"></span>
            </span>
        </label>
        ${l.medio === 'cheque' ? `<p class="vdt-cheque-plan-nota">Acá se define el plan de cuotas. Los cheques de cada cuota se cargan después, desde la deuda en Créditos y préstamos.</p>` : ''}
        <div class="vdt-pago-credito-extra">
            ${l.modoCuotas === 'libre' ? '' : `<div>
                <span class="vdt-pago-credito-label">Cuotas</span>
                <input type="number" class="vdt-pago-select" min="1" step="1" placeholder="Cuotas"
                       value="${l.cuotas || ''}" data-campo="cuotas" data-i="${idx}">
            </div>`}
            <div>
                <span class="vdt-pago-credito-label">Interés %</span>
                <input type="number" class="vdt-pago-select" min="0" step="0.01" placeholder="0"
                       value="${l.interesPct !== '' && l.interesPct != null ? l.interesPct : ''}" data-campo="interesPct" data-i="${idx}">
            </div>
            ${l.modoCuotas === 'libre' ? `<div class="vdt-credito-total-libre">
                <span class="vdt-pago-credito-label">Total con interés</span>
                <strong>${_fmtPeso((parseFloat(l.monto) || 0) * (1 + (parseFloat(l.interesPct) || 0) / 100))}</strong>
            </div>` : `<div>
                <span class="vdt-pago-credito-label">${l.medio === 'cheque' ? 'Fecha 1° cuota' : 'Inicio débito'}</span>
                <input type="date" class="vdt-pago-select" value="${l.fechaInicioDebito || ''}"
                       data-campo="fechaInicioDebito" data-i="${idx}">
            </div>`}
        </div>` : ''}
    </div>`;
    }).join('');

    pagoLineasEl.querySelectorAll('.vdt-medio-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            const l = cobroState.lineas[parseInt(btn.dataset.i, 10)];
            if (l && l.medio !== btn.dataset.medioBtn) _aplicarMedio(l, btn.dataset.medioBtn);
        });
    });
    pagoLineasEl.querySelectorAll('[data-campo]').forEach(el => {
        const evt = (el.type === 'checkbox' || el.tagName === 'SELECT') ? 'change' : 'input';
        el.addEventListener(evt, () => {
            const l = cobroState.lineas[parseInt(el.dataset.i, 10)];
            if (!l) return;
            const campo = el.dataset.campo;
            if (campo === 'monto') { l.monto = _round2(el.value); l.autofill = false; _pagoResumen(); _actualizarEstadoConfirmar(); return; }
            if (campo === 'cotizacion') { l.cotizacion = el.value; _pagoRenderLineas(); return; }
            if (campo === 'modoCuotas') { l.modoCuotas = el.checked ? 'libre' : 'fijas'; _pagoRenderLineas(); return; }
            if (campo === 'cuenta') { l.cuenta = el.value; l.cotizacion = ''; _pagoRenderLineas(); return; }
            if (campo === 'cuotas') { l.cuotas = el.value; }
            else if (campo === 'interesPct') { l.interesPct = el.value; if (l.modoCuotas === 'libre') { _pagoRenderLineas(); return; } }
            else { l[campo] = el.value; }
            _pagoResumen(); _actualizarEstadoConfirmar();
        });
    });
    pagoLineasEl.querySelectorAll('[data-quitar]').forEach(btn => {
        btn.addEventListener('click', () => {
            cobroState.lineas.splice(parseInt(btn.dataset.quitar, 10), 1);
            _pagoRenderLineas();
        });
    });

    _pagoResumen();
    _actualizarEstadoConfirmar();
}

function _pagoResumen() {
    const { total } = _ivaTotales();
    const asignado = cobroState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
    const interes  = cobroState.lineas.reduce((s, l) => s + _interesLinea(l), 0);
    const dif = total - asignado;

    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setTxt('cmpTotTotal', _fmtPeso(total));

    if (pagoResumenEl) {
        pagoResumenEl.className = 'vdt-pago-cierre';
        const est = document.getElementById('cmpPagoEstado');
        if (total < 0.01) {
            pagoResumenEl.classList.add('vdt-pago-cierre--pendiente');
            if (est) est.textContent = 'Agregá productos al carrito';
        } else if (Math.abs(dif) < 0.01 && cobroState.lineas.length) {
            pagoResumenEl.classList.add('vdt-pago-cierre--ok');
            if (est) est.textContent = '✓ Pago cubierto';
        } else if (dif > 0.01) {
            pagoResumenEl.classList.add('vdt-pago-cierre--pendiente');
            if (est) est.textContent = `Falta ${_fmtPeso(dif)}`;
        } else {
            pagoResumenEl.classList.add('vdt-pago-cierre--exceso');
            if (est) est.textContent = `Sobra ${_fmtPeso(-dif)}`;
        }
    }
    const intEl = document.getElementById('cmpPagoInteres');
    if (intEl) {
        if (interes > 0.01) {
            intEl.hidden = false;
            intEl.innerHTML = `+ <strong>${_fmtPeso(interes)}</strong> de interés · Total a pagar <strong>${_fmtPeso(total + interes)}</strong>`;
        } else {
            intEl.hidden = true;
        }
    }
}

function _pagoAgregar() {
    // Con más de un medio, el reparto es manual: la 1ra línea deja de
    // seguir al total sola.
    cobroState.lineas.forEach(l => { l.autofill = false; });
    const { total } = _ivaTotales();
    const asignado = cobroState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
    const restante = _round2(Math.max(0, total - asignado));
    const l = { id: cobroState.nextId++, medio: 'efectivo', monto: restante, autofill: false,
                cuenta: '', cotizacion: '', modoCuotas: 'fijas', cuotas: '', interesPct: '', fechaInicioDebito: '' };
    const e = _cuentaEfectivo();
    l.cuenta = e ? String(e.pk) : '';
    cobroState.lineas.push(l);
    _pagoRenderLineas();
}

function _pagoCubierto() {
    const { total } = _ivaTotales();
    const asignado = cobroState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
    return cobroState.lineas.length > 0 && Math.abs(total - asignado) < 0.01;
}

function _pagoFaltanDatos() {
    return cobroState.lineas.some(l => {
        if (!l.cuenta) return true;
        const info = _cuentaInfo(l.cuenta);
        if (info && info.moneda !== 'ARS' && !(parseFloat(l.cotizacion) > 0)) return true;
        if (_usaPlanCuotas(l) && l.modoCuotas !== 'libre') {
            if (!(parseInt(l.cuotas, 10) >= 1)) return true;
            if (!l.fechaInicioDebito) return true;
        }
        return false;
    });
}

function _getPagoPayload() {
    return cobroState.lineas.filter(l => (parseFloat(l.monto) || 0) > 0).map(l => {
        const base = { medio: l.medio, monto: parseFloat(l.monto) || 0,
                       cuenta_pk: l.cuenta || null, cotizacion: l.cotizacion || null };
        if (_usaPlanCuotas(l)) {
            base.modo_cuotas = l.modoCuotas === 'libre' ? 'libre' : 'fijas';
            base.cuotas = l.modoCuotas === 'libre' ? null : (parseInt(l.cuotas, 10) || null);
            base.interes_pct = (l.interesPct === '' || l.interesPct == null) ? 0 : parseFloat(l.interesPct);
            base.fecha_inicio_debito = l.modoCuotas === 'libre' ? null : (l.fechaInicioDebito || null);
        }
        return base;
    });
}

/* Atajos 1..6 → medio de la última línea de pago (si el foco no está en un campo). */
document.addEventListener('keydown', e => {
    if (_confirmada || e.key < '1' || e.key > '6') return;
    const a = document.activeElement;
    if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable)) return;
    if (!cobroState.lineas.length) return;
    const l = cobroState.lineas[cobroState.lineas.length - 1];
    const m = _MEDIOS[parseInt(e.key, 10) - 1];
    if (m && l.medio !== m.v) { e.preventDefault(); _aplicarMedio(l, m.v); }
});

/* ════════════════════════════════════════════════════════════════
   ESTADO DEL BOTÓN "CONFIRMAR COMPRA"
════════════════════════════════════════════════════════════════ */
function _actualizarEstadoConfirmar() {
    const dot = document.getElementById('cmpPagoDot');
    const cartOk  = carrito.length > 0;
    const vencOk  = !carrito.some(i => i.es_perecedero && !i.fecha_vencimiento);
    const fechaOk = !!(inFecha && inFecha.value);
    const pagoOk  = _pagoCubierto() && !_pagoFaltanDatos();
    if (dot) dot.classList.toggle('cdt-tab-dot--ok', pagoOk);
    if (btnConfirmar) btnConfirmar.disabled = _confirmada || !(cartOk && vencOk && fechaOk && pagoOk);
    if (panelHint) {
        panelHint.textContent = _confirmada ? 'confirmada'
            : !cartOk ? 'carrito vacío'
            : !vencOk ? 'falta vencimiento'
            : !fechaOk ? 'falta la fecha'
            : !pagoOk ? 'falta completar el pago'
            : 'listo para confirmar';
    }
}

/* ════════════════════════════════════════════════════════════════
   CONFIRMAR — guarda el borrador y lo confirma (2 requests), muestra
   el estado "confirmada" en el mismo panel (como Nueva Venta).
════════════════════════════════════════════════════════════════ */
function _itemsPayload() {
    return carrito.map(item => ({
        producto_pk:       item.producto_pk,
        proveedor_pk:      compraProveedor.pk || null,
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
}

async function _post(url, body) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
        body: JSON.stringify(body),
    });
    return res.json();
}

function _confirmarBtnLoading(on) {
    if (!btnConfirmar) return;
    btnConfirmar.disabled = on;
    btnConfirmar.innerHTML = on
        ? `<svg class="cmp-spin" width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/></svg> Confirmando…`
        : `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg> Confirmar compra`;
}

if (btnConfirmar) {
    btnConfirmar.addEventListener('click', async () => {
        if (_confirmada) return;
        if (!carrito.length) { _toast('Carrito vacío', 'Agregá al menos un producto.'); return; }
        const sinVenc = carrito.filter(i => i.es_perecedero && !i.fecha_vencimiento);
        if (sinVenc.length) {
            _toast('Falta la fecha de vencimiento', `Perecederos sin fecha: ${sinVenc.map(i => i.nombre).join(', ')}`);
            return;
        }
        if (!inFecha.value) { _toast('Fecha requerida', 'Ingresá la fecha del comprobante.'); return; }
        if (!_pagoCubierto()) {
            const { total } = _ivaTotales();
            const asignado = cobroState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
            _toast('Pago incompleto', cobroState.lineas.length ? `Falta cubrir ${_fmtPeso(total - asignado)}.` : 'Agregá un medio de pago.');
            return;
        }
        if (_pagoFaltanDatos()) {
            _toast('Datos del pago incompletos', 'Elegí la cuenta de cada línea (y cuotas/fecha si es crédito o cheque).');
            return;
        }

        _confirmarBtnLoading(true);

        const items = _itemsPayload();
        const guardarUrl  = _borradorPk ? CFG.urlActualizarBorrador : CFG.urlGuardarBorrador;
        const guardarBody = _borradorPk ? { compra_pk: _borradorPk, items } : { items, fecha: inFecha.value };
        let data;
        try {
            data = await _post(guardarUrl, guardarBody);
        } catch { _toast('Error de conexión', 'Intentá de nuevo.'); _confirmarBtnLoading(false); return; }
        if (!data.ok) { _toast('No se pudo guardar', data.error || 'Revisá los ítems.'); _confirmarBtnLoading(false); return; }
        _borradorPk = _borradorPk || data.pk;

        const confirmBody = {
            compra_pk: _borradorPk,
            fecha: inFecha.value,
            notas: inNotas ? inNotas.value.trim() : '',
            numero_comprobante: inNumComp ? inNumComp.value.trim() : '',
            tipo_documento: inTipoDoc.value,
            alicuota_iva: inTipoDoc.value === 'factura' ? inAlicuota.value : '',
            iva_incluido: inIvaIncluido.checked,
            proveedor_pk: compraProveedor.pk || null,
            pagos: _getPagoPayload(),
        };
        try {
            data = await _post(CFG.urlConfirmar, confirmBody);
        } catch { _toast('Error de conexión', 'La compra quedó como borrador — reintentá.'); _confirmarBtnLoading(false); return; }
        if (!data.ok) { _toast('No se pudo confirmar', data.error || 'Revisá el pago.'); _confirmarBtnLoading(false); return; }

        if (data.deuda_cheque_pk) {
            window.location.href = `${CFG.urlDeudas}?ver=${data.deuda_cheque_pk}`;
            return;
        }
        _mostrarConfirmada(data);
    });
}

function _mostrarConfirmada(data) {
    _confirmada = true;
    if (searchInput) searchInput.disabled = true;
    if (cobroForm) cobroForm.hidden = true;
    if (!cobroConfirmada) return;
    cobroConfirmada.hidden = false;
    cobroConfirmada.innerHTML = `
        <div class="cmp-confirmada">
            <div class="cmp-confirmada-ic">
                <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
                    <circle cx="13" cy="13" r="11" stroke="currentColor" stroke-width="1.6"/>
                    <path d="M8 13.5L11.5 17L18 9.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <div class="cmp-confirmada-tit">Compra confirmada</div>
            <div class="cmp-confirmada-num">${_esc(data.numero || '')}</div>
            <div class="cmp-confirmada-total">Total <strong>${_fmtPeso(data.total)}</strong></div>
            <div class="cmp-confirmada-actions">
                <a class="vta-btn vta-btn-primary" href="${CFG.urlNuevaCompra}">Nueva compra</a>
                <a class="vta-btn vta-btn-ghost" href="${CFG.urlDetalle}${data.pk}/">Ver detalle · adjuntar factura</a>
            </div>
        </div>`;
    _actualizarEstadoConfirmar();
}

if (btnCancelar) {
    btnCancelar.addEventListener('click', async () => {
        const hayAlgo = carrito.length || _borradorPk;
        if (hayAlgo && window.KaiConfirm) {
            const ok = await KaiConfirm(
                CFG.editingPk
                    ? '¿Cancelar la edición? La compra vuelve a quedar anulada, tal como estaba.'
                    : '¿Cancelar la compra? Se pierde lo cargado.',
                { danger: true, confirmText: 'Cancelar compra' });
            if (!ok) return;
        }
        if (_borradorPk) {
            try { await _post(CFG.urlEliminarBorrador, { compra_pk: _borradorPk }); }
            catch { /* el barrido de borradores vencidos lo limpia igual */ }
        }
        window.location.href = CFG.editingPk ? CFG.urlHistorial : CFG.urlNuevaCompra;
    });
}

/* ════════════════════════════════════════════════════════════════
   INIT
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

// Prefill del panel (modo ?editar=<pk>).
const _pref = CFG.editPrefill;
if (_pref) {
    if (_pref.proveedor_pk) compraProveedor = { pk: String(_pref.proveedor_pk), nombre: _pref.proveedor_nombre || '' };
    if (_pref.fecha && inFecha) inFecha.value = _pref.fecha;
    if (_pref.tipo_documento && inTipoDoc) inTipoDoc.value = _pref.tipo_documento;
    if (_pref.alicuota_iva && inAlicuota) inAlicuota.value = _pref.alicuota_iva;
    if (inIvaIncluido) inIvaIncluido.checked = _pref.iva_incluido !== false;
    if (_pref.numero_comprobante && inNumComp) inNumComp.value = _pref.numero_comprobante;
    if (_pref.notas && inNotas) inNotas.value = _pref.notas;
}
_sincronizarProveedorEnCarrito();

// Línea de pago inicial: total completo, efectivo (o cuenta principal).
(function _pagoInit() {
    const l = { id: cobroState.nextId++, medio: 'efectivo', monto: 0, autofill: true,
                cuenta: '', cotizacion: '', modoCuotas: 'fijas', cuotas: '', interesPct: '', fechaInicioDebito: '' };
    const e = _cuentaEfectivo();
    l.cuenta = e ? String(e.pk) : '';
    cobroState.lineas.push(l);
})();

[inTipoDoc, inAlicuota].forEach(el => { if (el) el.addEventListener('change', _recalcularPanel); });
if (inIvaIncluido) inIvaIncluido.addEventListener('change', _recalcularPanel);
if (inFecha) inFecha.addEventListener('input', _actualizarEstadoConfirmar);
const pagoAdd = document.getElementById('cmpPagoAdd');
if (pagoAdd) pagoAdd.addEventListener('click', _pagoAgregar);

_bindProveedorPanel();
_renderCarrito();
_actualizarTotales();
_pagoRenderLineas();
if (searchInput) searchInput.focus();