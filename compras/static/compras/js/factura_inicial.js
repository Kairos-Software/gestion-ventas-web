/**
 * factura_inicial.js
 * ─────────────────────────────────────────────────────────────────
 * Carrito de la herramienta "Factura inicial": los MISMOS datos que
 * un carrito de Compras normal (proveedor, ítems, tipo de comprobante
 * con letra A/B/C, alícuota, medios de pago con cuotas/cheque) pero
 * con el DISEÑO de la columna de cobro de Nueva Venta — panel anclado
 * a la derecha, botonera de medios de pago (.vdt-medio-tab), bloque de
 * cierre con el total (.vdt-pago-cierre).
 *
 * La forma de pago es SOLO informativa — no crea PagoCompra, ni Deuda,
 * ni movimiento de caja.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

const CFG = window.FI_CONFIG || {};
const $ = id => document.getElementById(id);

/* ════════════════════════════════════════════════════════════════
   ESTADO
════════════════════════════════════════════════════════════════ */
let carrito = [];
let nextId = 0;
let _lastResults = [];
let provPk = '';
let provNombre = '';
let _pagoLineas = [];     // [{ medio, monto, cuotas, interes_pct, banco, numero_cheque, fecha, detalle }]
let _confirmada = false;

/* Ventana del carrito — en cargas de cientos de ítems no renderizamos
   todo de una: se muestran los primeros N (el ítem recién agregado entra
   arriba de todo) y el resto queda detrás de "Mostrar más" o del filtro. */
const FI_CARRITO_LIMITE = 10;   // filas visibles antes de "Mostrar más"
const FI_FILTRO_DESDE   = 10;   // a partir de cuántos ítems aparece el filtro
let _carritoLimite = FI_CARRITO_LIMITE;
let _carritoVerTodo = false;
let _carritoFiltro = '';

/* Íconos de cada medio de pago para la botonera — mismo lenguaje que
   detalle_venta.js (Nueva Venta). */
const FI_MEDIO_ICONOS = {
    efectivo:      '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="2" y="5" width="16" height="10" rx="1.5" stroke="currentColor" stroke-width="1.4"/><circle cx="10" cy="10" r="2.2" stroke="currentColor" stroke-width="1.4"/></svg>',
    transferencia: '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 7.5h10M11 4.5l3 3-3 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 12.5H6M9 15.5l-3-3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    debito:        '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="2.5" y="4.5" width="15" height="11" rx="1.8" stroke="currentColor" stroke-width="1.4"/><path d="M2.5 8.5h15" stroke="currentColor" stroke-width="1.4"/></svg>',
    qr:            '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="3" y="3" width="6" height="6" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="11" y="3" width="6" height="6" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="3" y="11" width="6" height="6" rx="1" stroke="currentColor" stroke-width="1.4"/><path d="M11 11h3v3M17 11.5V17h-5.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    credito:       '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="2.5" y="4.5" width="15" height="11" rx="1.8" stroke="currentColor" stroke-width="1.4"/><path d="M2.5 8.5h15" stroke="currentColor" stroke-width="1.4"/><path d="M5 12h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    cheque:        '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="3" y="3.5" width="14" height="13" rx="1.6" stroke="currentColor" stroke-width="1.4"/><path d="M6 8h8M6 11h8M6 14h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
};
const FI_MEDIO_LABEL_CORTO = { transferencia: 'Transf.', credito: 'Crédito' };

/* ════════════════════════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════════════════════════ */
function _esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function _fmt(v) {
    return '$ ' + (parseFloat(v) || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
}
function _num(v) { return parseFloat(v) || 0; }
function _calcBase(i) { return _num(i.cantidad) * _num(i.costo); }
function _calcSub(i) {
    const b = _calcBase(i);
    return i.descuento ? b * (1 - _num(i.descuento) / 100) : b;
}
function _modoIva() {
    const opt = $('fiTipoComprobante').selectedOptions[0];
    return (opt && opt.dataset.modoIva) || 'discriminado';
}

/* ════════════════════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════════════════════ */
let _toastTimer;
function _toast(t, b) {
    $('fiToastTitle').textContent = t;
    $('fiToastBody').textContent = b || '';
    const el = $('fiToast');
    el.classList.add('show');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}

/* ════════════════════════════════════════════════════════════════
   BUSCADOR DE PRODUCTOS
════════════════════════════════════════════════════════════════ */
let searchTimer;
const searchInput = $('fiSearchInput');
const searchDropdown = $('fiSearchDropdown');
const cartBody = $('fiCartBody');
const cartEmpty = $('fiCartEmpty');
const cartCount = $('fiCartCount');
const cartFilter = $('fiCartFilter');
const cartFilterInput = $('fiCartFilterInput');
const cartFilterClear = $('fiCartFilterClear');
const cartMore = $('fiCartMore');
const badge = $('fiBadge');
const btnPdf = $('fiBtnPdf');
const btnImprimir = $('fiBtnImprimir');

async function _buscar(q, { forzar = false } = {}) {
    if (!q) { searchDropdown.classList.remove('open'); searchDropdown.innerHTML = ''; return; }
    try {
        const res = await fetch(`${CFG.urlBuscarProducto}?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        const results = data.results || [];
        _lastResults = results;
        const directo = (results.length === 1 && results[0].match_exacto) || (forzar && results.length === 1);
        if (directo) {
            _agregarItem(results[0]);
            searchDropdown.classList.remove('open'); searchDropdown.innerHTML = ''; searchInput.value = '';
            return;
        }
        if (!results.length) {
            searchDropdown.innerHTML = '<div class="vta-dropdown-empty">Sin resultados</div>';
        } else {
            searchDropdown.innerHTML = results.map((r, i) => `
                <div class="vta-dropdown-item" data-idx="${i}">
                    <div class="vta-dropdown-item-top">
                        <span class="vta-dropdown-item-nombre">${_esc(r.producto_nombre)}</span>
                        <span class="vta-dropdown-item-codigo">${_esc(r.codigo)}</span>
                    </div>
                    <div class="vta-dropdown-item-meta">
                        <span>Stock: <strong>${_num(r.stock_actual).toLocaleString('es-AR')}</strong></span>
                        ${r.variante_desc ? `<span>· ${_esc(r.variante_desc)}</span>` : ''}
                        ${r.costo_actual ? `<span>· Últ. costo: <strong>${_fmt(r.costo_actual)}</strong></span>` : ''}
                    </div>
                </div>`).join('');
            searchDropdown.querySelectorAll('.vta-dropdown-item[data-idx]').forEach(el => {
                el.addEventListener('click', () => {
                    const fila = _lastResults[parseInt(el.dataset.idx, 10)];
                    if (fila) _agregarItem(fila);
                    searchDropdown.classList.remove('open'); searchDropdown.innerHTML = '';
                    searchInput.value = ''; searchInput.focus();
                });
            });
        }
        searchDropdown.classList.add('open');
    } catch { searchDropdown.classList.remove('open'); }
}

searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    if (!q) { searchDropdown.classList.remove('open'); searchDropdown.innerHTML = ''; return; }
    searchTimer = setTimeout(() => _buscar(q), 260);
});
searchInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') { searchDropdown.classList.remove('open'); searchInput.value = ''; return; }
    if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(searchTimer);
        const q = searchInput.value.trim();
        if (q) _buscar(q, { forzar: true });
    }
});
document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) searchDropdown.classList.remove('open');
});

/* ── Filtro de ítems ya agregados (para cargas largas) ── */
function _filtroLimpiar() {
    _carritoFiltro = '';
    if (cartFilterInput) cartFilterInput.value = '';
    if (cartFilterClear) cartFilterClear.hidden = true;
}
if (cartFilterInput) {
    cartFilterInput.addEventListener('input', () => {
        _carritoFiltro = cartFilterInput.value;
        if (cartFilterClear) cartFilterClear.hidden = !cartFilterInput.value;
        _render();
    });
}
if (cartFilterClear) {
    cartFilterClear.addEventListener('click', () => {
        _filtroLimpiar();
        _render();
        if (cartFilterInput) cartFilterInput.focus();
    });
}

/* ════════════════════════════════════════════════════════════════
   CARRITO
════════════════════════════════════════════════════════════════ */
function _agregarItem(fila) {
    _filtroLimpiar();   // que el ítem que se agrega quede siempre a la vista
    const idx = carrito.findIndex(i =>
        String(i.producto_pk) === String(fila.producto_pk) &&
        (i.combinacion_pk || null) === (fila.combinacion_pk || null));
    if (idx !== -1) {
        const ex = carrito[idx];
        ex.cantidad = _num(ex.cantidad) + 1;
        carrito.splice(idx, 1);
        carrito.unshift(ex);          // se mueve arriba de todo
        _render();
        _toast('Cantidad actualizada', fila.nombre);
        return;
    }
    carrito.unshift({
        id: nextId++,
        producto_pk: fila.producto_pk,
        combinacion_pk: fila.combinacion_pk || null,
        producto_nombre: fila.producto_nombre,
        variante_desc: fila.variante_desc || '',
        codigo: fila.codigo || '',
        unidad: fila.unidad_medida || '',
        es_perecedero: !!fila.es_perecedero,
        cantidad: 1,
        costo: _num(fila.costo_actual),
        descuento: 0,
        lista_descuento_nombre: '',
        referencia: '',
        fecha_vencimiento: '',
    });
    _render();
    _toast('Producto agregado', fila.nombre);
}

function _optsListas(item) {
    const listas = CFG.listasDescuento || [];
    if (!listas.length) return '';
    return `
        <div class="fi-field">
            <label>Lista</label>
            <select data-id="${item.id}" data-campo="lista_descuento">
                <option value="">— Manual —</option>
                ${listas.map(l => `<option value="${_esc(l.nombre)}" ${item.lista_descuento_nombre === l.nombre ? 'selected' : ''}>${_esc(l.nombre)} (${l.porcentaje}%)</option>`).join('')}
            </select>
        </div>`;
}

function _render() {
    if (!carrito.length) {
        cartBody.innerHTML = '';
        cartEmpty.style.display = 'block';
        cartCount.textContent = '0 ítems';
        if (badge) badge.style.display = 'none';
        if (cartFilter) cartFilter.hidden = true;
        if (cartMore) cartMore.hidden = true;
        btnPdf.disabled = true;
        if (btnImprimir) btnImprimir.disabled = true;
        _recalc();
        return;
    }
    cartEmpty.style.display = 'none';
    cartCount.textContent = `${carrito.length} ${carrito.length === 1 ? 'ítem' : 'ítems'}`;
    if (badge) { badge.textContent = carrito.length; badge.style.display = 'inline-flex'; }
    btnPdf.disabled = false;
    if (btnImprimir) btnImprimir.disabled = false;

    // ── Ventana visible: filtro / "mostrar más" ──
    if (cartFilter) cartFilter.hidden = carrito.length < FI_FILTRO_DESDE;
    const _filtro = _carritoFiltro.trim().toLowerCase();
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
        const base = _calcBase(item), sub = _calcSub(item);
        const conDesc = item.descuento && sub !== base;
        return `
        <div class="fi-row" data-id="${item.id}">
            <div class="fi-row-top">
                <div class="fi-row-name">
                    <b>${_esc(item.producto_nombre)}</b>
                    <span>${_esc(item.codigo)}${item.unidad ? ' · ' + _esc(item.unidad) : ''}</span>
                    ${item.variante_desc ? `<span class="fi-row-variante">${_esc(item.variante_desc)}</span>` : ''}
                </div>
                <button class="fi-row-x" data-quitar="${item.id}" title="Quitar" aria-label="Quitar">
                    <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                        <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                    </svg>
                </button>
            </div>
            <div class="fi-row-grid">
                <div class="fi-field">
                    <label>Cantidad</label>
                    <input type="number" min="0" step="any" value="${item.cantidad}" data-id="${item.id}" data-campo="cantidad">
                </div>
                <div class="fi-field">
                    <label>Costo unit.</label>
                    <input type="number" min="0" step="any" value="${item.costo}" data-id="${item.id}" data-campo="costo">
                </div>
                <div class="fi-field">
                    <label>Desc. %</label>
                    <input type="number" min="0" max="100" step="0.01" value="${item.descuento}" data-id="${item.id}" data-campo="descuento">
                </div>
                ${_optsListas(item)}
                ${item.es_perecedero ? `
                <div class="fi-field">
                    <label>Vencimiento *</label>
                    <input type="date" value="${_esc(item.fecha_vencimiento)}" data-id="${item.id}" data-campo="fecha_vencimiento"
                           class="${item.fecha_vencimiento ? '' : 'fi-req-empty'}">
                </div>` : ''}
                <div class="fi-field full">
                    <label>Referencia (opcional)</label>
                    <input type="text" value="${_esc(item.referencia)}" data-id="${item.id}" data-campo="referencia"
                           placeholder="N° de remito, lote, nota…">
                </div>
            </div>
            <div class="fi-row-sub">
                <span>${_esc(String(item.cantidad))} × ${_fmt(item.costo)}</span>
                <strong id="fiSub_${item.id}">${conDesc ? `<s>${_fmt(base)}</s>` : ''}${_fmt(sub)}</strong>
            </div>
        </div>`;
    }).join('');

    cartBody.querySelectorAll('[data-quitar]').forEach(b => {
        b.addEventListener('click', () => {
            carrito = carrito.filter(i => i.id !== parseInt(b.dataset.quitar, 10));
            _render();
        });
    });
    cartBody.querySelectorAll('[data-campo]').forEach(el => {
        el.addEventListener('change', () => _updateField(parseInt(el.dataset.id, 10), el.dataset.campo, el.value));
    });
    _renderCartMore({ hayFiltro: _hayFiltro, filtro: _filtro, mostrados: _visibles.length, truncado: _truncado });
    _recalc();
}

function _renderCartMore({ hayFiltro, filtro, mostrados, truncado }) {
    if (!cartMore) return;
    if (hayFiltro) {
        cartMore.hidden = false;
        cartMore.className = 'fi-cart-more fi-cart-more--filtro';
        cartMore.innerHTML = mostrados
            ? `<span><strong>${mostrados}</strong> de ${carrito.length} ítems coinciden</span>
               <span class="fi-cart-more-btns"><button type="button" data-cart-accion="limpiar-filtro">Quitar filtro</button></span>`
            : `<span>Ningún ítem coincide con «${_esc(filtro)}»</span>
               <span class="fi-cart-more-btns"><button type="button" data-cart-accion="limpiar-filtro">Ver todos</button></span>`;
    } else if (truncado > 0) {
        const paso = Math.min(FI_CARRITO_LIMITE, truncado);
        cartMore.hidden = false;
        cartMore.className = 'fi-cart-more';
        cartMore.innerHTML = `
            <span>Mostrando <strong>${mostrados}</strong> de ${carrito.length} ítems</span>
            <span class="fi-cart-more-btns">
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
            if (a === 'mas') _carritoLimite += FI_CARRITO_LIMITE;
            else if (a === 'todos') _carritoVerTodo = true;
            else if (a === 'limpiar-filtro') _filtroLimpiar();
            _render();
        });
    });
}

function _updateField(id, campo, valor) {
    const item = carrito.find(i => i.id === id);
    if (!item) return;
    if (campo === 'lista_descuento') {
        item.lista_descuento_nombre = valor;
        if (valor) {
            const l = (CFG.listasDescuento || []).find(x => x.nombre === valor);
            if (l) {
                item.descuento = _num(l.porcentaje);
                const inp = cartBody.querySelector(`input[data-id="${id}"][data-campo="descuento"]`);
                if (inp) inp.value = item.descuento;
            }
        }
    } else if (['cantidad', 'costo', 'descuento'].includes(campo)) {
        let n = _num(valor);
        n = campo === 'descuento' ? Math.min(100, Math.max(0, n)) : Math.max(0, n);
        item[campo] = n;
        if (campo === 'descuento' && item.lista_descuento_nombre) {
            item.lista_descuento_nombre = '';
            const sel = cartBody.querySelector(`select[data-id="${id}"][data-campo="lista_descuento"]`);
            if (sel) sel.value = '';
        }
    } else if (campo === 'fecha_vencimiento') {
        item.fecha_vencimiento = valor;
        const inp = cartBody.querySelector(`input[data-id="${id}"][data-campo="fecha_vencimiento"]`);
        if (inp) inp.classList.toggle('fi-req-empty', !valor);
    } else {
        item[campo] = valor;
    }
    const base = _calcBase(item), sub = _calcSub(item);
    const subEl = $(`fiSub_${id}`);
    if (subEl) subEl.innerHTML = (item.descuento && sub !== base ? `<s>${_fmt(base)}</s>` : '') + _fmt(sub);
    _recalc();
}

/* ════════════════════════════════════════════════════════════════
   PROVEEDOR — selector en el panel (mismo widget que "Cliente" de
   Nueva Venta: .vta-cli-wrap + icono + .vta-cli-dropdown)
════════════════════════════════════════════════════════════════ */
(() => {
    const input = $('fiProvInput');
    const dd = $('fiProvDropdown');
    const clear = $('fiProvClear');
    const hint = $('fiProvHint');
    let timer;
    let _res = [];

    function _setHint(txt) {
        if (!txt) { hint.hidden = true; hint.textContent = ''; return; }
        hint.hidden = false; hint.textContent = txt;
    }

    input.addEventListener('input', () => {
        clearTimeout(timer);
        const q = input.value.trim();
        provPk = ''; provNombre = '';
        clear.style.display = 'none';
        _setHint('');
        if (!q) { dd.classList.remove('open'); dd.innerHTML = ''; return; }
        timer = setTimeout(async () => {
            try {
                const res = await fetch(`${CFG.urlBuscarProveedor}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (input.value.trim() !== q) return;
                _res = data.results || [];
                dd.innerHTML = _res.length
                    ? _res.map((p, i) => `<div class="vta-cli-option" data-idx="${i}">
                        <div class="vta-cli-option-top">
                            <span>${_esc(p.nombre)}</span>
                            ${p.cuit ? `<span class="vta-dropdown-item-codigo">${_esc(p.cuit)}</span>` : ''}
                        </div>
                        ${p.condicion_pago ? `<div class="vta-cli-option-doc">${_esc(p.condicion_pago)}</div>` : ''}
                       </div>`).join('')
                    : '<div class="vta-dropdown-empty">Sin resultados</div>';
                dd.querySelectorAll('.vta-cli-option[data-idx]').forEach(el => {
                    el.addEventListener('mousedown', e => {
                        e.preventDefault();
                        const p = _res[parseInt(el.dataset.idx, 10)];
                        if (!p) return;
                        provPk = String(p.pk); provNombre = p.nombre;
                        input.value = p.nombre;
                        clear.style.display = 'inline-flex';
                        dd.classList.remove('open'); dd.innerHTML = '';
                        _setHint(p.cuit ? `CUIT ${p.cuit} · sus datos van en el PDF` : 'Sus datos van en el PDF');
                        if (p.condicion_pago && !$('fiPagoCondicion').value) $('fiPagoCondicion').value = p.condicion_pago;
                    });
                });
                dd.classList.add('open');
            } catch { /* silencioso */ }
        }, 260);
    });
    clear.addEventListener('click', () => {
        provPk = ''; provNombre = ''; input.value = '';
        clear.style.display = 'none'; _setHint(''); input.focus();
    });
    document.addEventListener('mousedown', e => {
        if (!dd.contains(e.target) && e.target !== input) dd.classList.remove('open');
    });
})();

/* ════════════════════════════════════════════════════════════════
   FORMA DE PAGO (informativa) — botonera .vdt-medio-tab
════════════════════════════════════════════════════════════════ */
const MEDIOS = (CFG.mediosPago || []).map(m => [m.valor, m.label]);

function _medioBotones(p, idx) {
    return MEDIOS.map(([v, l], i) => `
        <button type="button" class="vdt-medio-tab${p.medio === v ? ' is-active' : ''}"
                data-medio-btn="${v}" data-i="${idx}" aria-pressed="${p.medio === v}"
                title="${_esc(l)}">
            <span class="vdt-medio-tab-num" aria-hidden="true">${i + 1}</span>
            ${FI_MEDIO_ICONOS[v] || ''}
            <span>${_esc(FI_MEDIO_LABEL_CORTO[v] || l)}</span>
        </button>`).join('');
}

function _renderPago() {
    const cont = $('fiPagoLineas');
    if (!_pagoLineas.length) {
        cont.innerHTML = `<p class="fi-pago-vacio">Sin medios de pago anotados. Es opcional — sólo se imprime en el PDF.</p>`;
        _recalcPago();
        return;
    }
    cont.innerHTML = _pagoLineas.map((p, i) => {
        const esCredito = p.medio === 'credito';
        const esCheque = p.medio === 'cheque';
        return `
        <div class="vdt-pago-linea-wrap" data-i="${i}">
            <div class="vdt-medio-tabs" role="group" aria-label="Medio de pago">
                ${_medioBotones(p, i)}
            </div>
            <div class="vdt-pago-linea">
                <input type="number" class="vdt-pago-monto" min="0" step="0.01"
                       placeholder="Importe (informativo)" value="${_esc(p.monto)}" data-campo="monto">
                <button type="button" class="vdt-pago-btn-quitar" data-i="${i}" title="Quitar">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                </button>
            </div>
            ${esCredito ? `
            <div class="fi-pago-extra">
                <input type="number" min="1" step="1" data-campo="cuotas" value="${_esc(p.cuotas)}" placeholder="Cuotas">
                <input type="number" min="0" step="0.01" data-campo="interes_pct" value="${_esc(p.interes_pct)}" placeholder="Interés %">
            </div>` : ''}
            ${esCheque ? `
            <div class="fi-pago-extra">
                <input type="number" min="1" step="1" data-campo="cuotas" value="${_esc(p.cuotas)}" placeholder="Cuotas">
                <input type="date" data-campo="fecha" value="${_esc(p.fecha)}" title="Fecha del cheque">
            </div>
            <div class="fi-pago-extra">
                <input type="text" data-campo="banco" value="${_esc(p.banco)}" placeholder="Banco">
                <input type="text" data-campo="numero_cheque" value="${_esc(p.numero_cheque)}" placeholder="N° de cheque">
            </div>` : ''}
            <input type="text" class="vta-control fi-pago-detalle" data-campo="detalle"
                   value="${_esc(p.detalle)}" placeholder="Detalle (opcional)">
        </div>`;
    }).join('');

    cont.querySelectorAll('.vdt-medio-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = parseInt(btn.dataset.i, 10);
            if (_pagoLineas[i] && _pagoLineas[i].medio !== btn.dataset.medioBtn) {
                _pagoLineas[i].medio = btn.dataset.medioBtn;
                _renderPago();
            }
        });
    });
    cont.querySelectorAll('.vdt-pago-linea-wrap [data-campo]').forEach(el => {
        el.addEventListener('change', () => {
            const i = parseInt(el.closest('.vdt-pago-linea-wrap').dataset.i, 10);
            _pagoLineas[i][el.dataset.campo] = el.value;
            _recalcPago();
        });
        if (el.dataset.campo === 'monto') {
            el.addEventListener('input', () => {
                const i = parseInt(el.closest('.vdt-pago-linea-wrap').dataset.i, 10);
                _pagoLineas[i].monto = el.value;
                _recalcPago();
            });
        }
    });
    cont.querySelectorAll('.vdt-pago-btn-quitar').forEach(b => {
        b.addEventListener('click', () => {
            _pagoLineas.splice(parseInt(b.dataset.i, 10), 1);
            _renderPago();
        });
    });
    _recalcPago();
}

$('fiPagoAdd').addEventListener('click', () => {
    _pagoLineas.push({ medio: 'efectivo', monto: '', cuotas: '', interes_pct: '', banco: '', numero_cheque: '', fecha: '', detalle: '' });
    _renderPago();
});

function _recalcPago() {
    const cierre = $('fiPagoResumen');
    const estado = $('fiPagoEstado');
    const desglose = $('fiPagoDesglose');
    const total = _totalActual();
    $('fiTotTotal').textContent = _fmt(total);
    cierre.classList.remove('vdt-pago-cierre--ok', 'vdt-pago-cierre--pendiente', 'vdt-pago-cierre--exceso');

    if (!_pagoLineas.length) {
        cierre.classList.add('vdt-pago-cierre--ok');
        estado.textContent = 'Total del comprobante';
        desglose.hidden = true;
        return;
    }
    const asignado = _pagoLineas.reduce((s, p) => s + _num(p.monto), 0);
    const dif = total - asignado;
    desglose.hidden = false;
    if (Math.abs(dif) < 0.005) {
        cierre.classList.add('vdt-pago-cierre--ok');
        estado.textContent = 'Coincide con el total ✓';
        desglose.innerHTML = `Anotado <strong>${_fmt(asignado)}</strong> en ${_pagoLineas.length} medio${_pagoLineas.length === 1 ? '' : 's'}`;
    } else if (dif > 0) {
        cierre.classList.add('vdt-pago-cierre--pendiente');
        estado.textContent = 'No cubre el total';
        desglose.innerHTML = `Anotado <strong>${_fmt(asignado)}</strong> · faltarían <strong>${_fmt(dif)}</strong> <span class="fi-pago-nota">(informativo)</span>`;
    } else {
        cierre.classList.add('vdt-pago-cierre--exceso');
        estado.textContent = 'Supera el total';
        desglose.innerHTML = `Anotado <strong>${_fmt(asignado)}</strong> · excede por <strong>${_fmt(-dif)}</strong> <span class="fi-pago-nota">(informativo)</span>`;
    }
}

/* ════════════════════════════════════════════════════════════════
   TOTALES (espejo del backend / Compra.total)
════════════════════════════════════════════════════════════════ */
function _totalesCarrito() {
    let bruto = 0, desc = 0;
    carrito.forEach(i => {
        const b = _calcBase(i);
        bruto += b;
        desc += i.descuento ? b * (_num(i.descuento) / 100) : 0;
    });
    return { bruto, desc, netoLineas: bruto - desc };
}

function _totalActual() {
    const { netoLineas } = _totalesCarrito();
    const modo = _modoIva();
    const alic = (parseFloat($('fiAlicuota').value) || 0) / 100;
    if (modo === 'sin' || modo === 'incluido' || alic === 0) return netoLineas;
    // discriminado: si los costos ya incluyen IVA, el total es el neto de
    // líneas; si no, se le suma el IVA por encima.
    return $('fiIvaIncluido').checked ? netoLineas : netoLineas * (1 + alic);
}

function _recalc() {
    const modo = _modoIva();
    const alic = (parseFloat($('fiAlicuota').value) || 0) / 100;
    const ivaIncluido = $('fiIvaIncluido').checked;
    const { bruto, desc, netoLineas } = _totalesCarrito();

    // Visibilidad de la sección de IVA según el tipo de comprobante.
    $('fiIvaSection').style.display = (modo === 'sin') ? 'none' : '';
    $('fiIvaIncluidoWrap').style.display = (modo === 'discriminado') ? '' : 'none';

    let neto, iva, total;
    if (modo === 'sin' || alic === 0) {
        neto = netoLineas; iva = 0; total = netoLineas;
    } else if (modo === 'incluido' || ivaIncluido) {
        total = netoLineas; neto = total / (1 + alic); iva = total - neto;
    } else {
        neto = netoLineas; iva = neto * alic; total = neto + iva;
    }

    const discrimina = modo === 'discriminado' && alic > 0;
    $('fiTotSubtotal').textContent = _fmt(bruto);
    $('fiTotDescuento').textContent = '–' + _fmt(desc);
    $('fiTotDescuentoRow').hidden = desc <= 0.005;
    $('fiTotNeto').textContent = _fmt(neto);
    $('fiTotIva').textContent = _fmt(iva);
    $('fiTotIvaPct').textContent = ($('fiAlicuota').value || '0').replace('.', ',');
    $('fiTotNetoRow').hidden = !discrimina;
    $('fiTotIvaRow').hidden = !discrimina;
    _recalcPago();
}

['fiTipoComprobante', 'fiAlicuota', 'fiIvaIncluido'].forEach(id => $(id).addEventListener('change', _recalc));

/* ════════════════════════════════════════════════════════════════
   CONFIRMAR
════════════════════════════════════════════════════════════════ */
function _leerDocumento() {
    return {
        tipo_comprobante: $('fiTipoComprobante').value,
        fecha: $('fiFecha').value,
        numero_comprobante: $('fiNumComp').value,
        alicuota_iva: $('fiAlicuota').value,
        iva_incluido: $('fiIvaIncluido').checked,
        proveedor_pk: provPk || null,
        pago: {
            condicion: $('fiPagoCondicion').value,
            lineas: _pagoLineas.filter(p => p.monto || p.detalle || p.banco || p.numero_cheque),
        },
        observaciones: $('fiObs').value,
        incluir_leyenda: $('fiLeyenda').checked,
    };
}

let _ultimaData = null;   // payload de la última factura creada (re-imprimir / re-descargar)

// accion: 'imprimir' → diálogo de impresión ; 'descargar' → baja el .pdf
async function _salida(accion, data) {
    const html = facturaInicialHtmlA4(data, { sinAutoImpresion: true });
    if (accion === 'imprimir') await facturaInicialImprimir(html);
    else await facturaInicialDescargarPdf(html, data);
}

async function _confirmar(accion, btn) {
    if (!carrito.length || _confirmada) return;
    const sinVenc = carrito.filter(i => i.es_perecedero && !i.fecha_vencimiento);
    if (sinVenc.length) {
        _toast('Falta la fecha de vencimiento', sinVenc.map(i => i.producto_nombre).join(', '));
        return;
    }
    const botones = [btnPdf, btnImprimir].filter(Boolean);
    const originales = botones.map(b => b.innerHTML);
    botones.forEach(b => { b.disabled = true; });
    btn.innerHTML = `<svg class="fi-spin" width="15" height="15" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.6" stroke-dasharray="20 14"/></svg> Confirmando…`;

    const restaurar = () => botones.forEach((b, i) => { b.disabled = false; b.innerHTML = originales[i]; });

    const body = {
        items: carrito.map(i => ({
            producto_pk: i.producto_pk,
            combinacion_pk: i.combinacion_pk || null,
            cantidad: i.cantidad,
            costo_unitario: i.costo,
            descuento_pct: i.descuento,
            lista_descuento_nombre: i.lista_descuento_nombre || '',
            referencia: i.referencia || '',
            fecha_vencimiento: i.fecha_vencimiento || null,
        })),
        documento: _leerDocumento(),
    };

    try {
        const res = await fetch(CFG.urlCrear, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!data.ok) {
            _toast('No se pudo confirmar', data.error || 'Revisá los datos.');
            restaurar();
            return;
        }
        _confirmada = true;
        _ultimaData = data;
        try {
            await _salida(accion, data);
        } catch (e) {
            _toast(accion === 'imprimir' ? 'Factura creada, pero falló la impresión' : 'Factura creada, pero falló el PDF',
                   'Reintentá desde "Ver facturas iniciales".');
        }
        _mostrarExito(data, accion);
    } catch {
        _toast('Error de conexión', 'Intentá de nuevo.');
        restaurar();
    }
}

btnPdf.addEventListener('click', () => _confirmar('descargar', btnPdf));
if (btnImprimir) btnImprimir.addEventListener('click', () => _confirmar('imprimir', btnImprimir));

function _mostrarExito(data, accion) {
    const hecho = accion === 'imprimir'
        ? 'Se mandó el comprobante a la impresora.'
        : 'El PDF del comprobante se descargó.';
    document.querySelector('.vta-cobro-main').innerHTML = `
        <div class="vta-card" style="padding:2rem;text-align:center;">
            <div style="color:#10B981;margin-bottom:.6rem;">
                <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.6"/>
                    <path d="M7.5 12.5L10.5 15.5L16.5 8.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <h2 style="margin:0 0 .3rem;font-family:'Plus Jakarta Sans',sans-serif;font-size:1.1rem;">
                Factura inicial ${_esc(data.numero_interno || '')} confirmada</h2>
            <p style="color:var(--text-muted);font-size:.9rem;margin:0 0 1.2rem;">
                Se sumó el stock y se crearon los lotes de inventario. ${hecho}
                No se generó ningún movimiento de caja.</p>
            <div style="display:flex;gap:.6rem;justify-content:center;flex-wrap:wrap;">
                <button type="button" id="fiExitoImprimir" class="vta-btn vta-btn-ghost" style="width:auto;margin:0;">Imprimir</button>
                <button type="button" id="fiExitoDescargar" class="vta-btn vta-btn-ghost" style="width:auto;margin:0;">Descargar PDF</button>
                <a href="${CFG.urlHistorial}" class="vta-btn vta-btn-ghost" style="width:auto;margin:0;">Ver facturas iniciales</a>
                <a href="" class="vta-btn vta-btn-primary" style="width:auto;margin:0;" onclick="location.reload();return false;">Cargar otra</a>
            </div>
        </div>`;
    const panel = $('fiPanel');
    if (panel) panel.style.display = 'none';
    const bi = $('fiExitoImprimir'), bd = $('fiExitoDescargar');
    if (bi) bi.addEventListener('click', () => { if (_ultimaData) _salida('imprimir', _ultimaData); });
    if (bd) bd.addEventListener('click', () => { if (_ultimaData) _salida('descargar', _ultimaData); });
}

/* ════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */
_renderPago();
_render();
searchInput.focus();
