/**
 * historial_presupuestos.js — listado centralizado de presupuestos.
 * No hay página de detalle: cada fila tiene sus propias acciones
 * (Editar/Eliminar/Imprimir) resueltas acá mismo.
 *   - Editar   → lleva al carrito (nuevo_presupuesto) con ?editar=<pk>.
 *   - Eliminar → AJAX + confirm() nativo, sin modal compartido.
 *   - Imprimir → trae los datos de impresión por AJAX (mismo shape que
 *                devuelve Crear/ActualizarPresupuestoAjax al guardar) y
 *                abre la ventana de impresión con presupuesto_a4.js.
 */
'use strict';

function _esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let currentPage    = 1;
let currentFilters = {};
let lastData       = null;

const listaContainer = document.getElementById('listaContainer');
const paginacion     = document.getElementById('paginacion');
const btnAnterior    = document.getElementById('btnAnterior');
const btnSiguiente   = document.getElementById('btnSiguiente');
const pagInfo        = document.getElementById('pagInfo');
const resumenBar     = document.getElementById('resumenBar');
const resumenTotal   = document.getElementById('resumenTotal');
const resumenPag     = document.getElementById('resumenPag');
const filtroQ        = document.getElementById('filtroQ');
const filtroDesde    = document.getElementById('filtroDesde');
const filtroHasta    = document.getElementById('filtroHasta');
const btnFiltrar     = document.getElementById('btnFiltrar');
const btnLimpiar     = document.getElementById('btnLimpiar');

function buildPresupuestoHTML(p) {
    const acciones = [];
    if (HISTORIAL_PRE_PERMISOS.editar) {
        acciones.push(`<button class="pre-btn-accion" data-accion="editar" data-pk="${p.pk}">Editar</button>`);
    }
    acciones.push(`<button class="pre-btn-accion" data-accion="imprimir" data-pk="${p.pk}">Imprimir</button>`);
    if (HISTORIAL_PRE_PERMISOS.eliminar) {
        acciones.push(`<button class="pre-btn-accion pre-btn-accion--eliminar" data-accion="eliminar" data-pk="${p.pk}">Eliminar</button>`);
    }

    return `
    <div class="pre-row" data-pk="${p.pk}">
        <div class="pre-row-top">
            <div>
                <span class="pre-numero">${_esc(p.numero)}</span>
                <span class="pre-fecha">${_esc(p.fecha)}</span>
            </div>
            <span class="pre-monto">$${parseFloat(p.total).toLocaleString('es-AR', { minimumFractionDigits: 2 })}</span>
        </div>
        <div class="pre-cliente">${p.cliente ? _esc(p.cliente) : 'Sin cliente especificado'}</div>
        <div class="pre-footer">
            <span>${p.cantidad_items} ítem(s) · ${p.creado_por ? _esc(p.creado_por) : ''}</span>
            <div class="pre-acciones">${acciones.join('')}</div>
        </div>
    </div>`;
}

async function _imprimirPresupuesto(pk) {
    try {
        const res  = await fetch(`${HISTORIAL_PRE_URLS.datos}?pk=${pk}`);
        const data = await res.json();
        if (!data.ok) { alert(data.error || 'No se pudo obtener el presupuesto.'); return; }
        const ventana = window.open('', '_blank', 'width=750,height=950');
        if (!ventana) { alert('El navegador bloqueó la ventana de impresión. Permití popups e intentá de nuevo.'); return; }
        ventana.document.write(presupuestoHtmlA4(data));
        ventana.document.close();
    } catch {
        alert('Error de conexión al traer el presupuesto.');
    }
}

async function _eliminarPresupuesto(pk) {
    if (!confirm('¿Eliminar este presupuesto? No se puede deshacer (aunque no afecta stock ni caja).')) return;
    try {
        const res = await fetch(HISTORIAL_PRE_URLS.eliminar, {
            method: 'POST',
            headers: { 'X-CSRFToken': HISTORIAL_PRE_CSRF },
            body: new URLSearchParams({ presupuesto_pk: pk }),
        });
        const data = await res.json();
        if (data.ok) {
            fetchPresupuestos(currentPage);
        } else {
            alert(data.error || 'No se pudo eliminar.');
        }
    } catch {
        alert('Error de conexión al eliminar.');
    }
}

listaContainer.addEventListener('click', e => {
    const btn = e.target.closest('.pre-btn-accion');
    if (!btn) return;
    const pk = btn.dataset.pk;
    if (btn.dataset.accion === 'editar')   window.location.href = `${HISTORIAL_PRE_URLS.editar}?editar=${pk}`;
    if (btn.dataset.accion === 'imprimir') _imprimirPresupuesto(pk);
    if (btn.dataset.accion === 'eliminar') _eliminarPresupuesto(pk);
});

function renderLista(data) {
    lastData = data;

    if (!data.results.length) {
        listaContainer.innerHTML = `<div class="empty-state"><p>No se encontraron presupuestos.</p></div>`;
        paginacion.style.display = 'none';
        resumenBar.style.display = 'none';
        return;
    }

    listaContainer.innerHTML = `<div class="ventas-lista">${data.results.map(buildPresupuestoHTML).join('')}</div>`;

    resumenBar.style.display = 'flex';
    resumenTotal.textContent = data.total;
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    resumenPag.textContent = `${data.page} / ${totalPages}`;

    paginacion.style.display = 'flex';
    pagInfo.textContent = `Página ${data.page} de ${totalPages}`;
    btnAnterior.disabled = !data.has_prev;
    btnSiguiente.disabled = !data.has_next;
}

function fetchPresupuestos(page) {
    currentPage = page || 1;

    listaContainer.innerHTML = `<div class="loading-state"><span class="spinner"></span> Cargando…</div>`;
    paginacion.style.display = 'none';
    resumenBar.style.display = 'none';

    const params = new URLSearchParams({ page: currentPage });
    if (currentFilters.q)           params.set('q', currentFilters.q);
    if (currentFilters.fecha_desde) params.set('fecha_desde', currentFilters.fecha_desde);
    if (currentFilters.fecha_hasta) params.set('fecha_hasta', currentFilters.fecha_hasta);

    fetch(`${HISTORIAL_PRE_URLS.listar}?${params.toString()}`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => renderLista(data))
        .catch(() => {
            listaContainer.innerHTML = `<div class="empty-state"><p>Error al cargar los presupuestos. Intentá de nuevo.</p></div>`;
        });
}

function aplicarFiltros() {
    currentFilters = {
        q:           filtroQ     ? filtroQ.value.trim() : '',
        fecha_desde: filtroDesde ? filtroDesde.value    : '',
        fecha_hasta: filtroHasta ? filtroHasta.value    : '',
    };
    fetchPresupuestos(1);
}

btnFiltrar.addEventListener('click', aplicarFiltros);
filtroQ.addEventListener('keydown', e => { if (e.key === 'Enter') aplicarFiltros(); });
btnLimpiar.addEventListener('click', () => {
    if (filtroQ)     filtroQ.value = '';
    if (filtroDesde) filtroDesde.value = '';
    if (filtroHasta) filtroHasta.value = '';
    currentFilters = {};
    fetchPresupuestos(1);
});

btnAnterior.addEventListener('click',  () => { if (currentPage > 1) fetchPresupuestos(currentPage - 1); });
btnSiguiente.addEventListener('click', () => { if (lastData && lastData.has_next) fetchPresupuestos(currentPage + 1); });

fetchPresupuestos(1);
