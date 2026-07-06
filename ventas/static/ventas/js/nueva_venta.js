/**
 * nueva_venta.js
 *
 * Carrito de filas planas: una fila por producto (o por producto+variante
 * puntual). Cada escaneo/selección ya identifica exactamente qué se
 * vende, así que simplemente suma cantidad — como pasar mercadería por
 * el lector en una caja de supermercado.
 *
 * Origen del stock:
 *   - tipo_escaneo NORMAL          → se resuelve el lote más VIEJO con
 *     stock (FIFO) recién al confirmar la venta.
 *   - tipo_escaneo LOTE_ESPECIFICO → se escaneó el código de lote
 *     puntual (LT-AAAA-XXXXX); ese lote queda fijo para esa fila.
 *
 * Caso borde: un código de barras a nivel producto que no identifica
 * una variante puntual (tipo_resultado='producto_con_variantes'). Si
 * el producto tiene una sola variante activa, se resuelve sola. Si
 * tiene más de una, se muestra el mismo desplegable de la búsqueda
 * manual para que el usuario elija cuál.
 *
 * Requiere window.VTA_CONFIG con:
 *   urlBuscarProducto, urlBuscarCliente, urlBuscarLote,
 *   urlGuardarBorrador, urlDetalle, csrfToken
 */
'use strict';

const CFG = window.VTA_CONFIG || {};
const LOTE_REGEX = /^LT-\d{4}-\d{5}$/i;

/* ════════════════════════════════════════════════════════════════
   ESTADO
════════════════════════════════════════════════════════════════ */
let nextId  = 0;
let carrito = (CFG.itemsIniciales || []).map(fila => ({
    id:              nextId++,
    producto_pk:     fila.producto_pk,
    combinacion_pk:  fila.combinacion_pk || null,
    nombre:          fila.nombre,
    codigo:          fila.codigo,
    tipo_escaneo:    fila.tipo_escaneo || 'normal',
    lote_pk:         fila.lote_pk || null,
    lote_codigo:     fila.lote_codigo || '',
    cliente_pk:      fila.cliente_pk || null,
    cliente_nombre:  fila.cliente_nombre || '',
    cantidad:        fila.cantidad,
    precio:          fila.precio,
    moneda:          fila.moneda || 'ARS',
    descuento:       fila.descuento || 0,
    condicion:       fila.condicion || 'contado',
    referencia:      fila.referencia || '',
}));

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

if (searchInput) {

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
    const base = (parseFloat(item.cantidad) || 0) * (parseFloat(item.precio) || 0);
    return item.descuento ? base * (1 - parseFloat(item.descuento) / 100) : base;
}
function _toast(titulo, cuerpo) {
    const toast = document.getElementById('vtaToast');
    document.getElementById('vtaToastTitle').textContent = titulo;
    document.getElementById('vtaToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

/* ════════════════════════════════════════════════════════════════
   RENDER DE UNA LISTA DE OPCIONES EN EL DESPLEGABLE
   (se usa tanto para resultados de búsqueda por texto como para
   desambiguar un producto con variantes que no vino resuelto)
════════════════════════════════════════════════════════════════ */
function _renderOpciones(filas, { vacioTexto = 'Sin resultados' } = {}) {
    if (!filas.length) {
        searchDropdown.innerHTML = `<div class="vta-dropdown-empty">${_esc(vacioTexto)}</div>`;
        searchDropdown.classList.add('open');
        return;
    }

    searchDropdown.innerHTML = filas.map((r, idx) => `
        <div class="vta-dropdown-item" data-idx="${idx}">
            <div class="vta-dropdown-item-top">
                <span class="vta-dropdown-item-nombre">${_esc(r.nombre)}</span>
                <span class="vta-dropdown-item-codigo">${_esc(r.codigo)}</span>
            </div>
            <div class="vta-dropdown-item-meta">
                <span class="vta-meta-chip vta-meta-chip--stock${parseFloat(r.stock_actual || 0) <= 0 ? ' bajo' : ''}">
                    Stock <strong>${parseFloat(r.stock_actual || 0).toLocaleString('es-AR')}</strong>
                </span>
                ${r.precio_venta != null
                    ? `<span class="vta-meta-chip vta-meta-chip--precio">Precio <strong>${_fmt(r.precio_venta, r.moneda)}</strong></span>`
                    : `<span class="vta-meta-chip--sin-precio">Sin precio cargado</span>`}
                ${r.variante_desc ? `<span class="vta-meta-chip vta-meta-chip--colores"><strong>${_esc(r.variante_desc)}</strong></span>` : ''}
            </div>
        </div>`
    ).join('');

    searchDropdown.querySelectorAll('.vta-dropdown-item[data-idx]').forEach(el => {
        el.addEventListener('click', () => {
            const fila = filas[parseInt(el.dataset.idx, 10)];
            if (fila) _agregarResultado(fila);
            searchDropdown.classList.remove('open');
            searchDropdown.innerHTML = '';
            searchInput.value = '';
        });
    });
    searchDropdown.classList.add('open');
}

/* ════════════════════════════════════════════════════════════════
   BUSCADOR / ESCÁNER — decide entre lote y producto
════════════════════════════════════════════════════════════════ */
let searchTimer;

async function _buscarPorCodigoDeLote(codigo) {
    try {
        const res  = await fetch(`${CFG.urlBuscarLote}?codigo=${encodeURIComponent(codigo)}`);
        const data = await res.json();

        if (data.error) {
            searchDropdown.innerHTML = `<div class="vta-dropdown-empty">${_esc(data.error)}</div>`;
            searchDropdown.classList.add('open');
            return;
        }
        const fila = (data.results || [])[0];
        if (fila) {
            _agregarResultado(fila);
            searchDropdown.classList.remove('open');
            searchDropdown.innerHTML = '';
            searchInput.value = '';
        }
    } catch {
        _toast('Error de conexión', 'No se pudo buscar el lote. Intentá de nuevo.');
    }
}

async function _ejecutarBusqueda(q, { forzarAgregado = false } = {}) {
    if (!q) {
        searchDropdown.classList.remove('open');
        searchDropdown.innerHTML = '';
        return;
    }

    if (LOTE_REGEX.test(q)) {
        await _buscarPorCodigoDeLote(q);
        return;
    }

    try {
        const res     = await fetch(`${CFG.urlBuscarProducto}?q=${encodeURIComponent(q)}`);
        const data    = await res.json();
        const results = data.results || [];

        const debeAgregarDirecto =
            (results.length === 1 && results[0].match_exacto) ||
            (forzarAgregado && results.length === 1);

        if (debeAgregarDirecto) {
            _agregarResultado(results[0]);
            searchDropdown.classList.remove('open');
            searchDropdown.innerHTML = '';
            searchInput.value = '';
            return;
        }

        _renderOpciones(results, {
            vacioTexto: forzarAgregado ? 'No se encontró ningún producto con ese código.' : 'Sin resultados',
        });
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
        e.preventDefault();
        clearTimeout(searchTimer);
        const q = searchInput.value.trim();
        if (q) _ejecutarBusqueda(q, { forzarAgregado: true });
    }
});

document.addEventListener('click', e => {
    if (!searchDropdown.contains(e.target) && e.target !== searchInput) {
        searchDropdown.classList.remove('open');
    }
    document.querySelectorAll('.vta-cli-dropdown.open').forEach(dd => {
        if (!dd.contains(e.target) && dd.previousElementSibling !== e.target) {
            dd.classList.remove('open');
        }
    });
});

/* ════════════════════════════════════════════════════════════════
   AGREGAR RESULTADO AL CARRITO
════════════════════════════════════════════════════════════════ */
function _agregarResultado(fila) {
    // Código de producto ambiguo (compartido por varias variantes):
    // si solo hay una variante activa, se resuelve sola; si hay más
    // de una, mostramos las opciones para que el usuario elija —
    // igual que en una búsqueda manual.
    if (fila.tipo_resultado === 'producto_con_variantes') {
        const combos = fila.combinaciones || [];
        if (combos.length === 1) {
            _agregarFila({
                ...fila,
                tipo_resultado: 'variante',
                combinacion_pk: combos[0].combinacion_pk,
                variante_desc:  combos[0].nombre,
                stock_actual:   combos[0].stock_actual,
            });
        } else if (combos.length > 1) {
            _toast('Elegí la variante', `"${fila.nombre}" tiene varias variantes activas — elegí cuál vendés.`);
            _renderOpciones(combos.map(c => ({
                ...fila,
                tipo_resultado: 'variante',
                combinacion_pk: c.combinacion_pk,
                variante_desc:  c.nombre,
                nombre:         `${fila.nombre} — ${c.nombre}`,
                stock_actual:   c.stock_actual,
            })));
        } else {
            _toast('Sin variantes activas', `"${fila.nombre}" no tiene ninguna variante activa cargada.`);
        }
        return;
    }

    _agregarFila(fila);
}

function _agregarFila(fila) {
    const existente = carrito.find(i =>
        i.producto_pk === fila.pk &&
        i.combinacion_pk === (fila.combinacion_pk || null) &&
        i.tipo_escaneo === (fila.tipo_escaneo || 'normal') &&
        i.lote_pk === (fila.lote_pk || null)
    );

    if (existente) {
        existente.cantidad = (parseFloat(existente.cantidad) || 0) + 1;
        _renderCarrito();
        return;
    }

    carrito.push({
        id:              nextId++,
        producto_pk:     fila.pk,
        combinacion_pk:  fila.combinacion_pk || null,
        nombre:          fila.nombre,
        codigo:          fila.codigo,
        tipo_escaneo:    fila.tipo_escaneo || 'normal',
        lote_pk:         fila.lote_pk || null,
        lote_codigo:     fila.lote_codigo || '',
        cliente_pk:      null,
        cliente_nombre:  '',
        cantidad:        1,
        precio:          fila.precio_venta ?? '',
        moneda:          fila.moneda || 'ARS',
        descuento:       0,
        condicion:       'contado',
        referencia:      '',
    });
    _renderCarrito();
}

function _quitarItem(id) {
    carrito = carrito.filter(i => i.id !== id);
    _renderCarrito();
}

/* ════════════════════════════════════════════════════════════════
   AUTOCOMPLETE DE CLIENTE POR ÍTEM
════════════════════════════════════════════════════════════════ */
let clienteSearchTimer;

function _bindClienteInput(inputEl, itemId) {
    const item = carrito.find(i => i.id === itemId);
    if (!item) return;
    const dropdown = inputEl.nextElementSibling;

    inputEl.addEventListener('input', () => {
        clearTimeout(clienteSearchTimer);
        const q = inputEl.value.trim();
        item.cliente_pk = null;

        if (!q) {
            dropdown.classList.remove('open');
            dropdown.innerHTML = '';
            return;
        }
        clienteSearchTimer = setTimeout(async () => {
            try {
                const res  = await fetch(`${CFG.urlBuscarCliente}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                const results = data.results || [];

                dropdown.innerHTML = results.length
                    ? results.map(c => `
                        <div class="vta-cli-option" data-pk="${c.pk}" data-nombre="${_esc(c.nombre)}">
                            <div class="vta-cli-option-nombre">${_esc(c.nombre)}</div>
                            ${c.telefono || c.email ? `<div class="vta-cli-option-meta">${_esc(c.telefono || c.email)}</div>` : ''}
                        </div>`).join('')
                    : '<div class="vta-dropdown-empty">Sin resultados</div>';

                dropdown.querySelectorAll('.vta-cli-option').forEach(el => {
                    el.addEventListener('click', () => {
                        item.cliente_pk     = parseInt(el.dataset.pk, 10);
                        item.cliente_nombre = el.dataset.nombre;
                        inputEl.value = el.dataset.nombre;
                        dropdown.classList.remove('open');
                        dropdown.innerHTML = '';
                    });
                });
                dropdown.classList.add('open');
            } catch { /* silencioso */ }
        }, 260);
    });
}

/* ════════════════════════════════════════════════════════════════
   RENDER DEL CARRITO
════════════════════════════════════════════════════════════════ */
function _chipOrigen(item) {
    if (item.tipo_escaneo === 'lote_especifico') {
        return `<span class="vta-origen-chip vta-origen-chip--lote" title="Descuenta específicamente de este lote">Lote ${_esc(item.lote_codigo)}</span>`;
    }
    return `<span class="vta-origen-chip vta-origen-chip--normal" title="Descuenta del lote más viejo con stock (FIFO)">Más viejo (FIFO)</span>`;
}

function _renderCarrito() {
    if (!carrito.length) {
        cartBody.innerHTML = '';
        cartEmpty.style.display  = 'flex';
        cartFooter.style.display = 'none';
        _actualizarBtnContinuar();
        return;
    }
    cartEmpty.style.display  = 'none';
    cartFooter.style.display = 'flex';

    cartBody.innerHTML = carrito.map(item => `
        <tr data-item-id="${item.id}">
            <td>
                <div class="vta-prod-cell">
                    <span class="vta-prod-nombre">${_esc(item.nombre)}</span>
                    <span class="vta-prod-meta">${_esc(item.codigo)}</span>
                </div>
            </td>
            <td>${_chipOrigen(item)}</td>
            <td><input type="number" min="0.001" step="0.001" class="vta-input-inline w-sm"
                       data-item-id="${item.id}" data-campo="cantidad" value="${item.cantidad}"></td>
            <td><input type="number" min="0" step="0.01" class="vta-input-inline w-sm"
                       data-item-id="${item.id}" data-campo="precio" value="${item.precio}"></td>
            <td>
                <select class="vta-select-inline" data-item-id="${item.id}" data-campo="moneda">
                    <option value="ARS" ${item.moneda === 'ARS' ? 'selected' : ''}>ARS</option>
                    <option value="USD" ${item.moneda === 'USD' ? 'selected' : ''}>USD</option>
                    <option value="EUR" ${item.moneda === 'EUR' ? 'selected' : ''}>EUR</option>
                </select>
            </td>
            <td><input type="number" min="0" max="100" step="0.01" class="vta-input-inline w-xs"
                       data-item-id="${item.id}" data-campo="descuento" value="${item.descuento}"></td>
            <td>
                <select class="vta-select-inline" data-item-id="${item.id}" data-campo="condicion">
                    <option value="contado" ${item.condicion === 'contado' ? 'selected' : ''}>Contado</option>
                    <option value="cuenta_corriente" ${item.condicion === 'cuenta_corriente' ? 'selected' : ''}>Cta. cte.</option>
                    <option value="tarjeta" ${item.condicion === 'tarjeta' ? 'selected' : ''}>Tarjeta</option>
                </select>
            </td>
            <td class="vta-cli-wrap">
                <input type="text" class="vta-input-inline vta-cli-input" data-item-id="${item.id}"
                       placeholder="Consumidor final" value="${_esc(item.cliente_nombre)}" autocomplete="off">
                <div class="vta-cli-dropdown"></div>
            </td>
            <td><input type="text" class="vta-input-inline w-md" data-item-id="${item.id}" data-campo="referencia" value="${_esc(item.referencia)}"></td>
            <td class="vta-subtotal-cell">${_fmt(_calcSub(item), item.moneda)}</td>
            <td><button class="vta-btn-remove" data-item-id="${item.id}" title="Quitar">✕</button></td>
        </tr>`
    ).join('');

    cartBody.querySelectorAll('.vta-input-inline[data-campo], .vta-select-inline[data-campo]').forEach(el => {
        const ev = el.tagName === 'SELECT' ? 'change' : 'input';
        el.addEventListener(ev, () => _onCampoCambiado(el));
    });
    cartBody.querySelectorAll('.vta-cli-input').forEach(el => {
        _bindClienteInput(el, parseInt(el.dataset.itemId, 10));
    });
    cartBody.querySelectorAll('.vta-btn-remove').forEach(el => {
        el.addEventListener('click', () => _quitarItem(parseInt(el.dataset.itemId, 10)));
    });

    _actualizarTotales();
    _actualizarBtnContinuar();
}

function _onCampoCambiado(el) {
    const id    = parseInt(el.dataset.itemId, 10);
    const campo = el.dataset.campo;
    const item  = carrito.find(i => i.id === id);
    if (!item) return;
    item[campo] = el.value;

    const fila = cartBody.querySelector(`tr[data-item-id="${id}"]`);
    if (fila) {
        const sub = fila.querySelector('.vta-subtotal-cell');
        if (sub) sub.textContent = _fmt(_calcSub(item), item.moneda);
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
    if (badge) { badge.textContent = carrito.length; badge.style.display = carrito.length ? 'inline-flex' : 'none'; }
}
function _actualizarBtnContinuar() {
    if (btnContinuar) btnContinuar.disabled = carrito.length === 0;
}

/* ════════════════════════════════════════════════════════════════
   GUARDAR BORRADOR Y NAVEGAR AL DETALLE
════════════════════════════════════════════════════════════════ */
if (btnContinuar) {
    btnContinuar.addEventListener('click', async () => {
        if (!carrito.length) return;

        btnContinuar.disabled  = true;
        btnContinuar.textContent = 'Guardando…';

        const itemsPayload = carrito.map(item => ({
            producto_pk:     item.producto_pk,
            cliente_pk:      item.cliente_pk || null,
            combinacion_pk:  item.combinacion_pk || null,
            tipo_escaneo:    item.tipo_escaneo,
            lote_pk:         item.lote_pk || null,
            cantidad:        item.cantidad,
            precio_unitario: item.precio,
            moneda:          item.moneda,
            descuento_pct:   item.descuento,
            condicion_pago:  item.condicion,
            referencia:      item.referencia,
        }));

        try {
            const res  = await fetch(CFG.urlGuardarBorrador, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                body:    JSON.stringify({ items: itemsPayload }),
            });
            const data = await res.json();

            if (data.ok) {
                if (CFG.ventaEditarPk) {
                    // Best-effort: no bloquea la redirección si falla.
                    fetch(CFG.urlEliminarBorrador, {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                        body:    JSON.stringify({ venta_pk: CFG.ventaEditarPk }),
                    }).catch(() => {});
                }
                window.location.href = CFG.urlDetalle + data.pk + '/';
            } else {
                _toast('Error al guardar', data.error || 'No se pudo guardar el borrador.');
                btnContinuar.disabled  = false;
                btnContinuar.innerHTML = 'Continuar al detalle';
            }
        } catch {
            _toast('Error de conexión', 'Intentá de nuevo.');
            btnContinuar.disabled  = false;
            btnContinuar.innerHTML = 'Continuar al detalle';
        }
    });
}

/* ════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */
_renderCarrito();
searchInput.focus();

} // if (searchInput)