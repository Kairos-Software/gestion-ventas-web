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
            setTimeout(() => location.reload(), 800);
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
            // Quitar la fila sin recargar
            const fila = document.querySelector(`tr[data-pk="${pkAEliminar}"]`);
            if (fila) fila.remove();
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