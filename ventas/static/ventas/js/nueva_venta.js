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

// El cliente es UNO SOLO para toda la venta (no por ítem) — no tiene
// sentido de negocio que un producto sea para un cliente y otro para
// "Consumidor Final", y complicaba la facturación. Se elige una vez
// (ver _bindClienteVentaInput) y se replica a cada ítem del payload,
// así el backend/DB (que sigue guardando cliente por ItemVenta) no
// necesitó cambiar. Si un borrador viejo llegara a tener clientes
// mezclados por ítem, acá se toma el primero no vacío como punto de
// partida y _sincronizarClienteEnCarrito() lo empareja en todos.
let clienteVenta = { pk: null, nombre: '' };
for (const fila of (CFG.itemsIniciales || [])) {
    if (fila.cliente_pk) { clienteVenta = { pk: fila.cliente_pk, nombre: fila.cliente_nombre || '' }; break; }
}

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
    cliente_pk:      clienteVenta.pk,
    cliente_nombre:  clienteVenta.nombre,
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
const cartCount      = document.getElementById('vtaCartCount');
const btnCobrar      = document.getElementById('vtaBtnCobrar');
const badge          = document.getElementById('vtaBadge');
const totalItemsEl   = document.getElementById('vtaTotalItems');
const totalMontoEl   = document.getElementById('vtaTotalMonto');
const clienteVentaInput    = document.getElementById('vtaClienteInput');
const clienteVentaDropdown = document.getElementById('vtaClienteDropdown');
const clienteVentaClear    = document.getElementById('vtaClienteClear');
const clienteVentaSpinner  = document.getElementById('vtaClienteSpinner');

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
    _navResIdx = -1;   // nueva lista → nada resaltado con el teclado
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
    // Con la guía de atajos abierta, no interceptar nada acá — que llegue
    // al handler global (Esc / F1 la cierran).
    if (document.getElementById('vtaAtajosPanel')?.classList.contains('is-open')) return;

    const abierto = searchDropdown.classList.contains('open');
    const ops     = _navOpcionesDropdown();

    // Estas teclas las resuelve el buscador por completo — que no lleguen
    // también al handler global de atajos (si no, ↓ movería la selección
    // dos veces al pasar del buscador al carrito).
    if (['Escape', 'ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) e.stopPropagation();

    if (e.key === 'Escape') {
        if (abierto) { searchDropdown.classList.remove('open'); _navResIdx = -1; }
        else searchInput.value = '';
        return;
    }

    // ↓/↑ con el desplegable abierto → moverse entre resultados.
    // ↓ con el desplegable cerrado y carrito con ítems → pasar al carrito.
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (abierto && ops.length) {
            _navResIdx = Math.min(ops.length - 1, _navResIdx + 1);
            _navPintarDropdown();
        } else if (carrito.length) {
            _navEntrarAlCarrito();
        }
        return;
    }
    if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (abierto && ops.length) {
            _navResIdx = Math.max(0, _navResIdx - 1);
            _navPintarDropdown();
        }
        return;
    }

    if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(searchTimer);
        if (abierto && _navResIdx >= 0 && ops[_navResIdx]) {
            ops[_navResIdx].click();   // reusa el handler de click del ítem
            return;
        }
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
            cliente_pk:      clienteVenta.pk,
            cliente_nombre:  clienteVenta.nombre,
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
        cliente_pk:      clienteVenta.pk,
        cliente_nombre:  clienteVenta.nombre,
        cantidad:        1,
        // Para avisar en el momento si la cantidad supera el stock
        // disponible, sin esperar a intentar confirmar la venta (ver
        // _stockInsuficiente). gestiona_stock=false (servicios, productos
        // sin control de inventario) nunca se valida.
        stock_actual:    fila.gestiona_stock === false ? null : parseFloat(fila.stock_actual),
        gestiona_stock:  fila.gestiona_stock !== false,
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
    const quitado = _navSelId === id;
    carrito = carrito.filter(i => i.id !== id);
    if (quitado) _navSelId = null;
    _renderCarrito();
}

/* ════════════════════════════════════════════════════════════════
   NAVEGACIÓN POR TECLADO — para trabajar sin mouse (así trabaja el
   cajero: una mano en el lector, la otra en el teclado). El buscador
   queda siempre activo para el lector; con ↓ se pasa al carrito.
   La guía de atajos está en #vtaAtajosPanel (botón "⌨ Atajos").
════════════════════════════════════════════════════════════════ */
let _navSelId = null;   // id del ítem del carrito "elegido" con el teclado
let _navResIdx = -1;    // índice resaltado en el desplegable del buscador

function _navEnCampo(el) {
    if (!el) return false;
    return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
        || el.tagName === 'SELECT' || el.isContentEditable;
}

function _navFilas() {
    return Array.from(cartBody.querySelectorAll('.vta-cart-row'));
}

function _navPintarSeleccion(scroll) {
    _navFilas().forEach(f => {
        const sel = parseInt(f.dataset.itemId, 10) === _navSelId;
        f.classList.toggle('is-selected', sel);
        if (sel && scroll) f.scrollIntoView({ block: 'nearest' });
    });
}

function _navSeleccionar(id, scroll) {
    _navSelId = id;
    if (_navEnCampo(document.activeElement)) document.activeElement.blur();
    _navPintarSeleccion(scroll);
}

function _navEntrarAlCarrito() {
    if (!carrito.length) return;
    if (_navSelId == null || !carrito.some(i => i.id === _navSelId)) {
        _navSeleccionar(carrito[0].id, true);
    } else {
        _navSeleccionar(_navSelId, true);
    }
}

function _navMover(delta) {
    const filas = _navFilas();
    if (!filas.length) return;
    let idx = filas.findIndex(f => parseInt(f.dataset.itemId, 10) === _navSelId);
    if (idx === -1) idx = delta > 0 ? -1 : filas.length;
    idx = Math.min(filas.length - 1, Math.max(0, idx + delta));
    _navSeleccionar(parseInt(filas[idx].dataset.itemId, 10), true);
}

function _navVolverAlBuscador() {
    _navSelId = null;
    _navPintarSeleccion(false);
    searchInput.focus();
}

function _navAjustarCantidad(delta) {
    const item = carrito.find(i => i.id === _navSelId);
    if (!item || item.etiqueta_balanza_pk) return;   // balanza: cantidad fija
    const nueva = Math.round(((parseFloat(item.cantidad) || 0) + delta) * 1000) / 1000;
    if (nueva < 0.001) { _quitarItem(item.id); return; }
    item.cantidad = nueva;
    _recalcularOfertaSeleccionada(item);
    _renderCarrito();
}

function _navQuitarSeleccion() {
    const filas = _navFilas();
    const idx = filas.findIndex(f => parseInt(f.dataset.itemId, 10) === _navSelId);
    if (idx === -1) return;
    _quitarItem(_navSelId);   // ya deja _navSelId en null
    const nuevas = _navFilas();
    if (nuevas.length) {
        _navSeleccionar(parseInt(nuevas[Math.min(idx, nuevas.length - 1)].dataset.itemId, 10), true);
    }
}

function _navToggleAdv() {
    const item = carrito.find(i => i.id === _navSelId);
    if (!item || item.etiqueta_balanza_pk) return;
    item.advOpen = !item.advOpen;
    _renderCarrito();
    if (item.advOpen) {
        const fila = cartBody.querySelector(`.vta-cart-row[data-item-id="${item.id}"]`);
        fila?.querySelector('[data-campo="descuento"]')?.focus();
    }
}

/* ── Desplegable del buscador ── */
function _navOpcionesDropdown() {
    return Array.from(searchDropdown.querySelectorAll('.vta-dropdown-item[data-idx]'));
}
function _navPintarDropdown() {
    const ops = _navOpcionesDropdown();
    ops.forEach((el, i) => el.classList.toggle('is-kbd', i === _navResIdx));
    if (ops[_navResIdx]) ops[_navResIdx].scrollIntoView({ block: 'nearest' });
}

/* ── Guía de atajos ── */
function _navToggleAtajos(forzar) {
    const panel = document.getElementById('vtaAtajosPanel');
    if (!panel) return;
    const abrir = forzar != null ? forzar : !panel.classList.contains('is-open');
    panel.classList.toggle('is-open', abrir);
}

/* ════════════════════════════════════════════════════════════════
   AUTOCOMPLETE DE CLIENTE — uno solo para toda la venta
════════════════════════════════════════════════════════════════ */
let clienteSearchTimer;

// Empareja el cliente elegido en TODOS los ítems ya cargados en el
// carrito (no solo en los que se agreguen de ahora en más).
function _sincronizarClienteEnCarrito() {
    carrito.forEach(item => {
        item.cliente_pk     = clienteVenta.pk;
        item.cliente_nombre = clienteVenta.nombre;
    });
}

// Scoring de riesgo de pago del cliente elegido — solo informativo acá
// (el carrito no cobra); el aviso/bloqueo real está en el panel de cobro
// (detalle_venta.js). {banda, label, sinHistorial, scoring} o null.
let clienteVentaScoring = null;

function _renderClienteScoringChipCarrito() {
    const chip = document.getElementById('vtaClienteScoringChip');
    if (!chip) return;
    if (!clienteVenta.pk || !clienteVentaScoring) {
        chip.hidden = true;
        chip.textContent = '';
        return;
    }
    chip.hidden = false;
    chip.className = 'vdt-sco-chip';
    if (clienteVentaScoring.sinHistorial) {
        chip.classList.add('vdt-sco-chip--sinhist');
        chip.textContent = 'Sin historial de crédito';
        return;
    }
    const banda = clienteVentaScoring.banda || 'excelente';
    chip.classList.add('vdt-sco-chip--' + banda);
    chip.textContent = 'Riesgo de pago: ' + (clienteVentaScoring.label || banda) +
        (clienteVentaScoring.scoring != null ? ' (' + clienteVentaScoring.scoring + ')' : '');
}

function _bindClienteVentaInput() {
    if (!clienteVentaInput || !clienteVentaDropdown) return;
    clienteVentaInput.value = clienteVenta.nombre;
    clienteVentaClear.style.display = clienteVenta.pk ? 'inline-flex' : 'none';
    _renderClienteScoringChipCarrito();

    clienteVentaInput.addEventListener('input', () => {
        clearTimeout(clienteSearchTimer);
        const q = clienteVentaInput.value.trim();
        clienteVenta = { pk: null, nombre: '' };
        clienteVentaScoring = null;
        _renderClienteScoringChipCarrito();
        clienteVentaClear.style.display = 'none';
        _sincronizarClienteEnCarrito();

        if (!q) {
            clienteVentaDropdown.classList.remove('open');
            clienteVentaDropdown.innerHTML = '';
            clienteVentaSpinner.style.display = 'none';
            return;
        }
        clienteSearchTimer = setTimeout(async () => {
            clienteVentaSpinner.style.display = 'block';
            try {
                const res  = await fetch(`${CFG.urlBuscarCliente}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                // Guarda contra respuestas que llegan fuera de orden: si el
                // usuario ya siguió escribiendo, esta respuesta quedó vieja.
                if (clienteVentaInput.value.trim() !== q) return;
                const results = data.results || [];

                clienteVentaDropdown.innerHTML = results.length
                    ? results.map((c, i) => `
                        <div class="vta-cli-option" data-idx="${i}" data-nombre="${_esc(c.nombre)}">
                            <div class="vta-cli-option-top">
                                <span class="vta-cli-option-nombre">${_esc(c.nombre)}</span>
                                ${c.scoring_banda && !c.scoring_sin_historial
                                    ? `<span class="vdt-sco-mini vdt-sco-mini--${c.scoring_banda}">${_esc(c.scoring_banda_label || '')}</span>`
                                    : ''}
                                ${c.codigo ? `<span class="vta-dropdown-item-codigo">${_esc(c.codigo)}</span>` : ''}
                            </div>
                            ${c.doc ? `
                            <div class="vta-cli-option-doc">
                                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                                    <rect x="1.5" y="3.5" width="13" height="9" rx="1.3" stroke="currentColor" stroke-width="1.2"/>
                                    <circle cx="5" cy="8" r="1.15" stroke="currentColor" stroke-width="1"/>
                                    <path d="M8.3 6.7H12M8.3 9.3H10.6" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
                                </svg>
                                ${_esc(c.doc)}
                            </div>` : ''}
                        </div>`).join('')
                    : `<div class="vta-dropdown-empty">Sin resultados para "${_esc(q)}"</div>`;

                clienteVentaDropdown.querySelectorAll('.vta-cli-option').forEach(el => {
                    el.addEventListener('click', () => {
                        const c = results[parseInt(el.dataset.idx, 10)];
                        clienteVenta = { pk: c.pk, nombre: el.dataset.nombre };
                        clienteVentaScoring = {
                            scoring:      c.scoring,
                            banda:        c.scoring_banda,
                            label:        c.scoring_banda_label,
                            sinHistorial: c.scoring_sin_historial,
                        };
                        clienteVentaInput.value = el.dataset.nombre;
                        clienteVentaClear.style.display = 'inline-flex';
                        clienteVentaDropdown.classList.remove('open');
                        clienteVentaDropdown.innerHTML = '';
                        _sincronizarClienteEnCarrito();
                        _renderClienteScoringChipCarrito();
                    });
                });
                clienteVentaDropdown.classList.add('open');
            } catch { /* silencioso */ }
            finally { clienteVentaSpinner.style.display = 'none'; }
        }, 260);
    });

    clienteVentaClear.addEventListener('click', () => {
        clienteVenta = { pk: null, nombre: '' };
        clienteVentaScoring = null;
        clienteVentaInput.value = '';
        clienteVentaClear.style.display = 'none';
        _sincronizarClienteEnCarrito();
        _renderClienteScoringChipCarrito();
        clienteVentaInput.focus();
    });
    // El cierre al clickear afuera ya lo maneja el listener global de
    // document más arriba en este archivo (busca .vta-cli-dropdown.open).
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

/* Opciones de los desplegables del panel "Descuento / oferta" de cada
   fila (se despliega por ítem, no es una columna siempre visible). */
function _opcionesListaAdv(item) {
    const listas = CFG.listasDescuento || [];
    return listas.map(l => `
        <option value="lista:${_esc(l.nombre)}" data-pct="${l.porcentaje}" ${item.lista_descuento_nombre === l.nombre ? 'selected' : ''}>
            ${_esc(l.nombre)} (${l.porcentaje}%)
        </option>`).join('');
}
function _selectListaAdv(item) {
    if (!(CFG.listasDescuento || []).length) {
        return `<select data-campo="lista_descuento" disabled><option>— sin listas cargadas —</option></select>`;
    }
    return `<select data-campo="lista_descuento"><option value="">— Manual —</option>${_opcionesListaAdv(item)}</select>`;
}
function _opcionesOfertaAdv(item) {
    const ofertas = _ofertasVigentesParaProducto(item.producto_pk, item.categoria_id);
    return ofertas.map(o => {
        const pct = _pctEfectivoOferta(o, item.cantidad);
        const etiqueta = o.tipo === 'nxm'
            ? `${o.cantidad_lleva}x${o.cantidad_paga} → ${pct.toFixed(0)}%`
            : `${pct.toFixed(0)}%`;
        return `<option value="${_esc(o.nombre)}" ${item.oferta_aplicada_nombre === o.nombre ? 'selected' : ''}>${_esc(o.nombre)} (${etiqueta})</option>`;
    }).join('');
}
function _selectOfertaAdv(item) {
    const ofertas = _ofertasVigentesParaProducto(item.producto_pk, item.categoria_id);
    if (!ofertas.length) {
        return `<select data-campo="oferta" disabled><option>— sin ofertas para este producto —</option></select>`;
    }
    return `<select data-campo="oferta"><option value="">— Ninguna —</option>${_opcionesOfertaAdv(item)}</select>`;
}

function _tieneDesc(item) {
    return item.descuento != null && parseFloat(item.descuento) > 0;
}
function _txtTagDesc(item) {
    const pct = parseFloat(item.descuento) || 0;
    const pctTxt = Number.isInteger(pct) ? String(pct) : String(Math.round(pct * 100) / 100);
    const fuente = item.oferta_aplicada_nombre || item.lista_descuento_nombre || '';
    return `−${pctTxt}%${fuente ? ' · ' + fuente : ''}`;
}

/** Avisa apenas se carga una cantidad mayor al stock disponible, en vez
 *  de dejar pasar al detalle y recién enterarse al confirmar la venta
 *  (que sí valida esto en serio, contra los lotes reales — este chequeo
 *  del carrito es solo un aviso temprano con el mismo dato que ya
 *  trajo la búsqueda, no reemplaza esa validación). */
function _stockInsuficiente(item) {
    if (!item.gestiona_stock || item.stock_actual == null) return false;
    return (parseFloat(item.cantidad) || 0) > item.stock_actual;
}

function _carritoTieneStockInsuficiente() {
    return carrito.some(_stockInsuficiente);
}

/** Muestra/oculta el aviso de stock insuficiente de una fila ya
 *  renderizada, sin reconstruirla — se llama en cada tecleo de cantidad
 *  (ver _onCampoCambiado) para no perder el foco del input. */
function _actualizarAvisoStockFila(fila, item) {
    if (!fila) return;
    const insuficiente = _stockInsuficiente(item);
    fila.classList.toggle('is-alert', insuficiente);
    const inputCantidad = fila.querySelector('.vta-stepper input');
    if (inputCantidad) inputCantidad.classList.toggle('vta-input-error', insuficiente);

    let aviso = fila.querySelector('.vta-cart-alert-msg');
    if (insuficiente) {
        if (!aviso) {
            aviso = document.createElement('div');
            aviso.className = 'vta-cart-alert-msg';
            const mid = fila.querySelector('.vta-cart-row-mid');
            if (mid) mid.insertAdjacentElement('afterend', aviso);
        }
        aviso.textContent = `Stock disponible: ${item.stock_actual}`;
    } else if (aviso) {
        aviso.remove();
    }
}

/** Refresca el chip "−X%" colapsado de una fila sin reconstruirla. */
function _refrescarTagDesc(fila, item) {
    const cont = fila.querySelector('.vta-cart-row-tags');
    if (!cont) return;
    let chip = cont.querySelector('.vta-tag-desc');
    if (_tieneDesc(item)) {
        if (!chip) {
            chip = document.createElement('span');
            chip.className = 'vta-tag-desc';
            cont.prepend(chip);
        }
        chip.textContent = _txtTagDesc(item);
    } else if (chip) {
        chip.remove();
    }
}

function _renderCarrito() {
    if (!carrito.length) {
        cartBody.innerHTML = '';
        cartEmpty.style.display  = 'block';
        cartFooter.style.display = 'none';
        if (cartCount) cartCount.textContent = '0 ítems';
        _navSelId = null;
        _actualizarBtnContinuar();
        return;
    }
    cartEmpty.style.display  = 'none';
    cartFooter.style.display = 'flex';

    cartBody.innerHTML = carrito.map(item => {
        const bloqueado = !!item.etiqueta_balanza_pk;
        const ro    = bloqueado ? 'readonly' : '';
        const roStep = bloqueado ? 'disabled' : '';
        const sub  = _calcSub(item);
        const base = (parseFloat(item.cantidad) || 0) * (parseFloat(item.precio) || 0);
        const insuf = _stockInsuficiente(item);
        const tag  = _tieneDesc(item) ? `<span class="vta-tag-desc">${_esc(_txtTagDesc(item))}</span>` : '';

        return `
        <div class="vta-cart-row${insuf ? ' is-alert' : ''}" data-item-id="${item.id}">
            <div class="vta-cart-row-top">
                ${_chipOrigen(item)}
                <div class="vta-cart-row-name">
                    <b>${_esc(item.nombre)}</b>
                    <span>${_esc(item.codigo)}</span>
                </div>
                <button type="button" class="vta-cart-row-x" data-act="quitar" title="Quitar">✕</button>
            </div>
            <div class="vta-cart-row-mid">
                <div class="vta-stepper">
                    <button type="button" data-act="menos" ${roStep} aria-label="Menos uno">−</button>
                    <input type="number" min="0.001" step="0.001" data-campo="cantidad" value="${item.cantidad}" ${ro}${bloqueado ? ' title="Fijado por la etiqueta de balanza"' : ''}>
                    <button type="button" data-act="mas" ${roStep} aria-label="Más uno">＋</button>
                </div>
                <div class="vta-cart-row-price">
                    <span>×</span>
                    <input type="number" min="0" step="0.01" data-campo="precio" value="${item.precio}" ${ro}>
                </div>
                <div class="vta-cart-row-sub">${_tieneDesc(item) ? `<s>${_fmt(base, item.moneda)}</s>` : ''}${_fmt(sub, item.moneda)}</div>
            </div>
            ${insuf ? `<div class="vta-cart-alert-msg">Stock disponible: ${item.stock_actual}</div>` : ''}
            ${bloqueado
                ? (tag ? `<div class="vta-cart-row-tags">${tag}</div>` : '')
                : `
            <div class="vta-cart-row-tags">
                ${tag}
                <button type="button" class="vta-cart-row-edit" data-act="adv">${item.advOpen ? 'Ocultar' : 'Descuento / oferta'}</button>
            </div>
            <div class="vta-cart-row-adv${item.advOpen ? ' open' : ''}">
                <div>
                    <label>Descuento manual %</label>
                    <input type="number" min="0" max="100" step="0.01" data-campo="descuento" value="${item.descuento}">
                </div>
                <div>
                    <label>Lista de descuento</label>
                    ${_selectListaAdv(item)}
                </div>
                <div class="full">
                    <label>Oferta vigente para este producto</label>
                    ${_selectOfertaAdv(item)}
                </div>
            </div>`}
        </div>`;
    }).join('');

    cartBody.querySelectorAll('.vta-cart-row').forEach(fila => {
        const id   = parseInt(fila.dataset.itemId, 10);
        const item = carrito.find(i => i.id === id);
        if (!item) return;

        // Click en la fila (fuera de un control) → elegirla (para después
        // ajustarla con el teclado).
        fila.addEventListener('click', e => {
            if (!e.target.closest('button, input, select, a')) _navSeleccionar(id, false);
        });

        fila.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', () => {
            const act = b.dataset.act;
            if (act === 'quitar') return _quitarItem(id);
            if (act === 'adv') { item.advOpen = !item.advOpen; _renderCarrito(); return; }
            if (act === 'menos') {
                const nueva = (parseFloat(item.cantidad) || 0) - 1;
                if (nueva < 0.001) { _quitarItem(id); return; }
                item.cantidad = nueva;
                _recalcularOfertaSeleccionada(item);
                _renderCarrito();
            }
            if (act === 'mas') {
                item.cantidad = (parseFloat(item.cantidad) || 0) + 1;
                _recalcularOfertaSeleccionada(item);
                _renderCarrito();
            }
        }));

        fila.querySelectorAll('[data-campo]').forEach(el => {
            const ev = el.tagName === 'SELECT' ? 'change' : 'input';
            el.addEventListener(ev, () => _onCampoCambiado(el, fila, item));
        });
    });

    // El ítem elegido con el teclado pudo haberse quitado → limpiar;
    // si no, volver a marcarlo (el re-render borró la clase).
    if (_navSelId != null && !carrito.some(i => i.id === _navSelId)) _navSelId = null;
    _navPintarSeleccion(false);

    _actualizarTotales();
    _actualizarBtnContinuar();
}

function _onCampoCambiado(el, fila, item) {
    if (!item) return;
    const campo = el.dataset.campo;

    // Los desplegables (lista / oferta) se confirman al elegir → re-render
    // completo (el panel "Descuento / oferta" queda abierto igual porque
    // item.advOpen sigue en true).
    if (campo === 'oferta') {
        // Elegir una oferta reemplaza cualquier lista o % manual — una sola
        // fuente de descuento activa por línea.
        item.oferta_aplicada_nombre = el.value;
        item.lista_descuento_nombre = '';
        if (el.value) {
            const ofertaElegida = (CFG.ofertasVigentes || []).find(o => o.nombre === el.value);
            if (ofertaElegida && ofertaElegida.tipo === 'nxm' && (parseFloat(item.cantidad) || 0) < ofertaElegida.cantidad_lleva) {
                item.cantidad = ofertaElegida.cantidad_lleva;
            }
            _recalcularOfertaSeleccionada(item);
        } else {
            item.descuento = 0;
        }
        _renderCarrito();
        return;
    }
    if (campo === 'lista_descuento') {
        item.oferta_aplicada_nombre = '';
        const [, ...resto] = el.value.split(':');
        item.lista_descuento_nombre = el.value ? resto.join(':') : '';
        if (el.value) {
            const opt = el.selectedOptions[0];
            item.descuento = opt ? opt.dataset.pct : item.descuento;
        } else {
            item.descuento = 0;
        }
        _renderCarrito();
        return;
    }

    // cantidad / precio / descuento — actualización en vivo, sin reconstruir
    // la fila (para no perder el foco mientras se tipea).
    if (campo === 'cantidad') {
        item.cantidad = el.value;
        _recalcularOfertaSeleccionada(item);
        const inputDesc = fila.querySelector('[data-campo="descuento"]');
        if (inputDesc && document.activeElement !== inputDesc) inputDesc.value = item.descuento;
        const selOferta = fila.querySelector('[data-campo="oferta"]');
        if (selOferta && !selOferta.disabled) {
            const cur = selOferta.value;
            selOferta.innerHTML = `<option value="">— Ninguna —</option>${_opcionesOfertaAdv(item)}`;
            selOferta.value = cur;
        }
        _actualizarAvisoStockFila(fila, item);
    } else if (campo === 'precio') {
        item.precio = el.value;
    } else if (campo === 'descuento') {
        item.descuento = el.value;
        item.lista_descuento_nombre = '';
        item.oferta_aplicada_nombre = '';
        const selLista = fila.querySelector('[data-campo="lista_descuento"]');
        if (selLista) selLista.value = '';
        const selOferta = fila.querySelector('[data-campo="oferta"]');
        if (selOferta) selOferta.value = '';
    } else {
        item[campo] = el.value;
    }

    const subEl = fila.querySelector('.vta-cart-row-sub');
    if (subEl) {
        const base = (parseFloat(item.cantidad) || 0) * (parseFloat(item.precio) || 0);
        subEl.innerHTML = (_tieneDesc(item) ? `<s>${_fmt(base, item.moneda)}</s>` : '') + _fmt(_calcSub(item), item.moneda);
    }
    _refrescarTagDesc(fila, item);
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
    if (cartCount) cartCount.textContent = carrito.length + (carrito.length === 1 ? ' ítem' : ' ítems');
    if (totalMontoEl) totalMontoEl.textContent = _fmtPeso(totalFinal);
    if (badge) { badge.textContent = carrito.length; badge.style.display = carrito.length ? 'inline-flex' : 'none'; }

    _renderOfertaGlobal(totalBruto, totalNeto, ofertaGlobal);
}
function _actualizarBtnContinuar() {
    if (btnCobrar) {
        // "Ir al cobro" es solo un atajo de scroll/foco (la columna de
        // cobro ya está siempre a la vista) — se deshabilita nada más
        // cuando el carrito está vacío.
        btnCobrar.disabled = carrito.length === 0;
    }
    _notificarCambioCarrito();
}

/* ════════════════════════════════════════════════════════════════
   API DEL CARRITO — la usa el panel flotante de cobro (panel_cobro.js).
   El carrito ya no navega a otra pantalla: "Cobrar" abre el panel.
════════════════════════════════════════════════════════════════ */
function _itemsPayload() {
    return carrito.map(item => ({
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
}

let _cambioCarritoCbs = [];
function _notificarCambioCarrito() {
    _cambioCarritoCbs.forEach(cb => { try { cb(); } catch (e) { console.error(e); } });
}

window.ventaCarrito = {
    estaVacio: () => carrito.length === 0,
    tieneStockInsuficiente: () => _carritoTieneStockInsuficiente(),
    onChange: (cb) => { if (typeof cb === 'function') _cambioCarritoCbs.push(cb); },

    reset() {
        carrito = [];
        nextId = 0;
        clienteVenta = { pk: null, nombre: '' };
        clienteVentaScoring = null;
        ofertaGlobalManualElegida = '';
        if (clienteVentaInput) clienteVentaInput.value = '';
        if (clienteVentaClear) clienteVentaClear.style.display = 'none';
        _renderClienteScoringChipCarrito();
        _renderCarrito();
    },

    /**
     * Espeja al carrito el cliente elegido en el panel flotante de cobro
     * (pestaña General → Cliente). Mantiene una sola fuente de verdad:
     * el cliente del carrito, que es el que viaja en cada guardado de
     * borrador (_itemsPayload). El sentido carrito → panel ya lo cubre
     * el fragmento que sirve el server (cliente_unico_venta).
     */
    setCliente(pk, nombre, scoring) {
        clienteVenta = { pk: pk || null, nombre: nombre || '' };
        clienteVentaScoring = pk ? (scoring || null) : null;
        if (clienteVentaInput) clienteVentaInput.value = clienteVenta.nombre;
        if (clienteVentaClear) {
            clienteVentaClear.style.display = clienteVenta.pk ? 'inline-flex' : 'none';
        }
        _sincronizarClienteEnCarrito();
        _renderClienteScoringChipCarrito();
    },

    /**
     * Guarda/actualiza el borrador de esta venta.
     *   - `ventaPkExistente` (del panel) o CFG.ventaEditarPk (modo Historial):
     *     actualiza en el mismo lugar (mismo pk/número).
     *   - si no hay ninguno: crea uno nuevo.
     * Devuelve la respuesta del server: { ok, pk, numero, total, error? }
     */
    async guardarBorrador(ventaPkExistente) {
        const pk  = CFG.ventaEditarPk || ventaPkExistente || null;
        const url = pk ? CFG.urlActualizarBorrador : CFG.urlGuardarBorrador;
        const body = {
            items: _itemsPayload(),
            descuento_global_pct: _ofertaGlobalActual ? _ofertaGlobalActual.porcentaje : 0,
            oferta_global_nombre: _ofertaGlobalActual ? _ofertaGlobalActual.nombre : '',
        };
        if (pk) body.venta_pk = pk;

        const res  = await fetch(url, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
            body:    JSON.stringify(body),
        });
        return res.json();
    },
};

// El botón "Ir al cobro" (#vtaBtnCobrar) lo maneja panel_cobro.js: la
// columna de cobro ya está siempre visible, así que solo hace scroll/foco.

/* ════════════════════════════════════════════════════════════════
   CANCELAR (solo relevante en modo edición — ver ventaEditarPk)
   Si no se intercepta, "Cancelar" es un link normal y la venta
   reactivada por "Editar" en el Historial queda como Borrador
   fantasma para siempre (no vuelve a Anulada, no aparece en ningún
   lado). Acá se revierte antes de salir de la página.
════════════════════════════════════════════════════════════════ */
const btnCancelarCarrito = document.getElementById('vtaBtnCancelar');
if (btnCancelarCarrito && CFG.ventaEditarPk) {
    btnCancelarCarrito.addEventListener('click', async (e) => {
        e.preventDefault();
        try {
            await fetch(CFG.urlEliminarBorrador, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                body:    JSON.stringify({ venta_pk: CFG.ventaEditarPk }),
            });
        } catch {
            // Si falla la red, igual navegamos — el barrido de borradores
            // vencidos la revierte sola más tarde (ver descartar_borradores_vencidos).
        }
        window.location.href = CFG.urlHistorial;
    });
}

/* ════════════════════════════════════════════════════════════════
   ATAJOS DE TECLADO — handler global
   ──────────────────────────────────────────────────────────────
   F2  buscador · F3  cobro · F4  confirmar (lo maneja panel_cobro.js)
   Con una fila elegida (y sin tipear en un campo):
     ↑↓  moverse · + −  cantidad · Supr  quitar · Enter  desc/oferta
   ?  abre/cierra la guía · Esc  vuelve al buscador
════════════════════════════════════════════════════════════════ */
document.addEventListener('keydown', e => {
    const panelAtajos = document.getElementById('vtaAtajosPanel');
    const guiaAbierta = panelAtajos && panelAtajos.classList.contains('is-open');

    // Con la guía abierta: Esc/F1/? la cierran; el resto de las teclas de
    // navegación se ignoran (para no operar el carrito que está detrás).
    if (guiaAbierta) {
        if (['Escape', 'F1', '?'].includes(e.key)) { e.preventDefault(); _navToggleAtajos(false); }
        else if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', '+', '-', '=', 'Delete', 'Enter'].includes(e.key)) {
            e.preventDefault();
        }
        return;
    }

    // F1 → guía de atajos (funciona desde cualquier lado). También "?"
    // cuando no estás escribiendo en un campo.
    if (e.key === 'F1' || (e.key === '?' && !_navEnCampo(document.activeElement))) {
        e.preventDefault();
        _navToggleAtajos();
        return;
    }

    if (e.key === 'F2') {
        e.preventDefault();
        _navSelId = null;
        _navPintarSeleccion(false);
        searchInput.focus();
        searchInput.select();
        return;
    }
    if (e.key === 'F3') {
        e.preventDefault();
        const btn = document.getElementById('vtaBtnCobrar');
        if (btn && !btn.disabled) btn.click();
        return;
    }
    // Esc dentro de un campo de la fila (ej. el % de descuento que se abre
    // con Enter) → salir del campo y quedarse con la fila elegida.
    if (e.key === 'Escape' && _navEnCampo(document.activeElement)
        && document.activeElement.closest && document.activeElement.closest('.vta-cart-row')) {
        e.preventDefault();
        document.activeElement.blur();
        _navPintarSeleccion(true);
        return;
    }

    // De acá para abajo: solo con una fila elegida y fuera de un campo.
    if (_navSelId == null || _navEnCampo(document.activeElement)) return;

    switch (e.key) {
        case 'ArrowDown':  e.preventDefault(); _navMover(1);  return;
        case 'ArrowUp':    e.preventDefault(); _navMover(-1); return;
        case '+':
        case '=':
        case 'ArrowRight': e.preventDefault(); _navAjustarCantidad(1);  return;
        case '-':
        case 'ArrowLeft':  e.preventDefault(); _navAjustarCantidad(-1); return;
        case 'Delete':     e.preventDefault(); _navQuitarSeleccion();   return;
        case 'Enter':      e.preventDefault(); _navToggleAdv();         return;
        case 'Escape':     e.preventDefault(); _navVolverAlBuscador();  return;
    }

    // Tipear una letra/número con una fila elegida → volver a escanear
    // sin perder ese primer carácter (típico: el lector dispara con la
    // fila todavía marcada).
    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        _navSelId = null;
        _navPintarSeleccion(false);
        searchInput.focus();
        searchInput.value = e.key;
        searchInput.dispatchEvent(new Event('input'));
    }
});

const _atajosBtn   = document.getElementById('vtaAtajosBtn');
const _atajosPanel = document.getElementById('vtaAtajosPanel');
if (_atajosBtn)   _atajosBtn.addEventListener('click', () => _navToggleAtajos());
if (_atajosPanel) {
    _atajosPanel.addEventListener('click', e => {
        if (e.target === _atajosPanel || e.target.closest('#vtaAtajosClose')) _navToggleAtajos(false);
    });
}

/* ════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */
_bindClienteVentaInput();
_renderCarrito();
searchInput.focus();

} // if (searchInput)