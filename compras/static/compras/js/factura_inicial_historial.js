/**
 * factura_inicial_historial.js
 * ─────────────────────────────────────────────────────────────────
 * Mini-historial de la herramienta Factura inicial: lista las cargas
 * iniciales confirmadas, con reimprimir PDF / anular / eliminar.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

const FIH = window.FIH_CONFIG || {};
const $h = id => document.getElementById(id);

let _page = 1;
let _q = '';
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
        const url = `${FIH.urlListar}?page=${_page}&q=${encodeURIComponent(_q)}`;
        const res = await fetch(url);
        const data = await res.json();
        $h('fihLoading').hidden = true;

        const rows = data.rows || [];
        if (_page === 1 && !rows.length) {
            $h('fihEmpty').hidden = false;
        } else {
            $h('fihEmpty').hidden = true;
        }

        rows.forEach(r => $h('fihBody').insertAdjacentHTML('beforeend', _fila(r)));
        _bind();
        $h('fihMore').hidden = !data.has_more;
    } catch {
        $h('fihLoading').hidden = true;
        _toast('Error de conexión', 'No se pudo cargar el historial.');
    } finally {
        _cargando = false;
    }
}

function _fila(r) {
    const anulada = r.estado === 'anulada';
    return `<tr data-pk="${r.pk}">
        <td class="fi-hist-num">${_esc(r.numero)}</td>
        <td>${_esc(r.fecha)}</td>
        <td>${_esc(r.comprobante)}</td>
        <td>${_esc(r.proveedor)}</td>
        <td>${r.items}</td>
        <td class="fi-hist-total">${_fmt(r.total)}</td>
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

function _bind() {
    $h('fihBody').querySelectorAll('[data-act]').forEach(b => {
        if (b._bound) return;
        b._bound = true;
        b.addEventListener('click', () => _accion(b.dataset.act, b.dataset.pk, b));
    });
}

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
$h('fihMoreBtn').addEventListener('click', () => { _page++; _cargar(false); });

_cargar(true);
