'use strict';

const VDT = window.VDT_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   TOTAL
════════════════════════════════════════════════════════════════ */
function _parsearTotal(val) {
    if (typeof val === 'number') return val;
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

/** "Cuotas" (venta financiada por el propio comercio) requiere un
 *  único cliente vinculado a la venta — no tiene sentido financiar a
 *  un Consumidor Final anónimo que después no se puede ubicar para
 *  cobrarle. Si no hay cliente, esa opción ni se ofrece. */
function _pagoMediosDisponibles() {
    const medios = VDT.mediosPago || [];
    if (VDT.clienteUnicoPk) return medios;
    return medios.filter(m => m.value !== 'cuotas');
}

function _pagoMediosOpts(seleccionado) {
    return _pagoMediosDisponibles().map(m =>
        `<option value="${m.value}" ${m.value === seleccionado ? 'selected' : ''}>${m.label}</option>`
    ).join('');
}

function _cuentaPorId(pk) {
    return (VDT.cuentas || []).find(c => String(c.pk) === String(pk));
}

/** TarjetaPago — con qué le pagó el CLIENTE (Visa, Mercado Pago, Personal
 *  Pay...). Es un dato aparte de `cuenta` (a cuál de MIS cuentas entra la
 *  plata) — ver ventas.models.TarjetaPago.__doc__. Define el recargo. */
function _tarjetaPorId(pk) {
    return (VDT.tarjetas || []).find(t => String(t.pk) === String(pk));
}

/** Recargos configurados (ver ventas.models.RecargoMedioPago) para una
 *  tarjeta+medio puntual — VDT.recargos es la lista plana embebida en la
 *  página (solo activos, ver DetalleVentaView). */
function _recargosDeTarjeta(tarjetaPk, medio) {
    return (VDT.recargos || []).filter(r =>
        String(r.tarjeta_pk) === String(tarjetaPk) && r.medio === medio
    );
}

/** % de recargo vigente para la línea, según tarjeta+medio+cantidad de
 *  pagos (siempre 1 salvo crédito). 0 si no hay ninguno configurado. */
function _recargoPctPara(l) {
    if (!l.tarjeta) return 0;
    const cantidad = l.medio === 'credito' ? (l.cantidadPagos || 1) : 1;
    const fila = _recargosDeTarjeta(l.tarjeta, l.medio).find(r => Number(r.cantidad_pagos) === Number(cantidad));
    return fila ? parseFloat(fila.recargo_pct) : 0;
}

/** Nombre comercial del plan elegido (ej. "Plan Z"), si el plan de
 *  tarjeta+cantidad_pagos tiene uno cargado — vacío si no. */
function _nombrePlanPara(l) {
    if (!l.tarjeta) return '';
    const cantidad = l.cantidadPagos || 1;
    const fila = _recargosDeTarjeta(l.tarjeta, 'credito').find(r => Number(r.cantidad_pagos) === Number(cantidad));
    return fila ? (fila.nombre_plan || '') : '';
}

/** Débito/QR/transferencia solo aplican recargo si el vendedor tildó el
 *  checkbox (por defecto sí, ver campo "medio"/"tarjeta" más abajo). En
 *  crédito el plan elegido YA define el recargo (elegir "1 pago" sin
 *  configuración es, en la práctica, no aplicar recargo). */
function _lineaAplicaRecargo(l) {
    const MEDIOS_CON_RECARGO = ['debito', 'credito', 'qr', 'transferencia'];
    if (!MEDIOS_CON_RECARGO.includes(l.medio) || !l.tarjeta) return false;
    if (l.medio === 'credito') return true;
    return !!l.aplicaRecargo;
}

/** Monto de recargo de esta línea (en la moneda de la cuenta), sumado
 *  ENCIMA de l.monto — ver Venta.confirmar en el backend, que hace lo
 *  mismo: l.monto sigue cubriendo la porción del precio de venta. */
function _recargoMontoLinea(l) {
    if (!_lineaAplicaRecargo(l)) return 0;
    return (l.monto || 0) * _recargoPctPara(l) / 100;
}

const CAMPO_ACEPTA_POR_MEDIO = {
    debito: 'acepta_debito', credito: 'acepta_credito',
    qr: 'acepta_qr', transferencia: 'acepta_transferencia',
};

/** Cuentas REALES disponibles — a cuál de MIS cuentas entra la plata de
 *  verdad (excluye efectivo, ese se resuelve solo en pesos, y tarjetas de
 *  crédito propias del negocio). Dato aparte de la tarjeta/billetera del
 *  cliente (ver _pagoTarjetaOpts) — ver ventas.models.TarjetaPago.__doc__
 *  para por qué son dos selectores distintos. La venta siempre es en
 *  pesos, pero el cobro puede ir a una cuenta en cualquier moneda
 *  (Argentina acepta cualquier moneda si ambas partes acuerdan) —
 *  ver cotización más abajo para la conversión.
 *  Solo se listan las que aceptan el `medio` de esta línea (ver
 *  CuentaCaja.acepta_* en el backend) — así no aparece, por ejemplo,
 *  una cuenta que solo cobra transferencias como opción para Crédito. */
function _cuentasDisponiblesParaMedio(medio) {
    const campo = CAMPO_ACEPTA_POR_MEDIO[medio];
    return (VDT.cuentas || []).filter(c => !campo || c[campo]);
}

function _pagoCuentaOpts(seleccionada, medio) {
    const disponibles = _cuentasDisponiblesParaMedio(medio);
    return '<option value="">— Elegí cuenta real —</option>' + disponibles.map(c =>
        `<option value="${c.pk}" ${String(c.pk) === String(seleccionada) ? 'selected' : ''}>${c.nombre} (${c.moneda})</option>`
    ).join('');
}

/** Tarjetas/billeteras del CLIENTE disponibles para el medio elegido —
 *  define el recargo (ver TarjetaPago.acepta_* en el backend). */
function _tarjetasDisponiblesParaMedio(medio) {
    const campo = CAMPO_ACEPTA_POR_MEDIO[medio];
    return (VDT.tarjetas || []).filter(t => !campo || t[campo]);
}

function _pagoTarjetaOpts(seleccionada, medio) {
    const disponibles = _tarjetasDisponiblesParaMedio(medio);
    return '<option value="">— Con qué te pagó (opcional) —</option>' + disponibles.map(t =>
        `<option value="${t.pk}" ${String(t.pk) === String(seleccionada) ? 'selected' : ''}>${t.nombre}</option>`
    ).join('');
}

/** Input de cotización — solo aparece si la cuenta elegida no es en
 *  pesos. No hay ninguna fuente automática de tipo de cambio: lo
 *  carga el vendedor con lo que acordó en el momento del cobro. */
function _cotizacionInputHTML(l) {
    if (l.medio === 'efectivo') return '';
    const cuenta = _cuentaPorId(l.cuenta);
    if (!cuenta || cuenta.moneda === 'ARS') return '';
    return `
        <input type="number" class="vdt-pago-cotizacion" min="0.0001" step="0.0001"
               placeholder="Cotización ($ por 1 ${cuenta.moneda})"
               value="${l.cotizacion || ''}"
               data-campo="cotizacion" data-id="${l.id}">`;
}

/** "≈ $ X" — cuánto vale en pesos esta línea, para que el vendedor
 *  vea la conversión mientras escribe. Vacío si no hace falta. */
function _equivalenteArsHTML(l) {
    if (l.medio === 'efectivo') return '';
    const cuenta = _cuentaPorId(l.cuenta);
    if (!cuenta || cuenta.moneda === 'ARS' || !l.cotizacion) return '';
    return `<span class="vdt-pago-equivalente">≈ ${_fmtARS(_montoArsLinea(l))}</span>`;
}

/** Equivalente en pesos de una línea de pago — igual criterio que
 *  PagoVenta.monto_ars en el backend. */
function _montoArsLinea(l) {
    if (l.medio === 'efectivo' || l.medio === 'cuotas') return l.monto || 0;
    const cuenta = _cuentaPorId(l.cuenta);
    if (cuenta && cuenta.moneda !== 'ARS') {
        return (l.monto || 0) * (l.cotizacion || 0);
    }
    return l.monto || 0;
}

/** Campos propios de una venta en cuotas: cantidad de cuotas, interés
 *  y fecha de la primera cuota — igual criterio que la compra a
 *  crédito (ver detalle_compra.js), pero acá no hay tarjeta ni cuenta:
 *  nada entra a caja hasta que se confirma cada cuota por separado
 *  desde "Cuentas por cobrar". */
function _cuotasExtraHTML(l) {
    return `
    <div class="vdt-pago-cuotas-extra">
        <div>
            <span class="vdt-pago-cuotas-label">Cuotas</span>
            <input type="number" class="vdt-pago-select" min="1" step="1" placeholder="Cuotas"
                   value="${l.cuotas || ''}" data-campo="cuotas" data-id="${l.id}">
        </div>
        <div>
            <span class="vdt-pago-cuotas-label">Interés %</span>
            <input type="number" class="vdt-pago-select" min="0" step="0.01" placeholder="0"
                   value="${l.interesPct != null ? l.interesPct : ''}" data-campo="interesPct" data-id="${l.id}">
        </div>
        <div>
            <span class="vdt-pago-cuotas-label">Primera cuota</span>
            <input type="date" class="vdt-pago-select"
                   value="${l.fechaInicioCobro || ''}" data-campo="fechaInicioCobro" data-id="${l.id}">
        </div>
    </div>`;
}

/** Controles de recargo de la línea, una vez elegida la tarjeta/billetera
 *  (con qué le pagó el cliente — dato aparte de la cuenta real):
 *  - Crédito: selector de plan de pagos (1, 3, 6 pagos...), cada uno con
 *    su recargo configurado en la tarjeta.
 *  - Débito/QR/transferencia: checkbox para aplicar o no el único
 *    recargo fijo configurado para esa tarjeta+medio. Si no hay ninguno
 *    configurado, no se muestra nada (no hay recargo que aplicar). */
function _recargoExtraHTML(l) {
    if (!l.tarjeta) return '';

    if (l.medio === 'credito') {
        const planes = _recargosDeTarjeta(l.tarjeta, 'credito')
            .slice()
            .sort((a, b) => a.cantidad_pagos - b.cantidad_pagos);
        const opciones = [];
        if (!planes.some(p => Number(p.cantidad_pagos) === 1)) {
            opciones.push('<option value="1">1 pago (sin recargo)</option>');
        }
        planes.forEach(p => {
            const pct = parseFloat(p.recargo_pct);
            const sufijo = pct > 0 ? ` (+${pct}%)` : ' (sin recargo)';
            const seleccionado = Number(l.cantidadPagos || 1) === Number(p.cantidad_pagos) ? 'selected' : '';
            opciones.push(`<option value="${p.cantidad_pagos}" ${seleccionado}>${p.etiqueta_plan}${sufijo}</option>`);
        });
        const montoRecargo = _recargoMontoLinea(l);
        return `
        <div class="vdt-pago-recargo-extra">
            <select class="vdt-pago-select" data-campo="cantidadPagos" data-id="${l.id}">
                ${opciones.join('')}
            </select>
            ${montoRecargo > 0.005 ? `<span class="vdt-pago-recargo-monto">+ ${_fmtARS(montoRecargo)} de recargo</span>` : ''}
        </div>`;
    }

    const disponible = _recargosDeTarjeta(l.tarjeta, l.medio).find(r => Number(r.cantidad_pagos) === 1);
    if (!disponible) return '';
    const pct = parseFloat(disponible.recargo_pct);
    const montoRecargo = _recargoMontoLinea(l);
    return `
    <div class="vdt-pago-recargo-extra">
        <label class="vdt-pago-recargo-check">
            <input type="checkbox" data-campo="aplicaRecargo" data-id="${l.id}" ${l.aplicaRecargo ? 'checked' : ''}>
            Aplicar recargo (+${pct}%)
        </label>
        ${montoRecargo > 0.005 ? `<span class="vdt-pago-recargo-monto">+ ${_fmtARS(montoRecargo)}</span>` : ''}
    </div>`;
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
    <div class="vdt-pago-linea-wrap" data-linea-id="${l.id}">
        <div class="vdt-pago-linea">
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
        </div>
        ${l.medio !== 'efectivo' && l.medio !== 'cuotas' ? `
        <div class="vdt-pago-linea-cuenta">
            <select class="vdt-pago-cuenta" data-campo="tarjeta" data-id="${l.id}">
                ${_pagoTarjetaOpts(l.tarjeta, l.medio)}
            </select>
        </div>
        ${_recargoExtraHTML(l)}
        <div class="vdt-pago-linea-cuenta">
            <select class="vdt-pago-cuenta" data-campo="cuenta" data-id="${l.id}">
                ${_pagoCuentaOpts(l.cuenta, l.medio)}
            </select>
            ${_cotizacionInputHTML(l)}
            ${_equivalenteArsHTML(l)}
        </div>` : ''}
        ${l.medio === 'cuotas' ? _cuotasExtraHTML(l) : ''}
    </div>`).join('');

    contenedor.querySelectorAll('[data-campo]').forEach(el => {
        el.addEventListener('change', () => {
            const id    = parseInt(el.dataset.id, 10);
            const campo = el.dataset.campo;
            const linea = pagoState.lineas.find(l => l.id === id);
            if (!linea) return;

            if (campo === 'medio') {
                linea.medio  = el.value;
                linea.tarjeta = '';
                linea.cuenta = '';
                linea.cantidadPagos = 1;
                linea.aplicaRecargo = true; // se sugiere aplicado; el vendedor lo destilda si no corresponde
                if (linea.medio === 'cuotas' && !linea.fechaInicioCobro) {
                    linea.fechaInicioCobro = VDT.hoy || '';
                }
                // Si solo hay UNA cuenta real posible para este medio (caso
                // común: un solo banco/Mercado Pago propio), se preselecciona
                // sola — menos clics para lo que va a elegir siempre igual.
                const cuentasPosibles = _cuentasDisponiblesParaMedio(linea.medio);
                if (cuentasPosibles.length === 1) linea.cuenta = String(cuentasPosibles[0].pk);
                _renderLineas();
                return;
            }
            if (campo === 'tarjeta') {
                linea.tarjeta = el.value;
                linea.cantidadPagos = 1;
                linea.aplicaRecargo = true;
                _renderLineas();
                return;
            }
            if (campo === 'cuenta') {
                linea.cuenta     = el.value;
                linea.cotizacion = ''; // cambiar de cuenta resetea la cotización cargada
                _renderLineas();
                return;
            }
            if (campo === 'cantidadPagos') {
                linea.cantidadPagos = parseInt(el.value, 10) || 1;
                _renderLineas();
                return;
            }
            if (campo === 'aplicaRecargo') {
                linea.aplicaRecargo = el.checked;
                _renderLineas();
                return;
            }
            if (campo === 'cotizacion') {
                linea.cotizacion = parseFloat(el.value) || 0;
                _renderLineas();
                return;
            }
            if (campo === 'cuotas') {
                linea.cuotas = parseInt(el.value, 10) || null;
                _actualizarResumen();
                return;
            }
            if (campo === 'interesPct') {
                linea.interesPct = el.value === '' ? 0 : parseFloat(el.value);
                _actualizarResumen();
                return;
            }
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
        if (el.dataset.campo === 'cotizacion') {
            el.addEventListener('input', () => {
                const id    = parseInt(el.dataset.id, 10);
                const linea = pagoState.lineas.find(l => l.id === id);
                if (linea) { linea.cotizacion = parseFloat(el.value) || 0; _actualizarResumen(); }
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
    const asignado  = pagoState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
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

    _actualizarRecargoResumen();
    _actualizarEstadoConfirmar();
}

/** El recargo se suma ENCIMA del total (no cuenta para "pago cubierto",
 *  ver _montoArsLinea) — se muestra aparte, informativo, para que el
 *  vendedor sepa cuánto termina cobrando el cliente en total. Actualiza
 *  dos lugares: el resumen chico dentro de la pestaña "Medios de pago"
 *  (#vdtRecargoResumen) y el total grande de abajo (#vdtTotalsGrandValue),
 *  visible sin importar qué pestaña esté abierta. */
function _actualizarRecargoResumen() {
    const totalRecargo = pagoState.lineas.reduce((s, l) => s + _recargoMontoLinea(l), 0);
    const hayRecargo = totalRecargo > 0.005;
    const totalConRecargo = pagoState.total + totalRecargo;

    const el      = document.getElementById('vdtRecargoResumen');
    const montoEl = document.getElementById('vdtRecargoMonto');
    const totalEl = document.getElementById('vdtTotalACobrar');
    if (el) {
        el.style.display = hayRecargo ? '' : 'none';
        if (hayRecargo) {
            if (montoEl) montoEl.textContent = _fmtARS(totalRecargo);
            if (totalEl) totalEl.textContent = _fmtARS(totalConRecargo);
        }
    }

    const filaRecargo  = document.getElementById('vdtTotalsRecargoRow');
    const valorRecargo = document.getElementById('vdtTotalsRecargoValue');
    const labelGrande   = document.getElementById('vdtTotalsGrandLabel');
    const valorGrande    = document.getElementById('vdtTotalsGrandValue');
    if (filaRecargo) filaRecargo.style.display = hayRecargo ? '' : 'none';
    if (valorRecargo) valorRecargo.textContent = _fmtARS(totalRecargo);
    if (labelGrande) labelGrande.textContent = hayRecargo ? 'Total a cobrar' : 'Total';
    if (valorGrande) valorGrande.textContent = _fmtARS(hayRecargo ? totalConRecargo : pagoState.total);
}

/** Habilita "Confirmar venta" solo cuando ya está todo cargado: fecha,
 *  pago cubierto exacto, cuenta/cotización de cada línea no efectivo,
 *  y datos completos de cada línea en cuotas. Se re-evalúa en cada
 *  cambio del panel de pago y de la fecha — así el botón nunca queda
 *  clickeable con datos a medio cargar. */
function _actualizarEstadoConfirmar() {
    const btn = document.getElementById('vdtBtnConfirmar');
    const dot = document.getElementById('vdtTabPagoDot');
    const pagoOk = _pagoEsCubierto() && !_pagoFaltanCuentas() && !_pagoFaltanDatosCuotas();

    if (dot) dot.classList.toggle('cdt-tab-dot--ok', pagoOk);

    if (btn) {
        const fecha = document.getElementById('vdtFecha');
        btn.disabled = !(fecha && fecha.value && pagoOk);
    }
}

function _agregarLinea() {
    const asignado = pagoState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
    const restante = Math.max(0, pagoState.total - asignado);
    pagoState.lineas.push({
        id:    pagoState.nextId++,
        medio: (VDT.mediosPago && VDT.mediosPago[0]) ? VDT.mediosPago[0].value : 'efectivo',
        monto: parseFloat(restante.toFixed(2)),
    });
    _renderLineas();
}

function _pagoEsCubierto() {
    const asignado = pagoState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
    return Math.abs(pagoState.total - asignado) < 0.005 && pagoState.lineas.length > 0;
}

/** Toda línea que no sea efectivo ni cuotas necesita una cuenta
 *  elegida (cuotas no acredita nada todavía), y si esa cuenta no es
 *  en pesos, también la cotización usada. */
function _pagoFaltanCuentas() {
    return pagoState.lineas.some(l => {
        if (l.medio === 'efectivo' || l.medio === 'cuotas') return false;
        if (!l.cuenta) return true;
        const cuenta = _cuentaPorId(l.cuenta);
        return !!cuenta && cuenta.moneda !== 'ARS' && !(l.cotizacion > 0);
    });
}

/** Toda línea en cuotas necesita cantidad de cuotas y fecha de la
 *  primera — igual criterio que _cdtPagoFaltanDatosCredito en compras. */
function _pagoFaltanDatosCuotas() {
    return pagoState.lineas.some(l =>
        l.medio === 'cuotas' && (!l.cuotas || l.cuotas < 1 || !l.fechaInicioCobro)
    );
}

function _getPagoPayload() {
    const pagos = pagoState.lineas.map(l => {
        if (l.medio === 'cuotas') {
            return {
                medio: l.medio,
                monto: l.monto,
                cuenta_pk: null,
                cotizacion: null,
                cuotas: l.cuotas,
                interes_pct: l.interesPct != null ? l.interesPct : 0,
                fecha_inicio_cobro: l.fechaInicioCobro || null,
            };
        }
        return {
            medio:      l.medio,
            monto:      l.monto,
            cuenta_pk:  l.medio === 'efectivo' ? null : (l.cuenta || null),
            tarjeta_pk: l.medio === 'efectivo' ? null : (l.tarjeta || null),
            cotizacion: l.medio === 'efectivo' ? null : (l.cotizacion || null),
            recargo_pct:    l.medio === 'efectivo' ? 0 : (_lineaAplicaRecargo(l) ? _recargoPctPara(l) : 0),
            cantidad_pagos: l.medio === 'credito' ? (l.cantidadPagos || 1) : 1,
            nombre_plan:    l.medio === 'credito' ? _nombrePlanPara(l) : '',
        };
    });
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

    // ── Botón "Ver ticket borrador" ──
    const btnPreview = document.getElementById('vdtBtnPreviewTicket');
    if (btnPreview) {
        btnPreview.addEventListener('click', () => {
            const modal = document.getElementById('vdtPreviewModal');
            if (modal) modal.style.display = 'flex';
        });
    }
}

/* ════════════════════════════════════════════════════════════════
   CONFIRMAR Y VOLVER
════════════════════════════════════════════════════════════════ */
if (VDT.esBorrador) {
    const btnConfirmar = document.getElementById('vdtBtnConfirmar');
    const inputFecha   = document.getElementById('vdtFecha');
    const inputNotas   = document.getElementById('vdtNotas');

    if (inputFecha) inputFecha.addEventListener('input', _actualizarEstadoConfirmar);
    _actualizarEstadoConfirmar();

    // ── Facturar electrónicamente (opcional) ──
    // Sin selector de cliente/condición de IVA acá: el cliente ya es el
    // único de la venta (elegido una vez en el carrito) y su condición de
    // IVA ya está en su ficha — el backend los deriva solos (ver
    // core/services_arca/facturacion.py). El tipo de comprobante mostrado
    // arriba del checkbox ya viene calculado server-side con ese mismo
    // criterio (tipo_comprobante_previsto_display).
    const facturarCheck = document.getElementById('vdtFacturarCheck');

    function _getFacturarPayload() {
        return { facturar: !!(facturarCheck && facturarCheck.checked) };
    }

    if (btnConfirmar) {
        btnConfirmar.addEventListener('click', async () => {
            const fecha = inputFecha ? inputFecha.value : '';
            if (!fecha) {
                vdtToast('Fecha requerida', 'Ingresá una fecha antes de confirmar.');
                return;
            }

            if (!_pagoEsCubierto()) {
                const asignado  = pagoState.lineas.reduce((s, l) => s + _montoArsLinea(l), 0);
                const pendiente = pagoState.total - asignado;
                if (!pagoState.lineas.length) {
                    vdtToast('Medio de pago requerido', 'Agregá al menos un medio de pago.');
                } else {
                    vdtToast('Pago incompleto', `Falta cubrir ${_fmtARS(pendiente)}.`);
                }
                return;
            }

            if (_pagoFaltanCuentas()) {
                vdtToast('Cuenta requerida', 'Elegí a qué cuenta se acredita cada pago que no sea efectivo, y la cotización si es en otra moneda.');
                return;
            }

            if (_pagoFaltanDatosCuotas()) {
                vdtToast('Datos de cuotas incompletos', 'Completá la cantidad de cuotas y la fecha de la primera para cada pago financiado.');
                return;
            }

            btnConfirmar.disabled  = true;
            btnConfirmar.innerHTML = `<svg class="vta-spin" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
            </svg> Confirmando…`;

            const pagoPayload = _getPagoPayload();
            const facturarPayload = _getFacturarPayload();

            try {
                const res  = await fetch(VDT.urlConfirmar, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': VDT.csrfToken },
                    body:    JSON.stringify({
                        venta_pk:   VDT.ventaPk,
                        fecha:      fecha,
                        notas:      inputNotas ? inputNotas.value.trim() : '',
                        medio_pago: pagoPayload.medio_pago,
                        pagos:      pagoPayload.pagos,
                        ...facturarPayload,
                    }),
                });
                const data = await res.json();

                if (data.ok) {
                    // La venta ya quedó confirmada pase lo que pase con la
                    // factura — si ARCA falló, avisamos en la página de
                    // destino (acá un toast no se alcanza a ver, redirige enseguida).
                    if (data.factura_error) {
                        sessionStorage.setItem('vdtFacturaError', data.factura_error);
                    }
                    window.location.href = VDT.urlDetalle + data.pk + '/';
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

    const btnEditarCarrito = document.getElementById('vdtBtnEditarCarrito');
    const btnCancelar      = document.getElementById('vdtBtnCancelar');

    if (btnEditarCarrito) {
        btnEditarCarrito.addEventListener('click', () => {
            // No se borra nada acá — el borrador se reemplaza recién
            // si el usuario efectivamente guarda cambios en el carrito.
            window.location.href = VDT.urlNuevaVenta + '?editar=' + VDT.ventaPk;
        });
    }

    if (btnCancelar) {
        btnCancelar.addEventListener('click', async () => {
            const ok = await KaiConfirm('¿Cancelar esta venta? El borrador y sus ítems se van a borrar.', { danger: true, confirmText: 'Cancelar venta' });
            if (!ok) return;

            btnCancelar.disabled  = true;
            btnCancelar.innerHTML = `<svg class="vta-spin" width="14" height="14" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
            </svg> Cancelando…`;

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
                    vdtToast('Error', data.error || 'No se pudo cancelar la venta.');
                    btnCancelar.disabled  = false;
                    btnCancelar.innerHTML = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path d="M3 4H13M6 4V2.5C6 2.22 6.22 2 6.5 2H9.5C9.78 2 10 2.22 10 2.5V4"
                              stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
                        <path d="M5 6L5.5 13H10.5L11 6" stroke="currentColor" stroke-width="1.4"
                              stroke-linecap="round" stroke-linejoin="round"/>
                    </svg> Cancelar venta`;
                }
            } catch {
                vdtToast('Error de conexión', 'Intentá de nuevo.');
                btnCancelar.disabled = false;
            }
        });
    }
}

/* ════════════════════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════════════════════ */
function vdtToast(titulo, cuerpo, duracionMs) {
    const toast = document.getElementById('vdtToast');
    if (!toast) return;
    document.getElementById('vdtToastTitle').textContent = titulo;
    document.getElementById('vdtToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    clearTimeout(toast._vdtTimer);
    toast._vdtTimer = setTimeout(() => toast.classList.remove('show'), duracionMs || 4500);
}

/* ════════════════════════════════════════════════════════════════
   FACTURACIÓN ELECTRÓNICA — reintento manual + aviso de error
   diferido (ver "vdtFacturaError" en sessionStorage, seteado antes
   del redirect en la confirmación cuando ARCA falla)
════════════════════════════════════════════════════════════════ */
(function () {
    const errorPendiente = sessionStorage.getItem('vdtFacturaError');
    if (errorPendiente) {
        sessionStorage.removeItem('vdtFacturaError');
        // Dura más que un toast normal — es un error técnico de ARCA,
        // más largo que "Falta la fecha" y necesita tiempo para leerse.
        // Se puede volver a ver (sin que se borre) con "Facturar ahora".
        vdtToast('Venta confirmada — no se pudo facturar', errorPendiente, 15000);
    }
})();

const btnFacturarAhora = document.getElementById('vdtBtnFacturarAhora');
if (btnFacturarAhora) {
    btnFacturarAhora.addEventListener('click', async () => {
        btnFacturarAhora.disabled = true;
        btnFacturarAhora.textContent = 'Facturando…';
        const msg = document.getElementById('vdtFacturarMsg');

        try {
            const res  = await fetch(VDT.urlFacturar, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': VDT.csrfToken },
                body:    JSON.stringify({}),
            });
            const data = await res.json();

            if (data.ok) {
                window.location.reload();
            } else {
                if (msg) { msg.style.color = '#e11d48'; msg.textContent = data.error; }
                btnFacturarAhora.disabled = false;
                btnFacturarAhora.textContent = 'Facturar ahora';
            }
        } catch {
            if (msg) { msg.style.color = '#e11d48'; msg.textContent = 'Error de conexión. Intentá de nuevo.'; }
            btnFacturarAhora.disabled = false;
            btnFacturarAhora.textContent = 'Facturar ahora';
        }
    });
}

function vdtEsc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ════════════════════════════════════════════════════════════════
   TICKET — imprimir
   ──────────────────────────────────────────────────────────────
   vdtImprimirTicket() → abre el selector de formato (A4 / 80mm / 58mm)
                         y delega la generación del HTML a ticket_imprimir.js.
   La vista previa real es la herramienta de impresión del navegador
   (window.print()) — no hay una vista previa propia en HTML: no
   sirve para saber cómo va a salir en papel real.
════════════════════════════════════════════════════════════════ */

/**
 * Abre el selector de formato de impresión.
 * La generación del HTML del ticket y la apertura de la ventana
 * son responsabilidad de ticket_imprimir.js → ticketAbrirSelector().
 */
function vdtImprimirTicket() {
    if (typeof ticketAbrirSelector !== 'function') {
        console.error('detalle_venta.js: ticketAbrirSelector no disponible. ¿Cargaste ticket_imprimir.js?');
        return;
    }
    ticketAbrirSelector();
}