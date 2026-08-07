/**
 * nuevo_presupuesto.js
 *
 * Carrito de cotización — versión simplificada del de Nueva Venta
 * (ventas/static/ventas/js/nueva_venta.js): sin escaneo de lote/balanza,
 * sin ofertas automáticas, sin condición de pago por línea. No hay
 * "borrador" — se guarda de una sola vez y esa misma respuesta trae
 * todo lo necesario para abrir la impresión al toque (ver
 * presupuestos/views.py::_datos_impresion).
 *
 * Modo edición (?editar=<pk>, ver CFG.presupuestoEditarPk): precarga
 * el carrito con los ítems de un presupuesto ya guardado — al guardar
 * se pisan sus ítems en vez de crear uno nuevo (mismo patrón que
 * ?editar=<pk> en Nueva Venta).
 *
 * Requiere window.PRE_CONFIG con:
 *   urlBuscarProducto, urlBuscarCliente, urlCrear, urlActualizar,
 *   urlHistorial, csrfToken, itemsIniciales, presupuestoEditarPk,
 *   clienteEditarPk, clienteEditarNombre
 */
'use strict';

const CFG = window.PRE_CONFIG || {};

let clienteElegido = { pk: CFG.clienteEditarPk || null, nombre: CFG.clienteEditarPk ? (CFG.clienteEditarNombre || '') : '' };
let clienteLibreInicial = (!CFG.clienteEditarPk && CFG.clienteEditarNombre) ? CFG.clienteEditarNombre : '';

let nextId  = 0;
let carrito = (CFG.itemsIniciales || []).map(fila => ({
    id:             nextId++,
    producto_pk:    fila.producto_pk,
    combinacion_pk: fila.combinacion_pk || null,
    nombre:         fila.nombre,
    codigo:         fila.codigo,
    stock_actual:   fila.stock_actual,
    cantidad:       fila.cantidad,
    precio:         fila.precio,
    moneda:         'ARS',
    descuento:      fila.descuento || 0,
    lista_descuento_nombre: fila.lista_descuento_nombre || '',
}));

const searchInput    = document.getElementById('preSearchInput');
const searchDropdown = document.getElementById('preSearchDropdown');
const cartBody        = document.getElementById('preCartBody');
const cartEmpty       = document.getElementById('preCartEmpty');
const cartFooter      = document.getElementById('preCartFooter');
const btnGuardar      = document.getElementById('preBtnGuardar');
const badge           = document.getElementById('preBadge');
const totalItemsEl    = document.getElementById('preTotalItems');
const totalMontoEl    = document.getElementById('preTotalMonto');
const clienteInput    = document.getElementById('preClienteInput');
const clienteDropdown = document.getElementById('preClienteDropdown');
const clienteClear    = document.getElementById('preClienteClear');
const clienteSpinner  = document.getElementById('preClienteSpinner');
const clienteLibre    = document.getElementById('preClienteLibre');

if (searchInput) {

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
    const toast = document.getElementById('preToast');
    document.getElementById('preToastTitle').textContent = titulo;
    document.getElementById('preToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

/* ════════════════════════════════════════════════════════════════
   BUSCADOR DE PRODUCTOS
════════════════════════════════════════════════════════════════ */
function _renderOpciones(filas) {
    if (!filas.length) {
        searchDropdown.innerHTML = `<div class="vta-dropdown-empty">Sin resultados</div>`;
        searchDropdown.classList.add('open');
        return;
    }
    searchDropdown.innerHTML = filas.map((r, idx) => `
        <div class="vta-dropdown-item" data-idx="${idx}">
            <div class="vta-dropdown-item-top">
                <span class="vta-dropdown-item-nombre">${_esc(r.nombre)}${r.marca ? ` <span class="vta-dropdown-item-marca">· ${_esc(r.marca)}</span>` : ''}</span>
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

let searchTimer;
async function _ejecutarBusqueda(q) {
    if (!q) {
        searchDropdown.classList.remove('open');
        searchDropdown.innerHTML = '';
        return;
    }
    try {
        const res     = await fetch(`${CFG.urlBuscarProducto}?q=${encodeURIComponent(q)}`);
        const data    = await res.json();
        const results = data.results || [];
        if (results.length === 1 && results[0].match_exacto) {
            _agregarResultado(results[0]);
            searchDropdown.classList.remove('open');
            searchDropdown.innerHTML = '';
            searchInput.value = '';
            return;
        }
        _renderOpciones(results);
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
    }
});
document.addEventListener('click', e => {
    if (!searchDropdown.contains(e.target) && e.target !== searchInput) {
        searchDropdown.classList.remove('open');
    }
    if (clienteDropdown && !clienteDropdown.contains(e.target) && e.target !== clienteInput) {
        clienteDropdown.classList.remove('open');
    }
});

/* ════════════════════════════════════════════════════════════════
   AGREGAR AL CARRITO
════════════════════════════════════════════════════════════════ */
function _agregarResultado(fila) {
    if (fila.tipo_resultado === 'producto_con_variantes') {
        const combos = fila.combinaciones || [];
        if (combos.length === 1) {
            _agregarFila({ ...fila, tipo_resultado: 'variante', combinacion_pk: combos[0].combinacion_pk,
                           variante_desc: combos[0].nombre, stock_actual: combos[0].stock_actual });
        } else if (combos.length > 1) {
            _toast('Elegí la variante', `"${fila.nombre}" tiene varias variantes activas — elegí cuál cotizás.`);
            _renderOpciones(combos.map(c => ({ ...fila, tipo_resultado: 'variante', combinacion_pk: c.combinacion_pk,
                                                variante_desc: c.nombre, nombre: `${fila.nombre} — ${c.nombre}`,
                                                stock_actual: c.stock_actual })));
        } else {
            _toast('Sin variantes activas', `"${fila.nombre}" no tiene ninguna variante activa cargada.`);
        }
        return;
    }
    _agregarFila(fila);
}

function _agregarFila(fila) {
    const existente = carrito.find(i =>
        i.producto_pk === fila.pk && i.combinacion_pk === (fila.combinacion_pk || null)
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
        stock_actual:    fila.stock_actual,
        cantidad:        1,
        precio:          fila.precio_venta ?? '',
        moneda:          fila.moneda || 'ARS',
        descuento:       0,
        lista_descuento_nombre: '',
    });
    _renderCarrito();
}

function _quitarItem(id) {
    carrito = carrito.filter(i => i.id !== id);
    _renderCarrito();
}

/* ════════════════════════════════════════════════════════════════
   CLIENTE — buscador de clientes registrados + campo de texto libre
════════════════════════════════════════════════════════════════ */
let clienteSearchTimer;

function _bindCliente() {
    if (!clienteInput || !clienteDropdown) return;

    clienteInput.addEventListener('input', () => {
        clearTimeout(clienteSearchTimer);
        const q = clienteInput.value.trim();
        clienteElegido = { pk: null, nombre: '' };
        clienteClear.style.display = 'none';

        if (!q) {
            clienteDropdown.classList.remove('open');
            clienteDropdown.innerHTML = '';
            clienteSpinner.style.display = 'none';
            return;
        }
        clienteSearchTimer = setTimeout(async () => {
            clienteSpinner.style.display = 'block';
            try {
                const res  = await fetch(`${CFG.urlBuscarCliente}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (clienteInput.value.trim() !== q) return;
                const results = data.results || [];
                clienteDropdown.innerHTML = results.length
                    ? results.map(c => `
                        <div class="vta-cli-option" data-pk="${c.pk}" data-nombre="${_esc(c.nombre)}">
                            <div class="vta-cli-option-top">
                                <span class="vta-cli-option-nombre">${_esc(c.nombre)}</span>
                                ${c.codigo ? `<span class="vta-dropdown-item-codigo">${_esc(c.codigo)}</span>` : ''}
                            </div>
                            ${c.doc ? `<div class="vta-cli-option-doc">${_esc(c.doc)}</div>` : ''}
                        </div>`).join('')
                    : `<div class="vta-dropdown-empty">Sin resultados para "${_esc(q)}"</div>`;

                clienteDropdown.querySelectorAll('.vta-cli-option').forEach(el => {
                    el.addEventListener('click', () => {
                        clienteElegido = { pk: parseInt(el.dataset.pk, 10), nombre: el.dataset.nombre };
                        clienteInput.value = el.dataset.nombre;
                        clienteClear.style.display = 'inline-flex';
                        clienteDropdown.classList.remove('open');
                        clienteDropdown.innerHTML = '';
                        if (clienteLibre) { clienteLibre.value = ''; clienteLibre.disabled = true; }
                    });
                });
                clienteDropdown.classList.add('open');
            } catch { /* silencioso */ }
            finally { clienteSpinner.style.display = 'none'; }
        }, 260);
    });

    clienteClear.addEventListener('click', () => {
        clienteElegido = { pk: null, nombre: '' };
        clienteInput.value = '';
        clienteClear.style.display = 'none';
        if (clienteLibre) clienteLibre.disabled = false;
        clienteInput.focus();
    });

    if (clienteLibre) {
        clienteLibre.addEventListener('input', () => {
            clienteInput.disabled = !!clienteLibre.value.trim();
        });
    }

    // Precarga en modo edición — cliente registrado o nombre libre.
    if (clienteElegido.pk) {
        clienteInput.value = clienteElegido.nombre;
        clienteClear.style.display = 'inline-flex';
    } else if (clienteLibreInicial) {
        if (clienteLibre) {
            clienteLibre.value = clienteLibreInicial;
            clienteInput.disabled = true;
        }
    }
}

/* ════════════════════════════════════════════════════════════════
   RENDER DEL CARRITO
════════════════════════════════════════════════════════════════ */
function _opcionesDescuento(item) {
    const listas = CFG.listasDescuento || [];
    if (!listas.length) return null;
    const opciones = listas.map(l => `
        <option value="lista:${_esc(l.nombre)}" data-pct="${l.porcentaje}" ${item.lista_descuento_nombre === l.nombre ? 'selected' : ''}>
            ${_esc(l.nombre)} (${l.porcentaje}%)
        </option>`).join('');
    return `<option value="">— Manual —</option>${opciones}`;
}
function _selectDescuento(item) {
    const opciones = _opcionesDescuento(item);
    if (opciones === null) return `<span class="vta-lista-vacia" title="No hay listas de descuento creadas">—</span>`;
    return `<select class="vta-select-inline w-sm" data-item-id="${item.id}" data-campo="lista_descuento" title="Aplicar % de una lista de descuento">${opciones}</select>`;
}

function _renderCarrito() {
    if (!carrito.length) {
        cartBody.innerHTML = '';
        cartEmpty.style.display  = 'flex';
        cartFooter.style.display = 'none';
        _actualizarBtnGuardar();
        return;
    }
    cartEmpty.style.display  = 'none';
    cartFooter.style.display = 'flex';

    cartBody.innerHTML = carrito.map(item => `
        <tr data-item-id="${item.id}">
            <td>
                <div class="vta-prod-cell">
                    <span class="vta-prod-nombre">${_esc(item.nombre)}</span>
                    <span class="vta-prod-meta">${_esc(item.codigo)} · Stock ${parseFloat(item.stock_actual || 0).toLocaleString('es-AR')}</span>
                </div>
            </td>
            <td><input type="number" min="0.001" step="0.001" class="vta-input-inline w-sm"
                       data-item-id="${item.id}" data-campo="cantidad" value="${item.cantidad}"></td>
            <td><input type="number" min="0" step="0.01" class="vta-input-inline w-sm"
                       data-item-id="${item.id}" data-campo="precio" value="${item.precio}"></td>
            <td><input type="number" min="0" max="100" step="0.01" class="vta-input-inline w-xs"
                       data-item-id="${item.id}" data-campo="descuento" value="${item.descuento}"></td>
            <td>${_selectDescuento(item)}</td>
            <td class="vta-subtotal-cell">${_fmt(_calcSub(item), item.moneda)}</td>
            <td><button class="vta-btn-remove" data-item-id="${item.id}" title="Quitar">✕</button></td>
        </tr>`
    ).join('');

    cartBody.querySelectorAll('.vta-input-inline[data-campo], .vta-select-inline[data-campo]').forEach(el => {
        const ev = el.tagName === 'SELECT' ? 'change' : 'input';
        el.addEventListener(ev, () => _onCampoCambiado(el));
    });
    cartBody.querySelectorAll('.vta-btn-remove').forEach(el => {
        el.addEventListener('click', () => _quitarItem(parseInt(el.dataset.itemId, 10)));
    });

    _actualizarTotales();
    _actualizarBtnGuardar();
}

function _onCampoCambiado(el) {
    const id    = parseInt(el.dataset.itemId, 10);
    const campo = el.dataset.campo;
    const item  = carrito.find(i => i.id === id);
    if (!item) return;
    const fila = cartBody.querySelector(`tr[data-item-id="${id}"]`);

    if (campo === 'lista_descuento') {
        const [, ...resto] = el.value.split(':');
        item.lista_descuento_nombre = el.value ? resto.join(':') : '';
        if (el.value) {
            const opt = el.selectedOptions[0];
            item.descuento = opt ? opt.dataset.pct : item.descuento;
        } else {
            item.descuento = 0;
        }
        const inputDesc = fila?.querySelector('[data-campo="descuento"]');
        if (inputDesc) inputDesc.value = item.descuento;
    } else if (campo === 'descuento') {
        item.descuento = el.value;
        if (item.lista_descuento_nombre) {
            item.lista_descuento_nombre = '';
            const selLista = fila?.querySelector('[data-campo="lista_descuento"]');
            if (selLista) selLista.value = '';
        }
    } else {
        item[campo] = el.value;
    }

    if (fila) {
        const sub = fila.querySelector('.vta-subtotal-cell');
        if (sub) sub.textContent = _fmt(_calcSub(item), item.moneda);
    }
    _actualizarTotales();
    _actualizarBtnGuardar();
}

function _actualizarTotales() {
    const totalNeto = carrito.reduce((s, i) => s + _calcSub(i), 0);
    if (totalItemsEl) totalItemsEl.textContent = carrito.length;
    if (totalMontoEl) totalMontoEl.textContent = _fmtPeso(totalNeto);
    if (badge) { badge.textContent = carrito.length; badge.style.display = carrito.length ? 'inline-flex' : 'none'; }
}
function _actualizarBtnGuardar() {
    if (btnGuardar) btnGuardar.disabled = carrito.length === 0;
}

/* ════════════════════════════════════════════════════════════════
   GUARDAR
════════════════════════════════════════════════════════════════ */
if (btnGuardar) {
    btnGuardar.addEventListener('click', async () => {
        if (!carrito.length) return;

        btnGuardar.disabled = true;
        btnGuardar.textContent = 'Guardando…';

        const itemsPayload = carrito.map(item => ({
            producto_pk:     item.producto_pk,
            combinacion_pk:  item.combinacion_pk || null,
            cantidad:        item.cantidad,
            precio_unitario: item.precio,
            descuento_pct:   item.descuento,
            lista_descuento_nombre: item.lista_descuento_nombre || '',
            stock_al_emitir: item.stock_actual,
        }));

        const editando = !!CFG.presupuestoEditarPk;
        const body = {
            items: itemsPayload,
            cliente_pk: clienteElegido.pk,
            cliente_nombre: clienteElegido.pk ? clienteElegido.nombre : (clienteLibre ? clienteLibre.value.trim() : ''),
        };
        if (editando) body.presupuesto_pk = CFG.presupuestoEditarPk;

        try {
            const res  = await fetch(editando ? CFG.urlActualizar : CFG.urlCrear, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.ok) {
                // Se guardó — la respuesta ya trae todo lo necesario para
                // imprimir (ver _datos_impresion en views.py), así que se
                // abre la ventana de impresión de una sola vez, sin pasar
                // por ninguna página de detalle intermedia.
                const ventana = window.open('', '_blank', 'width=750,height=950');
                if (ventana) {
                    ventana.document.write(presupuestoHtmlA4(data));
                    ventana.document.close();
                } else {
                    _toast('Guardado', `${data.numero} se guardó, pero el navegador bloqueó la ventana de impresión.`);
                }
                window.location.href = CFG.urlHistorial;
            } else {
                _toast('Error al guardar', data.error || 'No se pudo guardar el presupuesto.');
                btnGuardar.disabled = false;
                btnGuardar.innerHTML = 'Guardar e imprimir';
            }
        } catch {
            _toast('Error de conexión', 'Intentá de nuevo.');
            btnGuardar.disabled = false;
            btnGuardar.innerHTML = 'Guardar e imprimir';
        }
    });
}

/* ════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */
_bindCliente();
_renderCarrito();
searchInput.focus();

} // if (searchInput)
