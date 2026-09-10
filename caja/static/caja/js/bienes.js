/* caja/static/caja/js/bienes.js — Bienes (patrimonio del negocio) */
'use strict';

(function () {
    const tbody = document.getElementById('bienesTbody');
    if (!tbody) return; // sin permiso para ver, no hay tabla

    const buscar         = document.getElementById('bienesBuscar');
    const filtroTipo     = document.getElementById('bienesFiltroTipo');
    const filtroEstado   = document.getElementById('bienesFiltroEstado');
    const totalEl        = document.getElementById('bienesTotal');
    const btnNuevo       = document.getElementById('btnNuevoBien');

    const modalEl        = document.getElementById('bienModal');
    const modal           = new bootstrap.Modal(modalEl);
    const modalTitulo     = document.getElementById('bienModalTitulo');
    const bienPk          = document.getElementById('bienPk');
    const bienNombre      = document.getElementById('bienNombre');
    const bienTipo        = document.getElementById('bienTipo');
    const datalistTipos   = document.getElementById('bienTipoSugerencias');
    const bienValor       = document.getElementById('bienValor');
    const bienDescripcion = document.getElementById('bienDescripcion');
    const bienActivoWrap  = document.getElementById('bienActivoWrap');
    const bienActivo      = document.getElementById('bienActivo');
    const bienMeta        = document.getElementById('bienMeta');
    const bienMsg         = document.getElementById('bienMsg');
    const btnGuardar      = document.getElementById('btnGuardarBien');
    const btnEliminar     = document.getElementById('btnEliminarBien');

    let bienes = [];

    function escapeHtml(s) {
        return (s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    function moneda(valor) {
        const num = (window.KaiFormat && KaiFormat.moneda) ? KaiFormat.moneda(valor) : valor;
        return `$${num}`;
    }

    function formatoValorCelda(valor) {
        if (valor === '' || valor === null || valor === undefined) return '<span class="bien-sin-dato">—</span>';
        return moneda(valor);
    }

    // El campo "tipo" es libre. Refrescamos las sugerencias (datalist del
    // modal + opciones del filtro) con lo que devuelve el server en cada
    // carga, sin perder el tipo por el que se está filtrando.
    function refrescarTipos(tipos) {
        if (!Array.isArray(tipos)) return;
        datalistTipos.innerHTML = tipos.map((t) => `<option value="${escapeHtml(t)}"></option>`).join('');

        const elegido = filtroTipo.value;
        const opciones = ['<option value="">Todos los tipos</option>']
            .concat(tipos.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`));
        if (elegido && !tipos.includes(elegido)) {
            opciones.push(`<option value="${escapeHtml(elegido)}">${escapeHtml(elegido)}</option>`);
        }
        filtroTipo.innerHTML = opciones.join('');
        filtroTipo.value = elegido;
    }

    async function cargarBienes() {
        const params = new URLSearchParams();
        if (buscar.value.trim()) params.set('q', buscar.value.trim());
        if (filtroTipo.value) params.set('tipo', filtroTipo.value);
        params.set('estado', filtroEstado.value);

        const resp = await fetch(`${BIENES_URLS.listar}?${params.toString()}`);
        const data = await resp.json();
        if (data.error) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">${escapeHtml(data.error)}</td></tr>`;
            return;
        }
        bienes = data.results;
        totalEl.textContent = moneda(data.total_valorizado);
        refrescarTipos(data.tipos);
        renderTabla();
    }

    function renderTabla() {
        if (!bienes.length) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">Todavía no cargaste ningún bien.</td></tr>`;
            return;
        }
        tbody.innerHTML = bienes.map((b) => `
            <tr data-pk="${b.pk}" class="${b.activo ? '' : 'bien-fila-inactiva'}">
                <td class="bien-nombre-cell">${escapeHtml(b.nombre)}</td>
                <td>${b.tipo ? `<span class="bienes-badge-tipo">${escapeHtml(b.tipo)}</span>` : '<span class="bien-sin-dato">—</span>'}</td>
                <td class="bien-valor-cell">${formatoValorCelda(b.valor)}</td>
                <td class="col-truncate" title="${escapeHtml(b.descripcion)}">${b.descripcion ? escapeHtml(b.descripcion) : '<span class="bien-sin-dato">—</span>'}</td>
                <td>${b.activo ? '<span class="bienes-badge-activo">Activo</span>' : '<span class="bienes-badge-inactivo">De baja</span>'}</td>
                <td class="col-actions">
                    ${b.pk && BIENES_PUEDE_ELIMINAR ? `<button type="button" class="btn-ghost-sm btn-eliminar-bien" data-pk="${b.pk}" title="Eliminar">
                        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 4H11M4.5 4V3H8.5V4M5 6.5V10M8 6.5V10M2.8 4L3.5 11H9.5L10.2 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </button>` : ''}
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('tr[data-pk]').forEach((tr) => {
            tr.addEventListener('click', (e) => {
                if (e.target.closest('.btn-eliminar-bien')) return;
                abrirBien(parseInt(tr.dataset.pk, 10));
            });
        });
        tbody.querySelectorAll('.btn-eliminar-bien').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                eliminarBien(parseInt(btn.dataset.pk, 10));
            });
        });
    }

    function abrirBien(pk) {
        const b = bienes.find((x) => x.pk === pk);
        if (!b) return;

        modalTitulo.textContent = 'Bien';
        bienPk.value = b.pk;
        bienNombre.value = b.nombre;
        bienNombre.disabled = !BIENES_PUEDE_EDITAR;
        bienTipo.value = b.tipo;
        bienTipo.disabled = !BIENES_PUEDE_EDITAR;
        bienValor.value = b.valor || '';
        bienValor.disabled = !BIENES_PUEDE_EDITAR;
        bienDescripcion.value = b.descripcion;
        bienDescripcion.disabled = !BIENES_PUEDE_EDITAR;

        bienActivoWrap.style.display = 'flex';
        bienActivo.checked = b.activo;
        bienActivo.disabled = !BIENES_PUEDE_EDITAR;

        bienMeta.style.display = '';
        bienMeta.textContent = `Cargado por ${b.creado_por} el ${b.fecha_alta}` +
            (b.modificado_por ? ` — última edición de ${b.modificado_por} el ${b.fecha_modificacion}` : '');

        btnGuardar.style.display = BIENES_PUEDE_EDITAR ? '' : 'none';
        btnEliminar.style.display = BIENES_PUEDE_ELIMINAR ? '' : 'none';
        btnEliminar.dataset.pk = b.pk;
        bienMsg.style.display = 'none';

        modal.show();
    }

    if (btnNuevo) {
        btnNuevo.addEventListener('click', () => {
            modalTitulo.textContent = 'Nuevo bien';
            bienPk.value = '';
            bienNombre.value = '';
            bienNombre.disabled = false;
            bienTipo.value = '';
            bienTipo.disabled = false;
            bienValor.value = '';
            bienValor.disabled = false;
            bienDescripcion.value = '';
            bienDescripcion.disabled = false;
            bienActivoWrap.style.display = 'none';
            bienActivo.checked = true;
            bienActivo.disabled = false;
            bienMeta.style.display = 'none';
            btnGuardar.style.display = '';
            btnEliminar.style.display = 'none';
            bienMsg.style.display = 'none';
            modal.show();
        });
    }

    btnGuardar.addEventListener('click', async () => {
        const nombre = bienNombre.value.trim();
        if (!nombre) {
            bienMsg.textContent = 'Ponele un nombre al bien.';
            bienMsg.style.display = '';
            return;
        }
        const body = {
            nombre,
            tipo: bienTipo.value,
            valor: bienValor.value,
            descripcion: bienDescripcion.value.trim(),
            activo: bienActivo.checked,
        };
        if (bienPk.value) body.pk = bienPk.value;

        const resp = await fetch(BIENES_URLS.acciones, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            bienMsg.textContent = data.error || 'No se pudo guardar el bien.';
            bienMsg.style.display = '';
            return;
        }
        modal.hide();
        KaiToast.show(bienPk.value ? 'Bien actualizado.' : 'Bien cargado.', 'success');
        cargarBienes();
    });

    btnEliminar.addEventListener('click', async () => {
        const pk = btnEliminar.dataset.pk;
        modal.hide();
        eliminarBien(parseInt(pk, 10));
    });

    async function eliminarBien(pk) {
        const ok = await KaiConfirm('¿Eliminar este bien? No se puede deshacer.', { danger: true, confirmText: 'Eliminar' });
        if (!ok) return;

        const resp = await fetch(BIENES_URLS.eliminar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ pk }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            KaiToast.show(data.error || 'No se pudo eliminar el bien.', 'danger');
            return;
        }
        KaiToast.show('Bien eliminado.', 'success');
        cargarBienes();
    }

    let buscarDebounce = null;
    buscar.addEventListener('input', () => {
        clearTimeout(buscarDebounce);
        buscarDebounce = setTimeout(cargarBienes, 300);
    });
    filtroTipo.addEventListener('change', cargarBienes);
    filtroEstado.addEventListener('change', cargarBienes);

    cargarBienes();
})();
