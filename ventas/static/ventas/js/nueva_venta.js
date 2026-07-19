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
const BALANZA_REGEX = /^BAL-\d{4}-\d{5}$/i;

// Patrón "tolerante": prefijo + separador (cualquier símbolo, 1 char) +
// 4 dígitos + separador + 5 dígitos. Cubre distintos lectores de
// código de barras que, según su configuración de teclado, pueden
// mandar cualquier símbolo (', `, _, :, etc.) en vez del guión real
// del código impreso — sin necesidad de saber de antemano cuál.
const LOTE_REGEX_TOLERANTE = /^LT.(\d{4}).(\d{5})$/i;
const BALANZA_REGEX_TOLERANTE = /^BAL.(\d{4}).(\d{5})$/i;

/**
 * Si el texto escaneado no matchea el código de lote exacto pero sí
 * su forma general (LT-XXXX-XXXXX o BAL-XXXX-XXXXX con cualquier
 * separador), lo reconstruye con guiones. Independiente de marca/
 * modelo del lector.
 */
function _normalizarPosibleCodigoLote(raw) {
    if (LOTE_REGEX.test(raw) || BALANZA_REGEX.test(raw)) return raw;
    const mLote = raw.match(LOTE_REGEX_TOLERANTE);
    if (mLote) return `LT-${mLote[1]}-${mLote[2]}`;
    const mBal = raw.match(BALANZA_REGEX_TOLERANTE);
    if (mBal) return `BAL-${mBal[1]}-${mBal[2]}`;
    return raw;
}

/* ════════════════════════════════════════════════════════════════
   ESTADO
════════════════════════════════════════════════════════════════ */
let nextId  = 0;
let carrito = (CFG.itemsIniciales || []).map(fila => ({
    id:              nextId++,
    producto_pk:     fila.producto_pk,
    categoria_id:    fila.categoria_id || null,
    combinacion_pk:  fila.combinacion_pk || null,
    nombre:          fila.nombre,
    codigo:          fila.codigo,
    tipo_escaneo:    fila.tipo_escaneo || 'normal',
    lote_pk:         fila.lote_pk || null,
    lote_codigo:     fila.lote_codigo || '',
    etiqueta_balanza_pk:     fila.etiqueta_balanza_pk || null,
    etiqueta_balanza_codigo: fila.etiqueta_balanza_codigo || '',
    cliente_pk:      fila.cliente_pk || null,
    cliente_nombre:  fila.cliente_nombre || '',
    cantidad:        fila.cantidad,
    precio:          fila.precio,
    moneda:          fila.moneda || 'ARS',
    descuento:       fila.descuento || 0,
    lista_descuento_nombre: fila.lista_descuento_nombre || '',
    oferta_aplicada_nombre: fila.oferta_aplicada_nombre || '',
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
   OFERTAS — ya vienen filtradas por vigencia (fecha + día de semana)
   desde el servidor (ver ofertas_vigentes en la vista); acá se
   chequea el ALCANCE (¿esta oferta corresponde a este producto?) y,
   para las de tipo NXM ("llevá X, pagá Y"), se calcula el % efectivo
   según la cantidad actual de la línea — mismo cálculo que
   Oferta.descuento_equivalente() en productos/models.py, pero acá
   nunca vuelve al servidor: se recalcula solo cada vez que cambia la
   cantidad (ver _recalcularOfertaSeleccionada).

   Cada línea tiene UN desplegable "Oferta" con TODAS las ofertas
   vigentes para ese producto (automáticas y manuales juntas):
     - Automática: viene preseleccionada al agregar el producto.
     - Manual: el vendedor la elige de la lista.
   En ambos casos, una vez elegida (a mano o sola), si cambia la
   cantidad se recalcula su % — no importa cómo llegó a estar
   seleccionada. Elegir "Manual" o una lista de descuento la reemplaza
   (nunca se acumulan dos fuentes de descuento en la misma línea).
════════════════════════════════════════════════════════════════ */
function _ofertaAplicaAProducto(o, productoPk, categoriaId) {
    const sinAlcanceDefinido = !o.productos.length && !o.categorias.length;
    if (sinAlcanceDefinido) return true;
    if (o.productos.includes(productoPk)) return true;
    if (categoriaId != null && o.categorias.includes(categoriaId)) return true;
    return false;
}

function _pctEfectivoOferta(o, cantidad) {
    if (o.tipo === 'nxm') {
        const n = o.cantidad_lleva, m = o.cantidad_paga;
        const qty = Math.floor(parseFloat(cantidad) || 0);
        if (!n || !m || qty < n) return 0;
        const grupos = Math.floor(qty / n);
        const resto  = qty % n;
        const unidadesAPagar = grupos * m + resto;
        return (1 - unidadesAPagar / qty) * 100;
    }
    return parseFloat(o.porcentaje) || 0;
}

function _ofertasVigentesParaProducto(productoPk, categoriaId) {
    return (CFG.ofertasVigentes || [])
        .filter(o => o.tipo !== 'umbral' && _ofertaAplicaAProducto(o, productoPk, categoriaId));
}

function _mejorOfertaAutomatica(productoPk, categoriaId, cantidad) {
    const candidatas = _ofertasVigentesParaProducto(productoPk, categoriaId)
        .filter(o => o.aplicacion === 'automatica');
    if (!candidatas.length) return null;
    // La que dé mayor % efectivo a esta cantidad gana — no se acumulan
    // varias ofertas en una misma línea.
    let mejor = null, mejorPct = -1;
    for (const o of candidatas) {
        const pct = _pctEfectivoOferta(o, cantidad);
        if (pct > mejorPct) { mejor = o; mejorPct = pct; }
    }
    return mejor;
}

/**
 * Recalcula el % de la oferta actualmente seleccionada en la línea
 * (`item.oferta_aplicada_nombre`) según su cantidad ACTUAL — necesario
 * para NXM, donde el % depende de cuántas unidades hay (2x1 con 1
 * unidad no da nada; con 2, sí). No hace nada si la línea no tiene
 * ninguna oferta seleccionada (manual %, lista, o nada).
 */
function _recalcularOfertaSeleccionada(item) {
    if (!item.oferta_aplicada_nombre) return;
    const oferta = (CFG.ofertasVigentes || []).find(o => o.nombre === item.oferta_aplicada_nombre);
    if (!oferta) {
        item.oferta_aplicada_nombre = '';
        item.descuento = 0;
        return;
    }
    // 4 decimales (no 2): un 3x1 da 66,6666...% — con solo 2 decimales
    // el redondeo se nota en el subtotal (ej: $3000 con 3x1 daba
    // $999,90 en vez de $1000 exactos). El desplegable sigue mostrando
    // el % lindo con 2 decimales (ver _opcionesOferta); esto es lo que
    // realmente se guarda y se manda al confirmar la venta.
    item.descuento = _pctEfectivoOferta(oferta, item.cantidad).toFixed(4);
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

async function _buscarPorCodigoBalanza(codigo) {
    try {
        const res  = await fetch(`${CFG.urlBuscarBalanza}?codigo=${encodeURIComponent(codigo)}`);
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
        _toast('Error de conexión', 'No se pudo buscar la etiqueta. Intentá de nuevo.');
    }
}

async function _ejecutarBusqueda(q, { forzarAgregado = false } = {}) {
    if (!q) {
        searchDropdown.classList.remove('open');
        searchDropdown.innerHTML = '';
        return;
    }

    q = _normalizarPosibleCodigoLote(q);

    if (BALANZA_REGEX.test(q)) {
        await _buscarPorCodigoBalanza(q);
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
    // Etiqueta de balanza: código de un solo uso, con cantidad y precio
    // ya fijados al pesar — nunca se suma a una fila existente ni se
    // deja editar. Si ya está en el carrito, no se agrega de nuevo.
    if (fila.etiqueta_balanza_pk) {
        const yaEsta = carrito.find(i => i.etiqueta_balanza_pk === fila.etiqueta_balanza_pk);
        if (yaEsta) {
            _toast('Etiqueta ya agregada', `La etiqueta ${fila.etiqueta_balanza_codigo} ya está en el carrito.`);
            return;
        }
        carrito.push({
            id:              nextId++,
            producto_pk:     fila.pk,
            categoria_id:    fila.categoria_id ?? null,
            combinacion_pk:  null,
            nombre:          fila.nombre,
            codigo:          fila.codigo,
            tipo_escaneo:    'normal',
            lote_pk:         null,
            lote_codigo:     '',
            etiqueta_balanza_pk:     fila.etiqueta_balanza_pk,
            etiqueta_balanza_codigo: fila.etiqueta_balanza_codigo,
            cliente_pk:      null,
            cliente_nombre:  '',
            cantidad:        fila.cantidad_fija,
            precio:          fila.precio_venta ?? '',
            moneda:          fila.moneda || 'ARS',
            descuento:       0,
            lista_descuento_nombre: '',
            oferta_aplicada_nombre: '',
            condicion:       'contado',
            referencia:      '',
        });
        _renderCarrito();
        return;
    }

    const existente = carrito.find(i =>
        i.producto_pk === fila.pk &&
        i.combinacion_pk === (fila.combinacion_pk || null) &&
        i.tipo_escaneo === (fila.tipo_escaneo || 'normal') &&
        i.lote_pk === (fila.lote_pk || null) &&
        !i.etiqueta_balanza_pk
    );

    if (existente) {
        existente.cantidad = (parseFloat(existente.cantidad) || 0) + 1;
        _recalcularOfertaSeleccionada(existente);
        _renderCarrito();
        return;
    }

    const categoriaId = fila.categoria_id ?? null;
    // Oferta automática vigente para este producto (si hay más de una,
    // gana la de mayor % a 1 unidad) — queda preseleccionada en el
    // desplegable "Oferta" desde el alta. El vendedor puede elegir otra
    // cosa en cualquier momento, lo que la reemplaza sin problema.
    const ofertaAuto = _mejorOfertaAutomatica(fila.pk, categoriaId, 1);

    const nuevoItem = {
        id:              nextId++,
        producto_pk:     fila.pk,
        categoria_id:    categoriaId,
        combinacion_pk:  fila.combinacion_pk || null,
        nombre:          fila.nombre,
        codigo:          fila.codigo,
        tipo_escaneo:    fila.tipo_escaneo || 'normal',
        lote_pk:         fila.lote_pk || null,
        lote_codigo:     fila.lote_codigo || '',
        etiqueta_balanza_pk:     null,
        etiqueta_balanza_codigo: '',
        cliente_pk:      null,
        cliente_nombre:  '',
        cantidad:        1,
        precio:          fila.precio_venta ?? '',
        moneda:          fila.moneda || 'ARS',
        descuento:       0,
        lista_descuento_nombre: '',
        oferta_aplicada_nombre: ofertaAuto ? ofertaAuto.nombre : '',
        condicion:       'contado',
        referencia:      '',
    };
    _recalcularOfertaSeleccionada(nuevoItem);

    carrito.push(nuevoItem);
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
    if (item.etiqueta_balanza_pk) {
        return `<span class="vta-origen-chip vta-origen-chip--balanza" title="Cantidad y precio fijados por la etiqueta de balanza">Balanza ${_esc(item.etiqueta_balanza_codigo)}</span>`;
    }
    if (item.tipo_escaneo === 'lote_especifico') {
        return `<span class="vta-origen-chip vta-origen-chip--lote" title="Descuenta específicamente de este lote">Lote ${_esc(item.lote_codigo)}</span>`;
    }
    return `<span class="vta-origen-chip vta-origen-chip--normal" title="Descuenta del lote más viejo con stock (FIFO)">Más viejo (FIFO)</span>`;
}

function _opcionesDescuento(item) {
    const listas = CFG.listasDescuento || [];
    if (!listas.length) return null;
    const opcionesListas = listas.map(l => `
        <option value="lista:${_esc(l.nombre)}" data-pct="${l.porcentaje}" ${item.lista_descuento_nombre === l.nombre ? 'selected' : ''}>
            ${_esc(l.nombre)} (${l.porcentaje}%)
        </option>`).join('');
    return `<option value="">— Manual —</option>${opcionesListas}`;
}

function _selectDescuento(item) {
    const opciones = _opcionesDescuento(item);
    if (opciones === null) {
        return `<span class="vta-lista-vacia" title="No hay listas de descuento creadas">—</span>`;
    }
    return `
        <select class="vta-select-inline w-sm" data-item-id="${item.id}" data-campo="lista_descuento" title="Aplicar % de una lista de descuento">
            ${opciones}
        </select>`;
}

function _opcionesOferta(item) {
    const ofertas = _ofertasVigentesParaProducto(item.producto_pk, item.categoria_id);
    if (!ofertas.length) return null;
    const opciones = ofertas.map(o => {
        const pct = _pctEfectivoOferta(o, item.cantidad);
        const etiqueta = o.tipo === 'nxm'
            ? `${o.cantidad_lleva}x${o.cantidad_paga} → ${pct.toFixed(2)}%`
            : `${pct.toFixed(2)}%`;
        return `
        <option value="${_esc(o.nombre)}" ${item.oferta_aplicada_nombre === o.nombre ? 'selected' : ''}>
            ${_esc(o.nombre)} (${etiqueta})
        </option>`;
    }).join('');
    return `<option value="">— Ninguna —</option>${opciones}`;
}

function _selectOferta(item) {
    const opciones = _opcionesOferta(item);
    if (opciones === null) {
        return `<span class="vta-lista-vacia" title="No hay ofertas vigentes para este producto">—</span>`;
    }
    return `
        <select class="vta-select-inline w-sm" data-item-id="${item.id}" data-campo="oferta" title="Oferta vigente para este producto">
            ${opciones}
        </select>`;
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

    cartBody.innerHTML = carrito.map(item => {
        const bloqueado = !!item.etiqueta_balanza_pk;
        const soloLectura = bloqueado ? 'readonly title="Fijado por la etiqueta de balanza — no se puede editar"' : '';
        return `
        <tr data-item-id="${item.id}">
            <td>
                <div class="vta-prod-cell">
                    <span class="vta-prod-nombre">${_esc(item.nombre)}</span>
                    <span class="vta-prod-meta">${_esc(item.codigo)}</span>
                </div>
            </td>
            <td>${_chipOrigen(item)}</td>
            <td><input type="number" min="0.001" step="0.001" class="vta-input-inline w-sm"
                       data-item-id="${item.id}" data-campo="cantidad" value="${item.cantidad}" ${soloLectura}></td>
            <td><input type="number" min="0" step="0.01" class="vta-input-inline w-sm"
                       data-item-id="${item.id}" data-campo="precio" value="${item.precio}" ${soloLectura}></td>
            <td><input type="number" min="0" max="100" step="0.01" class="vta-input-inline w-xs"
                       data-item-id="${item.id}" data-campo="descuento" value="${item.descuento}"></td>
            <td>${_selectDescuento(item)}</td>
            <td>${_selectOferta(item)}</td>
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
        </tr>`;
    }).join('');

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

    const fila = cartBody.querySelector(`tr[data-item-id="${id}"]`);

    if (campo === 'oferta') {
        // Elegir una oferta (o "— Ninguna —") reemplaza cualquier lista de
        // descuento o % manual que hubiera en la línea — una sola fuente
        // de descuento activa a la vez.
        item.oferta_aplicada_nombre = el.value;
        item.lista_descuento_nombre = '';
        const selLista = fila?.querySelector('[data-campo="lista_descuento"]');
        if (selLista) selLista.value = '';
        if (el.value) {
            // Si es "llevá X, pagá Y" y todavía no hay unidades suficientes
            // para que aplique, subimos la cantidad sola — elegir un 3x1
            // con 1 sola unidad en el carrito no serviría de nada.
            const ofertaElegida = (CFG.ofertasVigentes || []).find(o => o.nombre === el.value);
            if (ofertaElegida && ofertaElegida.tipo === 'nxm' && (parseFloat(item.cantidad) || 0) < ofertaElegida.cantidad_lleva) {
                item.cantidad = ofertaElegida.cantidad_lleva;
                const inputCantidad = fila?.querySelector('[data-campo="cantidad"]');
                if (inputCantidad) inputCantidad.value = item.cantidad;
            }
            _recalcularOfertaSeleccionada(item);
        } else {
            item.descuento = 0;
        }
        const inputDesc = fila?.querySelector('[data-campo="descuento"]');
        if (inputDesc) inputDesc.value = item.descuento;
        // La cantidad puede haber cambiado (bump de NXM) — refrescar las
        // opciones de este mismo desplegable para que sus % reflejen la
        // cantidad nueva.
        const opcionesActualizadas = _opcionesOferta(item);
        if (opcionesActualizadas !== null) el.innerHTML = opcionesActualizadas;
    } else if (campo === 'lista_descuento') {
        // El valor viene con prefijo "lista:<nombre>" — reemplaza
        // cualquier oferta u % manual que hubiera en la línea.
        item.oferta_aplicada_nombre = '';
        const selOferta = fila?.querySelector('[data-campo="oferta"]');
        if (selOferta) selOferta.value = '';
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
        if (item.lista_descuento_nombre || item.oferta_aplicada_nombre) {
            item.lista_descuento_nombre = '';
            item.oferta_aplicada_nombre = '';
            const selLista = fila?.querySelector('[data-campo="lista_descuento"]');
            if (selLista) selLista.value = '';
            const selOferta = fila?.querySelector('[data-campo="oferta"]');
            if (selOferta) selOferta.value = '';
        }
    } else if (campo === 'cantidad') {
        item.cantidad = el.value;
        // Si la línea tiene una oferta seleccionada (sola o a mano),
        // recalcular acá es lo que hace que un 2x1/3x2 aparezca o se
        // ajuste solo apenas la cantidad lo amerita.
        _recalcularOfertaSeleccionada(item);
        const inputDesc = fila?.querySelector('[data-campo="descuento"]');
        if (inputDesc) inputDesc.value = item.descuento;
        const selOferta = fila?.querySelector('[data-campo="oferta"]');
        const opciones = selOferta ? _opcionesOferta(item) : null;
        if (selOferta && opciones !== null) selOferta.innerHTML = opciones;
    } else {
        item[campo] = el.value;
    }

    if (fila) {
        const sub = fila.querySelector('.vta-subtotal-cell');
        if (sub) sub.textContent = _fmt(_calcSub(item), item.moneda);
    }
    _actualizarTotales();
    _actualizarBtnContinuar();
}

/* ════════════════════════════════════════════════════════════════
   TOTALES, BADGE Y OFERTA POR MONTO MÍNIMO DE COMPRA
   (Oferta tipo=umbral — se mide sobre el TOTAL de la venta, no sobre
   una línea puntual. Convive con los descuentos de cada línea: la
   base de comparación contra el monto mínimo depende de lo que eligió
   cada oferta al crearla — base_calculo bruto/neto.)
════════════════════════════════════════════════════════════════ */
let ofertaGlobalManualElegida = CFG.ventaEditarOfertaGlobalNombre || '';
let _ofertaGlobalActual = null; // { nombre, porcentaje } aplicada ahora mismo, o null

function _calcularTotalesCarrito() {
    const totalBruto = carrito.reduce((s, i) => s + (parseFloat(i.cantidad) || 0) * (parseFloat(i.precio) || 0), 0);
    const totalNeto  = carrito.reduce((s, i) => s + _calcSub(i), 0);
    return { totalBruto, totalNeto };
}

function _ofertasUmbralCalificadas(totalBruto, totalNeto) {
    return (CFG.ofertasVigentes || [])
        .filter(o => o.tipo === 'umbral' && (o.base_calculo === 'bruto' ? totalBruto : totalNeto) >= parseFloat(o.monto_minimo || 0));
}

function _resolverOfertaGlobal(totalBruto, totalNeto) {
    const calificadas = _ofertasUmbralCalificadas(totalBruto, totalNeto);
    const automaticas = calificadas.filter(o => o.aplicacion === 'automatica');
    if (automaticas.length) {
        // La de mayor % gana — no se acumulan varias ofertas globales.
        return automaticas.reduce((a, b) => parseFloat(b.porcentaje) > parseFloat(a.porcentaje) ? b : a);
    }
    if (ofertaGlobalManualElegida) {
        const sigueCalificando = calificadas.find(o => o.nombre === ofertaGlobalManualElegida && o.aplicacion === 'manual');
        if (sigueCalificando) return sigueCalificando;
        ofertaGlobalManualElegida = ''; // dejó de calificar (bajó el total, por ejemplo)
    }
    return null;
}

function _renderOfertaGlobal(totalBruto, totalNeto, ofertaAplicada) {
    const cont = document.getElementById('vtaOfertaGlobal');
    if (!cont) return;

    if (ofertaAplicada && ofertaAplicada.aplicacion === 'automatica') {
        const monto = totalNeto * parseFloat(ofertaAplicada.porcentaje) / 100;
        cont.style.display = '';
        cont.innerHTML = `<span class="vta-oferta-global-badge">✓ Oferta "${_esc(ofertaAplicada.nombre)}" aplicada: -${ofertaAplicada.porcentaje}% (-${_fmtPeso(monto)})</span>`;
        return;
    }

    const manualesCalificadas = _ofertasUmbralCalificadas(totalBruto, totalNeto).filter(o => o.aplicacion === 'manual');
    if (!manualesCalificadas.length) {
        cont.style.display = 'none';
        cont.innerHTML = '';
        return;
    }

    cont.style.display = '';
    const opciones = manualesCalificadas.map(o => `
        <option value="${_esc(o.nombre)}" ${ofertaGlobalManualElegida === o.nombre ? 'selected' : ''}>
            ${_esc(o.nombre)} (-${o.porcentaje}%)
        </option>`).join('');
    cont.innerHTML = `
        <label class="vta-oferta-global-label">Oferta por monto mínimo disponible:</label>
        <select id="vtaSelectOfertaGlobal" class="vta-select-inline w-sm">
            <option value="">— No aplicar —</option>
            ${opciones}
        </select>`;
    document.getElementById('vtaSelectOfertaGlobal').addEventListener('change', (e) => {
        ofertaGlobalManualElegida = e.target.value;
        _actualizarTotales();
    });
}

function _actualizarTotales() {
    const { totalBruto, totalNeto } = _calcularTotalesCarrito();
    const ofertaGlobal = _resolverOfertaGlobal(totalBruto, totalNeto);
    const pctGlobal = ofertaGlobal ? (parseFloat(ofertaGlobal.porcentaje) || 0) : 0;
    const totalFinal = totalNeto * (1 - pctGlobal / 100);

    _ofertaGlobalActual = ofertaGlobal ? { nombre: ofertaGlobal.nombre, porcentaje: pctGlobal } : null;

    if (totalItemsEl) totalItemsEl.textContent = carrito.length;
    if (totalMontoEl) totalMontoEl.textContent = _fmtPeso(totalFinal);
    if (badge) { badge.textContent = carrito.length; badge.style.display = carrito.length ? 'inline-flex' : 'none'; }

    _renderOfertaGlobal(totalBruto, totalNeto, ofertaGlobal);
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
            etiqueta_balanza_pk: item.etiqueta_balanza_pk || null,
            cantidad:        item.cantidad,
            precio_unitario: item.precio,
            moneda:          item.moneda,
            descuento_pct:   item.descuento,
            lista_descuento_nombre: item.lista_descuento_nombre || '',
            oferta_aplicada_nombre: item.oferta_aplicada_nombre || '',
            condicion_pago:  item.condicion,
            referencia:      item.referencia,
        }));

        try {
            const res  = await fetch(CFG.urlGuardarBorrador, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                body:    JSON.stringify({
                    items: itemsPayload,
                    descuento_global_pct: _ofertaGlobalActual ? _ofertaGlobalActual.porcentaje : 0,
                    oferta_global_nombre: _ofertaGlobalActual ? _ofertaGlobalActual.nombre : '',
                }),
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