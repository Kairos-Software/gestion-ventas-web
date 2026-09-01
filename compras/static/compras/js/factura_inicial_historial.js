/**
 * factura_inicial_historial.js
 * ─────────────────────────────────────────────────────────────────
 * Historial de la herramienta Factura inicial:
 *  - lista las cargas iniciales (confirmadas / anuladas)
 *  - buscador por N° y buscador POR PRODUCTO ("¿en qué factura está?")
 *  - cada fila se despliega y muestra sus ítems
 *  - por ítem: Corregir (cantidad / costo, sin anular todo) y Quitar
 *  - reimprimir PDF / anular / eliminar la factura entera
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

const FIH = window.FIH_CONFIG || {};
const $h = id => document.getElementById(id);

let _page = 1;
let _q = '';
let _prodQ = '';
let _cargando = false;

function _esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function _fmt(v) {
    return '$ ' + (parseFloat(v) || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function _incluye(hay, aguja) {
    return String(hay || '').toLowerCase().includes(String(aguja || '').toLowerCase());
}

let _toastTimer;
function _toast(t, b) {
    $h('fihToastTitle').textContent = t;
    $h('fihToastBody').textContent = b || '';
    const el = $h('fihToast');
    el.classList.add('show');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}

async function _cargar(reset) {
    if (_cargando) return;
    _cargando = true;
    if (reset) { _page = 1; $h('fihBody').innerHTML = ''; }
    $h('fihLoading').hidden = false;

    try {
        const url = `${FIH.urlListar}?page=${_page}`
            + `&q=${encodeURIComponent(_q)}`
            + `&producto=${encodeURIComponent(_prodQ)}`;
        const res = await fetch(url);
        const data = await res.json();
        $h('fihLoading').hidden = true;

        const rows = data.rows || [];
        $h('fihEmpty').hidden = !(_page === 1 && !rows.length);
        if (_page === 1 && !rows.length && _prodQ) {
            $h('fihEmpty').textContent =
                `Ninguna factura inicial contiene "${_prodQ}".`;
        } else if (_page === 1 && !rows.length) {
            $h('fihEmpty').textContent =
                'Todavía no cargaste ninguna factura inicial.';
        }

        rows.forEach(r => {
            $h('fihBody').insertAdjacentHTML('beforeend', _fila(r));
            $h('fihBody').insertAdjacentHTML('beforeend', _filaDetalle(r.pk));
        });
        _bind();
        $h('fihMore').hidden = !data.has_more;

        // Con búsqueda por producto: abrir el detalle de cada factura
        // directo, resaltando las líneas que matchean.
        if (_prodQ) {
            rows.forEach(r => _abrirDetalle(r.pk, { autofocus: false }));
        }
    } catch {
        $h('fihLoading').hidden = true;
        _toast('Error de conexión', 'No se pudo cargar el historial.');
    } finally {
        _cargando = false;
    }
}

function _fila(r) {
    const anulada = r.estado === 'anulada';
    const hint = (r.items_match && r.items_match.length)
        ? `<div class="fih-row-hint">contiene: ${r.items_match.map(m =>
              `${_esc(m.producto)} <b>×${_esc(m.cantidad)}</b>`).join(' · ')}</div>`
        : '';
    return `<tr class="fih-row" data-pk="${r.pk}">
        <td class="fi-hist-num">
            <span class="fih-caret" aria-hidden="true">▸</span>${_esc(r.numero)}
            ${hint}
        </td>
        <td>${_esc(r.fecha)}</td>
        <td>${_esc(r.comprobante)}</td>
        <td>${_esc(r.proveedor)}</td>
        <td data-items>${r.items}</td>
        <td class="fi-hist-total" data-total>${_fmt(r.total)}</td>
        <td><span class="fi-badge-estado ${anulada ? 'anulada' : 'confirmada'}">${_esc(r.estado_label)}</span></td>
        <td>
            <div class="fi-hist-actions">
                <button class="fi-hist-btn" data-act="imprimir" data-pk="${r.pk}">Imprimir</button>
                <button class="fi-hist-btn" data-act="pdf" data-pk="${r.pk}">PDF</button>
                ${anulada ? '' : `<button class="fi-hist-btn danger" data-act="anular" data-pk="${r.pk}">Anular</button>`}
                <button class="fi-hist-btn danger" data-act="eliminar" data-pk="${r.pk}">Eliminar</button>
            </div>
        </td>
    </tr>`;
}

function _filaDetalle(pk) {
    return `<tr class="fih-detail-row" data-detail-for="${pk}" hidden>
        <td colspan="8"><div class="fih-detail" data-detail-body="${pk}">
            <div class="fih-detail-load">Cargando ítems…</div>
        </div></td>
    </tr>`;
}

function _bind() {
    $h('fihBody').querySelectorAll('.fih-row').forEach(tr => {
        if (tr._bound) return;
        tr._bound = true;
        tr.addEventListener('click', e => {
            if (e.target.closest('button, a, input, select')) return;
            _toggleDetalle(tr.dataset.pk);
        });
    });
    $h('fihBody').querySelectorAll('[data-act]').forEach(b => {
        if (b._bound) return;
        b._bound = true;
        b.addEventListener('click', () => _accion(b.dataset.act, b.dataset.pk, b));
    });
}

/* ═══════════════ DETALLE DESPLEGABLE ═══════════════ */

function _detalleRow(pk) {
    return $h('fihBody').querySelector(`.fih-detail-row[data-detail-for="${pk}"]`);
}
function _filaRow(pk) {
    return $h('fihBody').querySelector(`.fih-row[data-pk="${pk}"]`);
}

function _toggleDetalle(pk) {
    const dr = _detalleRow(pk);
    if (!dr) return;
    if (dr.hidden) _abrirDetalle(pk, { autofocus: true });
    else _cerrarDetalle(pk);
}
function _cerrarDetalle(pk) {
    const dr = _detalleRow(pk);
    if (dr) dr.hidden = true;
    const fr = _filaRow(pk);
    if (fr) fr.classList.remove('is-open');
}

async function _abrirDetalle(pk, { autofocus } = {}) {
    const dr = _detalleRow(pk);
    const fr = _filaRow(pk);
    if (!dr) return;
    dr.hidden = false;
    if (fr) fr.classList.add('is-open');
    const body = dr.querySelector('[data-detail-body]');
    if (dr._cargado) return;

    try {
        const res = await fetch(`${FIH.urlItems}?pk=${pk}`);
        const data = await res.json();
        if (!data.ok) { body.innerHTML = `<div class="fih-detail-load">${_esc(data.error || 'No se pudo cargar.')}</div>`; return; }
        dr._cargado = true;
        _renderItems(pk, data.items || []);
        if (autofocus) dr.scrollIntoView({ block: 'nearest' });
    } catch {
        body.innerHTML = '<div class="fih-detail-load">Error de conexión.</div>';
    }
}

function _renderItems(pk, items) {
    const dr = _detalleRow(pk);
    const body = dr.querySelector('[data-detail-body]');
    if (!items.length) {
        body.innerHTML = '<div class="fih-detail-load">Sin ítems.</div>';
        return;
    }
    body.innerHTML = `
        <table class="fih-items">
            <thead><tr>
                <th>Producto</th><th class="r">Cantidad</th><th class="r">Costo unit.</th>
                <th class="r">Subtotal</th><th></th>
            </tr></thead>
            <tbody>
                ${items.map(it => _itemRow(pk, it)).join('')}
            </tbody>
        </table>`;
    body.querySelectorAll('[data-item-act]').forEach(b => {
        b.addEventListener('click', () => _itemAccion(pk, b.dataset.itemAct,
            b.closest('tr'), JSON.parse(b.dataset.item)));
    });
}

function _itemRow(pk, it) {
    const resaltar = _prodQ && (_incluye(it.producto, _prodQ) || _incluye(it.codigo, _prodQ));
    const consumido = it.consumido
        ? `<span class="fih-consumido" title="Ya usado / vendido de esta carga">${_esc(it.consumido)} usados</span>` : '';
    const itJson = _esc(JSON.stringify(it));
    const acciones = it.editable ? `
        <button class="fi-hist-btn" data-item-act="corregir" data-item="${itJson}">Corregir</button>
        <button class="fi-hist-btn danger" data-item-act="quitar" data-item="${itJson}">Quitar</button>` : '';
    return `<tr data-item-pk="${it.item_pk}" class="${resaltar ? 'is-match' : ''}">
        <td>
            <b>${_esc(it.producto)}</b>
            <span class="fih-item-meta">${_esc(it.codigo)}${it.variante ? ' · ' + _esc(it.variante) : ''}${it.unidad ? ' · ' + _esc(it.unidad) : ''}</span>
            ${consumido}
        </td>
        <td class="r" data-cell="cantidad">${_esc(it.cantidad)}</td>
        <td class="r" data-cell="costo">${_fmt(it.costo)}</td>
        <td class="r" data-cell="subtotal">${_fmt(it.subtotal)}</td>
        <td class="fih-item-actions">${acciones}</td>
    </tr>`;
}

/* ═══════════════ CORREGIR / QUITAR ÍTEM ═══════════════ */

function _itemAccion(pk, act, tr, it) {
    if (act === 'quitar') return _quitarItem(pk, tr, it);
    if (act === 'corregir') return _editarItem(pk, tr, it);
}

function _editarItem(pk, tr, it) {
    if (tr.querySelector('.fih-edit-inp')) return;   // ya en edición
    const step = it.entero ? '1' : 'any';
    tr.querySelector('[data-cell="cantidad"]').innerHTML =
        `<input class="fih-edit-inp" type="number" min="0" step="${step}" value="${_esc(it.cantidad)}" data-e="cantidad">`;
    tr.querySelector('[data-cell="costo"]').innerHTML =
        `<input class="fih-edit-inp" type="number" min="0" step="0.01" value="${_esc(it.costo)}" data-e="costo">`;
    tr.querySelector('.fih-item-actions').innerHTML = `
        <button class="fi-hist-btn" data-e-act="guardar">Guardar</button>
        <button class="fi-hist-btn" data-e-act="cancelar">Cancelar</button>`;
    tr.querySelector('[data-e-act="cancelar"]').addEventListener('click',
        () => _recargarDetalle(pk));
    tr.querySelector('[data-e-act="guardar"]').addEventListener('click',
        ev => _guardarItem(pk, tr, it, ev));
    tr.querySelector('input[data-e="cantidad"]').focus();
}

async function _recargarDetalle(pk) {
    const dr = _detalleRow(pk);
    if (dr) dr._cargado = false;
    await _abrirDetalle(pk, {});
}

async function _guardarItem(pk, tr, it, ev) {
    const cantidad = tr.querySelector('input[data-e="cantidad"]').value;
    const costo = tr.querySelector('input[data-e="costo"]').value;
    const btn = ev.currentTarget;
    btn.disabled = true; btn.textContent = '…';
    try {
        const res = await fetch(FIH.urlCorregir, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': FIH.csrfToken },
            body: JSON.stringify({ item_pk: it.item_pk, cantidad, costo }),
        });
        const data = await res.json();
        if (!data.ok) {
            _toast('No se pudo corregir', data.error || '');
            btn.disabled = false; btn.textContent = 'Guardar';
            return;
        }
        // Actualizar total + contador de la fila padre
        const fr = _filaRow(pk);
        if (fr && data.total != null) fr.querySelector('[data-total]').textContent = _fmt(data.total);
        _toast('Línea corregida',
            `Stock del producto: ${data.stock_actual}. Se registró el ajuste.`);
        await _recargarDetalle(pk);
    } catch {
        _toast('Error de conexión', 'Intentá de nuevo.');
        btn.disabled = false; btn.textContent = 'Guardar';
    }
}

async function _quitarItem(pk, tr, it) {
    if (!confirm(`Quitar "${it.producto}" de esta factura inicial.\n`
        + `Se revierte su stock (${it.cantidad}) y queda registrado.\n\n¿Continuar?`)) return;
    try {
        const res = await fetch(FIH.urlQuitarItem, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': FIH.csrfToken },
            body: JSON.stringify({ item_pk: it.item_pk }),
        });
        const data = await res.json();
        if (!data.ok) { _toast('No se pudo quitar', data.error || ''); return; }
        const fr = _filaRow(pk);
        if (fr) {
            if (data.total != null) fr.querySelector('[data-total]').textContent = _fmt(data.total);
            if (data.items != null) fr.querySelector('[data-items]').textContent = data.items;
        }
        _toast('Ítem quitado', 'El stock quedó revertido.');
        await _recargarDetalle(pk);
    } catch {
        _toast('Error de conexión', 'Intentá de nuevo.');
    }
}

/* ═══════════════ ACCIONES DE LA FACTURA ENTERA ═══════════════ */

async function _accion(act, pk, btn) {
    if (act === 'pdf' || act === 'imprimir') {
        btn.disabled = true;
        const txt = btn.textContent;
        btn.textContent = '…';
        try {
            const res = await fetch(`${FIH.urlReimprimir}?pk=${pk}`);
            const data = await res.json();
            if (!data.ok) { _toast('No se pudo', data.error || ''); return; }
            const html = facturaInicialHtmlA4(data, { sinAutoImpresion: true });
            if (act === 'imprimir') await facturaInicialImprimir(html);
            else await facturaInicialDescargarPdf(html, data);
        } catch {
            _toast('Error de conexión', 'Intentá de nuevo.');
        } finally {
            btn.disabled = false;
            btn.textContent = txt;
        }
        return;
    }

    const labels = {
        anular: ['Anular esta factura inicial', 'Se revierte el stock que había sumado.'],
        eliminar: ['Eliminar esta factura inicial', 'Se borra del todo. Si estaba activa, primero se revierte el stock.'],
    };
    if (!confirm(`${labels[act][0]}.\n${labels[act][1]}\n\n¿Continuar?`)) return;

    btn.disabled = true;
    try {
        const url = act === 'anular' ? FIH.urlAnular : FIH.urlEliminar;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': FIH.csrfToken },
            body: JSON.stringify({ pk }),
        });
        const data = await res.json();
        if (!data.ok) {
            _toast('No se pudo', data.error || 'Revisá e intentá de nuevo.');
            btn.disabled = false;
            return;
        }
        _toast(act === 'anular' ? 'Factura inicial anulada' : 'Factura inicial eliminada',
               'El stock quedó actualizado.');
        _cargar(true);
    } catch {
        _toast('Error de conexión', 'Intentá de nuevo.');
        btn.disabled = false;
    }
}

/* ── eventos ── */
let _searchTimer;
$h('fihSearch').addEventListener('input', e => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => { _q = e.target.value.trim(); _cargar(true); }, 300);
});
let _prodTimer;
$h('fihProdSearch').addEventListener('input', e => {
    clearTimeout(_prodTimer);
    _prodTimer = setTimeout(() => { _prodQ = e.target.value.trim(); _cargar(true); }, 320);
});
$h('fihMoreBtn').addEventListener('click', () => { _page++; _cargar(false); });

_cargar(true);
