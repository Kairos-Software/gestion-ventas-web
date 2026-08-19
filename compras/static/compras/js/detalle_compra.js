'use strict';

const CDT = window.CDT_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   REFS DOM
════════════════════════════════════════════════════════════════ */
const cdtDocZone  = document.getElementById('cdtDocZone');
const cdtDocInput = document.getElementById('cdtDocInput');
const cdtDocLista = document.getElementById('cdtDocLista');

/* ════════════════════════════════════════════════════════════════
   PROVEEDOR DE LA COMPRA — editable también desde acá (pestaña
   General), no solo desde el carrito. Mismo mecanismo que Nueva
   Compra (ver nueva_compra.js _bindProveedorCompraInput), pero acá el
   cambio se manda recién al confirmar (ver el payload de
   ConfirmarCompraAjax más abajo y el backend, que actualiza el
   proveedor de TODOS los ítems antes de resolver los pagos) — nada se
   persiste solo por elegirlo, igual que Fecha/Notas en esta misma
   pestaña.
════════════════════════════════════════════════════════════════ */
let proveedorCompraDetalle = { pk: CDT.proveedorActualPk || null, nombre: CDT.proveedorActualNombre || '' };
let proveedorDetalleSearchTimer;

function _escCdt(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _bindProveedorCompraDetalle() {
    const input    = document.getElementById('cdtProveedorInput');
    const dropdown = document.getElementById('cdtProveedorDropdown');
    const clear    = document.getElementById('cdtProveedorClear');
    if (!input || !dropdown || !clear) return;

    input.value = proveedorCompraDetalle.nombre;
    clear.style.display = proveedorCompraDetalle.pk ? 'inline-flex' : 'none';

    function _aplicarProveedor(pk, nombre) {
        proveedorCompraDetalle = { pk, nombre };
    }

    input.addEventListener('input', () => {
        clearTimeout(proveedorDetalleSearchTimer);
        const q = input.value.trim();
        _aplicarProveedor(null, '');
        clear.style.display = 'none';

        if (!q) {
            dropdown.classList.remove('open');
            dropdown.innerHTML = '';
            return;
        }
        proveedorDetalleSearchTimer = setTimeout(async () => {
            try {
                const res  = await fetch(`${CDT.urlBuscarProveedor}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (input.value.trim() !== q) return; // respuesta vieja
                const results = data.results || [];

                dropdown.innerHTML = results.length
                    ? results.map(p => `
                        <div class="cmp-prov-option" data-pk="${p.pk}" data-nombre="${_escCdt(p.nombre)}">
                            <div class="cmp-prov-option-nombre">${_escCdt(p.nombre)}</div>
                            ${p.cuit ? `<div class="cmp-prov-option-meta">CUIT: ${_escCdt(p.cuit)}</div>` : ''}
                        </div>`).join('')
                    : `<div class="cmp-prov-option" style="color:var(--text-muted);cursor:default">Sin resultados</div>`;

                dropdown.querySelectorAll('.cmp-prov-option[data-pk]').forEach(el => {
                    el.addEventListener('click', () => {
                        const pk     = parseInt(el.dataset.pk, 10);
                        const nombre = el.dataset.nombre;
                        input.value  = nombre;
                        clear.style.display = 'inline-flex';
                        dropdown.classList.remove('open');
                        dropdown.innerHTML = '';
                        _aplicarProveedor(pk, nombre);
                    });
                });
                dropdown.classList.add('open');
            } catch { /* silencioso */ }
        }, 260);
    });

    clear.addEventListener('click', () => {
        input.value = '';
        clear.style.display = 'none';
        _aplicarProveedor(null, '');
        input.focus();
    });

    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target) && e.target !== input) {
            dropdown.classList.remove('open');
        }
    });
}
_bindProveedorCompraDetalle();

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

/** Plata que se termina pagando de más sobre el costo de los productos:
 *  el interés de una línea con tarjeta (compra a crédito) o con cheque
 *  a cuotas, sea modo fijas o libre. Compras no tiene recargo por medio
 *  de pago (eso es cosa de Ventas — TarjetaPago/RecargoMedioPago no
 *  existen acá), así que el único "extra" posible es este interés. */
function _cdtExtraMontoLinea(l) {
    if (!_cdtLineaUsaPlanCuotas(l)) return 0;
    return (l.monto || 0) * (l.interesPct || 0) / 100;
}

function _cdtCuentaEfectivo() {
    return _cdtCuentasDisponibles().find(c => c.nombre === 'Efectivo' && c.moneda === 'ARS');
}

/** Solo una cuenta bancaria real (chequera) puede usarse para pagar con
 *  cheque — no efectivo, no billeteras. Ver caja.cuenta_chequera_valida. */
function _cdtCuentaEsBanco(cuentaPk) {
    const info = _cdtCuentasDisponibles().find(c => String(c.pk) === String(cuentaPk));
    return !!info && info.tipo === 'banco';
}

/** Una línea paga con cheque cuando el usuario tildó "Pagar con
 *  cheque" Y la cuenta elegida es un banco real — mismo criterio en
 *  todos lados para no desincronizarse. */
function _cdtLineaEsCheque(l) {
    return _cdtCuentaEsBanco(l.cuenta) && !!l.esCheque;
}

/** Tarjeta (crédito) y cheque comparten el mismo plan de pago: cuotas
 *  fijas o libres + interés opcional. El cheque real de cada cuota se
 *  carga después, desde el detalle de la Deuda en Créditos y préstamos
 *  — acá solo se define el plan. */
function _cdtLineaUsaPlanCuotas(l) {
    return _cdtEsTarjeta(l.cuenta) || _cdtLineaEsCheque(l);
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
    const opt = c => `<option value="${c.pk}" ${String(c.pk) === String(seleccionada) ? 'selected' : ''}>${c.nombre}${c.titular ? ' · ' + c.titular : ''} (${c.moneda})</option>`;
    const todas = _cdtCuentasDisponibles();
    // Las cuentas tipo "banco" son las únicas que habilitan "Pagar con
    // cheque" en la línea (ver _cdtCuentaEsBanco) — se agrupan aparte
    // para que se note desde el combo, no recién después de elegirla.
    const otrasOpts = todas.filter(c => c.tipo !== 'banco').map(opt).join('');
    const bancos = todas.filter(c => c.tipo === 'banco');
    const bancosOpts = bancos.length
        ? `<optgroup label="Cuenta bancaria — habilita pagar con cheque">${bancos.map(opt).join('')}</optgroup>`
        : '';
    const tarjetas = _cdtTarjetasDisponibles();
    const tarjetasOpts = tarjetas.length ? `<optgroup label="Tarjeta de crédito">${tarjetas.map(t =>
        `<option value="${t.pk}" ${String(t.pk) === String(seleccionada) ? 'selected' : ''}>${t.nombre}${t.titular ? ' · ' + t.titular : ''}${t.terminada_en ? ' ·· ' + t.terminada_en : ''} (${t.moneda})</option>`
    ).join('')}</optgroup>` : '';
    return '<option value="">— Elegí cuenta o Efectivo —</option>' + otrasOpts + bancosOpts + tarjetasOpts;
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
        const puedeCheque = !esTarjeta && _cdtCuentaEsBanco(l.cuenta);
        const esCheque = _cdtLineaEsCheque(l);
        const usaPlanCuotas = _cdtLineaUsaPlanCuotas(l);
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
        ${!esTarjeta ? `
        <label class="vdt-cheque-toggle${puedeCheque ? '' : ' vdt-cheque-toggle--disabled'}">
            <input type="checkbox" data-campo="esCheque" data-id="${l.id}" ${l.esCheque ? 'checked' : ''} ${puedeCheque ? '' : 'disabled'}>
            Pagar con cheque (en vez de transferencia)
            ${puedeCheque ? '' : '<span class="vdt-cheque-toggle-hint">— elegí una cuenta bancaria arriba para habilitarlo</span>'}
        </label>` : ''}
        ${(_cdtCotizacionInputHTML(l) || _cdtEquivalenteArsHTML(l)) ? `
        <div class="vdt-pago-linea-cuenta">
            ${_cdtCotizacionInputHTML(l)}
            ${_cdtEquivalenteArsHTML(l)}
        </div>` : ''}
        ${usaPlanCuotas ? `
        <label class="vdt-credito-modo-row">
            <span class="vdt-pago-credito-label">Cuotas libres</span>
            <span class="toggle-switch">
                <input type="checkbox" data-campo="modoCuotas" data-id="${l.id}" ${l.modoCuotas === 'libre' ? 'checked' : ''}>
                <span class="toggle-track"></span>
            </span>
        </label>
        ${esCheque ? `<p class="vdt-cheque-plan-nota">Acá se define el plan de cuotas. Los cheques reales de cada
            cuota se cargan después, desde el detalle de esta deuda en Créditos y préstamos.</p>` : ''}
        <div class="vdt-pago-credito-extra">
            ${l.modoCuotas === 'libre' ? '' : `
            <div>
                <span class="vdt-pago-credito-label">Cuotas</span>
                <input type="number" class="vdt-pago-select" min="1" step="1" placeholder="Cuotas"
                       value="${l.cuotas || ''}" data-campo="cuotas" data-id="${l.id}">
            </div>`}
            <div>
                <span class="vdt-pago-credito-label">Interés %</span>
                <input type="number" class="vdt-pago-select" min="0" step="0.01" placeholder="0"
                       value="${l.interesPct != null ? l.interesPct : ''}" data-campo="interesPct" data-id="${l.id}">
            </div>
            ${l.modoCuotas === 'libre' ? `
            <div class="vdt-credito-total-libre">
                <span class="vdt-pago-credito-label">Total a pagar</span>
                <strong>${_cdtFmtARS((l.monto || 0) * (1 + (l.interesPct || 0) / 100))}</strong>
            </div>` : `
            <div>
                <span class="vdt-pago-credito-label">${esCheque ? 'Fecha de la 1° cuota' : 'Inicio débito'}</span>
                <input type="date" class="vdt-pago-select"
                       value="${l.fechaInicioDebito || ''}" data-campo="fechaInicioDebito" data-id="${l.id}">
            </div>`}
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
            } else if (campo === 'esCheque') {
                linea.esCheque = el.checked;
            } else if (campo === 'modoCuotas') {
                linea.modoCuotas = el.checked ? 'libre' : 'fijas';
            } else {
                linea[campo] = el.value;
            }
            if (campo === 'cuenta') {
                linea.cotizacion = ''; // cambiar de cuenta resetea la cotización cargada
                linea.esCheque = false; // idem el toggle de cheque
                _cdtPagoRenderLineas();
            } else if (campo === 'cotizacion' || campo === 'esCheque' || campo === 'modoCuotas') {
                _cdtPagoRenderLineas();
            } else if (campo === 'interesPct') {
                // Se re-renderiza también para actualizar "Total a pagar"
                // en vivo cuando la línea está en modo libre.
                if (linea.modoCuotas === 'libre') _cdtPagoRenderLineas();
                else _cdtPagoActualizarResumen();
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

    _cdtActualizarInteresResumen();
    _cdtActualizarEstadoConfirmar();
}

/** El interés se suma ENCIMA del total (no cuenta para "pago cubierto",
 *  ver _cdtMontoArsLinea) — se muestra aparte, informativo, para saber
 *  cuánto termina costando la compra en total. Actualiza dos lugares: el
 *  resumen chico dentro de la pestaña "Medios de pago" (#cdtInteresResumen)
 *  y el total grande de abajo (#cdtTotalsGrandValue), visible sin
 *  importar qué pestaña esté abierta. */
function _cdtActualizarInteresResumen() {
    const totalInteres = cdtPagoState.lineas.reduce((s, l) => s + _cdtExtraMontoLinea(l), 0);
    const hayInteres = totalInteres > 0.005;
    const totalConInteres = cdtPagoState.total + totalInteres;

    const el      = document.getElementById('cdtInteresResumen');
    const montoEl = document.getElementById('cdtInteresMonto');
    const totalEl = document.getElementById('cdtTotalAPagar');
    if (el) {
        el.style.display = hayInteres ? '' : 'none';
        if (hayInteres) {
            if (montoEl) montoEl.textContent = _cdtFmtARS(totalInteres);
            if (totalEl) totalEl.textContent = _cdtFmtARS(totalConInteres);
        }
    }

    const filaInteres  = document.getElementById('cdtTotalsInteresRow');
    const valorInteres = document.getElementById('cdtTotalsInteresValue');
    const labelGrande  = document.getElementById('cdtTotalsGrandLabel');
    const valorGrande  = document.getElementById('cdtTotalsGrandValue');
    if (filaInteres) filaInteres.style.display = hayInteres ? '' : 'none';
    if (valorInteres) valorInteres.textContent = _cdtFmtARS(totalInteres);
    if (labelGrande) labelGrande.textContent = hayInteres ? 'Total a pagar' : 'Total';
    if (valorGrande) valorGrande.textContent = _cdtFmtARS(hayInteres ? totalConInteres : cdtPagoState.total);
}

/** Habilita "Confirmar compra" solo cuando ya está todo cargado: fecha,
 *  pago cubierto exacto, cuenta/cotización de cada línea, y datos
 *  completos de cuotas para cada línea con tarjeta o cheque. Se
 *  re-evalúa en cada cambio del panel de pago y de la fecha. */
function _cdtActualizarEstadoConfirmar() {
    const btn = document.getElementById('cdtBtnConfirmar');
    const dot = document.getElementById('cdtTabPagoDot');
    const pagoOk = _cdtPagoEsCubierto() && !_cdtPagoFaltanCuentas() && !_cdtPagoFaltanDatosCredito();

    if (dot) dot.classList.toggle('cdt-tab-dot--ok', pagoOk);

    if (btn) {
        const fecha = document.getElementById('cdtFecha');
        btn.disabled = !(fecha && fecha.value && pagoOk);
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

/** Tarjeta y cheque comparten el mismo plan de cuotas — ver
 *  _cdtLineaUsaPlanCuotas. En modo libre no hace falta cuotas ni fecha
 *  de inicio (ver _cdtLineaUsaPlanCuotas / render de la línea). */
function _cdtPagoFaltanDatosCredito() {
    return cdtPagoState.lineas.some(l => {
        if (!_cdtLineaUsaPlanCuotas(l)) return false;
        if (l.modoCuotas === 'libre') return false; // no pide cuotas ni fecha de inicio
        return !l.cuotas || l.cuotas < 1 || !l.fechaInicioDebito;
    });
}

function _cdtGetPagoPayload() {
    const pagos = cdtPagoState.lineas.map(l => {
        if (_cdtEsTarjeta(l.cuenta)) {
            return {
                medio: 'credito',
                monto: l.monto,
                cuenta_pk: l.cuenta || null,
                cotizacion: l.cotizacion || null,
                modo_cuotas: l.modoCuotas === 'libre' ? 'libre' : 'fijas',
                cuotas: l.modoCuotas === 'libre' ? null : l.cuotas,
                interes_pct: l.interesPct != null ? l.interesPct : 0,
                fecha_inicio_debito: l.modoCuotas === 'libre' ? null : (l.fechaInicioDebito || null),
            };
        }
        if (_cdtLineaEsCheque(l)) {
            // Acá solo se define el plan de cuotas (igual que crédito) —
            // los cheques reales de cada cuota se cargan después, desde
            // el detalle de la Deuda en Créditos y préstamos.
            return {
                medio: 'cheque',
                monto: l.monto,
                cuenta_pk: l.cuenta || null,
                cotizacion: l.cotizacion || null,
                modo_cuotas: l.modoCuotas === 'libre' ? 'libre' : 'fijas',
                cuotas: l.modoCuotas === 'libre' ? null : l.cuotas,
                interes_pct: l.interesPct != null ? l.interesPct : 0,
                fecha_inicio_debito: l.modoCuotas === 'libre' ? null : (l.fechaInicioDebito || null),
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
    const inputNumeroComprobante = document.getElementById('cdtNumeroComprobante');
    const inputTipoDocumento = document.getElementById('cdtTipoDocumento');
    const inputAlicuotaIva   = document.getElementById('cdtAlicuotaIva');
    const inputIvaIncluido   = document.getElementById('cdtIvaIncluido');

    /* ── Tipo de documento + IVA ──────────────────────────────────
       Solo una Factura puede traer IVA discriminado — Presupuesto/
       Remito no muestran alícuota. El total real a pagar (y por lo
       tanto lo que pide cubrir el widget de pagos) cambia si el
       costo cargado en el carrito NO incluye IVA: ahí se le suma
       encima, igual que el cálculo del backend en
       Compra._total_desde_items(). */
    function _cdtCalcularTotalConIva() {
        const subtotal = parseFloat(CDT.subtotalItems) || 0;
        const esFactura = inputTipoDocumento && inputTipoDocumento.value === 'factura';
        const alicuota  = esFactura && inputAlicuotaIva ? parseFloat(inputAlicuotaIva.value) : 0;
        const incluido  = !inputIvaIncluido || inputIvaIncluido.checked;

        if (!esFactura || incluido || !alicuota) {
            const neto = esFactura ? subtotal / (1 + alicuota / 100) : null;
            return { total: subtotal, neto: esFactura ? neto : null, montoIva: esFactura ? subtotal - neto : null, esFactura };
        }
        const total = subtotal * (1 + alicuota / 100);
        return { total, neto: subtotal, montoIva: total - subtotal, esFactura };
    }

    function _cdtActualizarIvaUI(reiniciarPago) {
        const seccion = document.getElementById('cdtIvaSection');
        const hint    = document.getElementById('cdtIvaHint');
        const preview = document.getElementById('cdtIvaPreview');
        const esFactura = inputTipoDocumento && inputTipoDocumento.value === 'factura';

        if (seccion) seccion.style.display = esFactura ? '' : 'none';

        // El total (y por lo tanto lo que pide cubrir el widget de pagos)
        // se recalcula SIEMPRE, sea o no Factura — solo la vista previa de
        // Neto/IVA es exclusiva de Factura.
        const { total, neto, montoIva } = _cdtCalcularTotalConIva();

        if (esFactura) {
            if (hint) hint.textContent = (!inputIvaIncluido || inputIvaIncluido.checked)
                ? 'Lo que cargaste en el carrito es el precio final (con IVA).'
                : 'Lo que cargaste en el carrito es el costo SIN IVA — se le suma arriba.';

            if (preview) {
                const elNeto  = document.getElementById('cdtIvaPreviewNeto');
                const elIva   = document.getElementById('cdtIvaPreviewMonto');
                const elTotal = document.getElementById('cdtIvaPreviewTotal');
                if (elNeto)  elNeto.textContent  = _cdtFmtARS(neto);
                if (elIva)   elIva.textContent   = _cdtFmtARS(montoIva);
                if (elTotal) elTotal.textContent = _cdtFmtARS(total);
            }
        }

        if (reiniciarPago) {
            cdtPagoState.total = total;
            const efectivo = _cdtCuentaEfectivo();
            cdtPagoState.lineas = [{
                id:     cdtPagoState.nextId++,
                monto:  parseFloat(total.toFixed(2)),
                cuenta: efectivo ? efectivo.pk : '',
            }];
            _cdtPagoRenderLineas();
        }
    }

    [inputTipoDocumento, inputAlicuotaIva].forEach(el => {
        if (el) el.addEventListener('change', () => _cdtActualizarIvaUI(true));
    });
    if (inputIvaIncluido) inputIvaIncluido.addEventListener('change', () => _cdtActualizarIvaUI(true));

    /* ── Widget de pagos: línea inicial con el total completo,
           precargada en Efectivo si existe ──────────────────────── */
    const cdtEfectivoInicial = _cdtCuentaEfectivo();
    cdtPagoState.lineas.push({
        id:    cdtPagoState.nextId++,
        monto: parseFloat(cdtPagoState.total.toFixed(2)),
        cuenta: cdtEfectivoInicial ? cdtEfectivoInicial.pk : '',
    });
    _cdtPagoRenderLineas();
    _cdtActualizarIvaUI(false);

    const btnAgregarPago = document.getElementById('cdtBtnAgregarPago');
    if (btnAgregarPago) btnAgregarPago.addEventListener('click', _cdtPagoAgregarLinea);

    if (inputFecha) inputFecha.addEventListener('input', _cdtActualizarEstadoConfirmar);
    _cdtActualizarEstadoConfirmar();

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
            cdtToast('Datos del plan de pago incompletos', 'Completá cuotas y fecha de inicio para cada pago con tarjeta o cheque.');
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
                    numero_comprobante: inputNumeroComprobante ? inputNumeroComprobante.value.trim() : '',
                    tipo_documento: inputTipoDocumento ? inputTipoDocumento.value : 'factura',
                    alicuota_iva: (inputTipoDocumento && inputTipoDocumento.value === 'factura' && inputAlicuotaIva) ? inputAlicuotaIva.value : '',
                    iva_incluido: !inputIvaIncluido || inputIvaIncluido.checked,
                    proveedor_pk: proveedorCompraDetalle.pk,
                    pagos:     pagoPayload.pagos,
                }),
            });
            const data = await res.json();

            if (data.ok) {
                // Si el pago generó una Deuda de cheque, va directo a su
                // detalle en Créditos y préstamos para cargar los cheques
                // reales de cada cuota — si no, al historial de compras.
                window.location.href = data.deuda_cheque_pk
                    ? `${CDT.urlDeudas}?ver=${data.deuda_cheque_pk}`
                    : CDT.urlHistorial;
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
        const mensajeCancelar = CDT.esEdicionReactivada
            ? '¿Cancelar esta edición? La compra vuelve a quedar anulada, tal como estaba antes de editarla — no se pierde.'
            : '¿Cancelar esta compra? El borrador y todos los productos cargados se van a perder.';
        const ok = await KaiConfirm(mensajeCancelar, { danger: true, confirmText: 'Cancelar compra' });
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
                // Si no se borró (compra real revertida a anulada), va al
                // Historial para que se vea de una que sigue ahí.
                window.location.href = data.borrado ? CDT.urlNuevaCompra : CDT.urlHistorial;
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