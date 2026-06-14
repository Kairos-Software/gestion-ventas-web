'use strict';

const VDT = window.VDT_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   TOTAL — se pasa desde el template como número puro (sin formato
   local), pero por las dudas parseamos con reemplazo de coma.
════════════════════════════════════════════════════════════════ */
function _parsearTotal(val) {
    if (typeof val === 'number') return val;
    // Si Django renderizó con coma decimal (locale es-AR), lo normalizamos
    return parseFloat(String(val).replace(/\./g, '').replace(',', '.')) || 0;
}

/* ════════════════════════════════════════════════════════════════
   MÓDULO DE PAGOS — solo activo si es borrador
════════════════════════════════════════════════════════════════ */
const pagoState = {
    lineas: [],
    nextId: 0,
    total:  _parsearTotal(VDT.ventaTotal),
};

function _fmtARS(v) {
    return '$ ' + parseFloat(v || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

function _pagoMediosOpts(seleccionado) {
    return (VDT.mediosPago || []).map(m =>
        `<option value="${m.value}" ${m.value === seleccionado ? 'selected' : ''}>${m.label}</option>`
    ).join('');
}

function _renderLineas() {
    const contenedor = document.getElementById('vdtPagoLineas');
    if (!contenedor) return;

    if (!pagoState.lineas.length) {
        contenedor.innerHTML = `
        <p style="font-size:.8125rem;color:var(--text-muted);margin:.25rem 0">
            Sin medios de pago. Usá el botón de abajo para agregar.
        </p>`;
        _actualizarResumen();
        return;
    }

    contenedor.innerHTML = pagoState.lineas.map(l => `
    <div class="vdt-pago-linea" data-linea-id="${l.id}">
        <select class="vdt-pago-select" data-campo="medio" data-id="${l.id}">
            ${_pagoMediosOpts(l.medio)}
        </select>
        <input type="number" class="vdt-pago-monto" min="0" step="0.01"
               placeholder="Monto"
               value="${l.monto > 0 ? l.monto : ''}"
               data-campo="monto" data-id="${l.id}">
        <button class="vdt-pago-btn-quitar" data-id="${l.id}" title="Quitar">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
        </button>
    </div>`).join('');

    // Bind eventos
    contenedor.querySelectorAll('[data-campo]').forEach(el => {
        el.addEventListener('change', () => {
            const id    = parseInt(el.dataset.id, 10);
            const campo = el.dataset.campo;
            const linea = pagoState.lineas.find(l => l.id === id);
            if (!linea) return;
            linea[campo] = campo === 'monto' ? (parseFloat(el.value) || 0) : el.value;
            _actualizarResumen();
        });
        if (el.dataset.campo === 'monto') {
            el.addEventListener('input', () => {
                const id    = parseInt(el.dataset.id, 10);
                const linea = pagoState.lineas.find(l => l.id === id);
                if (linea) { linea.monto = parseFloat(el.value) || 0; _actualizarResumen(); }
            });
        }
    });

    contenedor.querySelectorAll('.vdt-pago-btn-quitar').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = parseInt(btn.dataset.id, 10);
            pagoState.lineas = pagoState.lineas.filter(l => l.id !== id);
            _renderLineas();
        });
    });

    _actualizarResumen();
}

function _actualizarResumen() {
    const asignado  = pagoState.lineas.reduce((s, l) => s + (l.monto || 0), 0);
    const pendiente = pagoState.total - asignado;
    const exceso    = asignado - pagoState.total;

    const resumenEl   = document.getElementById('vdtPagoResumen');
    const asignadoEl  = document.getElementById('vdtPagoAsignado');
    const pendienteEl = document.getElementById('vdtPagoPendiente');

    if (asignadoEl)  asignadoEl.textContent  = _fmtARS(asignado);
    if (pendienteEl) pendienteEl.textContent  =
        exceso > 0.005 ? `Exceso: ${_fmtARS(exceso)}` : _fmtARS(Math.max(0, pendiente));

    if (resumenEl) {
        resumenEl.className = 'vdt-pago-resumen ';
        if (Math.abs(pendiente) < 0.005 && pagoState.lineas.length) {
            resumenEl.classList.add('vdt-pago-resumen--ok');
            resumenEl.innerHTML = `
            <span>
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none" style="vertical-align:middle;margin-right:4px">
                    <path d="M2 7L5.5 10.5L12 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Pago cubierto
            </span>
            <span>Total: <strong>${_fmtARS(asignado)}</strong></span>`;
        } else if (exceso > 0.005) {
            resumenEl.classList.add('vdt-pago-resumen--exceso');
            resumenEl.innerHTML = `
            <span>Asignado: <strong>${_fmtARS(asignado)}</strong></span>
            <span>Exceso: <strong>${_fmtARS(exceso)}</strong></span>`;
        } else {
            resumenEl.classList.add('vdt-pago-resumen--pendiente');
            resumenEl.innerHTML = `
            <span>Asignado: <strong>${_fmtARS(asignado)}</strong></span>
            <span>Pendiente: <strong>${_fmtARS(pendiente)}</strong></span>`;
        }
    }
}

function _agregarLinea() {
    const asignado = pagoState.lineas.reduce((s, l) => s + (l.monto || 0), 0);
    const restante = Math.max(0, pagoState.total - asignado);
    pagoState.lineas.push({
        id:    pagoState.nextId++,
        medio: (VDT.mediosPago && VDT.mediosPago[0]) ? VDT.mediosPago[0].value : 'efectivo',
        monto: parseFloat(restante.toFixed(2)),
    });
    _renderLineas();
}

function _pagoEsCubierto() {
    const asignado = pagoState.lineas.reduce((s, l) => s + (l.monto || 0), 0);
    return Math.abs(pagoState.total - asignado) < 0.005 && pagoState.lineas.length > 0;
}

function _getPagoPayload() {
    const pagos     = pagoState.lineas.map(l => ({ medio: l.medio, monto: l.monto }));
    const principal = pagos.length ? pagos[0].medio : 'efectivo';
    return { medio_pago: principal, pagos };
}

/* ════════════════════════════════════════════════════════════════
   INIT — agrega línea inicial con el total completo
════════════════════════════════════════════════════════════════ */
if (VDT.esBorrador) {
    pagoState.lineas.push({
        id:    pagoState.nextId++,
        medio: (VDT.mediosPago && VDT.mediosPago[0]) ? VDT.mediosPago[0].value : 'efectivo',
        monto: parseFloat((pagoState.total).toFixed(2)),
    });
    _renderLineas();

    const btnAgregar = document.getElementById('vdtBtnAgregarPago');
    if (btnAgregar) btnAgregar.addEventListener('click', _agregarLinea);
}

/* ════════════════════════════════════════════════════════════════
   CONFIRMAR Y VOLVER
════════════════════════════════════════════════════════════════ */
if (VDT.esBorrador) {
    const btnConfirmar = document.getElementById('vdtBtnConfirmar');
    const btnVolver    = document.getElementById('vdtBtnVolver');
    const inputFecha   = document.getElementById('vdtFecha');
    const inputNotas   = document.getElementById('vdtNotas');

    if (btnConfirmar) {
        btnConfirmar.addEventListener('click', async () => {
            const fecha = inputFecha ? inputFecha.value : '';
            if (!fecha) {
                vdtToast('Fecha requerida', 'Ingresá una fecha antes de confirmar.');
                return;
            }

            if (!_pagoEsCubierto()) {
                const asignado  = pagoState.lineas.reduce((s, l) => s + (l.monto || 0), 0);
                const pendiente = pagoState.total - asignado;
                if (!pagoState.lineas.length) {
                    vdtToast('Medio de pago requerido', 'Agregá al menos un medio de pago.');
                } else {
                    vdtToast('Pago incompleto', `Falta cubrir ${_fmtARS(pendiente)}.`);
                }
                return;
            }

            btnConfirmar.disabled  = true;
            btnConfirmar.innerHTML = `<svg class="vta-spin" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
            </svg> Confirmando…`;

            const pagoPayload = _getPagoPayload();

            try {
                const res  = await fetch(VDT.urlConfirmar, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': VDT.csrfToken },
                    body:    JSON.stringify({
                        venta_pk:   VDT.ventaPk,
                        fecha:      fecha,
                        notas:      inputNotas ? inputNotas.value.trim() : '',
                        medio_pago: pagoPayload.medio_pago,
                    }),
                });
                const data = await res.json();

                if (data.ok) {
                    window.location.href = VDT.urlHistorial;
                } else {
                    vdtToast('Error al confirmar', data.error || 'No se pudo confirmar la venta.');
                    btnConfirmar.disabled  = false;
                    btnConfirmar.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6"
                              stroke-linecap="round" stroke-linejoin="round"/>
                    </svg> Confirmar venta`;
                }
            } catch {
                vdtToast('Error de conexión', 'Intentá de nuevo.');
                btnConfirmar.disabled  = false;
                btnConfirmar.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6"
                          stroke-linecap="round" stroke-linejoin="round"/>
                </svg> Confirmar venta`;
            }
        });
    }

    if (btnVolver) {
        btnVolver.addEventListener('click', async () => {
            const ok = confirm('¿Volvés a editar el carrito? El borrador se descartará.');
            if (!ok) return;

            btnVolver.disabled  = true;
            btnVolver.innerHTML = `<svg class="vta-spin" width="14" height="14" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
            </svg> Descartando…`;

            try {
                const res  = await fetch(VDT.urlEliminarBorrador, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': VDT.csrfToken },
                    body:    JSON.stringify({ venta_pk: VDT.ventaPk }),
                });
                const data = await res.json();

                if (data.ok) {
                    window.location.href = VDT.urlNuevaVenta;
                } else {
                    vdtToast('Error', data.error || 'No se pudo descartar el borrador.');
                    btnVolver.disabled  = false;
                    btnVolver.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M11 7H3M6.5 3L3 7L6.5 11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg> Volver y editar carrito`;
                }
            } catch {
                vdtToast('Error de conexión', 'Intentá de nuevo.');
                btnVolver.disabled = false;
            }
        });
    }
}

/* ════════════════════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════════════════════ */
function vdtToast(titulo, cuerpo) {
    const toast = document.getElementById('vdtToast');
    if (!toast) return;
    document.getElementById('vdtToastTitle').textContent = titulo;
    document.getElementById('vdtToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

function vdtEsc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}