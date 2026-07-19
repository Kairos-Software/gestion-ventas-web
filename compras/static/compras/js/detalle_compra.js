'use strict';

const CDT = window.CDT_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   REFS DOM
════════════════════════════════════════════════════════════════ */
const cdtDocZone  = document.getElementById('cdtDocZone');
const cdtDocInput = document.getElementById('cdtDocInput');
const cdtDocLista = document.getElementById('cdtDocLista');

/* ════════════════════════════════════════════════════════════════
   MÓDULO DE PAGOS — solo activo si es borrador
   Un solo selector por línea: "Efectivo" es una cuenta más de la
   lista (siempre está — ver asegurar_cuentas_efectivo). No se
   pregunta transferencia/débito/QR por separado: no importa CÓMO
   pagaste, importa DE QUÉ CUENTA salió la plata (o que fue efectivo).
════════════════════════════════════════════════════════════════ */
const cdtPagoState = {
    lineas: [],
    nextId: 0,
    total:  parseFloat(CDT.compraTotal) || 0,
};

function _cdtFmtARS(v) {
    return '$ ' + parseFloat(v || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
}

/** La compra siempre está en pesos, pero se puede pagar desde una
 *  cuenta en cualquier moneda (transferencia/efectivo/tarjeta en
 *  dólares, etc. — Argentina acepta cualquier moneda si ambas partes
 *  acuerdan). Ver cotización más abajo para la conversión. */
function _cdtCuentasDisponibles() {
    return CDT.cuentas || [];
}

function _cdtTarjetasDisponibles() {
    return CDT.tarjetas || [];
}

function _cdtEsTarjeta(cuentaPk) {
    return _cdtTarjetasDisponibles().some(t => String(t.pk) === String(cuentaPk));
}

function _cdtCuentaEfectivo() {
    return _cdtCuentasDisponibles().find(c => c.nombre === 'Efectivo' && c.moneda === 'ARS');
}

/** Cuenta o tarjeta elegida en una línea (ambas listas juntas). */
function _cdtCuentaInfo(cuentaPk) {
    return _cdtCuentasDisponibles().concat(_cdtTarjetasDisponibles())
        .find(c => String(c.pk) === String(cuentaPk));
}

/** Equivalente en pesos de una línea de pago — igual criterio que
 *  PagoCompra.monto_ars en el backend. */
function _cdtMontoArsLinea(l) {
    const info = _cdtCuentaInfo(l.cuenta);
    if (info && info.moneda !== 'ARS') {
        return (l.monto || 0) * (l.cotizacion || 0);
    }
    return l.monto || 0;
}

/** Input de cotización — solo aparece si la cuenta elegida no es en
 *  pesos. No hay ninguna fuente automática de tipo de cambio: lo
 *  carga quien confirma la compra con lo que acordó en el pago. */
function _cdtCotizacionInputHTML(l) {
    const info = _cdtCuentaInfo(l.cuenta);
    if (!info || info.moneda === 'ARS') return '';
    return `
        <input type="number" class="vdt-pago-cotizacion" min="0.0001" step="0.0001"
               placeholder="Cotización ($ por 1 ${info.moneda})"
               value="${l.cotizacion || ''}"
               data-campo="cotizacion" data-id="${l.id}">`;
}

/** "≈ $ X" — cuánto vale en pesos esta línea, para ver la conversión
 *  mientras se escribe. Vacío si no hace falta. */
function _cdtEquivalenteArsHTML(l) {
    const info = _cdtCuentaInfo(l.cuenta);
    if (!info || info.moneda === 'ARS' || !l.cotizacion) return '';
    return `<span class="vdt-pago-equivalente">≈ ${_cdtFmtARS(_cdtMontoArsLinea(l))}</span>`;
}

function _cdtPagoCuentaOpts(seleccionada) {
    const cuentasOpts = _cdtCuentasDisponibles().map(c =>
        `<option value="${c.pk}" ${String(c.pk) === String(seleccionada) ? 'selected' : ''}>${c.nombre} (${c.moneda})</option>`
    ).join('');
    const tarjetas = _cdtTarjetasDisponibles();
    const tarjetasOpts = tarjetas.length ? `<optgroup label="Tarjeta de crédito">${tarjetas.map(t =>
        `<option value="${t.pk}" ${String(t.pk) === String(seleccionada) ? 'selected' : ''}>${t.nombre}${t.terminada_en ? ' ·· ' + t.terminada_en : ''} (${t.moneda})</option>`
    ).join('')}</optgroup>` : '';
    return '<option value="">— Elegí cuenta o Efectivo —</option>' + cuentasOpts + tarjetasOpts;
}

function _cdtPagoRenderLineas() {
    const contenedor = document.getElementById('cdtPagoLineas');
    if (!contenedor) return;

    if (!cdtPagoState.lineas.length) {
        contenedor.innerHTML = `
        <p style="font-size:.8125rem;color:var(--text-muted);margin:.25rem 0">
            Sin medios de pago. Usá el botón de abajo para agregar.
        </p>`;
        _cdtPagoActualizarResumen();
        return;
    }

    contenedor.innerHTML = cdtPagoState.lineas.map(l => {
        const esTarjeta = _cdtEsTarjeta(l.cuenta);
        return `
    <div class="vdt-pago-linea-wrap" data-linea-id="${l.id}">
        <div class="vdt-pago-linea">
            <select class="vdt-pago-select" data-campo="cuenta" data-id="${l.id}">
                ${_cdtPagoCuentaOpts(l.cuenta)}
            </select>
            <input type="number" class="vdt-pago-monto" min="0" step="0.01"
                   placeholder="Monto"
                   value="${l.monto > 0 ? l.monto : ''}"
                   data-campo="monto" data-id="${l.id}">
            <button class="vdt-pago-btn-quitar" type="button" data-id="${l.id}" title="Quitar">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </button>
        </div>
        ${(_cdtCotizacionInputHTML(l) || _cdtEquivalenteArsHTML(l)) ? `
        <div class="vdt-pago-linea-cuenta">
            ${_cdtCotizacionInputHTML(l)}
            ${_cdtEquivalenteArsHTML(l)}
        </div>` : ''}
        ${esTarjeta ? `
        <div class="vdt-pago-credito-extra">
            <div>
                <span class="vdt-pago-credito-label">Cuotas</span>
                <input type="number" class="vdt-pago-select" min="1" step="1" placeholder="Cuotas"
                       value="${l.cuotas || ''}" data-campo="cuotas" data-id="${l.id}">
            </div>
            <div>
                <span class="vdt-pago-credito-label">Interés %</span>
                <input type="number" class="vdt-pago-select" min="0" step="0.01" placeholder="0"
                       value="${l.interesPct != null ? l.interesPct : ''}" data-campo="interesPct" data-id="${l.id}">
            </div>
            <div>
                <span class="vdt-pago-credito-label">Inicio débito</span>
                <input type="date" class="vdt-pago-select"
                       value="${l.fechaInicioDebito || ''}" data-campo="fechaInicioDebito" data-id="${l.id}">
            </div>
        </div>` : ''}
    </div>`;
    }).join('');

    contenedor.querySelectorAll('[data-campo]').forEach(el => {
        el.addEventListener('change', () => {
            const id    = parseInt(el.dataset.id, 10);
            const campo = el.dataset.campo;
            const linea = cdtPagoState.lineas.find(l => l.id === id);
            if (!linea) return;
            if (campo === 'monto') {
                linea.monto = parseFloat(el.value) || 0;
            } else if (campo === 'cuotas') {
                linea.cuotas = parseInt(el.value, 10) || null;
            } else if (campo === 'interesPct') {
                linea.interesPct = el.value === '' ? 0 : parseFloat(el.value);
            } else if (campo === 'cotizacion') {
                linea.cotizacion = parseFloat(el.value) || 0;
            } else {
                linea[campo] = el.value;
            }
            if (campo === 'cuenta') {
                linea.cotizacion = ''; // cambiar de cuenta resetea la cotización cargada
                _cdtPagoRenderLineas();
            } else if (campo === 'cotizacion') {
                _cdtPagoRenderLineas();
            } else {
                _cdtPagoActualizarResumen();
            }
        });
        if (el.dataset.campo === 'monto') {
            el.addEventListener('input', () => {
                const id    = parseInt(el.dataset.id, 10);
                const linea = cdtPagoState.lineas.find(l => l.id === id);
                if (linea) { linea.monto = parseFloat(el.value) || 0; _cdtPagoActualizarResumen(); }
            });
        }
        if (el.dataset.campo === 'cotizacion') {
            el.addEventListener('input', () => {
                const id    = parseInt(el.dataset.id, 10);
                const linea = cdtPagoState.lineas.find(l => l.id === id);
                if (linea) { linea.cotizacion = parseFloat(el.value) || 0; _cdtPagoActualizarResumen(); }
            });
        }
    });

    contenedor.querySelectorAll('.vdt-pago-btn-quitar').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = parseInt(btn.dataset.id, 10);
            cdtPagoState.lineas = cdtPagoState.lineas.filter(l => l.id !== id);
            _cdtPagoRenderLineas();
        });
    });

    _cdtPagoActualizarResumen();
}

function _cdtPagoActualizarResumen() {
    const asignado  = cdtPagoState.lineas.reduce((s, l) => s + _cdtMontoArsLinea(l), 0);
    const pendiente = cdtPagoState.total - asignado;
    const exceso    = asignado - cdtPagoState.total;

    const resumenEl   = document.getElementById('cdtPagoResumen');
    const asignadoEl  = document.getElementById('cdtPagoAsignado');
    const pendienteEl = document.getElementById('cdtPagoPendiente');

    if (asignadoEl)  asignadoEl.textContent  = _cdtFmtARS(asignado);
    if (pendienteEl) pendienteEl.textContent =
        exceso > 0.005 ? `Exceso: ${_cdtFmtARS(exceso)}` : _cdtFmtARS(Math.max(0, pendiente));

    if (resumenEl) {
        resumenEl.className = 'vdt-pago-resumen ';
        if (Math.abs(pendiente) < 0.005 && cdtPagoState.lineas.length) {
            resumenEl.classList.add('vdt-pago-resumen--ok');
            resumenEl.innerHTML = `
            <span>
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none" style="vertical-align:middle;margin-right:4px">
                    <path d="M2 7L5.5 10.5L12 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Pago cubierto
            </span>
            <span>Total: <strong>${_cdtFmtARS(asignado)}</strong></span>`;
        } else if (exceso > 0.005) {
            resumenEl.classList.add('vdt-pago-resumen--exceso');
            resumenEl.innerHTML = `
            <span>Asignado: <strong>${_cdtFmtARS(asignado)}</strong></span>
            <span>Exceso: <strong>${_cdtFmtARS(exceso)}</strong></span>`;
        } else {
            resumenEl.classList.add('vdt-pago-resumen--pendiente');
            resumenEl.innerHTML = `
            <span>Asignado: <strong>${_cdtFmtARS(asignado)}</strong></span>
            <span>Pendiente: <strong>${_cdtFmtARS(pendiente)}</strong></span>`;
        }
    }
}

function _cdtPagoAgregarLinea() {
    const asignado = cdtPagoState.lineas.reduce((s, l) => s + _cdtMontoArsLinea(l), 0);
    const restante = Math.max(0, cdtPagoState.total - asignado);
    const efectivo = _cdtCuentaEfectivo();
    cdtPagoState.lineas.push({
        id:    cdtPagoState.nextId++,
        monto: parseFloat(restante.toFixed(2)),
        cuenta: efectivo ? efectivo.pk : '',
    });
    _cdtPagoRenderLineas();
}

function _cdtPagoEsCubierto() {
    const asignado = cdtPagoState.lineas.reduce((s, l) => s + _cdtMontoArsLinea(l), 0);
    return Math.abs(cdtPagoState.total - asignado) < 0.005 && cdtPagoState.lineas.length > 0;
}

/** Toda línea necesita una cuenta elegida, y si esa cuenta no es en
 *  pesos, también la cotización usada. */
function _cdtPagoFaltanCuentas() {
    return cdtPagoState.lineas.some(l => {
        if (!l.cuenta) return true;
        const info = _cdtCuentaInfo(l.cuenta);
        return !!info && info.moneda !== 'ARS' && !(l.cotizacion > 0);
    });
}

function _cdtPagoFaltanDatosCredito() {
    return cdtPagoState.lineas.some(l =>
        _cdtEsTarjeta(l.cuenta) && (!l.cuotas || l.cuotas < 1 || !l.fechaInicioDebito)
    );
}

function _cdtGetPagoPayload() {
    const pagos = cdtPagoState.lineas.map(l => {
        if (_cdtEsTarjeta(l.cuenta)) {
            return {
                medio: 'credito',
                monto: l.monto,
                cuenta_pk: l.cuenta || null,
                cotizacion: l.cotizacion || null,
                cuotas: l.cuotas,
                interes_pct: l.interesPct != null ? l.interesPct : 0,
                fecha_inicio_debito: l.fechaInicioDebito || null,
            };
        }
        const cuentaInfo = _cdtCuentasDisponibles().find(c => String(c.pk) === String(l.cuenta));
        const esEfectivo = cuentaInfo && cuentaInfo.nombre === 'Efectivo' && cuentaInfo.moneda === 'ARS';
        return {
            medio: esEfectivo ? 'efectivo' : 'transferencia',
            monto: l.monto,
            cuenta_pk: l.cuenta || null,
            cotizacion: l.cotizacion || null,
        };
    });
    return { pagos };
}

/* ════════════════════════════════════════════════════════════════
   BORRADOR — Confirmar y Volver
════════════════════════════════════════════════════════════════ */
if (CDT.esBorrador) {
    const btnConfirmar = document.getElementById('cdtBtnConfirmar');
    const btnEditar    = document.getElementById('cdtBtnEditar');
    const btnVolver    = document.getElementById('cdtBtnVolver');
    const inputFecha   = document.getElementById('cdtFecha');
    const inputNotas   = document.getElementById('cdtNotas');

    /* ── Widget de pagos: línea inicial con el total completo,
           precargada en Efectivo si existe ──────────────────────── */
    const cdtEfectivoInicial = _cdtCuentaEfectivo();
    cdtPagoState.lineas.push({
        id:    cdtPagoState.nextId++,
        monto: parseFloat(cdtPagoState.total.toFixed(2)),
        cuenta: cdtEfectivoInicial ? cdtEfectivoInicial.pk : '',
    });
    _cdtPagoRenderLineas();

    const btnAgregarPago = document.getElementById('cdtBtnAgregarPago');
    if (btnAgregarPago) btnAgregarPago.addEventListener('click', _cdtPagoAgregarLinea);

    /* ── Editar carrito (vuelve a Nueva Compra CON los productos cargados) ── */
    btnEditar.addEventListener('click', () => {
        window.location.href = CDT.urlEditarCarrito;
    });

    /* ── Confirmar compra ─────────────────────────────────────── */
    btnConfirmar.addEventListener('click', async () => {
        const fecha = inputFecha.value;
        if (!fecha) { cdtToast('Fecha requerida', 'Ingresá una fecha antes de confirmar.'); return; }

        if (!_cdtPagoEsCubierto()) {
            const asignado  = cdtPagoState.lineas.reduce((s, l) => s + _cdtMontoArsLinea(l), 0);
            const pendiente = cdtPagoState.total - asignado;
            if (!cdtPagoState.lineas.length) {
                cdtToast('Medio de pago requerido', 'Agregá al menos un medio de pago.');
            } else {
                cdtToast('Pago incompleto', `Falta cubrir ${_cdtFmtARS(pendiente)}.`);
            }
            return;
        }

        if (_cdtPagoFaltanCuentas()) {
            cdtToast('Cuenta requerida', 'Elegí a qué cuenta se debita cada línea de pago, y la cotización si es en otra moneda.');
            return;
        }

        if (_cdtPagoFaltanDatosCredito()) {
            cdtToast('Datos de la tarjeta incompletos', 'Completá cuotas y fecha de inicio de débito para cada pago con tarjeta.');
            return;
        }

        btnConfirmar.disabled  = true;
        btnConfirmar.innerHTML = `<svg class="cmp-spin" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Confirmando…`;

        const pagoPayload = _cdtGetPagoPayload();

        try {
            const res  = await fetch(CDT.urlConfirmar, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CDT.csrfToken },
                body:    JSON.stringify({
                    compra_pk: CDT.compraPk,
                    fecha:     fecha,
                    notas:     inputNotas ? inputNotas.value.trim() : '',
                    pagos:     pagoPayload.pagos,
                }),
            });
            const data = await res.json();

            if (data.ok) {
                // Redirigir al historial con la compra ya confirmada
                window.location.href = CDT.urlHistorial;
            } else {
                cdtToast('Error al confirmar', data.error || 'No se pudo confirmar la compra.');
            }
        } catch {
            cdtToast('Error de conexión', 'Intentá de nuevo.');
        } finally {
            btnConfirmar.disabled  = false;
            btnConfirmar.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg> Confirmar compra`;
        }
    });

    /* ── Cancelar compra (descarta todo el borrador) ──────────── */
    btnVolver.addEventListener('click', async () => {
        const ok = await KaiConfirm('¿Cancelar esta compra? El borrador y todos los productos cargados se van a perder.', { danger: true, confirmText: 'Cancelar compra' });
        if (!ok) return;

        btnVolver.disabled  = true;
        btnVolver.innerHTML = `<svg class="cmp-spin" width="14" height="14" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Cancelando…`;

        try {
            const res  = await fetch(CDT.urlEliminarBorrador, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CDT.csrfToken },
                body:    JSON.stringify({ compra_pk: CDT.compraPk }),
            });
            const data = await res.json();

            if (data.ok) {
                window.location.href = CDT.urlNuevaCompra;
            } else {
                cdtToast('Error', data.error || 'No se pudo cancelar la compra.');
                btnVolver.disabled  = false;
                btnVolver.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                </svg> Cancelar compra`;
            }
        } catch {
            cdtToast('Error de conexión', 'Intentá de nuevo.');
            btnVolver.disabled = false;
        }
    });
}

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Selección por input
════════════════════════════════════════════════════════════════ */
cdtDocInput.addEventListener('change', () => {
    cdtSubirArchivos(Array.from(cdtDocInput.files));
    cdtDocInput.value = '';
});

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Drag & drop
════════════════════════════════════════════════════════════════ */
cdtDocZone.addEventListener('dragover', e => {
    e.preventDefault();
    cdtDocZone.classList.add('over');
});
cdtDocZone.addEventListener('dragleave', () => cdtDocZone.classList.remove('over'));
cdtDocZone.addEventListener('drop', e => {
    e.preventDefault();
    cdtDocZone.classList.remove('over');
    cdtSubirArchivos(Array.from(e.dataTransfer.files));
});

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Subir
════════════════════════════════════════════════════════════════ */
async function cdtSubirArchivos(files) {
    const PERMITIDOS = ['jpg','jpeg','png','webp','gif','pdf'];
    for (const file of files) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!PERMITIDOS.includes(ext)) {
            cdtToast('Tipo no permitido', `"${file.name}" debe ser JPG, PNG, WEBP, GIF o PDF.`);
            continue;
        }
        if (file.size > 10 * 1024 * 1024) {
            cdtToast('Archivo muy grande', `"${file.name}" supera los 10 MB.`);
            continue;
        }

        const tempId = `uploading-${Date.now()}`;
        cdtDocLista.insertAdjacentHTML('beforeend', `
            <div class="cmp-doc-item cmp-doc-item--uploading" id="${tempId}">
                <div class="cmp-doc-item-icon">
                    <svg class="cmp-spin" width="18" height="18" viewBox="0 0 18 18" fill="none">
                        <circle cx="9" cy="9" r="7" stroke="currentColor" stroke-width="1.5" stroke-dasharray="22 22" opacity=".3"/>
                        <path d="M9 2a7 7 0 0 1 7 7" stroke="var(--brand-orange)" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                </div>
                <div class="cmp-doc-item-info">
                    <span class="cmp-doc-item-nombre">${cdtEsc(file.name)}</span>
                    <span class="cmp-doc-item-tipo">Subiendo…</span>
                </div>
            </div>`);

        const fd = new FormData();
        fd.append('compra_pk', CDT.compraPk);
        fd.append('archivo',   file);
        fd.append('tipo',      document.getElementById('cdtDocTipo').value);

        try {
            const res  = await fetch(CDT.urlDocSubir, {
                method:  'POST',
                headers: { 'X-CSRFToken': CDT.csrfToken },
                body:    fd,
            });
            const data = await res.json();
            const tempEl = document.getElementById(tempId);

            if (data.ok) {
                if (tempEl) tempEl.outerHTML = cdtRenderDocItem(data);
                cdtActualizarBadge();
                cdtToast('Documento guardado', `"${data.nombre}" subido correctamente.`);
            } else {
                tempEl?.remove();
                cdtToast('Error al subir', data.error || 'No se pudo guardar el archivo.');
            }
        } catch {
            document.getElementById(tempId)?.remove();
            cdtToast('Error de conexión', 'No se pudo subir el archivo.');
        }
    }
}

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Eliminar
════════════════════════════════════════════════════════════════ */
async function cdtEliminarDoc(pk) {
    if (!await KaiConfirm('¿Eliminar este documento? Esta acción no se puede deshacer.', { danger: true, confirmText: 'Eliminar' })) return;
    try {
        const res  = await fetch(CDT.urlDocEliminar, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CDT.csrfToken },
            body:    JSON.stringify({ pk }),
        });
        const data = await res.json();
        if (data.ok) {
            document.getElementById(`cdtdoc-${pk}`)?.remove();
            cdtActualizarBadge();
            cdtToast('Documento eliminado', '');
        } else {
            cdtToast('Error', data.error || 'No se pudo eliminar.');
        }
    } catch {
        cdtToast('Error de conexión', '');
    }
}

/* ════════════════════════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════════════════════════ */
function cdtRenderDocItem(doc) {
    const icono = doc.es_pdf
        ? `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
               <path d="M4 2H11L15 6V16H4V2Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
               <path d="M11 2V6H15" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
               <path d="M6 9H12M6 11.5H9" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
           </svg>`
        : `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
               <rect x="2" y="2" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.2"/>
               <circle cx="6.5" cy="6.5" r="1.3" fill="currentColor" fill-opacity=".4"/>
               <path d="M2 12L5.5 9L8 11L11.5 7.5L16 12" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
           </svg>`;

    return `
    <div class="cmp-doc-item" id="cdtdoc-${doc.pk}">
        <div class="cmp-doc-item-icon">${icono}</div>
        <div class="cmp-doc-item-info">
            <a href="${doc.url}" target="_blank" class="cmp-doc-item-nombre">${cdtEsc(doc.nombre)}</a>
            <span class="cmp-doc-item-tipo">${cdtEsc(doc.tipo_display)}</span>
        </div>
        <button class="cmp-doc-item-del" onclick="cdtEliminarDoc(${doc.pk})" title="Eliminar">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            </svg>
        </button>
    </div>`;
}

function cdtActualizarBadge() {
    const total = cdtDocLista
        ? cdtDocLista.querySelectorAll('.cmp-doc-item:not(.cmp-doc-item--uploading)').length
        : 0;
    const badge = document.getElementById('cdtDocBadge');
    if (!badge) return;
    badge.textContent   = total;
    badge.style.display = total > 0 ? 'inline-flex' : 'none';
}

function cdtToast(titulo, cuerpo) {
    const toast = document.getElementById('cdtToast');
    document.getElementById('cdtToastTitle').textContent = titulo;
    document.getElementById('cdtToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

function cdtEsc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}