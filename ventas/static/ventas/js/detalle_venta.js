'use strict';

/*
 * Corre de dos formas:
 *   1. Pagina completa /ventas/detalle/<pk>/ — VDT_CONFIG viene en el HTML
 *      y al final del archivo se auto-inicializa.
 *   2. Panel flotante de cobro sobre /ventas/nueva/ — panel_cobro.js inyecta
 *      el fragmento y llama window.initDetalleVenta(). Se puede llamar muchas
 *      veces (una por venta): todo el estado de modulo vive adentro de la
 *      funcion, asi cada llamada arranca limpio y re-liga los handlers al
 *      DOM recien inyectado.
 */
window.initDetalleVenta = function initDetalleVenta(config) {
const VDT = config || window.VDT_CONFIG || {};
window.VDT_CONFIG = VDT;   // ticket_imprimir.js y otros lo leen de window

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

/* ════════════════════════════════════════════════════════════════
   SCORING DE RIESGO DE PAGO DEL CLIENTE
   ──────────────────────────────────────────────────────────────
   Avisa (o directamente esconde cuotas/cheque) según la banda del
   cliente. 'critico' esconde cuotas/cheque salvo que el vendedor
   toque "Habilitar de todos modos" (forzado=true). Ver core/scoring.py.
════════════════════════════════════════════════════════════════ */
const scoState = {
    banda:        VDT.clienteScoringBanda || '',
    label:        VDT.clienteScoringBandaLabel || '',
    alerta:       VDT.clienteScoringAlerta || '',
    sinHistorial: !!VDT.clienteScoringSinHistorial,
    forzado:      false,
};

const _SCO_BANDAS_AVISO   = ['regular', 'riesgo', 'critico'];
const _SCO_BANDA_BLOQUEA  = 'critico';

function _scoAplica() {
    return !!VDT.clienteUnicoPk && _SCO_BANDAS_AVISO.includes(scoState.banda);
}
function _scoBloqueaCuotasCheque() {
    return VDT.clienteUnicoPk && scoState.banda === _SCO_BANDA_BLOQUEA && !scoState.forzado;
}

function _setClienteScoring(datos) {
    scoState.banda        = (datos && datos.banda) || '';
    scoState.label        = (datos && datos.label) || '';
    scoState.alerta       = (datos && datos.alerta) || '';
    scoState.sinHistorial = !!(datos && datos.sinHistorial);
    scoState.forzado      = false;
    _renderClienteScoringChip();
    if (typeof _renderLineas === 'function') _renderLineas();
}

function _renderClienteScoringChip() {
    const chip = document.getElementById('vdtClienteScoringChip');
    if (!chip) return;
    if (!VDT.clienteUnicoPk) { chip.hidden = true; chip.textContent = ''; return; }
    chip.hidden = false;
    chip.className = 'vdt-sco-chip';
    if (scoState.sinHistorial) {
        chip.classList.add('vdt-sco-chip--sinhist');
        chip.textContent = 'Sin historial de crédito';
        return;
    }
    const banda = scoState.banda || 'excelente';
    chip.classList.add('vdt-sco-chip--' + banda);
    chip.textContent = 'Riesgo de pago: ' + (scoState.label || banda) +
        (VDT.clienteScoring != null && !isNaN(VDT.clienteScoring) ? ' (' + VDT.clienteScoring + ')' : '');
}

function _actualizarScoringAviso() {
    const box = document.getElementById('vdtScoringAviso');
    if (!box) return;
    if (!_scoAplica()) { box.hidden = true; box.innerHTML = ''; return; }

    box.hidden = false;
    box.className = 'vdt-sco-aviso vdt-sco-aviso--' + scoState.banda;
    const nombre = clienteVentaDetalle && clienteVentaDetalle.nombre ? clienteVentaDetalle.nombre : 'El cliente';
    const alerta = scoState.alerta ? ` ${scoState.alerta}` : '';

    if (scoState.banda === 'critico') {
        if (scoState.forzado) {
            box.innerHTML =
                `<strong>${_escVdt(nombre)} — banda Crítico.</strong>${_escVdt(alerta)} ` +
                `Cuotas y cheque habilitados manualmente para esta venta.`;
        } else {
            box.innerHTML =
                `<strong>${_escVdt(nombre)} — banda Crítico.</strong>${_escVdt(alerta)} ` +
                `Cuotas y cheque quedan deshabilitados. ` +
                `<button type="button" id="vdtScoForzar" class="vdt-sco-forzar">Habilitar de todos modos</button>`;
        }
    } else if (scoState.banda === 'riesgo') {
        box.innerHTML =
            `<strong>${_escVdt(nombre)} — banda Riesgo.</strong>${_escVdt(alerta)} ` +
            `Se desaconseja venderle en cuotas o aceptarle un cheque.`;
    } else {
        box.innerHTML =
            `<strong>${_escVdt(nombre)} — banda Regular.</strong>${_escVdt(alerta)} ` +
            `Revisá antes de venderle en cuotas o aceptarle un cheque.`;
    }

    const btn = document.getElementById('vdtScoForzar');
    if (btn) {
        btn.addEventListener('click', () => {
            scoState.forzado = true;
            _renderLineas();
        });
    }
}

function _fmtARS(v) {
    return '$ ' + parseFloat(v || 0).toLocaleString('es-AR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

/** "Cuotas" (venta financiada por el propio comercio) y "Cheque"
 *  requieren un único cliente vinculado a la venta — no tiene sentido
 *  financiar, ni tampoco reclamar un cheque rebotado, a un Consumidor
 *  Final anónimo que después no se puede ubicar. Si no hay cliente,
 *  ninguna de las dos opciones se ofrece. */
function _pagoMediosDisponibles() {
    const medios = VDT.mediosPago || [];
    // Sin cliente único, o cliente en banda Crítico sin forzar → no se
    // ofrecen cuotas ni cheque.
    if (!VDT.clienteUnicoPk || _scoBloqueaCuotasCheque()) {
        return medios.filter(m => m.value !== 'cuotas' && m.value !== 'cheque');
    }
    return medios;
}

function _pagoMediosOpts(seleccionado) {
    return _pagoMediosDisponibles().map(m =>
        `<option value="${m.value}" ${m.value === seleccionado ? 'selected' : ''}>${m.label}</option>`
    ).join('');
}

/* ════════════════════════════════════════════════════════════════
   CLIENTE DE LA VENTA — editable también desde acá (pestaña General),
   no solo desde el carrito. Mismo mecanismo que Nueva Venta
   (ver nueva_venta.js _bindClienteVentaInput), pero acá el cambio se
   manda recién al confirmar (ver _getPagoPayload/cliente_pk más abajo
   y ConfirmarVentaAjax en el backend, que actualiza el cliente de
   TODOS los ítems antes de resolver los pagos) — nada se persiste
   solo por elegirlo, igual que Fecha/Notas en esta misma pestaña.
════════════════════════════════════════════════════════════════ */
let clienteVentaDetalle = { pk: VDT.clienteUnicoPk || null, nombre: VDT.clienteUnicoNombre || '' };
let clienteDetalleSearchTimer;

function _escVdt(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _bindClienteVentaDetalle() {
    const input    = document.getElementById('vdtClienteInput');
    const dropdown = document.getElementById('vdtClienteDropdown');
    const clear    = document.getElementById('vdtClienteClear');
    if (!input || !dropdown || !clear) return;

    input.value = clienteVentaDetalle.nombre;
    clear.style.display = clienteVentaDetalle.pk ? 'inline-flex' : 'none';

    function _aplicarCliente(pk, nombre, scoring) {
        clienteVentaDetalle = { pk, nombre };
        VDT.clienteUnicoPk = pk;
        VDT.clienteScoring = scoring ? scoring.scoring : null;
        // Actualiza el chip de banda + el aviso + re-render de líneas
        // (por si "Cuotas"/"Cheque" pasan a estar disponibles o no).
        _setClienteScoring(scoring || null);
        // En el panel flotante: espejar el cliente al carrito de atrás,
        // así el borrador que se guarda en cada cambio del carrito
        // (ver panel_cobro.js onCartChange) no lo pisa con vacío.
        if (window.ventaCarrito && typeof window.ventaCarrito.setCliente === 'function') {
            window.ventaCarrito.setCliente(pk, nombre, scoring ? {
                scoring:      scoring.scoring,
                banda:        scoring.banda,
                label:        scoring.label,
                sinHistorial: scoring.sinHistorial,
            } : null);
        }
    }

    input.addEventListener('input', () => {
        clearTimeout(clienteDetalleSearchTimer);
        const q = input.value.trim();
        _aplicarCliente(null, '');
        clear.style.display = 'none';

        if (!q) {
            dropdown.classList.remove('open');
            dropdown.innerHTML = '';
            return;
        }
        clienteDetalleSearchTimer = setTimeout(async () => {
            try {
                const res  = await fetch(`${VDT.urlBuscarCliente}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (input.value.trim() !== q) return; // respuesta vieja, el usuario ya siguió escribiendo
                const results = data.results || [];

                dropdown.innerHTML = results.length
                    ? results.map((c, i) => `
                        <div class="vta-cli-option" data-idx="${i}" data-nombre="${_escVdt(c.nombre)}">
                            <div class="vta-cli-option-top">
                                <span class="vta-cli-option-nombre">${_escVdt(c.nombre)}</span>
                                ${c.scoring_banda && !c.scoring_sin_historial
                                    ? `<span class="vdt-sco-mini vdt-sco-mini--${c.scoring_banda}">${_escVdt(c.scoring_banda_label || '')}</span>`
                                    : ''}
                                ${c.codigo ? `<span class="vta-dropdown-item-codigo">${_escVdt(c.codigo)}</span>` : ''}
                            </div>
                            ${c.doc ? `<div class="vta-cli-option-doc">${_escVdt(c.doc)}</div>` : ''}
                        </div>`).join('')
                    : `<div class="vta-dropdown-empty">Sin resultados para "${_escVdt(q)}"</div>`;

                dropdown.querySelectorAll('.vta-cli-option').forEach(el => {
                    el.addEventListener('click', () => {
                        const c      = results[parseInt(el.dataset.idx, 10)];
                        const nombre = el.dataset.nombre;
                        input.value  = nombre;
                        clear.style.display = 'inline-flex';
                        dropdown.classList.remove('open');
                        dropdown.innerHTML = '';
                        _aplicarCliente(c.pk, nombre, {
                            scoring:      c.scoring,
                            banda:        c.scoring_banda,
                            label:        c.scoring_banda_label,
                            alerta:       c.scoring_alerta,
                            sinHistorial: c.scoring_sin_historial,
                        });
                    });
                });
                dropdown.classList.add('open');
            } catch { /* silencioso */ }
        }, 260);
    });

    clear.addEventListener('click', () => {
        input.value = '';
        clear.style.display = 'none';
        _aplicarCliente(null, '');
        input.focus();
    });

    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target) && e.target !== input) {
            dropdown.classList.remove('open');
        }
    });
}
_bindClienteVentaDetalle();
_renderClienteScoringChip();

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

/** Plata que el cliente termina pagando de más sobre lo que cubre el
 *  precio de venta, sea cual sea el motivo: recargo de tarjeta/débito/QR/
 *  transferencia (ver _recargoMontoLinea) o interés de un pago financiado
 *  en cuotas (interesPct, ver _cuotasExtraHTML). Une ambos conceptos bajo
 *  un solo "Total a cobrar" — antes solo se contaba el recargo de tarjeta,
 *  así que una venta en cuotas con interés seguía mostrando el total de
 *  productos nomás, sin el interés cargado. */
function _extraMontoLinea(l) {
    if (l.medio === 'cuotas') {
        return (l.monto || 0) * (l.interesPct || 0) / 100;
    }
    return _recargoMontoLinea(l);
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
        `<option value="${c.pk}" ${String(c.pk) === String(seleccionada) ? 'selected' : ''}>${c.nombre}${c.titular ? ' · ' + c.titular : ''} (${c.moneda})</option>`
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
    if (l.medio === 'efectivo' || l.medio === 'cuotas' || l.medio === 'cheque') return l.monto || 0;
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
 *  desde "Cuentas por cobrar". Igual que en Compras, un switch "Cuotas
 *  libres" oculta la cantidad de cuotas/fecha (no hay plan: se van
 *  registrando cobros de cualquier monto desde Cuentas por cobrar) y
 *  muestra el total a cobrar calculado en vivo. */
function _cuotasExtraHTML(l) {
    const libre = l.modoCuotas === 'libre';
    return `
    <label class="vdt-credito-modo-row">
        <span class="vdt-pago-cuotas-label">Cuotas libres</span>
        <span class="toggle-switch">
            <input type="checkbox" data-campo="modoCuotas" data-id="${l.id}" ${libre ? 'checked' : ''}>
            <span class="toggle-track"></span>
        </span>
    </label>
    <div class="vdt-pago-cuotas-extra">
        ${libre ? '' : `
        <div>
            <span class="vdt-pago-cuotas-label">Cuotas</span>
            <input type="number" class="vdt-pago-select" min="1" step="1" placeholder="Cuotas"
                   value="${l.cuotas || ''}" data-campo="cuotas" data-id="${l.id}">
        </div>`}
        <div>
            <span class="vdt-pago-cuotas-label">Interés %</span>
            <input type="number" class="vdt-pago-select" min="0" step="0.01" placeholder="0"
                   value="${l.interesPct != null ? l.interesPct : ''}" data-campo="interesPct" data-id="${l.id}">
        </div>
        ${libre ? `
        <div class="vdt-credito-total-libre">
            <span class="vdt-pago-cuotas-label">Total a cobrar</span>
            <strong>${_fmtARS((l.monto || 0) * (1 + (l.interesPct || 0) / 100))}</strong>
        </div>` : `
        <div>
            <span class="vdt-pago-cuotas-label">Primera cuota</span>
            <input type="date" class="vdt-pago-select"
                   value="${l.fechaInicioCobro || ''}" data-campo="fechaInicioCobro" data-id="${l.id}">
        </div>`}
    </div>`;
}

/** El monto de una línea "cheque" no se tipea: es la suma de los
 *  cheques cargados en el modal — así nunca puede desincronizarse. */
function _recalcularMontoCheque(l) {
    l.monto = (l.cheques || []).reduce((s, c) => s + (parseFloat(c.monto) || 0), 0);
}

/** Cheques cargados para esta línea (pago dividido: puede haber más de
 *  uno) + botón para agregar otro. Cada cheque se carga en un modal
 *  aparte (mismos campos que "Nuevo cheque" en la pantalla de Cheques,
 *  para A_COBRAR) y solo se crea de verdad cuando se confirma la venta
 *  — acá solo queda guardado en memoria. */
function _chequesExtraHTML(l) {
    const cheques = l.cheques || [];
    const filas = cheques.map((c, i) => `
        <div class="vdt-cheque-fila">
            <div class="vdt-cheque-fila-info">
                <strong>${_fmtARS(c.monto)}</strong>
                <span>${c.numero_cheque ? '#' + c.numero_cheque + ' · ' : ''}cobra ${c.fecha_cobro}${c.emisor ? ' · ' + c.emisor : ''}</span>
            </div>
            <button type="button" class="vdt-cheque-btn-editar" data-linea="${l.id}" data-index="${i}" title="Editar">
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2.5 13.5L13.5 2.5M13.5 2.5V7.5M13.5 2.5H8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button type="button" class="vdt-cheque-btn-quitar" data-linea="${l.id}" data-index="${i}" title="Quitar">
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M3 3L13 13M3 13L13 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
        </div>`).join('');
    return `
    <div class="vdt-pago-cheque-extra">
        ${filas}
        <button type="button" class="vdt-cheque-btn-agregar" data-linea="${l.id}">+ Cargar cheque</button>
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

    // Si el cliente pasó a banda Crítico (o se quitó el cliente) y alguna
    // línea tenía cuotas/cheque, la reseteamos al primer medio disponible
    // para no confirmar una venta con un medio ya no permitido.
    const permitidos = _pagoMediosDisponibles().map(m => m.value);
    pagoState.lineas.forEach(l => {
        if (!permitidos.includes(l.medio)) {
            l.medio = permitidos[0] || 'efectivo';
            l.tarjeta = ''; l.cuenta = ''; l.cheques = []; l.cuotas = null;
        }
    });

    _actualizarScoringAviso();

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
                   ${l.medio === 'cheque' ? 'readonly title="Suma de los cheques cargados"' : ''}
                   data-campo="monto" data-id="${l.id}">
            <button class="vdt-pago-btn-quitar" data-id="${l.id}" title="Quitar">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </button>
        </div>
        ${l.medio === 'cheque' ? _chequesExtraHTML(l) : ''}
        ${l.medio !== 'efectivo' && l.medio !== 'cuotas' && l.medio !== 'cheque' ? `
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
                if (linea.medio === 'cuotas') {
                    if (!linea.fechaInicioCobro) linea.fechaInicioCobro = VDT.hoy || '';
                    if (!linea.modoCuotas) linea.modoCuotas = 'fijas';
                }
                if (linea.medio === 'cheque') {
                    linea.cheques = linea.cheques || [];
                    _recalcularMontoCheque(linea);
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
            if (campo === 'modoCuotas') {
                linea.modoCuotas = el.checked ? 'libre' : 'fijas';
                _renderLineas();
                return;
            }
            if (campo === 'interesPct') {
                linea.interesPct = el.value === '' ? 0 : parseFloat(el.value);
                // Se re-renderiza también para actualizar "Total a cobrar"
                // en vivo cuando la línea está en modo libre.
                if (linea.medio === 'cuotas' && linea.modoCuotas === 'libre') _renderLineas();
                else _actualizarResumen();
                return;
            }
            linea[campo] = campo === 'monto' ? (parseFloat(el.value) || 0) : el.value;
            _actualizarResumen();
        });
        if (el.dataset.campo === 'monto') {
            el.addEventListener('input', () => {
                const id    = parseInt(el.dataset.id, 10);
                const linea = pagoState.lineas.find(l => l.id === id);
                if (linea) { linea.monto = parseFloat(el.value) || 0; linea._editadoManual = true; _actualizarResumen(); }
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

    contenedor.querySelectorAll('.vdt-cheque-btn-agregar').forEach(btn => {
        btn.addEventListener('click', () => {
            abrirModalCheque(parseInt(btn.dataset.linea, 10), null);
        });
    });
    contenedor.querySelectorAll('.vdt-cheque-btn-editar').forEach(btn => {
        btn.addEventListener('click', () => {
            abrirModalCheque(parseInt(btn.dataset.linea, 10), parseInt(btn.dataset.index, 10));
        });
    });
    contenedor.querySelectorAll('.vdt-cheque-btn-quitar').forEach(btn => {
        btn.addEventListener('click', () => {
            const linea = pagoState.lineas.find(l => l.id === parseInt(btn.dataset.linea, 10));
            if (!linea) return;
            linea.cheques.splice(parseInt(btn.dataset.index, 10), 1);
            _recalcularMontoCheque(linea);
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
    const totalRecargo = pagoState.lineas.reduce((s, l) => s + _extraMontoLinea(l), 0);
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
    const pagoOk = _pagoEsCubierto() && !_pagoFaltanCuentas() && !_pagoFaltanDatosCuotas() && !_pagoFaltanDatosCheque();

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
        if (l.medio === 'efectivo' || l.medio === 'cuotas' || l.medio === 'cheque') return false;
        if (!l.cuenta) return true;
        const cuenta = _cuentaPorId(l.cuenta);
        return !!cuenta && cuenta.moneda !== 'ARS' && !(l.cotizacion > 0);
    });
}

/** Toda línea en cuotas fijas necesita cantidad de cuotas y fecha de la
 *  primera — igual criterio que _cdtPagoFaltanDatosCredito en compras.
 *  En modo libre no hay plan que armar, así que no se exige ninguno
 *  de los dos. */
function _pagoFaltanDatosCuotas() {
    return pagoState.lineas.some(l =>
        l.medio === 'cuotas' && l.modoCuotas !== 'libre' && (!l.cuotas || l.cuotas < 1 || !l.fechaInicioCobro)
    );
}

/** Toda línea "cheque" necesita al menos un cheque cargado. */
function _pagoFaltanDatosCheque() {
    return pagoState.lineas.some(l => l.medio === 'cheque' && !(l.cheques && l.cheques.length));
}

function _getPagoPayload() {
    const pagos = pagoState.lineas.map(l => {
        if (l.medio === 'cuotas') {
            const libre = l.modoCuotas === 'libre';
            return {
                medio: l.medio,
                monto: l.monto,
                cuenta_pk: null,
                cotizacion: null,
                modo_cuotas: libre ? 'libre' : 'fijas',
                cuotas: libre ? null : l.cuotas,
                interes_pct: l.interesPct != null ? l.interesPct : 0,
                fecha_inicio_cobro: libre ? null : (l.fechaInicioCobro || null),
            };
        }
        if (l.medio === 'cheque') {
            return {
                medio: l.medio,
                monto: l.monto,
                cuenta_pk: null,
                cotizacion: null,
                cheques: (l.cheques || []).map(c => ({
                    numero_cheque: c.numero_cheque || '',
                    monto: c.monto,
                    moneda: 'ARS',
                    fecha_emision: c.fecha_emision,
                    fecha_cobro: c.fecha_cobro,
                    emisor: c.emisor || '',
                    receptor: c.receptor || '',
                    banco: c.banco || '',
                    notas: c.notas || '',
                })),
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
   MODAL "Cargar cheque" — mismos campos que "Nuevo cheque" (A_COBRAR)
   en la pantalla de Cheques, pero acá no crea nada todavía: solo
   guarda el cheque en memoria dentro de la línea de pago. El/los
   Cheque reales se crean recién al confirmar la venta.
════════════════════════════════════════════════════════════════ */
let _chequeModalLineaId = null;
let _chequeModalIndex = null;

function abrirModalCheque(lineaId, index) {
    const linea = pagoState.lineas.find(l => l.id === lineaId);
    if (!linea) return;
    _chequeModalLineaId = lineaId;
    _chequeModalIndex = index;

    const existente = index != null ? (linea.cheques || [])[index] : null;
    document.getElementById('vchTitulo').textContent = existente ? 'Editar cheque' : 'Cargar cheque';
    document.getElementById('vchNumeroCheque').value = existente ? existente.numero_cheque : '';
    document.getElementById('vchMonto').value = existente ? existente.monto : '';
    document.getElementById('vchFechaEmision').value = existente ? existente.fecha_emision : (VDT.hoy || '');
    document.getElementById('vchFechaCobro').value = existente ? existente.fecha_cobro : (VDT.hoy || '');
    document.getElementById('vchEmisor').value = existente ? existente.emisor : '';
    document.getElementById('vchReceptor').value = existente ? existente.receptor : '';
    document.getElementById('vchBanco').value = existente ? existente.banco : '';
    document.getElementById('vchNotas').value = existente ? existente.notas : '';
    document.getElementById('vchMsg').textContent = '';

    document.getElementById('vdtModalCheque').style.display = 'flex';
}

function cerrarModalCheque() {
    document.getElementById('vdtModalCheque').style.display = 'none';
    _chequeModalLineaId = null;
    _chequeModalIndex = null;
}

function _guardarModalCheque() {
    const msg = document.getElementById('vchMsg');
    const monto = parseFloat(document.getElementById('vchMonto').value) || 0;
    const fechaEmision = document.getElementById('vchFechaEmision').value;
    const fechaCobro = document.getElementById('vchFechaCobro').value;
    if (monto <= 0) { msg.textContent = 'El monto debe ser mayor a 0.'; return; }
    if (!fechaEmision || !fechaCobro) { msg.textContent = 'Indicá fecha de emisión y de cobro.'; return; }

    const linea = pagoState.lineas.find(l => l.id === _chequeModalLineaId);
    if (!linea) return;
    linea.cheques = linea.cheques || [];

    const dato = {
        numero_cheque: document.getElementById('vchNumeroCheque').value.trim(),
        monto,
        fecha_emision: fechaEmision,
        fecha_cobro: fechaCobro,
        emisor: document.getElementById('vchEmisor').value.trim(),
        receptor: document.getElementById('vchReceptor').value.trim(),
        banco: document.getElementById('vchBanco').value.trim(),
        notas: document.getElementById('vchNotas').value.trim(),
    };

    if (_chequeModalIndex != null) {
        linea.cheques[_chequeModalIndex] = dato;
    } else {
        linea.cheques.push(dato);
    }
    _recalcularMontoCheque(linea);
    cerrarModalCheque();
    _renderLineas();
}

document.getElementById('vchBtnCerrar')?.addEventListener('click', cerrarModalCheque);
document.getElementById('vchBtnCancelar')?.addEventListener('click', cerrarModalCheque);
document.getElementById('vchBtnGuardar')?.addEventListener('click', _guardarModalCheque);

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
                        cliente_pk: clienteVentaDetalle.pk,
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
                    if (typeof window.panelCobroOnConfirmada === 'function') {
                        window.panelCobroOnConfirmada(data);
                    } else {
                        window.location.href = VDT.urlDetalle + data.pk + '/';
                    }
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
            const mensaje = VDT.esEdicionReactivada
                ? '¿Cancelar esta edición? La venta vuelve a quedar anulada, tal como estaba antes de editarla — no se pierde.'
                : '¿Cancelar esta venta? El borrador y sus ítems se van a borrar.';
            const ok = await KaiConfirm(mensaje, { danger: true, confirmText: 'Cancelar venta' });
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
                    // En el panel flotante de cobro y borrador puro:
                    // reseteamos ahí mismo, sin recargar la página. Si era
                    // una venta real revertida a anulada (edición desde el
                    // Historial) o no hay panel, navegamos como siempre —
                    // no tiene sentido mandar al carrito vacío una venta
                    // que sigue existiendo en el Historial.
                    if (data.borrado && typeof window.panelCobroOnCancelada === 'function') {
                        window.panelCobroOnCancelada();
                    } else {
                        window.location.href = data.borrado ? VDT.urlNuevaVenta : VDT.urlHistorial;
                    }
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
    if (!toast) {
        // En el panel flotante de cobro (/ventas/nueva/) no existe
        // #vdtToast — caemos al toast global (notify.js, siempre cargado).
        if (window.KaiToast && typeof window.KaiToast.show === 'function') {
            window.KaiToast.show(cuerpo ? `${titulo} — ${cuerpo}` : titulo, 'warning', duracionMs || 4500);
        }
        return;
    }
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
                if (typeof window.panelCobroRefrescar === 'function') window.panelCobroRefrescar();
                else window.location.reload();
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
 * Abre el selector de formato.
 * @param {string} [modo]  'imprimir' (default) → window.print();
 *                         'pdf' → descarga el archivo (ticket_pdf.js).
 * La generación del HTML y la ventana/descarga son responsabilidad de
 * ticket_imprimir.js → ticketAbrirSelector().
 */
function vdtImprimirTicket(modo) {
    if (typeof ticketAbrirSelector !== 'function') {
        console.error('detalle_venta.js: ticketAbrirSelector no disponible. ¿Cargaste ticket_imprimir.js?');
        return;
    }
    ticketAbrirSelector(modo);
}

/* ════════════════════════════════════════════════════════════════
   DEVOLUCIONES — alternativa a editar/reactivar la venta para el
   caso "el cliente devuelve algo". La venta no se toca; se registra
   un objeto aparte que repone stock al lote exacto de origen y,
   opcionalmente, reembolsa plata. Por simplicidad, esta pantalla
   trata cada ítem como "vuelve entero a stock" o "está roto entero"
   — no divide una misma línea entre las dos ramas (el backend sí lo
   soporta si hiciera falta más adelante).
════════════════════════════════════════════════════════════════ */

function vdtAbrirModalDevolucion() {
    const modal = document.getElementById('vdtModalDevolucion');
    if (!modal) return;

    const tbody = document.getElementById('vdvItemsBody');
    tbody.innerHTML = (VDT.itemsDevolucion || []).map(item => {
        const disponible = parseFloat(item.disponible) || 0;
        if (disponible <= 0) return '';
        return `
        <tr data-item-pk="${item.pk}" data-precio="${item.precio_unitario}" data-descuento="${item.descuento_pct}" data-disponible="${disponible}">
            <td style="padding:.4rem .25rem">${vdtEsc(item.nombre)}</td>
            <td style="text-align:center; padding:.4rem .25rem">${disponible}</td>
            <td style="text-align:center; padding:.4rem .25rem">
                <input type="number" class="vdv-cantidad" min="0" max="${disponible}" step="any" value="0"
                    style="width:70px; text-align:center; padding:.3rem; border:1px solid var(--border-color); border-radius:.4rem">
            </td>
            <td style="text-align:center; padding:.4rem .25rem">
                <input type="checkbox" class="vdv-roto">
            </td>
        </tr>`;
    }).join('');

    if (!tbody.innerHTML.trim()) {
        tbody.innerHTML = '<tr><td colspan="4" style="padding:.75rem; text-align:center; color:var(--text-muted)">No queda nada disponible para devolver de esta venta.</td></tr>';
    }

    const selectCuenta = document.getElementById('vdvCuenta');
    selectCuenta.innerHTML = '<option value="">— No devolver plata (solo cambio) —</option>' +
        (VDT.cuentasReembolso || []).map(c => `<option value="${c.pk}" data-moneda="${c.moneda}">${vdtEsc(c.nombre)}${c.titular ? ' · ' + vdtEsc(c.titular) : ''} (${c.moneda})</option>`).join('');

    document.getElementById('vdvMonto').value = '0';
    document.getElementById('vdvDescripcion').value = '';
    document.getElementById('vdvMsg').textContent = '';

    tbody.querySelectorAll('.vdv-cantidad, .vdv-roto').forEach(el => {
        el.addEventListener('input', vdtRecalcularMontoDevolucion);
    });

    modal.style.display = 'flex';
}

function vdtCerrarModalDevolucion() {
    document.getElementById('vdtModalDevolucion').style.display = 'none';
}

function vdtRecalcularMontoDevolucion() {
    let total = 0;
    document.querySelectorAll('#vdvItemsBody tr[data-item-pk]').forEach(tr => {
        const cantidad = parseFloat(tr.querySelector('.vdv-cantidad').value) || 0;
        if (cantidad <= 0) return;
        const precio = parseFloat(tr.dataset.precio) || 0;
        const descuento = parseFloat(tr.dataset.descuento) || 0;
        total += cantidad * precio * (1 - descuento / 100);
    });
    document.getElementById('vdvMonto').value = total.toFixed(2);
}

(function () {
    const btnAbrir = document.getElementById('vdtBtnDevolucion');
    if (btnAbrir) btnAbrir.addEventListener('click', vdtAbrirModalDevolucion);

    const btnCerrar = document.getElementById('vdvBtnCerrar');
    if (btnCerrar) btnCerrar.addEventListener('click', vdtCerrarModalDevolucion);
    const btnCancelar = document.getElementById('vdvBtnCancelar');
    if (btnCancelar) btnCancelar.addEventListener('click', vdtCerrarModalDevolucion);

    const btnGuardar = document.getElementById('vdvBtnGuardar');
    if (!btnGuardar) return;

    btnGuardar.addEventListener('click', async () => {
        const msg = document.getElementById('vdvMsg');
        msg.textContent = '';

        const items = [];
        document.querySelectorAll('#vdvItemsBody tr[data-item-pk]').forEach(tr => {
            const cantidad = parseFloat(tr.querySelector('.vdv-cantidad').value) || 0;
            if (cantidad <= 0) return;
            items.push({
                item_venta_pk: parseInt(tr.dataset.itemPk, 10),
                cantidad: cantidad,
                es_perdida: tr.querySelector('.vdv-roto').checked,
            });
        });

        if (!items.length) {
            msg.textContent = 'Cargá alguna cantidad a devolver.';
            return;
        }
        const descripcion = document.getElementById('vdvDescripcion').value.trim();
        if (!descripcion) {
            msg.textContent = 'La descripción es obligatoria.';
            return;
        }

        const cuentaSelect = document.getElementById('vdvCuenta');
        const cuentaPk = cuentaSelect.value || null;
        const monto = parseFloat(document.getElementById('vdvMonto').value) || 0;
        if (monto > 0 && !cuentaPk) {
            msg.textContent = 'Elegí de qué cuenta sale el reembolso.';
            return;
        }

        btnGuardar.disabled = true;
        btnGuardar.textContent = 'Registrando…';

        try {
            const res = await fetch(VDT.urlRegistrarDevolucion, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': VDT.csrfToken },
                body: JSON.stringify({
                    venta_pk: VDT.ventaPk,
                    descripcion, cuenta_pk: cuentaPk, monto,
                    items,
                }),
            });
            const data = await res.json();
            if (data.ok) {
                if (typeof window.panelCobroRefrescar === 'function') window.panelCobroRefrescar();
                else window.location.reload();
            } else {
                msg.textContent = data.error || 'No se pudo registrar la devolución.';
                btnGuardar.disabled = false;
                btnGuardar.textContent = 'Registrar devolución';
            }
        } catch {
            msg.textContent = 'Error de conexión. Intentá de nuevo.';
            btnGuardar.disabled = false;
            btnGuardar.textContent = 'Registrar devolución';
        }
    });
})();

// ── Hooks para el panel flotante de cobro (panel_cobro.js) ──
window.vdtImprimirTicket = vdtImprimirTicket;
window.vdtAbrirModalDevolucion = vdtAbrirModalDevolucion;
window.detalleVentaSetTotal = function (nuevoTotal) {
    pagoState.total = Number(nuevoTotal) || 0;
    if (pagoState.lineas.length === 1 && !pagoState.lineas[0]._editadoManual) {
        pagoState.lineas[0].monto = parseFloat(pagoState.total.toFixed(2));
    }
    _renderLineas();
    _actualizarResumen();
};

};  // end initDetalleVenta

// Pagina completa: auto-init (en el panel, panel_cobro.js llama a mano)
if (window.VDT_CONFIG) window.initDetalleVenta();
