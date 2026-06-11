/* proveedores.js */

const modal         = document.getElementById('modal-proveedor');
const modalEliminar = document.getElementById('modal-eliminar');
const formProv      = document.getElementById('form-proveedor');
const toast         = document.getElementById('nx-toast');

// ── Utilidades ──────────────────────────────────────────────

function showToast(msg, tipo = 'ok') {
    toast.textContent = msg;
    toast.className   = `nx-toast nx-toast--${tipo} nx-toast--show`;
    setTimeout(() => toast.classList.remove('nx-toast--show'), 3000);
}

function abrirModal() { modal.style.display = 'flex'; }
function cerrarModal() {
    modal.style.display = 'none';
    formProv.reset();
    limpiarErrores();
    document.getElementById('f-pk').value = '';
    document.getElementById('modal-titulo').textContent = 'Nuevo proveedor';
    document.getElementById('btn-guardar-txt').style.display = '';
    document.getElementById('btn-guardar-spin').style.display = 'none';
}

function limpiarErrores() {
    document.querySelectorAll('.nx-field-error').forEach(el => el.textContent = '');
    document.querySelectorAll('.nx-input.is-invalid').forEach(el => el.classList.remove('is-invalid'));
}

function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = (val === null || val === undefined) ? '' : val;
}

function setCheck(id, val) {
    const el = document.getElementById(id);
    if (el) el.checked = !!val;
}

// ── Abrir modal NUEVO ────────────────────────────────────────

document.getElementById('btn-nuevo-proveedor').addEventListener('click', () => {
    cerrarModal();
    abrirModal();
});

// ── Abrir modal EDITAR ───────────────────────────────────────

document.getElementById('tabla-proveedores')?.addEventListener('click', async (e) => {
    const btn = e.target.closest('.btn-editar');
    if (!btn) return;
    const pk = btn.dataset.pk;

    try {
        const r    = await fetch(`${URL_ACCIONES}?pk=${pk}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const data = await r.json();

        document.getElementById('modal-titulo').textContent = 'Editar proveedor';
        document.getElementById('f-pk').value = data.pk;

        // Identidad
        setVal('id_nombre',      data.nombre);
        setVal('id_cuit',        data.cuit);
        setVal('id_tipo',        data.tipo);
        setVal('id_sitio_web',   data.sitio_web);
        setVal('id_descripcion', data.descripcion);
        setCheck('id_activo',    data.activo);

        // Contacto
        setVal('id_email',           data.email);
        setVal('id_telefono',         data.telefono);
        setVal('id_contacto_nombre',  data.contacto_nombre);
        setVal('id_contacto_cargo',   data.contacto_cargo);

        // Dirección
        setVal('id_calle',    data.calle);
        setVal('id_ciudad',   data.ciudad);
        setVal('id_provincia',data.provincia);
        setVal('id_pais',     data.pais);

        // Comercial
        setVal('id_condicion_pago', data.condicion_pago);
        setVal('id_moneda',         data.moneda);
        setVal('id_dias_entrega',   data.dias_entrega);
        setVal('id_notas',          data.notas);

        abrirModal();
    } catch {
        showToast('Error al cargar el proveedor.', 'error');
    }
});

// ── Cerrar modales ───────────────────────────────────────────

document.getElementById('btn-cerrar-modal').addEventListener('click', cerrarModal);
document.getElementById('btn-cancelar').addEventListener('click', cerrarModal);
modal.addEventListener('click', (e) => { if (e.target === modal) cerrarModal(); });

// ── Guardar (crear / editar) ─────────────────────────────────

document.getElementById('btn-guardar').addEventListener('click', async () => {
    limpiarErrores();

    const pk   = document.getElementById('f-pk').value;
    const body = {
        pk:              pk || null,
        nombre:          document.getElementById('id_nombre').value.trim(),
        cuit:            document.getElementById('id_cuit').value.trim(),
        tipo:            document.getElementById('id_tipo').value,
        activo:          document.getElementById('id_activo').checked,
        sitio_web:       document.getElementById('id_sitio_web').value.trim(),
        descripcion:     document.getElementById('id_descripcion').value.trim(),
        email:           document.getElementById('id_email').value.trim(),
        telefono:        document.getElementById('id_telefono').value.trim(),
        contacto_nombre: document.getElementById('id_contacto_nombre').value.trim(),
        contacto_cargo:  document.getElementById('id_contacto_cargo').value.trim(),
        calle:           document.getElementById('id_calle').value.trim(),
        ciudad:          document.getElementById('id_ciudad').value.trim(),
        provincia:       document.getElementById('id_provincia').value.trim(),
        pais:            document.getElementById('id_pais').value.trim(),
        condicion_pago:  document.getElementById('id_condicion_pago').value,
        moneda:          document.getElementById('id_moneda').value,
        dias_entrega:    document.getElementById('id_dias_entrega').value || null,
        notas:           document.getElementById('id_notas').value.trim(),
    };

    // Spinner
    document.getElementById('btn-guardar-txt').style.display  = 'none';
    document.getElementById('btn-guardar-spin').style.display = '';

    try {
        const r    = await fetch(URL_ACCIONES, {
            method:  'POST',
            headers: {
                'Content-Type':     'application/json',
                'X-CSRFToken':      CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify(body),
        });
        const data = await r.json();

        if (data.ok) {
            showToast(data.creado ? `Proveedor "${data.nombre}" creado.` : `Proveedor "${data.nombre}" actualizado.`);
            cerrarModal();
            if (data.creado) {
                agregarFilaTabla(data, body);
                actualizarContadores(1, body.activo ? 1 : 0);
            } else {
                actualizarFilaTabla(pk, data, body);
                // Si cambió el estado activo/inactivo, ajustar contador
                const filaAnterior = document.querySelector(`tr[data-pk="${pk}"]`);
                const eraActivo = filaAnterior?.dataset.activo === 'true';
                const esActivo  = body.activo;
                if (eraActivo !== esActivo) actualizarContadores(0, esActivo ? 1 : -1);
            }
        } else {
            // Mostrar errores de validación
            for (const [campo, errores] of Object.entries(data.errors || {})) {
                const errEl = document.getElementById(`err-${campo}`);
                const input = document.getElementById(`id_${campo}`);
                if (errEl) errEl.textContent = errores.join(' ');
                if (input) input.classList.add('is-invalid');
            }
            document.getElementById('btn-guardar-txt').style.display  = '';
            document.getElementById('btn-guardar-spin').style.display = 'none';
        }
    } catch {
        showToast('Error de conexión.', 'error');
        document.getElementById('btn-guardar-txt').style.display  = '';
        document.getElementById('btn-guardar-spin').style.display = 'none';
    }
});

// ── Eliminar ─────────────────────────────────────────────────

let pkAEliminar = null;

document.getElementById('tabla-proveedores')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-eliminar');
    if (!btn) return;
    pkAEliminar = btn.dataset.pk;
    document.getElementById('nombre-a-eliminar').textContent = btn.dataset.nombre;
    modalEliminar.style.display = 'flex';
});

function cerrarModalEliminar() {
    modalEliminar.style.display = 'none';
    pkAEliminar = null;
}

document.getElementById('btn-cerrar-eliminar').addEventListener('click', cerrarModalEliminar);
document.getElementById('btn-cancelar-eliminar').addEventListener('click', cerrarModalEliminar);
modalEliminar.addEventListener('click', (e) => { if (e.target === modalEliminar) cerrarModalEliminar(); });

document.getElementById('btn-confirmar-eliminar').addEventListener('click', async () => {
    if (!pkAEliminar) return;

    try {
        const r    = await fetch(URL_ELIMINAR, {
            method:  'POST',
            headers: {
                'Content-Type':     'application/json',
                'X-CSRFToken':      CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ pk: pkAEliminar }),
        });
        const data = await r.json();

        if (data.ok) {
            showToast(`Proveedor "${data.nombre}" eliminado.`, 'ok');
            cerrarModalEliminar();
            const fila = document.querySelector(`tr[data-pk="${pkAEliminar}"]`);
            const eraActivo = fila?.dataset.activo === 'true';
            if (fila) fila.remove();
            actualizarContadores(-1, eraActivo ? -1 : 0);
            // Si la tabla quedó vacía, mostrar estado vacío
            const tbody = document.querySelector('#tabla-proveedores tbody');
            if (tbody && tbody.querySelectorAll('tr').length === 0) {
                document.querySelector('.nx-table-wrap').innerHTML = `
                    <div class="nx-empty-state">
                        <div class="nx-empty-icon">◈</div>
                        <p class="nx-empty-title">No hay proveedores</p>
                        <p class="nx-empty-sub">Creá tu primer proveedor con el botón de arriba.</p>
                    </div>`;
            }
        } else {
            showToast('No se pudo eliminar el proveedor.', 'error');
        }
    } catch {
        showToast('Error de conexión.', 'error');
    }
});

// ── Búsqueda con debounce ────────────────────────────────────

const inputBusqueda = document.getElementById('input-busqueda');
let debounceTimer;
inputBusqueda?.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
        document.getElementById('form-filtros').submit();
    }, 400);
});

// ════════════════════════════════════════════════════════════════════
//  DOM — AGREGAR / ACTUALIZAR FILAS SIN RECARGAR
// ════════════════════════════════════════════════════════════════════

function _condicionLabel(val) {
    const map = {
        contado:    'Contado',
        '15_dias':  '15 días',
        '30_dias':  '30 días',
        '60_dias':  '60 días',
        '90_dias':  '90 días',
        consignacion: 'Consignación',
    };
    return map[val] || val || '—';
}

function _buildCeldas(data, body) {
    // Proveedor (nombre + sitio web)
    const sitioHtml = body.sitio_web
        ? `<div class="nx-cell-sub"><a href="${body.sitio_web}" target="_blank" class="nx-link">${body.sitio_web}</a></div>`
        : '';
    const proveedorHtml = `<div class="nx-cell-main">${body.nombre}</div>${sitioHtml}`;

    // CUIT
    const cuitHtml = body.cuit || '—';

    // Contacto
    let contactoHtml;
    if (body.contacto_nombre) {
        contactoHtml = `<div class="nx-cell-main">${body.contacto_nombre}</div>
            ${body.contacto_cargo ? `<div class="nx-cell-sub">${body.contacto_cargo}</div>` : ''}`;
    } else if (body.email) {
        contactoHtml = `<div class="nx-cell-sub">${body.email}</div>`;
    } else {
        contactoHtml = '<span class="nx-empty">—</span>';
    }

    // Ciudad
    const ciudadHtml = body.ciudad || '—';

    // Condición de pago
    const condicionHtml = `<span class="nx-badge nx-badge--pago">${_condicionLabel(body.condicion_pago)}</span>`;

    // Estado
    const estadoHtml = body.activo
        ? '<span class="nx-badge nx-badge--activo">Activo</span>'
        : '<span class="nx-badge nx-badge--inactivo">Inactivo</span>';

    // Acciones
    const nombre = (body.nombre || '').replace(/'/g, "\\'");
    const accionesHtml = `
        <button class="nx-btn-icon btn-editar" data-pk="${data.pk}" title="Editar">✎</button>
        <button class="nx-btn-icon btn-eliminar nx-btn-icon--danger" data-pk="${data.pk}" data-nombre="${body.nombre}" title="Eliminar">✕</button>`;

    return { proveedorHtml, cuitHtml, contactoHtml, ciudadHtml, condicionHtml, estadoHtml, accionesHtml };
}

function agregarFilaTabla(data, body) {
    // Si hay estado vacío, reemplazar con la tabla
    const wrap = document.querySelector('.nx-table-wrap');
    if (!wrap) return;

    let tabla = document.getElementById('tabla-proveedores');
    if (!tabla) {
        wrap.innerHTML = `
            <table class="nx-table" id="tabla-proveedores">
                <thead><tr>
                    <th>Proveedor</th><th>CUIT</th><th>Contacto</th>
                    <th>Ciudad</th><th>Condición</th><th>Estado</th>
                    <th class="nx-th-actions">Acciones</th>
                </tr></thead>
                <tbody></tbody>
            </table>`;
        tabla = document.getElementById('tabla-proveedores');
        // Re-adjuntar eventos de tabla (editar y eliminar)
        adjuntarEventosTabla();
    }

    const c = _buildCeldas(data, body);
    const tr = document.createElement('tr');
    tr.className     = 'nx-tr';
    tr.dataset.pk    = data.pk;
    tr.dataset.activo = body.activo ? 'true' : 'false';
    tr.innerHTML = `
        <td>${c.proveedorHtml}</td>
        <td class="nx-cell-mono">${c.cuitHtml}</td>
        <td>${c.contactoHtml}</td>
        <td>${c.ciudadHtml}</td>
        <td>${c.condicionHtml}</td>
        <td>${c.estadoHtml}</td>
        <td class="nx-td-actions">${c.accionesHtml}</td>`;

    // Animación entrada
    tr.style.opacity   = '0';
    tr.style.transition = 'opacity .2s ease';
    tabla.querySelector('tbody').prepend(tr);
    requestAnimationFrame(() => { tr.style.opacity = '1'; });
}

function actualizarFilaTabla(pk, data, body) {
    const tr = document.querySelector(`tr[data-pk="${pk}"]`);
    if (!tr) return;

    const c = _buildCeldas(data, body);
    tr.dataset.activo = body.activo ? 'true' : 'false';
    tr.cells[0].innerHTML = c.proveedorHtml;
    tr.cells[1].innerHTML = c.cuitHtml;
    tr.cells[2].innerHTML = c.contactoHtml;
    tr.cells[3].innerHTML = c.ciudadHtml;
    tr.cells[4].innerHTML = c.condicionHtml;
    tr.cells[5].innerHTML = c.estadoHtml;
    tr.cells[6].innerHTML = c.accionesHtml;

    // Destello visual
    tr.style.transition = 'background .15s';
    tr.style.background = 'rgba(34,197,94,0.07)';
    setTimeout(() => { tr.style.background = ''; }, 700);
}

function actualizarContadores(deltTotal, deltActivo) {
    const elTotal  = document.querySelector('.nx-stat-pill:not(.nx-stat-pill--green) .nx-stat-pill-val');
    const elActivo = document.querySelector('.nx-stat-pill--green .nx-stat-pill-val');
    if (elTotal  && deltTotal  !== 0) elTotal.textContent  = Math.max(0, (parseInt(elTotal.textContent)  || 0) + deltTotal);
    if (elActivo && deltActivo !== 0) elActivo.textContent = Math.max(0, (parseInt(elActivo.textContent) || 0) + deltActivo);
}

// Re-adjunta eventos cuando se crea la tabla desde cero (estado vacío → primer proveedor)
function adjuntarEventosTabla() {
    const tabla = document.getElementById('tabla-proveedores');
    if (!tabla) return;

    tabla.addEventListener('click', async (e) => {
        // Editar
        const btnEditar = e.target.closest('.btn-editar');
        if (btnEditar) {
            const pk = btnEditar.dataset.pk;
            try {
                const r    = await fetch(`${URL_ACCIONES}?pk=${pk}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                const data = await r.json();
                document.getElementById('modal-titulo').textContent = 'Editar proveedor';
                document.getElementById('f-pk').value = data.pk;
                setVal('id_nombre', data.nombre); setVal('id_cuit', data.cuit);
                setVal('id_tipo', data.tipo); setVal('id_sitio_web', data.sitio_web);
                setVal('id_descripcion', data.descripcion); setCheck('id_activo', data.activo);
                setVal('id_email', data.email); setVal('id_telefono', data.telefono);
                setVal('id_contacto_nombre', data.contacto_nombre); setVal('id_contacto_cargo', data.contacto_cargo);
                setVal('id_calle', data.calle); setVal('id_ciudad', data.ciudad);
                setVal('id_provincia', data.provincia); setVal('id_pais', data.pais);
                setVal('id_condicion_pago', data.condicion_pago); setVal('id_moneda', data.moneda);
                setVal('id_dias_entrega', data.dias_entrega); setVal('id_notas', data.notas);
                abrirModal();
            } catch { showToast('Error al cargar el proveedor.', 'error'); }
        }

        // Eliminar
        const btnEliminar = e.target.closest('.btn-eliminar');
        if (btnEliminar) {
            pkAEliminar = btnEliminar.dataset.pk;
            document.getElementById('nombre-a-eliminar').textContent = btnEliminar.dataset.nombre;
            modalEliminar.style.display = 'flex';
        }
    });
}