/* ================================================================
   Maqueta Nueva Venta — lógica (sin servidor)
   ----------------------------------------------------------------
   Reimplementa en el navegador el mismo comportamiento del flujo
   real (carrito + panel de cobro), pero con datos de mentira y
   una interfaz nueva: el cobro está anclado a la derecha y SIEMPRE
   visible. No hay ningún panel flotante.
   ================================================================ */
'use strict';

(function () {

const M = window.MOCK;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

/* ---------------- helpers ---------------- */
const hoyISO = () => new Date().toISOString().slice(0, 10);
function fmt(n) {
  return '$ ' + (Number(n) || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
// Búsqueda tolerante a acentos: "martin" encuentra "Martín".
function norm(s) {
  return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}
let toastT;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('show'), 3200);
}

/* ---------------- estado ---------------- */
const estado = {
  carrito: [],
  nextId: 1,
  cliente: null,
  fecha: hoyISO(),
  notas: '',
  ofertaGlobalManual: '',
  ofertaGlobalActual: null,
  pagos: [],
  nextPagoId: 1,
  forzarScoring: false,
  facturar: false,
  confirmada: null,
  sinTurno: false,
  arca: true,
};

/* ================================================================
   BÚSQUEDA DE PRODUCTOS
   ================================================================ */
const buscar = $('#buscar');
const buscarDrop = $('#buscarDrop');
const LOTE_RE = /^LT.\d{4}.\d{4,5}$/i;
const BAL_RE = /^BAL.\d{4}.\d{4,5}$/i;

buscar.addEventListener('input', () => {
  const q = buscar.value.trim();
  if (!q) { cerrarDrop(buscarDrop); return; }
  if (LOTE_RE.test(q) || BAL_RE.test(q)) { return; } // se resuelve al Enter
  renderResultados(filtrarProductos(q));
});

buscar.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { buscar.value = ''; cerrarDrop(buscarDrop); return; }
  if (e.key === 'Enter') {
    e.preventDefault();
    const q = buscar.value.trim();
    if (!q) return;
    const normal = q.replace(/^(LT|BAL).(\d{4}).(\d{4,5})$/i, (m, p, a, b) => `${p.toUpperCase()}-${a}-${b}`);
    if (M.lotes[normal]) { agregarPorLote(M.lotes[normal]); limpiarBuscador(); return; }
    if (M.balanzas[normal]) { agregarPorBalanza(M.balanzas[normal]); limpiarBuscador(); return; }
    const res = filtrarProductos(q);
    if (res.length === 1) { if (elegirResultado(res[0])) limpiarBuscador(); }
    else renderResultados(res);
  }
});

function limpiarBuscador() { buscar.value = ''; cerrarDrop(buscarDrop); buscar.focus(); }
function cerrarDrop(d) { d.classList.remove('open'); d.innerHTML = ''; }

function filtrarProductos(q) {
  const t = norm(q);
  return M.productos.filter(p =>
    norm(p.nombre).includes(t) ||
    norm(p.codigo).includes(t) ||
    norm(p.marca).includes(t)
  ).slice(0, 8);
}

function renderResultados(filas) {
  if (!filas.length) {
    buscarDrop.innerHTML = '<div class="drop-empty">Sin resultados</div>';
    buscarDrop.classList.add('open');
    return;
  }
  buscarDrop.innerHTML = filas.map((p, i) => {
    const hayStock = !p.gestiona_stock || p.stock > 0;
    const stockTxt = !p.gestiona_stock ? 'Sin control de stock'
      : `Stock ${Number(p.stock).toLocaleString('es-AR')}`;
    return `<div class="drop-item" data-i="${i}">
      <div class="drop-item-top">
        <span class="drop-item-name">${esc(p.nombre)}${p.marca ? ` · ${esc(p.marca)}` : ''}${p.tipo === 'variantes' ? ' <span class="chip">variantes</span>' : ''}</span>
        <span class="drop-item-code">${esc(p.codigo)}</span>
      </div>
      <div class="drop-item-meta">
        <span class="chip ${hayStock ? 'chip--stock-ok' : 'chip--stock-no'}">${stockTxt}</span>
        <span class="chip chip--price">${fmt(p.precio)}</span>
        ${p.tipo === 'pesable' ? '<span class="chip">se pesa</span>' : ''}
      </div>
    </div>`;
  }).join('');
  $$('.drop-item', buscarDrop).forEach(el => {
    el.addEventListener('click', () => { if (elegirResultado(filas[+el.dataset.i])) limpiarBuscador(); });
  });
  buscarDrop.classList.add('open');
}

// Devuelve true si agregó el producto; false si abrió el selector de
// variantes (y hay que dejar el dropdown abierto para elegir).
function elegirResultado(p) {
  if (p.tipo === 'variantes') {
    buscar.value = '';
    toast(`"${p.nombre}" tiene varias variantes — elegí cuál vendés.`);
    buscarDrop.innerHTML = p.combinaciones.map((c, i) => `
      <div class="drop-item" data-c="${i}">
        <div class="drop-item-top">
          <span class="drop-item-name">${esc(p.nombre)} — ${esc(c.nombre)}</span>
          <span class="drop-item-code">${esc(p.codigo)}</span>
        </div>
        <div class="drop-item-meta"><span class="chip ${c.stock > 0 ? 'chip--stock-ok' : 'chip--stock-no'}">Stock ${c.stock}</span></div>
      </div>`).join('');
    $$('.drop-item', buscarDrop).forEach(el => {
      el.addEventListener('click', () => {
        agregarProducto(p, p.combinaciones[+el.dataset.c]);
        limpiarBuscador();
      });
    });
    buscarDrop.classList.add('open');
    return false;
  }
  agregarProducto(p, null);
  return true;
}

/* ================================================================
   AGREGAR / QUITAR / EDITAR CARRITO
   ================================================================ */
function agregarProducto(p, comb, opts = {}) {
  const combPk = comb ? comb.combinacion_pk : null;
  const existe = estado.carrito.find(it =>
    it.producto_pk === p.pk && it.combinacion_pk === combPk && it.origen === (opts.origen || 'fifo') && !it.bloqueado);
  if (existe) {
    existe.cantidad = (parseFloat(existe.cantidad) || 0) + 1;
    recalcOfertaLinea(existe);
    render();
    return;
  }
  const ofertaAuto = mejorOfertaAuto(p.pk, p.categoria_id, 1);
  estado.carrito.push({
    id: estado.nextId++,
    producto_pk: p.pk,
    combinacion_pk: combPk,
    categoria_id: p.categoria_id,
    nombre: comb ? `${p.nombre} — ${comb.nombre}` : p.nombre,
    codigo: p.codigo,
    origen: opts.origen || 'fifo',
    loteCodigo: opts.loteCodigo || '',
    balanzaCodigo: opts.balanzaCodigo || '',
    cantidad: opts.cantidad != null ? opts.cantidad : 1,
    precio: opts.precio != null ? opts.precio : p.precio,
    bloqueado: !!opts.bloqueado,
    gestiona_stock: p.gestiona_stock,
    stock: comb ? comb.stock : p.stock,
    descuento: 0,
    listaNombre: '',
    ofertaNombre: ofertaAuto ? ofertaAuto.nombre : '',
    advOpen: false,
  });
  const nuevo = estado.carrito[estado.carrito.length - 1];
  recalcOfertaLinea(nuevo);
  render();
}

function agregarPorLote(lote) {
  const p = M.productos.find(x => x.pk === lote.producto_pk);
  if (!p) return;
  agregarProducto(p, null, { origen: 'lote', loteCodigo: lote.lote_codigo });
  toast(`Lote ${lote.lote_codigo} agregado — descuenta de ese lote puntual`);
}
function agregarPorBalanza(b) {
  const p = M.productos.find(x => x.pk === b.producto_pk);
  if (!p) return;
  agregarProducto(p, null, {
    origen: 'balanza', balanzaCodigo: b.etiqueta_codigo,
    cantidad: b.cantidad_fija, precio: b.precio_fijo, bloqueado: true,
  });
  toast(`Etiqueta ${b.etiqueta_codigo} — cantidad y precio fijados al pesar`);
}

function quitarItem(id) {
  estado.carrito = estado.carrito.filter(it => it.id !== id);
  render();
}

/* ================================================================
   OFERTAS
   ================================================================ */
function ofertaAplica(o, prodPk, catId) {
  if (!o.productos.length && !o.categorias.length) return true;
  if (o.productos.includes(prodPk)) return true;
  if (catId != null && o.categorias.includes(catId)) return true;
  return false;
}
function pctEfectivo(o, cantidad) {
  if (o.tipo === 'nxm') {
    const n = o.cantidad_lleva, m = o.cantidad_paga;
    const q = Math.floor(parseFloat(cantidad) || 0);
    if (!n || !m || q < n) return 0;
    const grupos = Math.floor(q / n), resto = q % n;
    return (1 - (grupos * m + resto) / q) * 100;
  }
  return parseFloat(o.porcentaje) || 0;
}
function ofertasParaProducto(prodPk, catId) {
  return M.ofertas.filter(o => o.tipo !== 'umbral' && ofertaAplica(o, prodPk, catId));
}
function mejorOfertaAuto(prodPk, catId, cantidad) {
  const cands = ofertasParaProducto(prodPk, catId).filter(o => o.aplicacion === 'automatica');
  let mejor = null, mejorPct = -1;
  cands.forEach(o => { const p = pctEfectivo(o, cantidad); if (p > mejorPct) { mejor = o; mejorPct = p; } });
  return mejor;
}
function recalcOfertaLinea(it) {
  if (!it.ofertaNombre) return;
  const o = M.ofertas.find(x => x.nombre === it.ofertaNombre);
  if (!o) { it.ofertaNombre = ''; it.descuento = 0; return; }
  it.descuento = +pctEfectivo(o, it.cantidad).toFixed(4);
}

/* ================================================================
   TOTALES
   ================================================================ */
function subLinea(it) {
  const base = (parseFloat(it.cantidad) || 0) * (parseFloat(it.precio) || 0);
  return it.descuento ? base * (1 - parseFloat(it.descuento) / 100) : base;
}
function totalesCarrito() {
  const bruto = estado.carrito.reduce((s, i) => s + (parseFloat(i.cantidad) || 0) * (parseFloat(i.precio) || 0), 0);
  const neto = estado.carrito.reduce((s, i) => s + subLinea(i), 0);
  return { bruto, neto };
}
function ofertasUmbral(bruto, neto) {
  return M.ofertas.filter(o => o.tipo === 'umbral' &&
    (o.base_calculo === 'bruto' ? bruto : neto) >= parseFloat(o.monto_minimo || 0));
}
function resolverOfertaGlobal(bruto, neto) {
  const cal = ofertasUmbral(bruto, neto);
  const autos = cal.filter(o => o.aplicacion === 'automatica');
  if (autos.length) return autos.reduce((a, b) => parseFloat(b.porcentaje) > parseFloat(a.porcentaje) ? b : a);
  if (estado.ofertaGlobalManual) {
    const sigue = cal.find(o => o.nombre === estado.ofertaGlobalManual && o.aplicacion === 'manual');
    if (sigue) return sigue;
    estado.ofertaGlobalManual = '';
  }
  return null;
}
function totalFinalCarrito() {
  const { bruto, neto } = totalesCarrito();
  const og = resolverOfertaGlobal(bruto, neto);
  const pct = og ? (parseFloat(og.porcentaje) || 0) : 0;
  estado.ofertaGlobalActual = og ? { nombre: og.nombre, porcentaje: pct } : null;
  return neto * (1 - pct / 100);
}
function stockInsuficiente(it) {
  if (!it.gestiona_stock || it.stock == null) return false;
  return (parseFloat(it.cantidad) || 0) > it.stock;
}
function hayStockInsuficiente() { return estado.carrito.some(stockInsuficiente); }

/* ================================================================
   RENDER — carrito
   ================================================================ */
function render() {
  renderCarrito();
  renderCobro();
}

function renderCarrito() {
  const cont = $('#carrito');
  const vacio = $('#carritoVacio');
  const foot = $('#cartFoot');

  if (!estado.carrito.length) {
    cont.innerHTML = '';
    vacio.hidden = false;
    foot.hidden = true;
    $('#cartCount').textContent = '0 ítems';
    return;
  }
  vacio.hidden = true;
  foot.hidden = false;

  const listas = M.listasDescuento;

  cont.innerHTML = estado.carrito.map(it => {
    const sub = subLinea(it);
    const base = (parseFloat(it.cantidad) || 0) * (parseFloat(it.precio) || 0);
    const insuf = stockInsuficiente(it);
    const origenCls = it.origen === 'lote' ? 'origen--lote' : it.origen === 'balanza' ? 'origen--balanza' : 'origen--fifo';
    const origenTxt = it.origen === 'lote' ? `Lote ${esc(it.loteCodigo)}` : it.origen === 'balanza' ? `Balanza ${esc(it.balanzaCodigo)}` : 'Más viejo (FIFO)';

    const ofertas = ofertasParaProducto(it.producto_pk, it.categoria_id);
    const optListas = listas.map(l => `<option value="lista:${esc(l.nombre)}" ${it.listaNombre === l.nombre ? 'selected' : ''}>${esc(l.nombre)} (${l.porcentaje}%)</option>`).join('');
    const optOfertas = ofertas.map(o => {
      const pe = pctEfectivo(o, it.cantidad);
      const et = o.tipo === 'nxm' ? `${o.cantidad_lleva}x${o.cantidad_paga} → ${pe.toFixed(0)}%` : `${pe.toFixed(0)}%`;
      return `<option value="${esc(o.nombre)}" ${it.ofertaNombre === o.nombre ? 'selected' : ''}>${esc(o.nombre)} (${et})</option>`;
    }).join('');

    const tagDesc = it.descuento
      ? `<span class="tag-desc">−${(+it.descuento).toFixed(it.descuento % 1 ? 1 : 0)}%${it.ofertaNombre ? ` · ${esc(it.ofertaNombre)}` : it.listaNombre ? ` · ${esc(it.listaNombre)}` : ''}</span>`
      : '';

    return `<div class="cart-row ${insuf ? 'is-alert' : ''}" data-id="${it.id}">
      <div class="cart-row-top">
        <span class="origen ${origenCls}">${origenTxt}</span>
        <div class="cart-row-name">
          <b>${esc(it.nombre)}</b>
          <span>${esc(it.codigo)}</span>
        </div>
        <button class="cart-row-x" data-act="quitar" title="Quitar">✕</button>
      </div>
      <div class="cart-row-mid">
        <div class="stepper">
          <button data-act="menos" ${it.bloqueado ? 'disabled' : ''}>−</button>
          <input type="number" min="0" step="0.001" value="${it.cantidad}" data-f="cantidad" ${it.bloqueado ? 'readonly' : ''} class="${insuf ? 'input-error' : ''}">
          <button data-act="mas" ${it.bloqueado ? 'disabled' : ''}>＋</button>
        </div>
        <div class="cart-row-price">
          <span>×</span>
          <input type="number" min="0" step="0.01" value="${it.precio}" data-f="precio" ${it.bloqueado ? 'readonly' : ''}>
        </div>
        <div class="cart-row-sub">${it.descuento ? `<s>${fmt(base)}</s>` : ''}${fmt(sub)}</div>
      </div>
      ${insuf ? `<div class="cart-alert-msg">Stock disponible: ${it.stock}</div>` : ''}
      <div class="cart-row-tags">
        ${tagDesc}
        ${it.bloqueado ? '' : `<button class="cart-row-edit" data-act="adv">${it.advOpen ? 'Ocultar' : 'Descuento / oferta'}</button>`}
      </div>
      <div class="cart-row-adv ${it.advOpen ? 'open' : ''}">
        <div>
          <label>Descuento manual %</label>
          <input type="number" min="0" max="100" step="0.01" value="${it.descuento}" data-f="descuento">
        </div>
        <div>
          <label>Lista de descuento</label>
          <select data-f="lista">
            <option value="">— Manual —</option>
            ${optListas}
          </select>
        </div>
        <div class="full">
          <label>Oferta vigente para este producto</label>
          <select data-f="oferta">
            <option value="">— Ninguna —</option>
            ${optOfertas}
          </select>
        </div>
      </div>
    </div>`;
  }).join('');

  // listeners
  $$('.cart-row', cont).forEach(row => {
    const id = +row.dataset.id;
    const it = estado.carrito.find(x => x.id === id);
    row.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', () => {
      const act = b.dataset.act;
      if (act === 'quitar') return quitarItem(id);
      if (act === 'menos') { it.cantidad = Math.max(0, (parseFloat(it.cantidad) || 0) - 1); recalcOfertaLinea(it); render(); }
      if (act === 'mas') { it.cantidad = (parseFloat(it.cantidad) || 0) + 1; recalcOfertaLinea(it); render(); }
      if (act === 'adv') { it.advOpen = !it.advOpen; renderCarrito(); }
    }));
    row.querySelectorAll('[data-f]').forEach(inp => {
      const ev = inp.tagName === 'SELECT' ? 'change' : 'input';
      inp.addEventListener(ev, () => campoCarritoCambiado(it, inp, row));
    });
  });

  $('#cartCount').textContent = `${estado.carrito.length} ítem${estado.carrito.length === 1 ? '' : 's'}`;
  $('#cartFootItems').textContent = `${estado.carrito.length} ítem${estado.carrito.length === 1 ? '' : 's'}`;
  $('#cartFootTotal').textContent = fmt(totalFinalCarrito());
  renderOfertaGlobal();
}

function campoCarritoCambiado(it, inp, row) {
  const f = inp.dataset.f;

  // Campos de texto (cantidad / precio / descuento): actualización "en
  // vivo" sin reconstruir la fila, para no perder el foco en cada tecla.
  if (f === 'cantidad' || f === 'precio' || f === 'descuento') {
    if (f === 'cantidad') { it.cantidad = inp.value; recalcOfertaLinea(it); }
    else if (f === 'precio') { it.precio = inp.value; }
    else if (f === 'descuento') {
      it.descuento = inp.value;
      it.listaNombre = ''; it.ofertaNombre = '';
      const sl = row.querySelector('[data-f="lista"]'); if (sl) sl.value = '';
      const so = row.querySelector('[data-f="oferta"]'); if (so) so.value = '';
    }
    // refrescar subtotal de la fila + alerta de stock + totales + cobro
    const base = (parseFloat(it.cantidad) || 0) * (parseFloat(it.precio) || 0);
    const subEl = row.querySelector('.cart-row-sub');
    if (subEl) subEl.innerHTML = (it.descuento ? `<s>${fmt(base)}</s>` : '') + fmt(subLinea(it));
    const insuf = stockInsuficiente(it);
    row.classList.toggle('is-alert', insuf);
    const cantInp = row.querySelector('[data-f="cantidad"]');
    if (cantInp) cantInp.classList.toggle('input-error', insuf);
    let msg = row.querySelector('.cart-alert-msg');
    if (insuf && !msg) {
      msg = document.createElement('div');
      msg.className = 'cart-alert-msg';
      row.querySelector('.cart-row-mid').insertAdjacentElement('afterend', msg);
    }
    if (insuf) msg.textContent = `Stock disponible: ${it.stock}`;
    else if (msg) msg.remove();
    $('#cartFootTotal').textContent = fmt(totalFinalCarrito());
    renderOfertaGlobal();
    renderCobro();
    return;
  }

  // Selects (lista / oferta): sí reconstruyen la fila.
  if (f === 'lista') {
    it.ofertaNombre = '';
    if (inp.value) {
      const nombre = inp.value.split(':').slice(1).join(':');
      it.listaNombre = nombre;
      const l = M.listasDescuento.find(x => x.nombre === nombre);
      it.descuento = l ? l.porcentaje : 0;
    } else { it.listaNombre = ''; it.descuento = 0; }
  } else if (f === 'oferta') {
    it.listaNombre = '';
    it.ofertaNombre = inp.value;
    if (inp.value) {
      const o = M.ofertas.find(x => x.nombre === inp.value);
      if (o && o.tipo === 'nxm' && (parseFloat(it.cantidad) || 0) < o.cantidad_lleva) it.cantidad = o.cantidad_lleva;
      recalcOfertaLinea(it);
    } else it.descuento = 0;
  }
  renderCarrito();
  renderCobro();
}

function renderOfertaGlobal() {
  const cont = $('#ofertaGlobal');
  const { bruto, neto } = totalesCarrito();
  const og = estado.ofertaGlobalActual;
  if (og) {
    const monto = neto * og.porcentaje / 100;
    cont.hidden = false;
    cont.innerHTML = `<span class="oferta-global-badge">✓ ${esc(og.nombre)}: −${og.porcentaje}% (−${fmt(monto)})</span>`;
    return;
  }
  const manuales = ofertasUmbral(bruto, neto).filter(o => o.aplicacion === 'manual');
  if (!manuales.length) { cont.hidden = true; cont.innerHTML = ''; return; }
  cont.hidden = false;
  cont.innerHTML = `<span>Oferta por monto disponible:</span>
    <select id="selOfertaGlobal">
      <option value="">— No aplicar —</option>
      ${manuales.map(o => `<option value="${esc(o.nombre)}" ${estado.ofertaGlobalManual === o.nombre ? 'selected' : ''}>${esc(o.nombre)} (−${o.porcentaje}%)</option>`).join('')}
    </select>`;
  $('#selOfertaGlobal').addEventListener('change', e => { estado.ofertaGlobalManual = e.target.value; render(); });
}

/* ================================================================
   CLIENTE + SCORING
   ================================================================ */
const clienteInput = $('#clienteInput');
const clienteDrop = $('#clienteDrop');
const clienteClear = $('#clienteClear');

clienteInput.addEventListener('input', () => {
  const q = norm(clienteInput.value.trim());
  estado.cliente = null;
  estado.forzarScoring = false;
  clienteClear.hidden = true;
  renderScoChip();
  renderCobro();
  if (!q) { cerrarDrop(clienteDrop); return; }
  const res = M.clientes.filter(c => norm(c.nombre).includes(q) || norm(c.doc).includes(q)).slice(0, 8);
  clienteDrop.innerHTML = res.length
    ? res.map((c, i) => `<div class="drop-item" data-i="${i}">
        <div class="drop-item-top">
          <span class="drop-item-name">${esc(c.nombre)}</span>
          ${c.banda && !c.sinHistorial ? `<span class="chip sco-chip--${c.banda}">${esc(c.label)}</span>` : c.sinHistorial ? '<span class="chip">sin historial</span>' : ''}
        </div>
        <div class="drop-item-meta"><span class="drop-item-code">${esc(c.doc || '')}</span></div>
      </div>`).join('')
    : `<div class="drop-empty">Sin resultados</div>`;
  $$('.drop-item', clienteDrop).forEach(el => el.addEventListener('click', () => elegirCliente(res[+el.dataset.i])));
  clienteDrop.classList.add('open');
});

function elegirCliente(c) {
  estado.cliente = c;
  estado.forzarScoring = false;
  clienteInput.value = c.nombre;
  clienteClear.hidden = false;
  cerrarDrop(clienteDrop);
  renderScoChip();
  renderCobro();
}
clienteClear.addEventListener('click', () => {
  estado.cliente = null; estado.forzarScoring = false;
  clienteInput.value = ''; clienteClear.hidden = true;
  renderScoChip(); renderCobro(); clienteInput.focus();
});

function renderScoChip() {
  const chip = $('#scoChip');
  const c = estado.cliente;
  if (!c) { chip.hidden = true; return; }
  chip.hidden = false;
  if (c.sinHistorial) { chip.className = 'sco-chip sco-chip--sinhist'; chip.textContent = 'Sin historial de crédito'; return; }
  chip.className = 'sco-chip sco-chip--' + (c.banda || 'excelente');
  chip.textContent = `Riesgo de pago: ${c.label}${c.scoring != null ? ` (${c.scoring})` : ''}`;
}

const SCO_AVISO = ['regular', 'riesgo', 'critico'];
function scoAplica() { return estado.cliente && SCO_AVISO.includes(estado.cliente.banda); }
function scoBloquea() { return estado.cliente && estado.cliente.banda === 'critico' && !estado.forzarScoring; }

/* ================================================================
   TIPO DE COMPROBANTE
   ================================================================ */
function tipoComprobante() {
  const c = estado.cliente;
  if (c && c.tipo === 'empresa') return 'Factura A';
  return 'Factura B';
}

/* ================================================================
   PAGOS
   ================================================================ */
function mediosDisponibles() {
  let m = M.medios;
  if (!estado.cliente || scoBloquea()) m = m.filter(x => x.value !== 'cuotas' && x.value !== 'cheque');
  return m;
}
function cuentaPorPk(pk) { return M.cuentas.find(c => String(c.pk) === String(pk)); }
const CAMPO_ACEPTA = { debito: 'acepta_debito', credito: 'acepta_credito', qr: 'acepta_qr', transferencia: 'acepta_transferencia' };
function cuentasParaMedio(medio) {
  const campo = CAMPO_ACEPTA[medio];
  return M.cuentas.filter(c => !campo || c[campo]);
}
function tarjetasParaMedio(medio) {
  const campo = CAMPO_ACEPTA[medio];
  return M.tarjetas.filter(t => !campo || t[campo]);
}
function recargosDe(tarjetaPk, medio) {
  return M.recargos.filter(r => String(r.tarjeta_pk) === String(tarjetaPk) && r.medio === medio);
}
function recargoPct(l) {
  if (!l.tarjeta) return 0;
  const cant = l.medio === 'credito' ? (l.cantidadPagos || 1) : 1;
  const row = recargosDe(l.tarjeta, l.medio).find(r => Number(r.cantidad_pagos) === Number(cant));
  return row ? parseFloat(row.recargo_pct) : 0;
}
function lineaAplicaRecargo(l) {
  const con = ['debito', 'credito', 'qr', 'transferencia'];
  if (!con.includes(l.medio) || !l.tarjeta) return false;
  if (l.medio === 'credito') return true;
  return !!l.aplicaRecargo;
}
function montoArsLinea(l) {
  if (['efectivo', 'cuotas', 'cheque'].includes(l.medio)) return l.monto || 0;
  const c = cuentaPorPk(l.cuenta);
  if (c && c.moneda !== 'ARS') return (l.monto || 0) * (l.cotizacion || 0);
  return l.monto || 0;
}
function extraLinea(l) {
  if (l.medio === 'cuotas') return (l.monto || 0) * (l.interesPct || 0) / 100;
  if (!lineaAplicaRecargo(l)) return 0;
  return (l.monto || 0) * recargoPct(l) / 100;
}

function agregarLinea() {
  const asignado = estado.pagos.reduce((s, l) => s + montoArsLinea(l), 0);
  const resto = Math.max(0, totalFinalCarrito() - asignado);
  estado.pagos.push({
    id: estado.nextPagoId++,
    medio: mediosDisponibles()[0] ? mediosDisponibles()[0].value : 'efectivo',
    monto: +resto.toFixed(2),
    tarjeta: '', cuenta: '', cotizacion: 0,
    cantidadPagos: 1, aplicaRecargo: true,
    modoCuotas: 'fijas', cuotas: null, interesPct: 0, fechaInicio: '',
    cheques: [], editadoManual: false,
  });
  renderCobro();
}

function renderPagos() {
  const cont = $('#pagoLineas');
  const permitidos = mediosDisponibles().map(m => m.value);
  estado.pagos.forEach(l => {
    if (!permitidos.includes(l.medio)) { l.medio = permitidos[0] || 'efectivo'; l.tarjeta = ''; l.cuenta = ''; l.cheques = []; }
  });

  if (!estado.pagos.length) {
    cont.innerHTML = '<p class="pago-hint">Sin medios de pago. Agregá al menos uno.</p>';
    return;
  }

  cont.innerHTML = estado.pagos.map(l => {
    const opciones = mediosDisponibles().map(m => `<option value="${m.value}" ${m.value === l.medio ? 'selected' : ''}>${m.label}</option>`).join('');
    let sub = '';

    if (l.medio === 'cheque') {
      const cheques = (l.cheques || []).map((c, i) => `
        <div class="pago-cheque-item">
          <strong>${fmt(c.monto)}</strong>
          <span>${c.numero ? '#' + esc(c.numero) + ' · ' : ''}cobra ${esc(c.cobro)}</span>
          <button data-cheque-del="${i}">✕</button>
        </div>`).join('');
      sub = `<div class="pago-sub">
        <div class="pago-cheques">${cheques}</div>
        <button class="btn-cheque-add" data-cheque-add>＋ Cargar cheque</button>
      </div>`;
    } else if (l.medio === 'cuotas') {
      const libre = l.modoCuotas === 'libre';
      sub = `<div class="pago-sub">
        <label class="pago-toggle"><input type="checkbox" data-f="modoCuotas" ${libre ? 'checked' : ''}> Cuotas libres (sin plan fijo)</label>
        <div class="pago-sub-row">
          ${libre ? '' : `<input type="number" min="1" step="1" placeholder="N° de cuotas" value="${l.cuotas || ''}" data-f="cuotas">`}
          <input type="number" min="0" step="0.01" placeholder="Interés %" value="${l.interesPct || ''}" data-f="interesPct">
        </div>
        ${libre
          ? `<div class="pago-hint">Total a cobrar: <strong>${fmt((l.monto || 0) * (1 + (l.interesPct || 0) / 100))}</strong></div>`
          : `<input type="date" value="${l.fechaInicio || ''}" data-f="fechaInicio">`}
        <div class="pago-hint">No entra a caja hasta cobrar cada cuota desde "Cuentas por cobrar".</div>
      </div>`;
    } else if (l.medio !== 'efectivo') {
      const tarjetas = tarjetasParaMedio(l.medio);
      const cuentas = cuentasParaMedio(l.medio);
      const cta = cuentaPorPk(l.cuenta);
      let recargoHtml = '';
      if (l.tarjeta) {
        if (l.medio === 'credito') {
          const planes = recargosDe(l.tarjeta, 'credito').slice().sort((a, b) => a.cantidad_pagos - b.cantidad_pagos);
          const opts = [];
          if (!planes.some(p => Number(p.cantidad_pagos) === 1)) opts.push('<option value="1">1 pago (sin recargo)</option>');
          planes.forEach(p => {
            const pct = parseFloat(p.recargo_pct);
            opts.push(`<option value="${p.cantidad_pagos}" ${Number(l.cantidadPagos || 1) === Number(p.cantidad_pagos) ? 'selected' : ''}>${esc(p.etiqueta_plan)}${pct > 0 ? ` (+${pct}%)` : ' (sin recargo)'}</option>`);
          });
          const mr = (l.monto || 0) * recargoPct(l) / 100;
          recargoHtml = `<select data-f="cantidadPagos">${opts.join('')}</select>${mr > 0.005 ? `<span class="pago-recargo-tag">+ ${fmt(mr)} de recargo</span>` : ''}`;
        } else {
          const row = recargosDe(l.tarjeta, l.medio).find(r => Number(r.cantidad_pagos) === 1);
          if (row && parseFloat(row.recargo_pct) > 0) {
            const mr = (l.monto || 0) * parseFloat(row.recargo_pct) / 100;
            recargoHtml = `<label class="pago-toggle"><input type="checkbox" data-f="aplicaRecargo" ${l.aplicaRecargo ? 'checked' : ''}> Aplicar recargo (+${parseFloat(row.recargo_pct)}%)</label>${l.aplicaRecargo && mr > 0.005 ? `<span class="pago-recargo-tag">+ ${fmt(mr)}</span>` : ''}`;
          }
        }
      }
      sub = `<div class="pago-sub">
        <select data-f="tarjeta"><option value="">— Con qué te pagó (opcional) —</option>${tarjetas.map(t => `<option value="${t.pk}" ${String(t.pk) === String(l.tarjeta) ? 'selected' : ''}>${esc(t.nombre)}</option>`).join('')}</select>
        ${recargoHtml}
        <select data-f="cuenta"><option value="">— A qué cuenta entra —</option>${cuentas.map(c => `<option value="${c.pk}" ${String(c.pk) === String(l.cuenta) ? 'selected' : ''}>${esc(c.nombre)} (${c.moneda})</option>`).join('')}</select>
        ${cta && cta.moneda !== 'ARS' ? `<input type="number" min="0" step="0.0001" placeholder="Cotización ($ por 1 ${cta.moneda})" value="${l.cotizacion || ''}" data-f="cotizacion">` : ''}
        ${cta && cta.moneda !== 'ARS' && l.cotizacion ? `<div class="pago-hint">≈ ${fmt(montoArsLinea(l))}</div>` : ''}
      </div>`;
    }

    return `<div class="pago-linea" data-id="${l.id}">
      <div class="pago-linea-top">
        <select data-f="medio">${opciones}</select>
        <input type="number" class="pago-monto" min="0" step="0.01" placeholder="Monto" value="${l.monto > 0 ? l.monto : ''}" data-f="monto" ${l.medio === 'cheque' ? 'readonly' : ''}>
        <button class="pago-x" data-del>✕</button>
      </div>
      ${sub}
    </div>`;
  }).join('');

  // listeners
  $$('.pago-linea', cont).forEach(row => {
    const l = estado.pagos.find(x => x.id === +row.dataset.id);
    row.querySelector('[data-del]').addEventListener('click', () => {
      estado.pagos = estado.pagos.filter(x => x.id !== l.id);
      renderCobro();
    });
    row.querySelector('[data-cheque-add]')?.addEventListener('click', () => abrirModalCheque(l));
    row.querySelectorAll('[data-cheque-del]').forEach(b => b.addEventListener('click', () => {
      l.cheques.splice(+b.dataset.chequeDel, 1);
      l.monto = l.cheques.reduce((s, c) => s + (parseFloat(c.monto) || 0), 0);
      renderCobro();
    }));
    row.querySelectorAll('[data-f]').forEach(inp => {
      const ev = (inp.type === 'checkbox' || inp.tagName === 'SELECT') ? 'change' : 'input';
      inp.addEventListener(ev, () => campoPagoCambiado(l, inp));
    });
  });
}

function campoPagoCambiado(l, inp) {
  const f = inp.dataset.f;
  const val = inp.type === 'checkbox' ? inp.checked : inp.value;

  if (f === 'medio') {
    l.medio = val; l.tarjeta = ''; l.cuenta = ''; l.cantidadPagos = 1; l.aplicaRecargo = true;
    if (l.medio === 'cuotas') { l.modoCuotas = l.modoCuotas || 'fijas'; if (!l.fechaInicio) l.fechaInicio = estado.fecha; }
    if (l.medio === 'cheque') { l.cheques = l.cheques || []; l.monto = l.cheques.reduce((s, c) => s + (+c.monto || 0), 0); }
    const posibles = cuentasParaMedio(l.medio);
    if (posibles.length === 1) l.cuenta = String(posibles[0].pk);
    return renderCobro();
  }
  if (f === 'monto') { l.monto = parseFloat(val) || 0; l.editadoManual = true; return renderResumenPago(); }
  if (f === 'tarjeta') { l.tarjeta = val; l.cantidadPagos = 1; l.aplicaRecargo = true; return renderCobro(); }
  if (f === 'cuenta') { l.cuenta = val; l.cotizacion = 0; return renderCobro(); }
  if (f === 'cantidadPagos') { l.cantidadPagos = parseInt(val, 10) || 1; return renderCobro(); }
  if (f === 'aplicaRecargo') { l.aplicaRecargo = val; return renderCobro(); }
  if (f === 'cotizacion') { l.cotizacion = parseFloat(val) || 0; return renderResumenPago(); }
  if (f === 'modoCuotas') { l.modoCuotas = val ? 'libre' : 'fijas'; return renderCobro(); }
  if (f === 'cuotas') { l.cuotas = parseInt(val, 10) || null; return renderResumenPago(); }
  if (f === 'interesPct') {
    // Sin rebuild: mantené el foco mientras se tipea. Solo refrescamos
    // el hint de "Total a cobrar" (modo libre) y el resumen.
    l.interesPct = val === '' ? 0 : parseFloat(val);
    if (l.modoCuotas === 'libre') {
      const row = inp.closest('.pago-linea');
      const hint = row && row.querySelector('.pago-hint strong');
      if (hint) hint.textContent = fmt((l.monto || 0) * (1 + (l.interesPct || 0) / 100));
    }
    return renderResumenPago();
  }
  if (f === 'fechaInicio') { l.fechaInicio = val; return renderResumenPago(); }
}

/* ---- resumen de pago ---- */
function pagoCubierto() {
  const asignado = estado.pagos.reduce((s, l) => s + montoArsLinea(l), 0);
  return Math.abs(totalFinalCarrito() - asignado) < 0.005 && estado.pagos.length > 0;
}
function faltanCuentas() {
  return estado.pagos.some(l => {
    if (['efectivo', 'cuotas', 'cheque'].includes(l.medio)) return false;
    if (!l.cuenta) return true;
    const c = cuentaPorPk(l.cuenta);
    return !!c && c.moneda !== 'ARS' && !(l.cotizacion > 0);
  });
}
function faltanDatosCuotas() {
  return estado.pagos.some(l => l.medio === 'cuotas' && l.modoCuotas !== 'libre' && (!l.cuotas || l.cuotas < 1 || !l.fechaInicio));
}
function faltanDatosCheque() {
  return estado.pagos.some(l => l.medio === 'cheque' && !(l.cheques && l.cheques.length));
}

function renderResumenPago() {
  const total = totalFinalCarrito();
  const asignado = estado.pagos.reduce((s, l) => s + montoArsLinea(l), 0);
  const pendiente = total - asignado;
  const exceso = asignado - total;

  $('#pagoAsignado').textContent = fmt(asignado);
  const res = $('#pagoResumen');
  const pw = $('#pagoPendienteWrap');

  if (!estado.carrito.length || total <= 0) {
    res.className = 'pago-resumen';
    pw.innerHTML = 'Sin ítems todavía';
  } else if (Math.abs(pendiente) < 0.005 && estado.pagos.length) {
    res.className = 'pago-resumen pago-resumen--ok';
    pw.innerHTML = '✓ Pago cubierto';
  } else if (exceso > 0.005) {
    res.className = 'pago-resumen pago-resumen--exceso';
    pw.innerHTML = `Exceso <strong>${fmt(exceso)}</strong>`;
  } else {
    res.className = 'pago-resumen';
    pw.innerHTML = `Pendiente <strong>${fmt(Math.max(0, pendiente))}</strong>`;
  }

  const extra = estado.pagos.reduce((s, l) => s + extraLinea(l), 0);
  const extraBox = $('#pagoExtra');
  if (extra > 0.005) {
    extraBox.hidden = false;
    $('#pagoRecargo').textContent = fmt(extra);
    $('#pagoTotalFinal').textContent = fmt(total + extra);
  } else {
    extraBox.hidden = true;
  }

  const dot = $('#pagoDot');
  const ok = estado.carrito.length && pagoCubierto() && !faltanCuentas() && !faltanDatosCuotas() && !faltanDatosCheque();
  dot.classList.toggle('ok', !!ok);

  actualizarConfirmar();
}

/* ================================================================
   FACTURACIÓN
   ================================================================ */
function renderFacturacion() {
  const box = $('#factBox');
  box.hidden = !estado.arca;
  if (!estado.arca) return;
  const tipo = tipoComprobante();
  $('#factPreview').textContent = tipo;
  $('#factTipo').textContent = tipo;
  const c = estado.cliente;
  $('#factNote').textContent = c
    ? `${c.nombre} (${c.doc || 'sin documento'}) — se emite ${tipo}.`
    : `Consumidor Final — se emite ${tipo}. Elegí un cliente para emitir Factura A.`;
}

/* ================================================================
   SCORING — aviso en el área de pago
   ================================================================ */
function renderScoAviso() {
  const box = $('#scoAviso');
  if (!scoAplica()) { box.hidden = true; box.innerHTML = ''; return; }
  const c = estado.cliente;
  box.hidden = false;
  box.className = 'sco-aviso sco-aviso--' + c.banda;
  const alerta = c.alerta ? ` ${esc(c.alerta)}` : '';
  if (c.banda === 'critico') {
    box.innerHTML = estado.forzarScoring
      ? `<strong>${esc(c.nombre)} — banda Crítico.</strong>${alerta} Cuotas y cheque habilitados manualmente para esta venta.`
      : `<strong>${esc(c.nombre)} — banda Crítico.</strong>${alerta} Cuotas y cheque quedan deshabilitados. <button class="sco-forzar" id="scoForzar">Habilitar de todos modos</button>`;
  } else if (c.banda === 'riesgo') {
    box.innerHTML = `<strong>${esc(c.nombre)} — banda Riesgo.</strong>${alerta} Se desaconseja venderle en cuotas o aceptarle un cheque.`;
  } else {
    box.innerHTML = `<strong>${esc(c.nombre)} — banda Regular.</strong>${alerta} Revisá antes de venderle en cuotas o aceptarle un cheque.`;
  }
  $('#scoForzar')?.addEventListener('click', () => { estado.forzarScoring = true; renderCobro(); });
}

/* ================================================================
   RENDER — cobro (columna derecha)
   ================================================================ */
function renderCobro() {
  if (estado.confirmada) { renderListo(); return; }
  $('#cobroBorrador').hidden = false;
  $('#cobroListo').hidden = true;

  // total grande (productos, sin recargo)
  const total = totalFinalCarrito();
  $('#totalGrande').textContent = fmt(total);
  const { neto } = totalesCarrito();
  const sub = $('#totalSub');
  if (estado.ofertaGlobalActual) {
    sub.hidden = false;
    sub.textContent = `Incluye oferta ${estado.ofertaGlobalActual.nombre} (−${estado.ofertaGlobalActual.porcentaje}%)`;
  } else sub.hidden = true;

  // si hay una sola línea de pago sin tocar a mano, seguí el total
  if (estado.pagos.length === 1 && !estado.pagos[0].editadoManual && !['cheque'].includes(estado.pagos[0].medio)) {
    estado.pagos[0].monto = +total.toFixed(2);
  }

  renderScoAviso();
  renderPagos();
  renderResumenPago();
  renderFacturacion();
}

function actualizarConfirmar() {
  const btn = $('#btnConfirmar');
  const razones = [];
  if (!estado.carrito.length) razones.push('carrito vacío');
  if (hayStockInsuficiente()) razones.push('stock insuficiente');
  if (!estado.fecha) razones.push('falta fecha');
  if (!pagoCubierto()) razones.push('pago incompleto');
  if (faltanCuentas()) razones.push('falta cuenta/cotización');
  if (faltanDatosCuotas()) razones.push('faltan datos de cuotas');
  if (faltanDatosCheque()) razones.push('falta cargar cheque');
  if (estado.sinTurno) razones.push('sin turno de caja');

  btn.disabled = razones.length > 0;
  btn.title = razones.length ? 'Falta: ' + razones.join(', ') : 'Listo para confirmar (F4)';
}

/* ================================================================
   CONFIRMAR / NUEVA VENTA / CANCELAR
   ================================================================ */
$('#btnConfirmar').addEventListener('click', confirmar);

function confirmar() {
  if ($('#btnConfirmar').disabled) { toast('Todavía falta algo para confirmar.'); return; }
  const total = totalFinalCarrito();
  const extra = estado.pagos.reduce((s, l) => s + extraLinea(l), 0);
  const num = 'V-0001-' + String(11 + Math.floor(Math.random() * 89)).padStart(5, '0');
  const medios = [...new Set(estado.pagos.map(l => M.medios.find(m => m.value === l.medio)?.label || l.medio))].join(' + ');

  estado.confirmada = {
    numero: num,
    total: total + extra,
    medios,
    factura: (estado.arca && estado.facturar) ? {
      tipo: tipoComprobante(),
      numero: '0001-' + String(1000 + Math.floor(Math.random() * 9000)),
      cae: String(Math.floor(1e13 + Math.random() * 9e13)),
      vto: new Date(Date.now() + 10 * 864e5).toLocaleDateString('es-AR'),
    } : null,
  };
  renderCobro();
  toast('Venta confirmada ✓');
}

function renderListo() {
  $('#cobroBorrador').hidden = true;
  $('#cobroListo').hidden = false;
  const c = estado.confirmada;
  $('#listoNum').textContent = c.numero;
  $('#listoTotal').textContent = fmt(c.total);
  $('#listoMedios').textContent = c.medios;
  if (c.factura) {
    $('#listoArcaRow').hidden = false;
    $('#listoCaeRow').hidden = false;
    $('#listoArca').textContent = `${c.factura.tipo} ${c.factura.numero}`;
    $('#listoCae').textContent = c.factura.cae;
  } else {
    $('#listoArcaRow').hidden = true;
    $('#listoCaeRow').hidden = true;
  }
}

$('#btnNuevaVenta').addEventListener('click', nuevaVenta);
function nuevaVenta() {
  estado.carrito = [];
  estado.cliente = null;
  estado.notas = '';
  estado.ofertaGlobalManual = '';
  estado.ofertaGlobalActual = null;
  estado.pagos = [];
  estado.forzarScoring = false;
  estado.facturar = false;
  estado.confirmada = null;
  clienteInput.value = '';
  clienteClear.hidden = true;
  $('#notasInput').value = '';
  $('#factCheck').checked = false;
  $('#cobroListo').hidden = true;
  $('#cobroBorrador').hidden = false;
  renderScoChip();
  agregarLinea();
  render();
  buscar.focus();
}

$('#btnCancelar').addEventListener('click', () => {
  if (!estado.carrito.length) { toast('No hay nada que cancelar.'); return; }
  if (confirm('¿Cancelar esta venta? Se vacía el carrito y el cobro.')) nuevaVenta();
});

/* ================================================================
   TICKET (vista previa) + FORMATO DE IMPRESIÓN
   ================================================================ */
$('#btnTicket').addEventListener('click', () => abrirTicket(false));
$$('#cobroListo [data-formato]').forEach(b => b.addEventListener('click', () => {
  const map = { a4: 'A4 / PDF', t80: 'Térmica 80mm', t58: 'Térmica 58mm' };
  toast(`(Maqueta) Abriría la ventana de impresión — formato ${map[b.dataset.formato]}`);
  abrirTicket(true);
}));

function abrirTicket(confirmada) {
  const total = estado.confirmada ? estado.confirmada.total : totalFinalCarrito();
  const num = estado.confirmada ? estado.confirmada.numero : 'BORRADOR';
  $('#ticketBody').innerHTML = `
    <div class="ticket-h">
      <b>${esc(M.empresa.nombre)}</b>
      <span>CUIT ${esc(M.empresa.cuit)} · ${esc(M.empresa.condicion_iva)}</span>
      <span>${esc(M.empresa.domicilio)}</span>
    </div>
    <div class="ticket-h">
      <b>${confirmada ? 'Comprobante de Venta' : 'Vista previa (borrador)'}</b>
      <span>${num} · ${new Date().toLocaleDateString('es-AR')}</span>
      ${estado.cliente ? `<span>Cliente: ${esc(estado.cliente.nombre)}</span>` : '<span>Consumidor Final</span>'}
    </div>
    <table>
      ${estado.carrito.map(it => `<tr>
        <td>${parseFloat(it.cantidad)} × ${esc(it.nombre)}${it.descuento ? ` (−${(+it.descuento).toFixed(0)}%)` : ''}</td>
        <td class="tr-r">${fmt(subLinea(it))}</td>
      </tr>`).join('')}
    </table>
    <div class="ticket-tot"><span>TOTAL</span><span>${fmt(total)}</span></div>
    ${estado.confirmada && estado.confirmada.factura
      ? `<div class="ticket-foot">${estado.confirmada.factura.tipo} ${estado.confirmada.factura.numero} · CAE ${estado.confirmada.factura.cae}</div>`
      : `<div class="ticket-foot">Documento no válido como factura</div>`}
  `;
  $('#modalTicket').hidden = false;
}

/* ================================================================
   MODAL CHEQUE
   ================================================================ */
let chequeLinea = null;
function abrirModalCheque(linea) {
  chequeLinea = linea;
  $('#chNumero').value = '';
  $('#chMonto').value = '';
  $('#chEmision').value = estado.fecha;
  $('#chCobro').value = estado.fecha;
  $('#chEmisor').value = '';
  $('#chBanco').value = '';
  $('#chErr').textContent = '';
  $('#modalCheque').hidden = false;
}
$('#chGuardar').addEventListener('click', () => {
  const monto = parseFloat($('#chMonto').value) || 0;
  if (monto <= 0) { $('#chErr').textContent = 'El monto debe ser mayor a 0.'; return; }
  if (!$('#chEmision').value || !$('#chCobro').value) { $('#chErr').textContent = 'Indicá fecha de emisión y de cobro.'; return; }
  chequeLinea.cheques.push({
    numero: $('#chNumero').value.trim(), monto,
    emision: $('#chEmision').value, cobro: $('#chCobro').value,
    emisor: $('#chEmisor').value.trim(), banco: $('#chBanco').value.trim(),
  });
  chequeLinea.monto = chequeLinea.cheques.reduce((s, c) => s + (parseFloat(c.monto) || 0), 0);
  $('#modalCheque').hidden = true;
  renderCobro();
});

/* cerrar modales */
$$('[data-close]').forEach(b => b.addEventListener('click', () => {
  b.closest('.modal').hidden = true;
}));
$$('.modal').forEach(m => m.addEventListener('click', e => { if (e.target === m) m.hidden = true; }));

/* ================================================================
   OTROS CAMPOS
   ================================================================ */
$('#fechaInput').addEventListener('input', e => { estado.fecha = e.target.value; actualizarConfirmar(); });
$('#notasInput').addEventListener('input', e => { estado.notas = e.target.value; });
$('#factCheck').addEventListener('change', e => { estado.facturar = e.target.checked; });
$('#btnAgregarPago').addEventListener('click', agregarLinea);

/* cerrar dropdowns al clickear afuera */
document.addEventListener('click', e => {
  if (!buscarDrop.contains(e.target) && e.target !== buscar) cerrarDrop(buscarDrop);
  if (!clienteDrop.contains(e.target) && e.target !== clienteInput) cerrarDrop(clienteDrop);
});

/* ================================================================
   PANEL DEMO
   ================================================================ */
$('#demoBtn').addEventListener('click', () => { $('#demoPanel').hidden = !$('#demoPanel').hidden; });
$('#demoSinTurno').addEventListener('change', e => {
  estado.sinTurno = e.target.checked;
  $('#bannerTurno').hidden = !e.target.checked;
  actualizarConfirmar();
});
$('#demoArca').addEventListener('change', e => { estado.arca = e.target.checked; renderCobro(); });
$('#demoReset').addEventListener('click', nuevaVenta);

/* ================================================================
   ATAJOS DE TECLADO
   ----------------------------------------------------------------
   Ya no hace falta un atajo para "mostrar/ocultar" nada: el cobro
   está siempre a la vista. F2 salta el foco entre el buscador y el
   monto del pago; F4 confirma.
   ================================================================ */
document.addEventListener('keydown', e => {
  if (e.key === 'F2') {
    e.preventDefault();
    if (estado.confirmada) return nuevaVenta();
    const monto = $('#pagoLineas .pago-monto');
    if (document.activeElement === monto) buscar.focus();
    else if (monto) monto.focus();
    else buscar.focus();
  }
  if (e.key === 'F4') {
    e.preventDefault();
    if (!estado.confirmada && !$('#btnConfirmar').disabled) confirmar();
  }
});

/* ================================================================
   INIT
   ================================================================ */
$('#fechaInput').value = estado.fecha;
agregarLinea();     // primera línea de pago con el total
render();
buscar.focus();

})();
