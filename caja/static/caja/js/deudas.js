document.addEventListener('DOMContentLoaded', function () {
    const urls = window.deudasUrls;
    const today = window.deudasToday;
    const puedeConfirmar = window.deudasPuedeConfirmar;
    const puedeEditar = window.deudasPuedeEditar;

    // ── Cuentas (para los selects, filtradas por moneda y por es_credito) ──
    const cuentasDataEl = document.getElementById('cuentas-data');
    const CUENTAS = cuentasDataEl ? JSON.parse(cuentasDataEl.textContent) : [];

    function cuentasPorMoneda(moneda, esCredito) {
        return CUENTAS.filter(c => c.moneda === moneda && c.es_credito === esCredito);
    }

    // pk (string) de la cuenta principal del negocio si está en `lista`,
    // para preseleccionarla en los selects. '' si no aplica.
    function cuentaPrincipalEn(lista) {
        const p = (lista || CUENTAS).find(c => c.preferida);
        return p ? String(p.pk) : '';
    }

    // La chequera de un pago con cheque solo puede ser una cuenta
    // bancaria real (no efectivo, no billetera) — mismo criterio que
    // en Cheques/Compras.
    function cuentasBancariasPorMoneda(moneda) {
        return CUENTAS.filter(c => c.moneda === moneda && c.tipo === 'banco');
    }

    function poblarSelect(select, opciones, seleccionarPk) {
        select.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            opciones.map(c => `<option value="${c.pk}">${c.nombre}${c.titular ? ' · ' + c.titular : ''}</option>`).join('');
        if (seleccionarPk) select.value = String(seleccionarPk);
    }

    // Construir URLs base reemplazando el placeholder 0
    const urlEditarBase = urls.editar.replace('/0/', '/');
    const urlEliminarBase = urls.eliminar.replace('/0/', '/');
    const urlDetalleBase = urls.detalle.replace('/0/', '/');

    // confirmarCuota tiene el placeholder en el medio (.../cuotas/0/confirmar/),
    // no al final — no sirve el patrón base+pk, hay que reemplazar el 0 por el pk real.
    function urlConfirmarCuota(cuotaPk) {
        return urls.confirmarCuota.replace('/0/', `/${cuotaPk}/`);
    }

    function urlRegistrarAbono(deudaPk) {
        return urls.registrarAbono.replace('/0/', `/${deudaPk}/`);
    }

    let paginaActual = 1;
    let porPagina = 50;
    let deudaDetalleActual = null;

    // Modo edición de #modalDeuda: reusa el mismo formulario de alta,
    // prellenado, en vez de un modal aparte (ver editarDeuda()).
    let modoEdicion = false;
    let deudaEditandoPk = null;
    let deudaEditandoOrigen = null;   // 'lista' | 'detalle' — a dónde volver al guardar

    // ── Elementos DOM ───────────────────────────────────────────────
    const btnNuevaDeuda = document.getElementById('btnNuevaDeuda');
    const btnToggleFiltros = document.getElementById('btnToggleFiltros');
    const formFiltros = document.getElementById('formFiltros');
    const btnLimpiarFiltros = document.getElementById('btnLimpiarFiltros');
    const deudasBody = document.getElementById('deudasBody');
    const paginacionContainer = document.getElementById('paginacionContainer');

    // Modal alta
    const modalDeuda = document.getElementById('modalDeuda');
    const modalBackdrop = document.getElementById('modalBackdrop');
    const btnCerrarModal = document.getElementById('btnCerrarModal');
    const btnCancelarModal = document.getElementById('btnCancelarModal');
    const formDeuda = document.getElementById('formDeuda');
    const btnGuardarDeuda = document.getElementById('btnGuardarDeuda');
    const btnGuardarDeudaTexto = document.getElementById('btnGuardarDeudaTexto');
    const modalDeudaTitle = document.getElementById('modalDeudaTitle');
    const modalDeudaSubtitle = document.getElementById('modalDeudaSubtitle');
    const notaBloqueoEdicion = document.getElementById('notaBloqueoEdicion');
    const bloqueGenerarCuotasVar = document.getElementById('bloqueGenerarCuotasVar');
    const bloqueCargaInicialCreacion = document.getElementById('bloqueCargaInicialCreacion');
    const bloqueCuotasEdicion = document.getElementById('bloqueCuotasEdicion');
    const bloqueConvertirVariable = document.getElementById('bloqueConvertirVariable');
    const dCuotasActualesBody = document.getElementById('dCuotasActualesBody');
    const dNumeroComprobante = document.getElementById('dNumeroComprobante');
    const dNotas = document.getElementById('dNotas');
    const dTipo = document.getElementById('dTipo');
    const dMoneda = document.getElementById('dMoneda');
    const dCuentaTarjeta = document.getElementById('dCuentaTarjeta');
    const dCuentaAcreditacion = document.getElementById('dCuentaAcreditacion');
    const dDescuentoAcreditacion = document.getElementById('dDescuentoAcreditacion');
    const campoTarjeta = document.getElementById('campoTarjeta');
    const campoAcreditacion = document.getElementById('campoAcreditacion');
    const campoDescuentoAcreditacion = document.getElementById('campoDescuentoAcreditacion');
    const montoAcreditadoHint = document.getElementById('montoAcreditadoHint');
    const botonesTipo = document.querySelectorAll('.deudas-tipo-btn[data-tipo]');
    const dCargaInicial = document.getElementById('dCargaInicial');
    const deudasCuotasHistoricas = document.getElementById('deudasCuotasHistoricas');
    const deudasCuotasHistoricasBody = document.getElementById('deudasCuotasHistoricasBody');
    const deudasTotales = document.getElementById('deudasTotales');
    const dMonto = document.getElementById('dMonto');
    const dInteres = document.getElementById('dInteres');
    const dCuotas = document.getElementById('dCuotas');
    const dFechaInicio = document.getElementById('dFechaInicio');

    // Modo de plan (segmentado: fijas / variable / libre)
    const dModoCuotas = document.getElementById('dModoCuotas');   // hidden input
    const dModoCuotasHint = document.getElementById('dModoCuotasHint');
    const gridPlanFijo = document.getElementById('gridPlanFijo');
    const gridPlanVariable = document.getElementById('gridPlanVariable');
    const bloqueInteres = document.getElementById('bloqueInteres');
    const dMontoLabel = document.getElementById('dMontoLabel');
    const dMontoHint = document.getElementById('dMontoHint');
    const dMontoHintBtn = document.getElementById('dMontoHintBtn');
    const dPlanTotal = document.getElementById('dPlanTotal');
    const dTotalPagar = document.getElementById('dTotalPagar');
    const dMontoCuota = document.getElementById('dMontoCuota');
    const interesCalcHint = document.getElementById('interesCalcHint');
    const botonesInteres = document.querySelectorAll('.deudas-interes-seg-btn[data-int]');
    const dCuotasVarN = document.getElementById('dCuotasVarN');
    const dCuotasVarFecha = document.getElementById('dCuotasVarFecha');
    const dCuotasVarMonto = document.getElementById('dCuotasVarMonto');
    const deudasCuotasVariables = document.getElementById('deudasCuotasVariables');
    const deudasCuotasVariablesWrap = document.getElementById('deudasCuotasVariablesWrap');
    const btnAgregarCuotaVariable = document.getElementById('btnAgregarCuotaVariable');
    const deudasCuotasVariablesResumen = document.getElementById('deudasCuotasVariablesResumen');
    const deudasAbonosHistoricos = document.getElementById('deudasAbonosHistoricos');
    const deudasAbonosHistoricosWrap = document.getElementById('deudasAbonosHistoricosWrap');
    const btnAgregarAbonoHistorico = document.getElementById('btnAgregarAbonoHistorico');
    const deudasAbonosHistoricosTotal = document.getElementById('deudasAbonosHistoricosTotal');
    const dDescripcion = document.getElementById('dDescripcion');

    // Modal detalle
    const modalDetalle = document.getElementById('modalDetalle');
    const modalDetalleBackdrop = document.getElementById('modalDetalleBackdrop');
    const btnCerrarDetalle = document.getElementById('btnCerrarDetalle');
    const detalleSubtitle = document.getElementById('detalleSubtitle');
    const detalleResumen = document.getElementById('detalleResumen');
    const detNotas = document.getElementById('detNotas');
    const cuotasBody = document.getElementById('cuotasBody');
    const cuotasTitle = document.getElementById('cuotasTitle');
    const cuotasMeta = document.getElementById('cuotasMeta');
    const btnEditarDeuda = document.getElementById('btnEditarDeuda');
    const btnEliminarDeuda = document.getElementById('btnEliminarDeuda');
    const btnImprimirDeuda = document.getElementById('btnImprimirDeuda');
    const deudasDocumentos = document.getElementById('deudasDocumentos');
    const deudasRegistrarAbono = document.getElementById('deudasRegistrarAbono');
    const raSaldoLabel = document.getElementById('raSaldoLabel');
    const btnAbonar = document.getElementById('btnAbonar');
    const btnConvertirVariable = document.getElementById('btnConvertirVariable');
    const btnAyudaConvertirVariable = document.getElementById('btnAyudaConvertirVariable');
    const deudasEditarCuotas = document.getElementById('deudasEditarCuotas');
    const deudasEditarCuotasWrap = document.getElementById('deudasEditarCuotasWrap');
    const btnAgregarCuotaPendiente = document.getElementById('btnAgregarCuotaPendiente');
    const ecGenerarN = document.getElementById('ecGenerarN');
    const btnEcGenerar = document.getElementById('btnEcGenerar');
    const deudasEditarCuotasResumen = document.getElementById('deudasEditarCuotasResumen');
    const ecMsg = document.getElementById('ecMsg');
    const btnGuardarCuotas = document.getElementById('btnGuardarCuotas');

    // ── Tipo de deuda: compra_credito / prestamo / cheque / otro ─────
    const HINT_TIPO = {
        compra_credito: 'Una compra pagada con tarjeta de crédito.',
        prestamo: 'Plata que te prestaron y tenés que devolver.',
        cheque: 'Una compra que vas a pagar con uno o varios cheques propios.',
        otro: 'Cualquier otra cosa que debas y pagues en cuotas (una compra sin tarjeta, un servicio…).',
    };
    const dTipoHint = document.getElementById('dTipoHint');
    function actualizarEtiquetaMonto() {
        if (!dMontoLabel) return;
        const variable = dModoCuotas?.value === 'variable';
        if (dTipo.value === 'prestamo') {
            dMontoLabel.textContent = variable ? 'Monto del préstamo / capital' : 'Monto del préstamo *';
        } else {
            dMontoLabel.textContent = variable ? 'Capital / cuánto se pidió' : 'Monto *';
        }
    }
    function setTipo(tipo) {
        dTipo.value = tipo;
        botonesTipo.forEach(btn => {
            const activo = btn.dataset.tipo === tipo;
            btn.classList.toggle('deudas-tipo-btn--active', activo);
            btn.setAttribute('aria-pressed', String(activo));
        });
        // Solo compra a crédito y préstamo necesitan una cuenta propia.
        // Cheque y "otra deuda" no: cada cuota se paga sola después.
        campoTarjeta.hidden = tipo !== 'compra_credito';
        campoAcreditacion.hidden = tipo !== 'prestamo';
        if (campoDescuentoAcreditacion) campoDescuentoAcreditacion.hidden = tipo !== 'prestamo';
        if (dTipoHint) dTipoHint.textContent = HINT_TIPO[tipo] || '';
        actualizarEtiquetaMonto();
        poblarSelectsCuentas();
        actualizarMontoAcreditadoHint();
    }
    botonesTipo.forEach(btn => {
        btn.addEventListener('click', () => setTipo(btn.dataset.tipo));
    });

    // Cuánto entra de verdad a la cuenta elegida (capital pedido menos
    // sellado/seguro/etc.) — solo informativo, el cálculo real lo hace
    // el modelo (Deuda.monto_acreditado).
    function actualizarMontoAcreditadoHint() {
        if (!montoAcreditadoHint) return;
        if (dTipo.value !== 'prestamo') { montoAcreditadoHint.textContent = ''; return; }
        const capital = parseFloat(dMonto.value) || 0;
        const descuento = parseFloat(dDescuentoAcreditacion?.value) || 0;
        if (!capital || !descuento) { montoAcreditadoHint.textContent = ''; return; }
        const neto = capital - descuento;
        montoAcreditadoHint.textContent = neto > 0
            ? `Se van a acreditar ${fmtMoneda(neto, dMoneda.value)}.`
            : 'Los gastos no pueden ser mayores o iguales al monto solicitado.';
    }
    [dMonto, dDescuentoAcreditacion].forEach(el => el?.addEventListener('input', actualizarMontoAcreditadoHint));

    function poblarSelectsCuentas(tarjetaPk, acreditacionPk) {
        poblarSelect(dCuentaTarjeta, cuentasPorMoneda(dMoneda.value, true), tarjetaPk);
        const acred = cuentasPorMoneda(dMoneda.value, false);
        // La plata del préstamo entra en la cuenta principal por defecto.
        poblarSelect(dCuentaAcreditacion, acred, acreditacionPk || cuentaPrincipalEn(acred));
    }
    dMoneda?.addEventListener('change', () => {
        poblarSelectsCuentas();
        recalcularInteres();
        actualizarMontoAcreditadoHint();
    });

    // ── Modo de plan: fijas / variables / libres ─────────────────────
    const HINT_FIJAS = 'Cuotas fijas: se reparte el total en N cuotas iguales con vencimiento mensual — usalo si sabés el total (o el interés) y todas las cuotas son iguales.';
    const HINT_VARIABLE = 'Cuotas variables: para cuando no tenés todos los datos. Cargá el capital si lo sabés (si no, dejalo vacío) y las cuotas que ya tengas — sumás el resto más adelante desde "Ver cuotas". El interés se calcula solo, cuando estén todas cargadas.';
    const HINT_LIBRE = 'Abonos libres: no hay plan ni fechas — se van registrando pagos de cualquier monto hasta cubrir el total. Si es un préstamo con cuotas (aunque no las sepas todas), mejor usá "Cuotas variables".';
    const botonesModo = document.querySelectorAll('.deudas-modo-seg-btn[data-modo]');

    function modoCuotas() {
        return dModoCuotas.value || 'fijas';
    }
    function esModoLibre() {
        return modoCuotas() === 'libre';
    }
    function esModoVariable() {
        return modoCuotas() === 'variable';
    }

    // ── Interés: se puede tipear el %, o dar el total / la cuota y calcularlo ──
    let modoInteres = 'pct';   // pct | total | cuota

    function setModoInteres(m) {
        if (!['pct', 'total', 'cuota'].includes(m)) m = 'pct';
        modoInteres = m;
        botonesInteres.forEach(b => {
            const activo = b.dataset.int === m;
            b.classList.toggle('deudas-interes-seg-btn--active', activo);
            b.setAttribute('aria-pressed', String(activo));
        });
        dInteres.hidden = m !== 'pct';
        dTotalPagar.hidden = m !== 'total';
        dMontoCuota.hidden = m !== 'cuota';
        recalcularInteres();
    }
    botonesInteres.forEach(b => b.addEventListener('click', () => setModoInteres(b.dataset.int)));

    // Deja `dInteres` (name=porcentaje_interes, lo que se envía) con el % que
    // corresponde y muestra el total / interés calculado. En cuotas variables
    // el interés sale de la suma de las cuotas, así que acá no se toca.
    function recalcularInteres() {
        if (esModoVariable()) {
            interesCalcHint.textContent = '';
            return;
        }
        const capital = parseFloat(dMonto.value) || 0;
        const nCuotas = parseInt(dCuotas.value, 10) || 0;
        let total = 0;
        let pct = 0;

        if (modoInteres === 'pct') {
            pct = parseFloat(dInteres.value) || 0;
            total = capital * (1 + pct / 100);
        } else if (modoInteres === 'total') {
            total = parseFloat(dTotalPagar.value) || 0;
            pct = capital > 0 && total > 0 ? (total - capital) / capital * 100 : 0;
            dInteres.value = pct > 0 ? pct.toFixed(2) : '0';
        } else {   // cuota
            const mc = parseFloat(dMontoCuota.value) || 0;
            total = esModoLibre() ? 0 : mc * nCuotas;
            pct = capital > 0 && total > 0 ? (total - capital) / capital * 100 : 0;
            dInteres.value = pct > 0 ? pct.toFixed(2) : '0';
        }

        let txt = '';
        if (total > 0) {
            txt = `Total a pagar: ${fmtMoneda(total, dMoneda.value)}`;
            if (capital > 0) {
                txt += total < capital
                    ? ' · ⚠ el total es menor al capital'
                    : ` · Interés: ${pct.toFixed(2)}%`;
            } else if (modoInteres !== 'pct') {
                txt += ' · cargá el capital para ver el interés';
            }
        }
        interesCalcHint.textContent = txt;
    }

    function setModoCuotas(modo) {
        if (!['fijas', 'variable', 'libre'].includes(modo)) modo = 'fijas';
        dModoCuotas.value = modo;
        botonesModo.forEach(b => {
            const activo = b.dataset.modo === modo;
            b.classList.toggle('deudas-modo-seg-btn--active', activo);
            b.setAttribute('aria-pressed', String(activo));
        });

        const libre = modo === 'libre';
        const variable = modo === 'variable';

        gridPlanFijo.hidden = libre || variable;
        gridPlanVariable.hidden = !variable;
        deudasCuotasVariables.hidden = !variable;
        bloqueInteres.hidden = variable;            // en variables el interés se calcula solo
        dModoCuotasHint.textContent = variable ? HINT_VARIABLE : (libre ? HINT_LIBRE : HINT_FIJAS);

        // "Monto de cada cuota" no aplica sin un plan de cuotas fijo (libre).
        const btnIntCuota = document.querySelector('.deudas-interes-seg-btn[data-int="cuota"]');
        if (btnIntCuota) btnIntCuota.hidden = libre;

        // El capital es obligatorio salvo en cuotas variables.
        dMonto.required = !variable;
        actualizarEtiquetaMonto();
        // El "?" de "no sé este monto" solo tiene sentido (y solo se muestra) en variable.
        if (dMontoHintBtn) dMontoHintBtn.hidden = !variable;
        dMontoHint.classList.remove('is-visible');
        dMontoHintBtn?.classList.remove('is-active');

        if (libre && modoInteres === 'cuota') setModoInteres('total');
        else recalcularInteres();

        if (variable && !deudasCuotasVariablesWrap.children.length) agregarFilaCuotaVariable();
        if (variable) sincronizarPagoColumnasVariables();

        // Bloques de "ya pagado" según el modo, si carga inicial está tildado.
        if (dCargaInicial.checked) {
            deudasAbonosHistoricos.hidden = !libre;
            deudasCuotasHistoricas.hidden = libre || variable;
            if (libre && !deudasAbonosHistoricosWrap.children.length) agregarFilaAbonoHistorico();
            if (!libre && !variable) actualizarPrevisualizacionCuotas();
        }
        actualizarResumenVariables();
    }
    botonesModo.forEach(b => b.addEventListener('click', () => setModoCuotas(b.dataset.modo)));

    // ── Carga inicial: previsualización de cuotas ya pagadas (fijas) /
    //    lista libre de abonos ya pagados (libre) ────────────────────
    let previsualizacionTimeout = null;

    function limpiarCuotasHistoricas() {
        deudasCuotasHistoricasBody.innerHTML = '';
        deudasCuotasHistoricas.hidden = true;
        deudasAbonosHistoricosWrap.innerHTML = '';
        deudasAbonosHistoricosTotal.textContent = '';
        deudasAbonosHistoricos.hidden = true;
        deudasCuotasVariablesWrap.innerHTML = '';
        deudasCuotasVariablesResumen.textContent = '';
        deudasCuotasVariables.hidden = true;
    }

    dCargaInicial?.addEventListener('change', () => {
        if (dCargaInicial.checked) {
            if (esModoLibre()) {
                deudasAbonosHistoricos.hidden = false;
                if (!deudasAbonosHistoricosWrap.children.length) agregarFilaAbonoHistorico();
            } else if (esModoVariable()) {
                sincronizarPagoColumnasVariables();
            } else {
                deudasCuotasHistoricas.hidden = false;
                actualizarPrevisualizacionCuotas();
            }
        } else {
            deudasCuotasHistoricasBody.innerHTML = '';
            deudasCuotasHistoricas.hidden = true;
            deudasAbonosHistoricosWrap.innerHTML = '';
            deudasAbonosHistoricosTotal.textContent = '';
            deudasAbonosHistoricos.hidden = true;
            sincronizarPagoColumnasVariables();
        }
    });

    // ── Cuotas variables: filas editables (fecha + monto + "ya pagada") ──
    window.onCvPagadaChange = function (checkbox) {
        const fila = checkbox.closest('.deudas-cv-fila');
        const activo = checkbox.checked;
        fila.querySelector('.dcv-fecha-pago').disabled = !activo;
        const medio = fila.querySelector('.ph-medio');
        medio.disabled = !activo;
        if (!activo) {
            medio.value = '';
            fila.querySelector('.ph-detalle').innerHTML = '';
        }
    };

    function sincronizarPagoColumnasVariables() {
        // Las columnas de "ya pagada" solo tienen sentido si la deuda ya existía.
        const conPago = dCargaInicial.checked;
        deudasCuotasVariables.classList.toggle('deudas-cv--con-pago', conPago);
        if (!conPago) {
            deudasCuotasVariablesWrap.querySelectorAll('.dcv-pagada').forEach(chk => {
                if (chk.checked) { chk.checked = false; window.onCvPagadaChange(chk); }
            });
        }
    }

    function agregarFilaCuotaVariable(valores) {
        valores = valores || {};
        const fila = document.createElement('div');
        fila.className = 'deudas-cv-fila';
        fila.innerHTML = `
            <div class="deudas-cv-fila-linea">
                <span class="deudas-cv-numero"></span>
                <input type="date" class="dcv-fecha" value="${valores.fecha || ''}" title="Vencimiento">
                <input type="number" class="dcv-monto" step="0.01" min="0.01" placeholder="Monto" value="${valores.monto || ''}">
                <label class="deudas-cv-pagada-lbl"><input type="checkbox" class="dcv-pagada" onchange="onCvPagadaChange(this)"> ya pagada</label>
                <input type="date" class="dcv-fecha-pago" max="${today}" title="Fecha de pago" disabled>
                <select class="ph-medio" onchange="onPhMedioChange(this)" disabled>${opcionesMedioPago()}</select>
                <button type="button" class="deudas-cv-quitar" aria-label="Quitar">&times;</button>
            </div>
            <div class="ph-detalle"></div>
        `;
        // Un campo que el usuario tocó a mano no se pisa ni se descarta al regenerar.
        fila.querySelector('.dcv-monto').addEventListener('input', (e) => {
            e.target.dataset.touched = '1';
            actualizarResumenVariables();
        });
        fila.querySelector('.dcv-fecha').addEventListener('input', (e) => { e.target.dataset.touched = '1'; });
        fila.querySelector('.deudas-cv-quitar').addEventListener('click', () => {
            fila.remove();
            sincronizarPlanTotalConFilas();
            actualizarResumenVariables();
        });
        deudasCuotasVariablesWrap.appendChild(fila);
        return fila;
    }

    // Mientras no lo toquen a mano, "Cantidad total de cuotas" sigue a la
    // cantidad de filas cargadas (el caso normal: cargás todas las que hay).
    function sincronizarPlanTotalConFilas() {
        if (planTotalTocado || !esModoVariable()) return;
        const n = filasCuotasVariables().length;
        dPlanTotal.value = n ? String(n) : '';
    }

    btnAgregarCuotaVariable?.addEventListener('click', () => {
        agregarFilaCuotaVariable();
        sincronizarPlanTotalConFilas();
        actualizarResumenVariables();
    });

    // ── Cuotas variables: generar N filas de una y completarlas ──────
    function sumarMesesISO(iso, n) {
        if (!iso) return '';
        const partes = iso.split('-').map(Number);
        if (partes.length !== 3 || partes.some(isNaN)) return '';
        const [y, m, d] = partes;
        const mesTotal = (m - 1) + n;
        const anio = y + Math.floor(mesTotal / 12);
        const mes = ((mesTotal % 12) + 12) % 12;               // 0-11
        const ultimoDia = new Date(anio, mes + 1, 0).getDate();  // clamp de día
        const dia = Math.min(d, ultimoDia);
        return `${anio}-${String(mes + 1).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
    }

    function filasCuotasVariables() {
        return Array.from(deudasCuotasVariablesWrap.querySelectorAll('.deudas-cv-fila'));
    }

    function aplicarFechasVariables() {
        const base = dCuotasVarFecha.value;
        if (!base) return;
        filasCuotasVariables().forEach((f, i) => {
            const campo = f.querySelector('.dcv-fecha');
            if (campo.dataset.touched) return;
            campo.value = sumarMesesISO(base, i);
        });
    }

    function aplicarMontoVariables() {
        const m = dCuotasVarMonto.value;
        if (!m || parseFloat(m) <= 0) return;
        filasCuotasVariables().forEach(f => {
            const campo = f.querySelector('.dcv-monto');
            if (!campo.value) campo.value = m;
        });
    }

    let planTotalTocado = false;
    let generarVarTimeout = null;

    function generarFilasVariables() {
        const n = parseInt(dCuotasVarN.value, 10) || 0;
        if (n < 1 || n > 600) return;
        const filas = filasCuotasVariables();
        if (n > filas.length) {
            for (let i = filas.length; i < n; i++) agregarFilaCuotaVariable();
        } else if (n < filas.length) {
            // Sacar filas sobrantes desde el final, nunca una que el usuario editó.
            for (let i = filas.length - 1; i >= n; i--) {
                const f = filas[i];
                const conDatos = f.querySelector('.dcv-monto').dataset.touched
                    || f.querySelector('.dcv-fecha').dataset.touched
                    || f.querySelector('.dcv-pagada').checked;
                if (conDatos) break;
                f.remove();
            }
        }
        aplicarFechasVariables();
        aplicarMontoVariables();
        sincronizarPlanTotalConFilas();   // sigue a la cantidad real de filas
        actualizarResumenVariables();
    }

    dCuotasVarN?.addEventListener('input', () => {
        clearTimeout(generarVarTimeout);
        generarVarTimeout = setTimeout(generarFilasVariables, 350);
    });
    dCuotasVarFecha?.addEventListener('change', () => { aplicarFechasVariables(); actualizarResumenVariables(); });
    dCuotasVarMonto?.addEventListener('input', () => { aplicarMontoVariables(); actualizarResumenVariables(); });
    dPlanTotal?.addEventListener('input', () => { planTotalTocado = true; actualizarResumenVariables(); });

    // Numeración visual (1, 2, 3…) de las filas cargadas a mano — se recalcula
    // sola cada vez que se agrega/saca una fila (ver actualizarResumenVariables).
    function renumerarCuotasVariables() {
        filasCuotasVariables().forEach((f, i) => {
            const badge = f.querySelector('.deudas-cv-numero');
            if (badge) badge.textContent = String(i + 1);
        });
    }

    function actualizarResumenVariables() {
        renumerarCuotasVariables();
        if (!esModoVariable()) return;
        const montos = Array.from(deudasCuotasVariablesWrap.querySelectorAll('.dcv-monto'))
            .map(i => parseFloat(i.value) || 0).filter(v => v > 0);
        const total = montos.reduce((a, b) => a + b, 0);
        const capital = parseFloat(dMonto.value) || 0;
        const planTotal = parseInt(dPlanTotal.value, 10) || 0;
        const n = montos.length;
        let txt = `${n} cuota${n === 1 ? '' : 's'} · Total ${fmtMoneda(total, dMoneda.value)}`;
        if (capital > 0 && total > 0) {
            const completo = !planTotal || n >= planTotal;
            txt += completo
                ? ` · Interés real ${((total - capital) / capital * 100).toFixed(2)}%`
                : ' · Interés: faltan cuotas para calcularlo';
        } else if (total > 0) {
            txt += ' · Interés: cargá el capital para calcularlo';
        }
        deudasCuotasVariablesResumen.textContent = txt;
    }

    function recolectarCuotasVariables() {
        if (!esModoVariable()) return [];
        const conPago = dCargaInicial.checked;
        return Array.from(deudasCuotasVariablesWrap.querySelectorAll('.deudas-cv-fila')).map(fila => {
            const row = {
                monto: fila.querySelector('.dcv-monto').value,
                fecha_vencimiento: fila.querySelector('.dcv-fecha').value,
            };
            const chk = fila.querySelector('.dcv-pagada');
            if (conPago && chk && chk.checked) {
                row.pagada = true;
                row.fecha_pago = fila.querySelector('.dcv-fecha-pago').value;
                Object.assign(row, recolectarPagoHistorico(fila));
            }
            return row;
        }).filter(r => parseFloat(r.monto) > 0 && r.fecha_vencimiento);
    }

    [dMonto, dInteres, dCuotas, dFechaInicio, dPlanTotal, dTotalPagar, dMontoCuota].forEach(el => {
        el?.addEventListener('input', () => {
            recalcularInteres();
            actualizarResumenVariables();
            if (!dCargaInicial.checked || esModoLibre() || esModoVariable()) return;
            clearTimeout(previsualizacionTimeout);
            previsualizacionTimeout = setTimeout(actualizarPrevisualizacionCuotas, 400);
        });
    });

    // ── Cómo se pagó una cuota/abono histórico: cuenta real (informativa),
    //    cheque real (crea un Cheque es_historico=True) u otro (nota) ────
    function opcionesMedioPago() {
        const cuentas = cuentasPorMoneda(dMoneda.value, false);
        const princ = cuentaPrincipalEn(cuentas);
        const sel = pk => (princ && String(pk) === princ) ? ' selected' : '';
        let html = `<option value=""${princ ? '' : ' selected'}>— Sin especificar —</option>`;
        html += cuentas.map(c => `<option value="cuenta:${c.pk}"${sel(c.pk)}>${c.nombre}${c.titular ? ' · ' + c.titular : ''}</option>`).join('');
        html += '<option value="cheque">Cheque</option>';
        html += '<option value="otro">Otro (nota)</option>';
        return html;
    }

    function detallePagoHtml(medio) {
        if (medio === 'cheque') {
            const chequeras = cuentasBancariasPorMoneda(dMoneda.value);
            return `
                <div class="ph-cheque-campos">
                    <input type="text" class="ph-cheque-numero" placeholder="N° cheque">
                    <select class="ph-cheque-cuenta">
                        <option value="">— Chequera —</option>
                        ${chequeras.map(c => `<option value="${c.pk}">${c.nombre}${c.titular ? ' · ' + c.titular : ''}</option>`).join('')}
                    </select>
                    <input type="date" class="ph-cheque-emision" max="${today}" title="Fecha de emisión">
                    <input type="text" class="ph-cheque-banco" placeholder="Banco (opcional)">
                </div>`;
        }
        if (medio === 'otro') {
            return `<input type="text" class="ph-nota" placeholder="Nota (ej: permuta, compensación...)">`;
        }
        return '';
    }

    window.onPhMedioChange = function (select) {
        const contenedor = select.closest('tr, .deudas-abono-historico-fila, .deudas-cv-fila');
        contenedor.querySelector('.ph-detalle').innerHTML = detallePagoHtml(select.value);
    };

    function recolectarPagoHistorico(contenedor) {
        const medioSelect = contenedor.querySelector('.ph-medio');
        const medio = medioSelect ? medioSelect.value : '';
        const resultado = {};
        if (medio.startsWith('cuenta:')) {
            resultado.cuenta_pago_historica_pk = medio.slice('cuenta:'.length);
        } else if (medio === 'cheque') {
            resultado.cheque_historico = {
                numero_cheque: contenedor.querySelector('.ph-cheque-numero')?.value || '',
                cuenta_origen_pk: contenedor.querySelector('.ph-cheque-cuenta')?.value || '',
                fecha_emision: contenedor.querySelector('.ph-cheque-emision')?.value || '',
                banco: contenedor.querySelector('.ph-cheque-banco')?.value || '',
            };
        } else if (medio === 'otro') {
            resultado.medio_pago = contenedor.querySelector('.ph-nota')?.value || '';
        }
        return resultado;
    }

    // ── Carga inicial (modo libre): filas de abono ya pagado ─────────
    function agregarFilaAbonoHistorico() {
        const fila = document.createElement('div');
        fila.className = 'deudas-abono-historico-fila';
        fila.innerHTML = `
            <div class="deudas-abono-historico-fila-linea">
                <input type="number" class="dah-monto" step="0.01" min="0.01" placeholder="Monto">
                <input type="date" class="dah-fecha" value="${today}" max="${today}">
                <select class="ph-medio" onchange="onPhMedioChange(this)">${opcionesMedioPago()}</select>
                <button type="button" class="deudas-abono-historico-quitar" aria-label="Quitar">&times;</button>
            </div>
            <div class="ph-detalle"></div>
        `;
        fila.querySelector('.dah-monto').addEventListener('input', actualizarTotalAbonosHistoricos);
        fila.querySelector('.deudas-abono-historico-quitar').addEventListener('click', () => {
            fila.remove();
            actualizarTotalAbonosHistoricos();
        });
        deudasAbonosHistoricosWrap.appendChild(fila);
    }
    btnAgregarAbonoHistorico?.addEventListener('click', agregarFilaAbonoHistorico);

    // ── Navegar entre filas con ↓/↑ (como en una planilla) ────────────
    // Parado en un campo de una fila (fecha, monto...), ↓/↑ salta al mismo
    // campo de la fila de abajo/arriba, en vez de mover el spinner nativo
    // del input date/number. Un solo listener por contenedor (delegación),
    // así funciona con las filas que se van agregando después.
    const CLASES_NAV_FILA = ['dcv-fecha', 'dcv-monto', 'dcv-fecha-pago', 'dah-monto', 'dah-fecha'];

    function habilitarNavegacionFilas(container) {
        if (!container) return;
        container.addEventListener('keydown', (e) => {
            if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
            const campo = e.target;
            if (!campo.matches || !campo.matches('input, select')) return;
            const clase = CLASES_NAV_FILA.find(c => campo.classList.contains(c));
            if (!clase) return;
            const fila = campo.closest('.deudas-cv-fila, .deudas-abono-historico-fila');
            if (!fila) return;
            const destino = e.key === 'ArrowDown' ? fila.nextElementSibling : fila.previousElementSibling;
            const objetivo = destino && destino.querySelector(`.${clase}`);
            if (!objetivo || objetivo.disabled) return;
            e.preventDefault();
            objetivo.focus();
            objetivo.select?.();
        });
    }
    [deudasCuotasVariablesWrap, deudasEditarCuotasWrap, deudasAbonosHistoricosWrap]
        .forEach(habilitarNavegacionFilas);

    function actualizarTotalAbonosHistoricos() {
        const montos = Array.from(deudasAbonosHistoricosWrap.querySelectorAll('.dah-monto'))
            .map(inp => parseFloat(inp.value) || 0);
        const totalAbonado = montos.reduce((a, b) => a + b, 0);
        const monto = parseFloat(dMonto.value) || 0;
        const interes = parseFloat(dInteres.value) || 0;
        const totalDeuda = monto * (1 + interes / 100);
        const excede = totalAbonado > totalDeuda + 0.01;
        deudasAbonosHistoricosTotal.textContent =
            `Total ya pagado: ${fmtMoneda(totalAbonado, dMoneda.value)} de ${fmtMoneda(totalDeuda, dMoneda.value)}`;
        deudasAbonosHistoricosTotal.style.color = excede ? '#dc2626' : '';
    }

    function recolectarAbonosHistoricos() {
        if (!dCargaInicial.checked || !esModoLibre()) return [];
        return Array.from(deudasAbonosHistoricosWrap.querySelectorAll('.deudas-abono-historico-fila'))
            .map(fila => ({
                monto: fila.querySelector('.dah-monto').value,
                fecha_pago: fila.querySelector('.dah-fecha').value,
                ...recolectarPagoHistorico(fila),
            }))
            .filter(ab => parseFloat(ab.monto) > 0 && ab.fecha_pago);
    }

    async function actualizarPrevisualizacionCuotas() {
        const monto = parseFloat(dMonto.value);
        const cantidadCuotas = parseInt(dCuotas.value, 10);
        const fechaInicio = dFechaInicio.value;
        if (!monto || monto <= 0 || !cantidadCuotas || cantidadCuotas < 1 || !fechaInicio) {
            deudasCuotasHistoricasBody.innerHTML = '<tr><td colspan="7" class="deudas-tabla-loading">Completá monto, cuotas y fecha de inicio para ver el plan.</td></tr>';
            return;
        }

        try {
            const response = await fetch(urls.previsualizarCuotas, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    monto_original: dMonto.value,
                    porcentaje_interes: dInteres.value || 0,
                    cantidad_cuotas: dCuotas.value,
                    fecha_inicio: fechaInicio,
                }),
            });
            const data = await response.json();
            if (!data.cuotas) {
                deudasCuotasHistoricasBody.innerHTML = `<tr><td colspan="7" class="deudas-tabla-loading">${data.error || 'No se pudo calcular el plan de cuotas.'}</td></tr>`;
                return;
            }
            deudasCuotasHistoricasBody.innerHTML = data.cuotas.map(c => `
                <tr>
                    <td>${c.numero}</td>
                    <td>${c.fecha_vencimiento}</td>
                    <td class="deudas-monto">${fmtMoneda(c.monto, dMoneda.value)}</td>
                    <td><input type="checkbox" class="dch-pagada" data-numero="${c.numero}" onchange="onDchPagadaChange(this)"></td>
                    <td><input type="date" class="dch-fecha" data-numero="${c.numero}" value="${c.fecha_vencimiento < today ? c.fecha_vencimiento : today}" max="${today}" disabled></td>
                    <td><select class="ph-medio" onchange="onPhMedioChange(this)" disabled>${opcionesMedioPago()}</select></td>
                    <td class="ph-detalle"></td>
                </tr>
            `).join('');
        } catch (error) {
            console.error('Error al previsualizar cuotas:', error);
        }
    }

    window.onDchPagadaChange = function (checkbox) {
        const fila = checkbox.closest('tr');
        fila.querySelector('.dch-fecha').disabled = !checkbox.checked;
        const medioSelect = fila.querySelector('.ph-medio');
        medioSelect.disabled = !checkbox.checked;
        if (!checkbox.checked) {
            medioSelect.value = '';
            fila.querySelector('.ph-detalle').innerHTML = '';
        }
    };

    function recolectarCuotasHistoricas() {
        if (!dCargaInicial.checked || esModoLibre()) return [];
        return Array.from(deudasCuotasHistoricasBody.querySelectorAll('.dch-pagada:checked')).map(chk => {
            const fila = chk.closest('tr');
            return {
                numero: parseInt(chk.dataset.numero, 10),
                fecha_pago: fila.querySelector('.dch-fecha').value,
                ...recolectarPagoHistorico(fila),
            };
        });
    }

    // ── Cargar deudas ─────────────────────────────────────────────
    async function cargarDeudas() {
        const params = new URLSearchParams({
            pagina: paginaActual,
            por_pagina: porPagina,
            ...getFiltrosActivos(),
        });

        try {
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();

            renderizarDeudas(data.results);
            renderizarPaginacion(data.total, data.pagina, data.por_pagina);
            renderizarTotales(data.totales_pendientes);
        } catch (error) {
            console.error('Error al cargar deudas:', error);
            deudasBody.innerHTML = '<tr><td colspan="7" class="deudas-tabla-loading">Error al cargar deudas</td></tr>';
        }
    }

    function getFiltrosActivos() {
        const tipo = document.getElementById('fTipo').value;
        const estado = document.getElementById('fEstado').value;
        const moneda = document.getElementById('fMoneda').value;
        const q = document.getElementById('fQ').value;

        const filtros = {};
        if (tipo) filtros.tipo = tipo;
        if (estado) filtros.estado = estado;
        if (moneda) filtros.moneda = moneda;
        if (q) filtros.q = q;

        return filtros;
    }

    function fmtMoneda(v, moneda) {
        return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${moneda || ''}`.trim();
    }

    function fmtFecha(fechaIso) {
        if (!fechaIso) return '—';
        const partes = String(fechaIso).split('-').map(Number);
        if (partes.length !== 3 || partes.some(Number.isNaN)) return fechaIso;
        return new Intl.DateTimeFormat('es-AR').format(new Date(partes[0], partes[1] - 1, partes[2]));
    }

    function _deudaEscInput(str) {
        return String(str == null ? '' : str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    function renderizarDeudas(deudas) {
        if (!deudas || deudas.length === 0) {
            deudasBody.innerHTML = '<tr><td colspan="7" class="deudas-tabla-loading">No hay deudas registradas</td></tr>';
            return;
        }

        deudasBody.innerHTML = deudas.map(d => `
            <tr>
                <td><span class="deudas-badge-tipo deudas-badge-tipo--${d.tipo}">${d.tipo_display}</span></td>
                <td>${d.descripcion || d.compra_numero || '-'}</td>
                <td>${d.numero_comprobante || '-'}</td>
                <td class="deudas-monto">${fmtMoneda(d.monto_total, d.moneda)}</td>
                <td>${
                    d.modo_cuotas === 'libre'
                        ? `${d.cuotas_pagadas} abono${d.cuotas_pagadas === 1 ? '' : 's'}`
                        : d.modo_cuotas === 'variable'
                            ? `${d.cuotas_pagadas}/${d.cantidad_cuotas || d.cuotas_cargadas}`
                            : `${d.cuotas_pagadas}/${d.cantidad_cuotas}`
                }</td>
                <td><span class="deudas-badge-estado deudas-badge-estado--${d.estado}">${d.estado_display}</span></td>
                <td>
                    <div class="deudas-tabla-acciones">
                        <button type="button" class="btn btn-ghost btn--sm" onclick="verDeuda(${d.pk})">Ver cuotas</button>
                        ${window.deudasPuedeEditar && d.estado === 'activa' && !d.compra_numero
                            ? `<button type="button" class="btn btn-ghost btn--sm" onclick="editarDeuda(${d.pk}, 'lista')">Editar</button>`
                            : ''}
                        <button type="button" class="btn btn-ghost btn--sm btn--icon" onclick="imprimirDeudaDesdeLista(${d.pk})" title="Imprimir" aria-label="Imprimir">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M4 5V2H12V5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                                <rect x="2" y="5" width="12" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/>
                                <path d="M4 9H12M4 12H12V14H4V12Z" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    function renderizarTotales(totalesPendientes) {
        if (!deudasTotales) return;
        const entradas = Object.entries(totalesPendientes || {});
        if (entradas.length === 0) {
            deudasTotales.innerHTML = '';
            return;
        }
        deudasTotales.innerHTML = entradas.map(([moneda, total]) => `
            <div class="deudas-total-card">
                <span class="deudas-total-label">Debés</span>
                <span class="deudas-total-monto">${fmtMoneda(total, moneda)}</span>
            </div>
        `).join('');
    }

    function renderizarPaginacion(total, pagina, porPagina) {
        const totalPaginas = Math.ceil(total / porPagina);

        if (totalPaginas <= 1) {
            paginacionContainer.innerHTML = '';
            return;
        }

        let html = '<span class="deudas-paginacion-info">Página ' + pagina + ' de ' + totalPaginas + ' (' + total + ' registros)</span>';
        html += '<div class="deudas-paginacion-botones">';
        if (pagina > 1) {
            html += '<button type="button" class="btn btn-ghost btn--sm" onclick="cambiarPagina(' + (pagina - 1) + ')">Anterior</button>';
        }
        if (pagina < totalPaginas) {
            html += '<button type="button" class="btn btn-ghost btn--sm" onclick="cambiarPagina(' + (pagina + 1) + ')">Siguiente</button>';
        }
        html += '</div>';
        paginacionContainer.innerHTML = html;
    }

    window.cambiarPagina = function (nuevaPagina) {
        paginaActual = nuevaPagina;
        cargarDeudas();
    };

    // ── Modal alta ────────────────────────────────────────────────
    function abrirModal() {
        modalDeuda.hidden = false;
        document.body.style.overflow = 'hidden';
        window.requestAnimationFrame(() => dDescripcion?.focus());
    }

    function cerrarModal() {
        modalDeuda.hidden = true;
        document.body.style.overflow = '';
        formDeuda.reset();
        document.getElementById('dFechaInicio').value = today;
        planTotalTocado = false;

        // Deshacer todo lo que el modo edición pudo haber bloqueado/ocultado.
        modoEdicion = false;
        deudaEditandoPk = null;
        deudaEditandoOrigen = null;
        deudaDetalleActual = null;
        botonesTipo.forEach(b => { b.disabled = false; });
        botonesModo.forEach(b => { b.disabled = false; });
        botonesInteres.forEach(b => { b.disabled = false; });
        [dMoneda, dCuentaTarjeta, dCuentaAcreditacion, dMonto, dInteres, dCuotas,
         dFechaInicio, dPlanTotal, dTotalPagar, dMontoCuota, dDescripcion, dNumeroComprobante]
            .forEach(el => { if (el) el.disabled = false; });
        if (notaBloqueoEdicion) { notaBloqueoEdicion.hidden = true; notaBloqueoEdicion.textContent = ''; }
        if (bloqueCargaInicialCreacion) bloqueCargaInicialCreacion.hidden = false;
        if (bloqueCuotasEdicion) bloqueCuotasEdicion.hidden = true;
        setModoTitulo(false);

        setTipo('compra_credito');
        setModoInteres('pct');
        setModoCuotas('fijas');
        limpiarCuotasHistoricas();
    }

    function setModoTitulo(editando) {
        if (modalDeudaTitle) modalDeudaTitle.textContent = editando ? 'Editar deuda' : 'Nueva deuda';
        if (modalDeudaSubtitle) modalDeudaSubtitle.textContent = editando
            ? 'Modificá los datos de esta deuda.'
            : 'Completá los datos para registrar la deuda.';
        if (btnGuardarDeudaTexto) btnGuardarDeudaTexto.textContent = editando ? 'Guardar cambios' : 'Crear deuda';
    }

    btnNuevaDeuda?.addEventListener('click', () => {
        document.getElementById('dFechaInicio').value = today;
        planTotalTocado = false;
        setTipo('compra_credito');
        setModoInteres('pct');
        setModoCuotas('fijas');
        abrirModal();
    });

    btnCerrarModal.addEventListener('click', cerrarModal);
    btnCancelarModal.addEventListener('click', cerrarModal);
    // El modal solo se cierra con los botones — un clic afuera no descarta
    // sin querer lo que ya se cargó.
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modalDeuda.hidden) cerrarModal();
    });

    formDeuda.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (modoEdicion) {
            await guardarEdicionDeuda();
            return;
        }

        const formData = new FormData(formDeuda);
        const data = Object.fromEntries(formData.entries());
        data.cuotas_historicas = recolectarCuotasHistoricas();
        data.abonos_historicos = recolectarAbonosHistoricos();
        data.cuotas_variables = recolectarCuotasVariables();
        if (esModoVariable()) {
            if (!data.cuotas_variables.length) {
                KaiToast.show('Agregá al menos una cuota (fecha y monto).', 'danger');
                return;
            }
            // "Cantidad total de cuotas": nunca menor a lo que se está cargando.
            // Si no se indica, es la cantidad de cuotas cargadas (están todas).
            const cargadas = data.cuotas_variables.length;
            const planTotal = parseInt(dPlanTotal.value, 10) || 0;
            data.cantidad_cuotas = String(planTotal > cargadas ? planTotal : cargadas);
        }

        btnGuardarDeuda.disabled = true;

        try {
            const response = await fetch(urls.crear, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify(data),
            });

            const result = await response.json();

            if (result.success) {
                cerrarModal();
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar:', error);
            KaiToast.show('Error al guardar', 'danger');
        } finally {
            btnGuardarDeuda.disabled = false;
        }
    });

    // ── Modal alta en modo edición: mismo formulario, prellenado ─────
    // "Ver cuotas" es de solo lectura + pago — toda edición de la deuda
    // (monto, cuotas, si una está pagada o no, etc.) pasa por acá.
    function aplicarBloqueosEdicion(d) {
        const hayPagos = d.cuotas.some(c => c.estado === 'confirmada');
        const esVariable = d.modo_cuotas === 'variable';

        dMoneda.disabled = hayPagos;
        dCuentaTarjeta.disabled = hayPagos;
        dCuentaAcreditacion.disabled = hayPagos;

        if (esVariable) {
            dMonto.disabled = false;
            dPlanTotal.disabled = false;
            dInteres.disabled = true;
            dCuotas.disabled = true;
            dFechaInicio.disabled = true;
        } else {
            dMonto.disabled = hayPagos;
            dInteres.disabled = hayPagos;
            dCuotas.disabled = hayPagos;
            dFechaInicio.disabled = hayPagos;
            botonesInteres.forEach(b => { b.disabled = hayPagos; });
            if (dTotalPagar) dTotalPagar.disabled = hayPagos;
            if (dMontoCuota) dMontoCuota.disabled = hayPagos;
        }

        if (notaBloqueoEdicion) {
            notaBloqueoEdicion.hidden = !hayPagos;
            notaBloqueoEdicion.textContent = esVariable
                ? 'Ya hay cuotas confirmadas — la moneda y la cuenta ya no se pueden cambiar. El capital y el plan total sí (solo recalculan el interés).'
                : 'Esta deuda ya tiene cuotas confirmadas — el monto, interés, cantidad de cuotas, fecha de inicio, moneda y cuenta ya no se pueden editar. Para agregar, corregir o destildar una cuota puntual usá la tabla de abajo.';
        }
    }

    // Repuebla la parte de "cuotas de esta deuda" del formulario con datos
    // frescos — se usa al abrir la edición y después de cualquier acción
    // puntual sobre una cuota (marcar pagada, revertir, editar, eliminar,
    // convertir a variable, guardar cuotas pendientes).
    function refrescarFormularioEdicion(d) {
        deudaDetalleActual = d;
        setModoCuotas(d.modo_cuotas);
        // El generador de alta y la lista "ya pagada" de creación no
        // aplican acá — para variable, agregar cuotas es el panel de abajo.
        if (bloqueGenerarCuotasVar) bloqueGenerarCuotasVar.hidden = true;
        if (deudasCuotasVariables) deudasCuotasVariables.hidden = true;

        dMonto.value = d.monto_original || '';
        if (d.modo_cuotas === 'variable') {
            dPlanTotal.value = d.cantidad_cuotas || '';
        } else {
            dInteres.value = d.porcentaje_interes || '0';
            dCuotas.value = d.cantidad_cuotas || '';
            dFechaInicio.value = d.fecha_inicio || today;
        }
        if (dDescuentoAcreditacion) {
            dDescuentoAcreditacion.value = parseFloat(d.descuento_acreditacion) > 0 ? d.descuento_acreditacion : '';
        }
        actualizarMontoAcreditadoHint();

        aplicarBloqueosEdicion(d);
        renderizarCuotasEdicion(d);
    }

    window.editarDeuda = async function (pk, origen) {
        try {
            const response = await fetch(`${urlDetalleBase}${pk}/`);
            const data = await response.json();
            if (!data.deuda) {
                KaiToast.show('Deuda no encontrada', 'danger');
                return;
            }
            const d = data.deuda;

            modoEdicion = true;
            deudaEditandoPk = pk;
            deudaEditandoOrigen = origen || 'lista';

            setModoTitulo(true);
            if (bloqueCargaInicialCreacion) bloqueCargaInicialCreacion.hidden = true;
            if (bloqueCuotasEdicion) bloqueCuotasEdicion.hidden = false;
            botonesTipo.forEach(b => { b.disabled = true; });
            botonesModo.forEach(b => { b.disabled = true; });

            setTipo(d.tipo);
            dDescripcion.value = d.descripcion || '';
            if (dNumeroComprobante) dNumeroComprobante.value = d.numero_comprobante || '';
            dMoneda.value = d.moneda;
            poblarSelectsCuentas(d.cuenta_tarjeta_pk, d.cuenta_acreditacion_pk);
            setModoInteres('pct');
            dNotas.value = d.notas || '';

            refrescarFormularioEdicion(d);
            recalcularInteres();

            abrirModal();
        } catch (error) {
            console.error('Error al cargar deuda para editar:', error);
            KaiToast.show('Error al cargar la deuda', 'danger');
        }
    };

    async function guardarEdicionDeuda() {
        if (!deudaEditandoPk) return;

        const payload = { notas: dNotas.value };
        if (!dDescripcion.disabled) payload.descripcion = dDescripcion.value;
        if (dNumeroComprobante && !dNumeroComprobante.disabled) payload.numero_comprobante = dNumeroComprobante.value;
        if (!dMoneda.disabled) payload.moneda = dMoneda.value;

        if (esModoVariable()) {
            if (!dMonto.disabled) payload.monto_original = dMonto.value;
            if (!dPlanTotal.disabled) payload.cantidad_cuotas = dPlanTotal.value;
        } else {
            if (!dMonto.disabled) payload.monto_original = dMonto.value;
            if (!dInteres.disabled) payload.porcentaje_interes = dInteres.value;
            if (!esModoLibre() && !dCuotas.disabled) payload.cantidad_cuotas = dCuotas.value;
            if (!esModoLibre() && !dFechaInicio.disabled) payload.fecha_inicio = dFechaInicio.value;
        }

        if (dTipo.value === 'compra_credito' && !dCuentaTarjeta.disabled) payload.cuenta_tarjeta_pk = dCuentaTarjeta.value;
        if (dTipo.value === 'prestamo' && !dCuentaAcreditacion.disabled) payload.cuenta_acreditacion_pk = dCuentaAcreditacion.value;
        if (dTipo.value === 'prestamo' && dDescuentoAcreditacion) payload.descuento_acreditacion = dDescuentoAcreditacion.value;

        btnGuardarDeuda.disabled = true;
        try {
            const response = await fetch(`${urlEditarBase}${deudaEditandoPk}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify(payload),
            });
            const result = await response.json();
            if (!result.success) {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
                return;
            }
            deudaDetalleActual = result.deuda;

            // Si el panel "Agregar o editar cuotas pendientes" está abierto y
            // el usuario cargó o tildó algo ahí sin usar su botón de guardar,
            // "Guardar cambios" también lo guarda — antes hacía falta
            // acordarse de los dos botones por separado, y era fácil creer
            // que no había pasado nada con el primero. OJO: el chequeo tiene
            // que ser contra lo que hay AHORA en el panel (sin repintarlo
            // antes) — si se lo repinta primero con la respuesta del server
            // se pierde lo que el usuario cargó y nunca se detecta como
            // "sucio".
            const panelAbierto = deudasEditarCuotas && !deudasEditarCuotas.hidden;
            if (panelAbierto && serializarFilasEditarCuotas() !== snapshotEditarCuotas) {
                const resultadoCuotas = await guardarCuotasPendientesPanel();
                if (resultadoCuotas.error) {
                    // Los datos de arriba ya se guardaron — lo que falló es
                    // puntualmente el panel de cuotas. Se deja el modal
                    // abierto (ya con los campos de arriba al día) para que
                    // lo corrija ahí mismo con "Guardar cuotas pendientes".
                    KaiToast.show('Cambios guardados. Las cuotas de abajo no: ' + resultadoCuotas.error, 'warning');
                    ecMsg.textContent = resultadoCuotas.error;
                    return;
                }
                deudaDetalleActual = resultadoCuotas.deuda;
                KaiToast.show(
                    resultadoCuotas.erroresPago
                        ? `Cambios guardados. ${resultadoCuotas.erroresPago} cuota(s) nueva(s) no se pudieron marcar como pagadas.`
                        : 'Cambios guardados.',
                    resultadoCuotas.erroresPago ? 'warning' : 'success',
                );
            } else {
                KaiToast.show('Cambios guardados.', 'success');
            }

            const origen = deudaEditandoOrigen;
            const pk = deudaEditandoPk;
            cerrarModal();
            cargarDeudas();
            if (origen === 'detalle') window.verDeuda(pk);
        } catch (error) {
            console.error('Error al guardar cambios:', error);
            KaiToast.show('Error al guardar cambios', 'danger');
        } finally {
            btnGuardarDeuda.disabled = false;
        }
    }

    // ── Modal detalle (cuotas) ───────────────────────────────────────
    function abrirDetalle() {
        modalDetalle.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function cerrarDetalle() {
        modalDetalle.hidden = true;
        document.body.style.overflow = '';
        deudaDetalleActual = null;
    }

    btnCerrarDetalle.addEventListener('click', cerrarDetalle);

    window.verDeuda = async function (pk) {
        try {
            const response = await fetch(`${urlDetalleBase}${pk}/`);
            const data = await response.json();

            if (!data.deuda) {
                KaiToast.show('Deuda no encontrada', 'danger');
                return;
            }

            deudaDetalleActual = data.deuda;
            renderizarDetalle(data.deuda);
            abrirDetalle();
        } catch (error) {
            console.error('Error al cargar deuda:', error);
            KaiToast.show('Error al cargar deuda', 'danger');
        }
    };

    // El listado no trae `cuotas`/`documentos` (eso solo lo da el
    // detalle) — hay que pedirlo antes de poder armar la impresión. La
    // ventana se abre ACÁ, en blanco, antes del `await`: si se abriera
    // recién después del fetch, ya no cuenta como gesto directo del
    // usuario y el navegador la bloquea sin avisar (pasó en las pruebas).
    window.imprimirDeudaDesdeLista = async function (pk) {
        const ventana = window.open('', '_blank', 'width=800,height=950');
        if (!ventana) {
            KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio e intentá de nuevo.', 'warning', 6000);
            return;
        }
        try {
            const response = await fetch(`${urlDetalleBase}${pk}/`);
            const data = await response.json();
            if (!data.deuda) {
                ventana.close();
                KaiToast.show('Deuda no encontrada', 'danger');
                return;
            }
            if (typeof deudaImprimir === 'function') {
                deudaImprimir(data.deuda, ventana);
            } else {
                ventana.close();
                console.error('deudas_imprimir.js no está cargado.');
            }
        } catch (error) {
            ventana.close();
            console.error('Error al cargar deuda para imprimir:', error);
            KaiToast.show('Error al cargar la deuda', 'danger');
        }
    };

    function renderizarDetalle(d) {
        // "Ver cuotas" es de solo lectura + pago — ver informacion actual y
        // pagar cuotas, nada más. Toda edición (monto, cuotas, si una está
        // pagada o no, etc.) se hace aparte, desde editarDeuda() (mismo
        // formulario de alta, prellenado) — así no se edita nada por error
        // mientras se está mirando o pagando una cuota.
        const tieneCuentaPropia = d.tipo === 'compra_credito' || d.tipo === 'prestamo';
        const cuentaLabel = d.tipo === 'compra_credito' ? 'Tarjeta' : 'Cuenta acreditada';
        const cuentaValor = d.tipo === 'compra_credito'
            ? (d.cuenta_tarjeta_nombre || '-')
            : (d.cuenta_acreditacion_nombre || '-');
        const esVariable = d.modo_cuotas === 'variable';
        // Sellado/seguro/etc.: solo tiene sentido mostrarlo si es un
        // préstamo con algo cargado ahí (ver Deuda.monto_acreditado).
        const mostrarDescuento = d.tipo === 'prestamo' && parseFloat(d.descuento_acreditacion || 0) > 0;

        const item = (label, valor, wide, highlight) => `<div class="deudas-resumen-item${wide ? ' deudas-resumen-item--wide' : ''}${highlight ? ' deudas-resumen-item--highlight' : ''}"><span class="deudas-resumen-label">${label}</span><div class="deudas-resumen-value">${valor}</div></div>`;
        const totalNum = parseFloat(d.monto_total) || 0;
        const saldoNum = Math.max(0, parseFloat(d.saldo_pendiente) || 0);
        const pagadoNum = Math.max(0, totalNum - saldoNum);
        const progreso = totalNum > 0 ? Math.max(0, Math.min(100, pagadoNum / totalNum * 100)) : 0;
        const estadoHtml = `<span class="deudas-badge-estado deudas-badge-estado--${d.estado}">${d.estado_display}</span>${d.es_carga_inicial ? ' <span class="deudas-badge-carga-inicial">Carga inicial</span>' : ''}`;
        const overviewHtml = `
            <div class="deudas-detail-overview">
                <div class="deudas-detail-overview-head">
                    <div class="deudas-detail-identidad">
                        <span class="deudas-badge-tipo deudas-badge-tipo--${d.tipo}">${d.tipo_display}</span>
                        ${estadoHtml}
                    </div>
                    <span class="deudas-detail-moneda">${d.moneda}</span>
                </div>
                <div class="deudas-detail-metrics">
                    <div class="deudas-detail-metric">
                        <span>Total de la deuda</span>
                        <strong>${fmtMoneda(totalNum, d.moneda)}</strong>
                    </div>
                    <div class="deudas-detail-metric deudas-detail-metric--paid">
                        <span>Pagado</span>
                        <strong>${fmtMoneda(pagadoNum, d.moneda)}</strong>
                    </div>
                    <div class="deudas-detail-metric deudas-detail-metric--pending">
                        <span>Saldo pendiente</span>
                        <strong>${fmtMoneda(saldoNum, d.moneda)}</strong>
                    </div>
                </div>
                <div class="deudas-detail-progress">
                    <div><span>Progreso de pago</span><strong>${progreso.toFixed(0)}%</strong></div>
                    <div class="deudas-detail-progress-track" role="progressbar" aria-label="Progreso de pago" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progreso.toFixed(0)}">
                        <span style="width:${progreso.toFixed(2)}%"></span>
                    </div>
                </div>
            </div>`;

        if (detalleSubtitle) {
            detalleSubtitle.textContent = `${d.descripcion || d.compra_numero || 'Deuda'} · ${d.tipo_display}`;
        }

        if (esVariable) {
            const interesTxt = d.interes_implicito != null
                ? `${d.interes_implicito}%`
                : `<span class="deudas-resumen-muted">— (${d.capital_conocido ? 'faltan cuotas del plan' : 'falta cargar el capital'})</span>`;
            const planTxt = `${d.cuotas_cargadas} cargadas${d.cantidad_cuotas ? ' de ' + d.cantidad_cuotas : ''} · ${d.cuotas_pagadas} pagadas`;
            detalleResumen.innerHTML = `${overviewHtml}
                <div class="deudas-detail-data">
                    <div class="deudas-detail-data-title">Datos de la deuda</div>
                    <div class="deudas-resumen-grid">
                    ${item('Descripción', d.descripcion || '-', true)}
                    ${item('N° de comprobante', d.numero_comprobante || '-')}
                    ${tieneCuentaPropia ? item(cuentaLabel, cuentaValor) : ''}
                    ${mostrarDescuento ? item('Gastos de otorgamiento', fmtMoneda(d.descuento_acreditacion, d.moneda)) : ''}
                    ${mostrarDescuento ? item('Monto acreditado', d.monto_acreditado ? fmtMoneda(d.monto_acreditado, d.moneda) : '—') : ''}
                    ${item('Moneda', d.moneda)}
                    ${item('Capital', d.capital_conocido ? fmtMoneda(d.monto_original, d.moneda) : '<span class="deudas-resumen-muted">sin especificar</span>')}
                    ${item('Plan total de cuotas', d.cantidad_cuotas || '—')}
                    ${item('Interés calculado', interesTxt)}
                    ${item('Situación del plan', planTxt)}
                    </div>
                </div>
            `;
        } else {
        detalleResumen.innerHTML = `${overviewHtml}
            <div class="deudas-detail-data">
                <div class="deudas-detail-data-title">Datos de la deuda</div>
                <div class="deudas-resumen-grid">
                ${item('Descripción', d.descripcion || d.compra_numero || '-', true)}
                ${item('N° de comprobante', d.numero_comprobante || '-')}
                ${tieneCuentaPropia ? item(cuentaLabel, cuentaValor) : ''}
                ${mostrarDescuento ? item('Gastos de otorgamiento', fmtMoneda(d.descuento_acreditacion, d.moneda)) : ''}
                ${mostrarDescuento ? item('Monto acreditado', d.monto_acreditado ? fmtMoneda(d.monto_acreditado, d.moneda) : '—') : ''}
                ${item('Moneda', d.moneda)}
                ${item('Monto original', fmtMoneda(d.monto_original, d.moneda))}
                ${item('Interés %', `${d.porcentaje_interes}%`)}
                ${d.modo_cuotas === 'libre' ? '' : `
                ${item('Cantidad de cuotas', `${d.cuotas_pagadas}/${d.cantidad_cuotas}`)}
                ${item('Inicio de débito', d.fecha_inicio)}`}
                </div>
            </div>
            ${d.compra_numero ? `<p class="deudas-edicion-nota">Esta deuda nació de una compra — se edita desde su historial de Compras.</p>` : ''}
        `;
        }

        if (detNotas) detNotas.textContent = d.notas || '—';
        // Se puede eliminar aunque ya tenga cuotas pagadas (reales o
        // históricas) — el aviso fuerte de qué implica eso va en el
        // confirm al hacer click, no acá.

        if (typeof renderizarDocumentosDeuda === 'function') renderizarDocumentosDeuda(d);

        if (cuotasTitle) cuotasTitle.textContent = d.modo_cuotas === 'libre' ? 'Abonos registrados' : 'Plan de cuotas';
        if (cuotasMeta) {
            if (d.modo_cuotas === 'libre') {
                cuotasMeta.textContent = `${d.cuotas.length} pago${d.cuotas.length === 1 ? '' : 's'} registrado${d.cuotas.length === 1 ? '' : 's'}`;
            } else {
                const totalCuotas = d.cantidad_cuotas || d.cuotas.length;
                cuotasMeta.textContent = `${d.cuotas_pagadas} de ${totalCuotas} pagadas`;
            }
        }

        const saldoPendienteNum = parseFloat(d.saldo_pendiente) || 0;
        const mostrarRegistrarAbono = d.modo_cuotas === 'libre' && d.estado === 'activa'
            && saldoPendienteNum > 0 && puedeConfirmar;
        // Una deuda tipo Cheque se paga SOLO con cheque — nunca con cuentas.
        const soloCheque = d.tipo === 'cheque';

        if (deudasRegistrarAbono) {
            deudasRegistrarAbono.hidden = !mostrarRegistrarAbono;
            if (mostrarRegistrarAbono && raSaldoLabel) {
                raSaldoLabel.textContent = fmtMoneda(d.saldo_pendiente, d.moneda);
            }
        }

        // "Editar deuda" — misma condición con la que se decide mostrar el
        // botón en el listado (ver renderizarDeudas): activa y no nacida
        // de una compra.
        if (btnEditarDeuda) {
            btnEditarDeuda.hidden = !(puedeEditar && d.estado === 'activa' && !d.compra_numero);
        }

        cuotasBody.innerHTML = d.cuotas.map(c => {
            const chequeActivo = c.cheque_pk && (c.cheque_estado === 'pendiente' || c.cheque_estado === 'confirmado');
            const notaChequeRechazado = (c.cheque_pk && c.cheque_estado === 'rechazado' && c.estado === 'pendiente')
                ? `<span class="deudas-cuota-nota">Cheque #${c.cheque_numero} rechazado</span> ` : '';

            let accion = '<span class="deudas-cuota-nota">—</span>';
            if (c.estado === 'pendiente' && chequeActivo) {
                accion = `<span class="deudas-cuota-nota">Cheque #${c.cheque_numero} en trámite</span>`;
            } else if (c.estado === 'pendiente' && puedeConfirmar && (c.habilitada || soloCheque)) {
                accion = notaChequeRechazado + (soloCheque
                    ? `<button type="button" class="btn btn-primary btn--sm" onclick="pagarCuota(${c.pk})">Pagar con cheque</button>`
                    : `<button type="button" class="btn btn-primary btn--sm" onclick="pagarCuota(${c.pk})">Pagar</button>`);
            } else if (c.estado === 'pendiente' && puedeConfirmar && !c.habilitada) {
                accion = notaChequeRechazado
                    + `<button type="button" class="btn btn-secondary btn--sm" onclick="pagarCuota(${c.pk}, true)">Adelantar pago</button>`
                    + `<span class="deudas-cuota-nota">Vence ${fmtFecha(c.fecha_vencimiento)}</span>`;
            } else if (c.estado === 'pendiente') {
                accion = notaChequeRechazado + `<span class="deudas-cuota-nota">Vence ${fmtFecha(c.fecha_vencimiento)}</span>`;
            } else if (c.estado === 'anulada' && c.cheque_pk) {
                accion = `<span class="deudas-cuota-nota">Cheque #${c.cheque_numero} rechazado — no cuenta</span>`;
            } else if (c.estado === 'confirmada' && c.es_historica) {
                let detallePago = 'carga inicial';
                if (c.cheque_pk && c.cheque_es_historico) detallePago = `cheque #${c.cheque_numero}`;
                else if (c.cuenta_pago_historica_nombre) detallePago = _deudaEscInput(c.cuenta_pago_historica_nombre);
                else if (c.medio_pago_historico) detallePago = _deudaEscInput(c.medio_pago_historico);
                accion = `<span class="deudas-cuota-pago">${detallePago}</span><span class="deudas-cuota-nota">no afectó caja</span>`;
            } else if (c.estado === 'confirmada' && c.cheque_pk) {
                accion = `<span class="deudas-cuota-pago">Cheque #${c.cheque_numero}</span>`;
            } else if (c.estado === 'confirmada' && c.pagos && c.pagos.length) {
                accion = c.pagos.map(p =>
                    `<span class="deudas-cuota-pago">${_deudaEscInput(p.cuenta_nombre)} ${fmtMoneda(p.monto, d.moneda)}</span>`
                ).join('');
            } else if (c.estado === 'confirmada') {
                accion = `<span class="deudas-cuota-pago">${_deudaEscInput(c.cuenta_pago_nombre || 'pagada')}</span>`;
            }

            const estadoLabel = c.estado === 'confirmada' ? 'Pagada' : (c.estado === 'anulada' ? 'Anulada' : 'Pendiente');
            return `
                <tr class="deudas-cuota-row deudas-cuota-row--${c.estado}">
                    <td data-label="Cuota"><span class="deudas-cuota-numero">${c.numero}</span></td>
                    <td data-label="Vencimiento" class="deudas-cuota-vencimiento">${fmtFecha(c.fecha_vencimiento)}</td>
                    <td data-label="Monto" class="deudas-monto">${fmtMoneda(c.monto, d.moneda)}</td>
                    <td data-label="Estado"><span class="deudas-badge-estado deudas-badge-estado--${c.estado === 'confirmada' ? 'activa' : c.estado === 'anulada' ? 'anulada' : 'pendiente'}">${estadoLabel}</span></td>
                    <td data-label="Acción / pago"><div class="deudas-cuota-accion">${accion}</div></td>
                </tr>`;
        }).join('') || '<tr><td colspan="5" class="deudas-cuotas-empty">Todavía no hay pagos registrados.</td></tr>';
    }

    // ── Tabla de cuotas dentro del modal de edición: acá sí se puede
    //    tildar pagada/pendiente, editar o eliminar una cuota puntual —
    //    "Ver cuotas" (arriba) es de solo lectura + pago.
    function renderizarFilaCuotaEditable(c, d) {
        const chequeActivo = c.cheque_pk && (c.cheque_estado === 'pendiente' || c.cheque_estado === 'confirmado');
        const puedeEditarEstaCuota = puedeEditar && d.estado === 'activa' && !d.compra_numero
            && !chequeActivo && (c.estado === 'pendiente' || c.estado === 'confirmada');

        let acciones = '<span class="deudas-cuota-nota">—</span>';
        if (puedeEditarEstaCuota) {
            const iconPago = c.estado === 'pendiente'
                ? `<button type="button" class="deudas-cuota-icono deudas-cuota-icono--success" title="Marcar como ya pagada"
                            onclick='marcarCuotaPagadaPrompt(${JSON.stringify(c)})'>✓</button>`
                : `<button type="button" class="deudas-cuota-icono" title="Revertir a pendiente"
                            onclick='revertirCuotaPendientePrompt(${JSON.stringify(c)})'>↩</button>`;
            acciones = `
                <div class="deudas-cuota-iconos">
                    ${iconPago}
                    <button type="button" class="deudas-cuota-icono" title="Editar cuota"
                            onclick='editarCuotaPrompt(${JSON.stringify(c)})'>✎</button>
                    <button type="button" class="deudas-cuota-icono deudas-cuota-icono--danger" title="Eliminar cuota"
                            onclick='eliminarCuotaPrompt(${JSON.stringify(c)})'>🗑</button>
                </div>`;
        }

        const estadoLabel = c.estado === 'confirmada' ? 'Pagada' : (c.estado === 'anulada' ? 'Anulada' : 'Pendiente');
        return `
            <tr class="deudas-cuota-row deudas-cuota-row--${c.estado}">
                <td data-label="Cuota"><span class="deudas-cuota-numero">${c.numero}</span></td>
                <td data-label="Vencimiento" class="deudas-cuota-vencimiento">${fmtFecha(c.fecha_vencimiento)}</td>
                <td data-label="Monto" class="deudas-monto">${fmtMoneda(c.monto, d.moneda)}</td>
                <td data-label="Estado"><span class="deudas-badge-estado deudas-badge-estado--${c.estado === 'confirmada' ? 'activa' : c.estado === 'anulada' ? 'anulada' : 'pendiente'}">${estadoLabel}</span></td>
                <td data-label="Acción">${acciones}</td>
            </tr>`;
    }

    function renderizarCuotasEdicion(d) {
        if (dCuotasActualesBody) {
            dCuotasActualesBody.innerHTML = d.cuotas.map(c => renderizarFilaCuotaEditable(c, d)).join('')
                || '<tr><td colspan="5" class="deudas-cuotas-empty">Todavía no hay cuotas cargadas.</td></tr>';
        }

        const esVariableEd = d.modo_cuotas === 'variable';

        // "Pasar a cuotas variables" — solo deudas fijas propias y activas.
        if (bloqueConvertirVariable) {
            bloqueConvertirVariable.hidden = !(d.modo_cuotas === 'fijas' && d.estado === 'activa'
                && !d.compra_numero && puedeEditar);
        }

        // Panel "agregar / editar cuotas pendientes" — solo cuotas variables activas propias.
        if (deudasEditarCuotas) {
            const mostrarEditarCuotas = esVariableEd && d.estado === 'activa' && puedeEditar && !d.compra_numero;
            deudasEditarCuotas.hidden = !mostrarEditarCuotas;
            if (mostrarEditarCuotas) {
                deudasEditarCuotasWrap.innerHTML = '';
                d.cuotas.filter(c => c.editable).forEach(c => {
                    agregarFilaCuotaEditable({ fecha: c.fecha_vencimiento, monto: c.monto });
                });
                ecMsg.textContent = '';
                actualizarResumenEditarCuotas(d);
            }
            // Punto de referencia para saber, más adelante, si el usuario
            // tocó algo acá (agregó/editó/tildó una fila) — ver guardarEdicionDeuda.
            snapshotEditarCuotas = serializarFilasEditarCuotas();
        }
    }

    // Estado actual de las filas del panel "Agregar o editar cuotas
    // pendientes", para poder comparar contra `snapshotEditarCuotas` y
    // detectar si el usuario cargó algo ahí sin usar su botón de guardar.
    function serializarFilasEditarCuotas() {
        return JSON.stringify(Array.from(deudasEditarCuotasWrap.querySelectorAll('.deudas-cv-fila')).map(f => ({
            monto: f.querySelector('.dcv-monto').value,
            fecha: f.querySelector('.dcv-fecha').value,
            pagada: !!f.querySelector('.dcv-pagada')?.checked,
            fechaPago: f.querySelector('.dcv-fecha-pago')?.value || '',
        })));
    }
    let snapshotEditarCuotas = '[]';

    // ════════════════════════════════════════════════════════════════
    //  Modal "Pagar cuota / abono" — pago dividido en varias cuentas
    // ════════════════════════════════════════════════════════════════
    const modalPagoCuota = document.getElementById('modalPagoCuota');
    const modalPagoCuotaBackdrop = document.getElementById('modalPagoCuotaBackdrop');
    const btnCerrarPagoCuota = document.getElementById('btnCerrarPagoCuota');
    const pagoCuotaTitle = document.getElementById('pagoCuotaTitle');
    const pagoCuotaObjetivo = document.getElementById('pagoCuotaObjetivo');
    const pagoCuotaObjetivoFijo = document.getElementById('pagoCuotaObjetivoFijo');
    const pagoCuotaCamposAbono = document.getElementById('pagoCuotaCamposAbono');
    const pagoCuotaMonto = document.getElementById('pagoCuotaMonto');
    const pagoCuotaFecha = document.getElementById('pagoCuotaFecha');
    const pagoCuotaLineas = document.getElementById('pagoCuotaLineas');
    const btnAgregarLineaPago = document.getElementById('btnAgregarLineaPago');
    const pagoCuotaResumen = document.getElementById('pagoCuotaResumen');
    const pagoCuotaMsg = document.getElementById('pagoCuotaMsg');
    const btnConfirmarPagoCuota = document.getElementById('btnConfirmarPagoCuota');
    const btnPagarConCheque = document.getElementById('btnPagarConCheque');

    // ctx: { modo: 'cuota'|'abono', cuotaPk?, adelantar?, deudaPk, moneda, objetivo, pedirFecha }
    let pagoCtx = null;

    function cerrarModalPagoCuota() {
        modalPagoCuota.hidden = true;
        document.body.style.overflow = '';
        pagoCtx = null;
    }
    btnCerrarPagoCuota.addEventListener('click', cerrarModalPagoCuota);

    function agregarLineaPago(preset) {
        preset = preset || {};
        const cuentas = cuentasPorMoneda(pagoCtx.moneda, false);
        const princ = cuentaPrincipalEn(cuentas);
        const fila = document.createElement('div');
        fila.className = 'deudas-pago-linea';
        fila.innerHTML = `
            <select class="dpl-cuenta">
                <option value="">— Cuenta —</option>
                ${cuentas.map(c => `<option value="${c.pk}"${(preset.cuenta_pk ? String(c.pk) === String(preset.cuenta_pk) : String(c.pk) === princ) ? ' selected' : ''}>${c.nombre}${c.titular ? ' · ' + c.titular : ''}</option>`).join('')}
            </select>
            <input type="number" class="dpl-monto" step="0.01" min="0.01" placeholder="Monto" value="${preset.monto != null ? preset.monto : ''}">
            <button type="button" class="deudas-cv-quitar" aria-label="Quitar">&times;</button>
        `;
        fila.querySelector('.dpl-monto').addEventListener('input', actualizarResumenPago);
        fila.querySelector('.deudas-cv-quitar').addEventListener('click', () => {
            fila.remove();
            actualizarResumenPago();
        });
        pagoCuotaLineas.appendChild(fila);
    }
    btnAgregarLineaPago.addEventListener('click', () => { agregarLineaPago(); actualizarResumenPago(); });

    function _lineasPago() {
        return Array.from(pagoCuotaLineas.querySelectorAll('.deudas-pago-linea')).map(f => ({
            cuenta_pk: f.querySelector('.dpl-cuenta').value,
            monto: parseFloat(f.querySelector('.dpl-monto').value) || 0,
        }));
    }

    function _objetivoActual() {
        if (pagoCtx && pagoCtx.modo === 'abono') return parseFloat(pagoCuotaMonto.value) || 0;
        return pagoCtx ? pagoCtx.objetivo : 0;
    }

    function actualizarResumenPago() {
        if (!pagoCtx) return;
        const objetivo = _objetivoActual();
        const total = _lineasPago().reduce((a, l) => a + l.monto, 0);
        const dif = objetivo - total;
        const ok = objetivo > 0 && Math.abs(dif) < 0.01;
        pagoCuotaResumen.textContent = objetivo <= 0
            ? 'Indicá cuánto pagás'
            : (ok ? 'Cubre el pago ✓'
                  : (dif > 0 ? `Faltan ${fmtMoneda(dif, pagoCtx.moneda)}` : `Sobran ${fmtMoneda(-dif, pagoCtx.moneda)}`));
        pagoCuotaResumen.classList.toggle('deudas-pago-resumen--ok', ok);
    }
    pagoCuotaMonto.addEventListener('input', actualizarResumenPago);

    function abrirModalPagoCuota(ctx) {
        pagoCtx = ctx;
        const esAbono = ctx.modo === 'abono';
        pagoCuotaTitle.textContent = esAbono ? 'Registrar un pago' : 'Pagar cuota';
        pagoCuotaObjetivoFijo.hidden = esAbono;
        pagoCuotaCamposAbono.hidden = !esAbono;
        if (esAbono) {
            pagoCuotaMonto.value = ctx.objetivo;
            pagoCuotaMonto.max = ctx.objetivo;
            pagoCuotaFecha.value = today;
            pagoCuotaFecha.max = today;
        } else {
            pagoCuotaObjetivo.textContent = fmtMoneda(ctx.objetivo, ctx.moneda);
        }
        pagoCuotaMsg.textContent = '';
        pagoCuotaLineas.innerHTML = '';
        agregarLineaPago({ monto: ctx.objetivo });
        actualizarResumenPago();
        // Cheque no admite pago con cuenta.
        btnConfirmarPagoCuota.hidden = ctx.soloCheque;
        btnAgregarLineaPago.hidden = ctx.soloCheque;
        pagoCuotaLineas.hidden = ctx.soloCheque;
        pagoCuotaResumen.hidden = ctx.soloCheque;
        modalPagoCuota.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    window.pagarCuota = function (cuotaPk, adelantar = false) {
        const c = deudaDetalleActual.cuotas.find(x => x.pk === cuotaPk);
        if (!c) return;
        abrirModalPagoCuota({
            modo: 'cuota', cuotaPk, adelantar: !!adelantar,
            deudaPk: deudaDetalleActual.pk, moneda: deudaDetalleActual.moneda,
            objetivo: parseFloat(c.monto), pedirFecha: false,
            soloCheque: deudaDetalleActual.tipo === 'cheque',
        });
    };

    async function _enviarPago(body) {
        pagoCuotaMsg.textContent = '';
        const url = pagoCtx.modo === 'abono'
            ? urlRegistrarAbono(pagoCtx.deudaPk)
            : urlConfirmarCuota(pagoCtx.cuotaPk);
        btnConfirmarPagoCuota.disabled = true;
        try {
            const r = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify(body),
            });
            const result = await r.json();
            if (result.success) {
                cerrarModalPagoCuota();
                window.verDeuda(deudaDetalleActual.pk);
                cargarDeudas();
            } else {
                pagoCuotaMsg.textContent = result.error || 'No se pudo registrar el pago.';
            }
        } catch (e) {
            console.error(e);
            pagoCuotaMsg.textContent = 'No se pudo registrar el pago.';
        } finally {
            btnConfirmarPagoCuota.disabled = false;
        }
    }

    btnConfirmarPagoCuota.addEventListener('click', async () => {
        if (!pagoCtx) return;
        const objetivo = _objetivoActual();
        if (objetivo <= 0) { pagoCuotaMsg.textContent = 'Indicá cuánto pagás.'; return; }
        const lineas = _lineasPago().filter(l => l.monto > 0);
        if (!lineas.length) { pagoCuotaMsg.textContent = 'Agregá al menos una cuenta con su monto.'; return; }
        if (lineas.some(l => !l.cuenta_pk)) { pagoCuotaMsg.textContent = 'Elegí la cuenta de cada línea.'; return; }
        const total = lineas.reduce((a, l) => a + l.monto, 0);
        if (Math.abs(total - objetivo) > 0.01) {
            pagoCuotaMsg.textContent = `Las líneas suman ${fmtMoneda(total, pagoCtx.moneda)}, tienen que sumar ${fmtMoneda(objetivo, pagoCtx.moneda)}.`;
            return;
        }
        if (pagoCtx.modo === 'abono' && !pagoCuotaFecha.value) { pagoCuotaMsg.textContent = 'Indicá la fecha del pago.'; return; }
        if (!await KaiConfirm('¿Registrar este pago? Va a impactar la caja.')) return;

        const body = { pagos: lineas };
        if (pagoCtx.modo === 'cuota') { body.adelantar = pagoCtx.adelantar; }
        if (pagoCtx.modo === 'abono') { body.monto = objetivo; body.fecha = pagoCuotaFecha.value; }
        _enviarPago(body);
    });

    btnPagarConCheque.addEventListener('click', () => {
        if (!pagoCtx) return;
        const objetivo = _objetivoActual();
        if (objetivo <= 0) { pagoCuotaMsg.textContent = 'Indicá cuánto pagás.'; return; }
        chequeCuotaActual = pagoCtx.modo === 'abono'
            ? { modoAbono: true, deudaPk: pagoCtx.deudaPk, monto: objetivo, fecha: pagoCuotaFecha.value || today }
            : { modoAbono: false, cuotaPk: pagoCtx.cuotaPk, adelantar: pagoCtx.adelantar, monto: objetivo };
        cerrarModalPagoCuota();
        _prepararModalChequeComun(chequeCuotaActual.monto, deudaDetalleActual.moneda);
    });

    // ── Modal "Pagar con cheque" (reusado desde el modal de pago) ─────
    const modalChequeCuota = document.getElementById('modalChequeCuota');
    const modalChequeCuotaBackdrop = document.getElementById('modalChequeCuotaBackdrop');
    const btnCerrarChequeCuota = document.getElementById('btnCerrarChequeCuota');
    const btnCancelarChequeCuota = document.getElementById('btnCancelarChequeCuota');
    const btnGuardarChequeCuota = document.getElementById('btnGuardarChequeCuota');
    let chequeCuotaActual = null;

    function _prepararModalChequeComun(monto, moneda) {
        document.getElementById('cchcMontoLabel').textContent = fmtMoneda(monto, moneda);
        document.getElementById('cchc_numero_cheque').value = '';
        document.getElementById('cchc_fecha_emision').value = today;
        document.getElementById('cchc_fecha_cobro').value = today;
        document.getElementById('cchc_receptor').value = '';
        document.getElementById('cchc_emisor').value = '';
        document.getElementById('cchcMsg').textContent = '';

        const chequeraSelect = document.getElementById('cchc_cuenta_origen');
        const financiadoraSelect = document.getElementById('cchc_financiadora');
        const chequeras = cuentasBancariasPorMoneda(moneda);
        chequeraSelect.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            chequeras.map(c => `<option value="${c.pk}">${c.nombre}${c.titular ? ' · ' + c.titular : ''}</option>`).join('');
        const financiadoras = CUENTAS.filter(c => c.moneda === moneda && !c.es_credito);
        financiadoraSelect.innerHTML = '<option value="">— No hace falta, ya tiene fondos —</option>' +
            financiadoras.map(c => `<option value="${c.pk}">${c.nombre}${c.titular ? ' · ' + c.titular : ''}</option>`).join('');

        modalChequeCuota.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function cerrarModalChequeCuota() {
        modalChequeCuota.hidden = true;
        document.body.style.overflow = '';
        chequeCuotaActual = null;
    }
    btnCerrarChequeCuota.addEventListener('click', cerrarModalChequeCuota);
    btnCancelarChequeCuota.addEventListener('click', cerrarModalChequeCuota);

    btnGuardarChequeCuota.addEventListener('click', async () => {
        if (!chequeCuotaActual) return;
        const msg = document.getElementById('cchcMsg');
        const cuentaOrigenPk = document.getElementById('cchc_cuenta_origen').value;
        const fechaEmision = document.getElementById('cchc_fecha_emision').value;
        const fechaCobro = document.getElementById('cchc_fecha_cobro').value;
        if (!cuentaOrigenPk) { msg.textContent = 'Elegí la cuenta bancaria (chequera).'; return; }
        if (!fechaEmision || !fechaCobro) { msg.textContent = 'Indicá fecha de emisión y de cobro.'; return; }

        const mensajeConfirmacion = chequeCuotaActual.modoAbono
            ? '¿Registrar este abono con este cheque? Queda confirmado ya mismo; el egreso real de caja se genera recién cuando confirmes el cheque desde la pantalla de Cheques.'
            : '¿Pagar esta cuota con este cheque? La cuota queda confirmada ya mismo; el egreso real de caja se genera recién cuando confirmes el cheque desde la pantalla de Cheques.';
        if (!await KaiConfirm(mensajeConfirmacion)) return;

        const chequeData = {
            numero_cheque: document.getElementById('cchc_numero_cheque').value,
            monto: chequeCuotaActual.monto,
            fecha_emision: fechaEmision,
            fecha_cobro: fechaCobro,
            cuenta_origen_pk: cuentaOrigenPk,
            cuenta_financiadora_pk: document.getElementById('cchc_financiadora').value || null,
            receptor: document.getElementById('cchc_receptor').value,
            emisor: document.getElementById('cchc_emisor').value,
        };

        btnGuardarChequeCuota.disabled = true;
        try {
            const response = chequeCuotaActual.modoAbono
                ? await fetch(urlRegistrarAbono(chequeCuotaActual.deudaPk), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({
                        monto: chequeCuotaActual.monto,
                        fecha: chequeCuotaActual.fecha,
                        cheque: chequeData,
                    }),
                })
                : await fetch(urlConfirmarCuota(chequeCuotaActual.cuotaPk), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({ adelantar: chequeCuotaActual.adelantar, cheque: chequeData }),
                });
            const result = await response.json();
            if (result.success) {
                cerrarModalChequeCuota();
                window.verDeuda(deudaDetalleActual.pk);
                cargarDeudas();
            } else {
                msg.textContent = result.error || 'Error al confirmar el pago con cheque.';
            }
        } catch (error) {
            console.error('Error al confirmar pago con cheque:', error);
            msg.textContent = 'Error al confirmar el pago con cheque.';
        } finally {
            btnGuardarChequeCuota.disabled = false;
        }
    });

    // ── Registrar abono (modo_cuotas=libre) — abre el modal de pago ───
    btnAbonar?.addEventListener('click', () => {
        if (!deudaDetalleActual) return;
        const saldo = parseFloat(deudaDetalleActual.saldo_pendiente) || 0;
        if (saldo <= 0) return;
        abrirModalPagoCuota({
            modo: 'abono', deudaPk: deudaDetalleActual.pk, moneda: deudaDetalleActual.moneda,
            objetivo: saldo, pedirFecha: true,
            soloCheque: deudaDetalleActual.tipo === 'cheque',
        });
    });

    // ── Agregar / editar cuotas pendientes (modo_cuotas=variable) ─────
    function urlEditarCuotas(deudaPk) {
        return urls.editarCuotas.replace('/0/', `/${deudaPk}/`);
    }

    // Cada fila permite, además de fecha/monto, tildar "ya pagada" — para
    // cuando la cuota que se está agregando (no una de las que ya existían)
    // resulta que ya se pagó. Mismo patrón de campos que agregarFilaCuotaVariable
    // (alta), reutilizando sus mismos helpers (opcionesMedioPago, onCvPagadaChange,
    // onPhMedioChange, recolectarPagoHistorico) — ver btnGuardarCuotas.
    function agregarFilaCuotaEditable(valores) {
        valores = valores || {};
        const fila = document.createElement('div');
        fila.className = 'deudas-cv-fila';
        fila.innerHTML = `
            <div class="deudas-cv-fila-linea">
                <span class="deudas-cv-numero"></span>
                <input type="date" class="dcv-fecha" value="${valores.fecha || ''}" title="Vencimiento">
                <input type="number" class="dcv-monto" step="0.01" min="0.01" placeholder="Monto" value="${valores.monto || ''}">
                <label class="deudas-cv-pagada-lbl"><input type="checkbox" class="dcv-pagada" onchange="onCvPagadaChange(this)"> ya pagada</label>
                <input type="date" class="dcv-fecha-pago" max="${today}" title="Fecha de pago" disabled>
                <select class="ph-medio" onchange="onPhMedioChange(this)" disabled>${opcionesMedioPago()}</select>
                <button type="button" class="deudas-cv-quitar" aria-label="Quitar">&times;</button>
            </div>
            <div class="ph-detalle"></div>`;
        fila.querySelector('.dcv-monto').addEventListener('input', () => actualizarResumenEditarCuotas());
        fila.querySelector('.deudas-cv-quitar').addEventListener('click', () => {
            fila.remove();
            actualizarResumenEditarCuotas();
        });
        deudasEditarCuotasWrap.appendChild(fila);
        return fila;
    }
    btnAgregarCuotaPendiente?.addEventListener('click', () => {
        agregarFilaCuotaEditable();
        actualizarResumenEditarCuotas();
    });

    // Generar de una N filas nuevas, mensuales desde la última cuota cargada,
    // con el mismo monto que la anterior (después se ajusta lo que difiera).
    btnEcGenerar?.addEventListener('click', () => {
        const n = parseInt(ecGenerarN.value, 10) || 0;
        if (n < 1 || n > 200) return;
        const filas = Array.from(deudasEditarCuotasWrap.querySelectorAll('.deudas-cv-fila'));
        const ultima = filas[filas.length - 1];
        let baseFecha = ultima ? ultima.querySelector('.dcv-fecha').value : '';
        const baseMonto = ultima ? ultima.querySelector('.dcv-monto').value : '';
        if (!baseFecha && deudaDetalleActual && (deudaDetalleActual.cuotas || []).length) {
            const cuotas = deudaDetalleActual.cuotas;
            baseFecha = cuotas[cuotas.length - 1].fecha_vencimiento;
        }
        for (let i = 1; i <= n; i++) {
            agregarFilaCuotaEditable({
                fecha: baseFecha ? sumarMesesISO(baseFecha, i) : '',
                monto: baseMonto || '',
            });
        }
        ecGenerarN.value = '';
        actualizarResumenEditarCuotas();
    });

    // Numeración visual de las filas de este panel, continuando después de
    // las cuotas que ya existen (pagadas / históricas / con cheque en trámite).
    function renumerarEditarCuotas(d) {
        const offset = d ? d.cuotas.filter(c => !c.editable).length : 0;
        Array.from(deudasEditarCuotasWrap.querySelectorAll('.deudas-cv-fila')).forEach((f, i) => {
            const badge = f.querySelector('.deudas-cv-numero');
            if (badge) badge.textContent = String(offset + i + 1);
        });
    }

    function actualizarResumenEditarCuotas(d) {
        d = d || deudaDetalleActual;
        renumerarEditarCuotas(d);
        if (!d || !deudasEditarCuotasResumen) return;
        const nuevos = Array.from(deudasEditarCuotasWrap.querySelectorAll('.dcv-monto'))
            .map(i => parseFloat(i.value) || 0).filter(v => v > 0);
        const nuevosTotal = nuevos.reduce((a, b) => a + b, 0);
        const pagadas = d.cuotas.filter(c => c.estado === 'confirmada');
        const yaPagado = pagadas.reduce((a, c) => a + (parseFloat(c.monto) || 0), 0);
        const totalPlan = yaPagado + nuevosTotal;
        const capital = parseFloat(d.monto_original) || 0;
        const n = pagadas.length + nuevos.length;
        let txt = `${n} cuota${n === 1 ? '' : 's'} en total · pendiente ${fmtMoneda(nuevosTotal, d.moneda)}`;
        if (capital > 0 && totalPlan > 0) {
            const planTotal = parseInt(d.cantidad_cuotas, 10) || 0;
            const completo = !planTotal || n >= planTotal;
            txt += completo
                ? ` · Interés real ${((totalPlan - capital) / capital * 100).toFixed(2)}%`
                : ' · Interés: faltan cuotas del plan';
        }
        deudasEditarCuotasResumen.textContent = txt;
    }

    // Guarda el panel "Agregar o editar cuotas pendientes": reemplaza las
    // pendientes por lo que hay cargado ahí y, para las filas tildadas "ya
    // pagada", las marca como tales a continuación (ver comentario sobre
    // el reordenamiento más abajo). Sin confirmación ni toast propios —
    // eso lo maneja quien la llama (el botón de acá abajo, o "Guardar
    // cambios" si detecta que este panel tiene algo sin guardar).
    // Devuelve { deuda } o { error } — nunca lanza.
    async function guardarCuotasPendientesPanel() {
        const filasCrudas = Array.from(deudasEditarCuotasWrap.querySelectorAll('.deudas-cv-fila')).map(f => {
            const fila = {
                monto: f.querySelector('.dcv-monto').value,
                fecha_vencimiento: f.querySelector('.dcv-fecha').value,
            };
            const chk = f.querySelector('.dcv-pagada');
            if (chk && chk.checked) {
                fila.pagada = true;
                fila.fecha_pago = f.querySelector('.dcv-fecha-pago').value;
                Object.assign(fila, recolectarPagoHistorico(f));
            }
            return fila;
        }).filter(r => parseFloat(r.monto) > 0 && r.fecha_vencimiento);

        if (filasCrudas.some(r => r.pagada && !r.fecha_pago)) {
            return { error: 'Indicá la fecha de pago de las cuotas que tildaste "ya pagada".' };
        }

        // El backend reemplaza TODAS las cuotas pendientes por esta lista y
        // las numera ordenadas por vencimiento (ver Deuda.editar_cuotas_pendientes)
        // — así que las nuevas siempre nacen sin cheque ni pago. Para poder
        // marcar como pagada la que corresponda después de guardar, hay que
        // saber cuál cuota nueva (con pk recién asignado) es cuál fila: se
        // ordena acá igual que el backend, para matchear por posición contra
        // las pendientes que vuelvan en la respuesta.
        const filasOrdenadas = [...filasCrudas].sort((a, b) => a.fecha_vencimiento.localeCompare(b.fecha_vencimiento));

        try {
            const response = await fetch(urlEditarCuotas(deudaDetalleActual.pk), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ filas: filasCrudas.map(({ monto, fecha_vencimiento }) => ({ monto, fecha_vencimiento })) }),
            });
            const result = await response.json();
            if (!result.success) return { error: result.error || 'Error al guardar las cuotas.' };

            let deudaActual = result.deuda;
            const pendientesNuevas = deudaActual.cuotas
                .filter(c => c.estado === 'pendiente')
                .sort((a, b) => a.fecha_vencimiento.localeCompare(b.fecha_vencimiento));

            let erroresPago = 0;
            for (let i = 0; i < filasOrdenadas.length; i++) {
                if (!filasOrdenadas[i].pagada) continue;
                const cuotaNueva = pendientesNuevas[i];
                if (!cuotaNueva) continue;
                try {
                    const rPago = await fetch(urls.marcarPagada.replace('/0/', `/${cuotaNueva.pk}/`), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                        body: JSON.stringify({
                            fecha_pago: filasOrdenadas[i].fecha_pago,
                            cuenta_pago_historica_pk: filasOrdenadas[i].cuenta_pago_historica_pk,
                            cheque_historico: filasOrdenadas[i].cheque_historico,
                            medio_pago: filasOrdenadas[i].medio_pago,
                        }),
                    });
                    const resultPago = await rPago.json();
                    if (resultPago.success) deudaActual = resultPago.deuda;
                    else erroresPago++;
                } catch (e) {
                    console.error('Error al marcar cuota nueva como pagada:', e);
                    erroresPago++;
                }
            }

            return { deuda: deudaActual, erroresPago };
        } catch (error) {
            console.error('Error al guardar cuotas:', error);
            return { error: 'Error al guardar las cuotas.' };
        }
    }

    btnGuardarCuotas?.addEventListener('click', async () => {
        if (!deudaDetalleActual) return;
        ecMsg.textContent = '';

        const hayPagadas = Array.from(deudasEditarCuotasWrap.querySelectorAll('.dcv-pagada')).some(c => c.checked);
        const msg = hayPagadas
            ? '¿Guardar el cronograma de cuotas pendientes? Las que tildaste "ya pagada" quedan registradas '
              + 'como pagadas (sin afectar la caja, como una carga inicial) — las demás quedan pendientes. '
              + 'Las cuotas ya pagadas de antes no se tocan.'
            : '¿Guardar el cronograma de cuotas pendientes? Las cuotas ya pagadas no se tocan.';
        if (!await KaiConfirm(msg)) return;

        btnGuardarCuotas.disabled = true;
        try {
            const resultado = await guardarCuotasPendientesPanel();
            if (resultado.error) {
                ecMsg.textContent = resultado.error;
                return;
            }
            KaiToast.show(
                resultado.erroresPago
                    ? `Cuotas guardadas, pero ${resultado.erroresPago} no se pudieron marcar como pagadas.`
                    : 'Cuotas actualizadas.',
                resultado.erroresPago ? 'warning' : 'success',
            );
            deudaDetalleActual = resultado.deuda;
            refrescarFormularioEdicion(resultado.deuda);
            cargarDeudas();
        } finally {
            btnGuardarCuotas.disabled = false;
        }
    });

    // ── Pasar de cuotas fijas a variables ────────────────────────────
    btnConvertirVariable?.addEventListener('click', async () => {
        if (!deudaDetalleActual) return;
        if (!await KaiConfirm(
            '¿Pasar esta deuda a "cuotas variables"? Las cuotas actuales quedan como están; '
            + 'después vas a poder editarlas de a una y agregar las que falten.'
        )) return;
        try {
            const r = await fetch(urls.convertirVariable.replace('/0/', `/${deudaDetalleActual.pk}/`), {
                method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const result = await r.json();
            if (result.success) {
                KaiToast.show('Ahora es de cuotas variables.', 'success');
                refrescarFormularioEdicion(result.deuda);
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'No se pudo convertir.', 'danger');
            }
        } catch (e) {
            console.error(e);
            KaiToast.show('No se pudo convertir.', 'danger');
        }
    });

    // ── Editar / eliminar una cuota puntual ──────────────────────────
    window.editarCuotaPrompt = async function (c) {
        const nuevaFecha = window.prompt('Vencimiento de la cuota (AAAA-MM-DD):', c.fecha_vencimiento);
        if (nuevaFecha === null) return;
        const nuevoMonto = window.prompt('Monto de la cuota:', c.monto);
        if (nuevoMonto === null) return;
        const pagada = c.estado === 'confirmada';
        if (pagada && !await KaiConfirm(
            'Esta cuota ya está pagada. Si cambiás el monto, se ajusta el movimiento de caja '
            + '(la diferencia vuelve o sale de la cuenta con la que se pagó). ¿Seguir?', { danger: true }
        )) return;
        try {
            const r = await fetch(urls.editarCuota.replace('/0/', `/${c.pk}/`), {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ fecha_vencimiento: nuevaFecha || null, monto: nuevoMonto || null }),
            });
            const result = await r.json();
            if (result.success) {
                KaiToast.show('Cuota actualizada.', 'success');
                deudaDetalleActual = result.deuda;
                renderizarCuotasEdicion(result.deuda);
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'No se pudo editar la cuota.', 'danger');
            }
        } catch (e) {
            console.error(e);
            KaiToast.show('No se pudo editar la cuota.', 'danger');
        }
    };

    // Corregir una carga inicial después del hecho: tildar como ya pagada
    // una cuota que quedó pendiente por error. No genera egreso de caja —
    // mismo mecanismo que una cuota "ya pagada" al crear la deuda.
    window.marcarCuotaPagadaPrompt = async function (c) {
        const fecha = window.prompt('¿Qué día se pagó esta cuota? (AAAA-MM-DD)', c.fecha_vencimiento < today ? c.fecha_vencimiento : today);
        if (!fecha) return;
        if (!await KaiConfirm(
            `¿Marcar la cuota ${c.numero} como ya pagada el ${fmtFecha(fecha)}? No genera ningún movimiento `
            + `de caja — se asume que esa plata ya salió antes de cargar el sistema.`
        )) return;
        try {
            const r = await fetch(urls.marcarPagada.replace('/0/', `/${c.pk}/`), {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ fecha_pago: fecha }),
            });
            const result = await r.json();
            if (result.success) {
                KaiToast.show('Cuota marcada como pagada.', 'success');
                deudaDetalleActual = result.deuda;
                renderizarCuotasEdicion(result.deuda);
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'No se pudo marcar la cuota como pagada.', 'danger');
            }
        } catch (e) {
            console.error(e);
            KaiToast.show('No se pudo marcar la cuota como pagada.', 'danger');
        }
    };

    // Deshacer el pago de una cuota (real o histórico) sin borrarla — para
    // corregir una que se marcó pagada por error, sin perder su lugar en
    // el plan (a diferencia de eliminarCuotaPrompt, que la saca del todo).
    window.revertirCuotaPendientePrompt = async function (c) {
        const msg = c.es_historica
            ? `¿Revertir la cuota ${c.numero} a pendiente? No había movido caja real (era histórica) — solo `
              + `deja de contar como pagada.`
            : `¿Revertir la cuota ${c.numero} a pendiente? Se revierte su pago: la plata vuelve a la cuenta `
              + `(o se rechaza el cheque) y queda pendiente de nuevo.`;
        if (!await KaiConfirm(msg, { danger: true, confirmText: 'Revertir' })) return;
        try {
            const r = await fetch(urls.revertirPendiente.replace('/0/', `/${c.pk}/`), {
                method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const result = await r.json();
            if (result.success) {
                KaiToast.show('Cuota revertida a pendiente.', 'success');
                deudaDetalleActual = result.deuda;
                renderizarCuotasEdicion(result.deuda);
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'No se pudo revertir la cuota.', 'danger');
            }
        } catch (e) {
            console.error(e);
            KaiToast.show('No se pudo revertir la cuota.', 'danger');
        }
    };

    window.eliminarCuotaPrompt = async function (c) {
        const pagada = c.estado === 'confirmada';
        const msg = pagada
            ? `La cuota ${c.numero} ya está pagada. Al eliminarla se revierte su movimiento de caja `
              + `(la plata vuelve a la cuenta con la que se pagó) y, si tenía un cheque, se rechaza. ¿Eliminar?`
            : `¿Eliminar la cuota ${c.numero}?`;
        if (!await KaiConfirm(msg, { danger: true, confirmText: 'Eliminar' })) return;
        try {
            const r = await fetch(urls.eliminarCuota.replace('/0/', `/${c.pk}/`), {
                method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const result = await r.json();
            if (result.success) {
                KaiToast.show('Cuota eliminada.', 'success');
                deudaDetalleActual = result.deuda;
                renderizarCuotasEdicion(result.deuda);
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'No se pudo eliminar la cuota.', 'danger');
            }
        } catch (e) {
            console.error(e);
            KaiToast.show('No se pudo eliminar la cuota.', 'danger');
        }
    };

    btnEditarDeuda?.addEventListener('click', () => {
        if (!deudaDetalleActual) return;
        const pk = deudaDetalleActual.pk;
        cerrarDetalle();
        window.editarDeuda(pk, 'detalle');
    });

    btnImprimirDeuda?.addEventListener('click', () => {
        if (!deudaDetalleActual) return;
        if (typeof deudaImprimir === 'function') {
            deudaImprimir(deudaDetalleActual);
        } else {
            console.error('deudas_imprimir.js no está cargado.');
        }
    });

    btnEliminarDeuda?.addEventListener('click', async () => {
        if (!deudaDetalleActual) return;
        const tieneCuotasReales = deudaDetalleActual.cuotas.some(c => c.estado === 'confirmada' && !c.es_historica);
        const mensaje = tieneCuotasReales
            ? 'Esta deuda ya tiene cuotas pagadas de verdad — al eliminarla también se borran esos egresos de la caja (la plata "vuelve" a la cuenta de origen). ¿Eliminar de todas formas?'
            : '¿Estás seguro de eliminar esta deuda?';
        if (!await KaiConfirm(mensaje, { danger: true, confirmText: 'Eliminar' })) return;

        try {
            const response = await fetch(`${urlEliminarBase}${deudaDetalleActual.pk}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const result = await response.json();

            if (result.success) {
                cerrarDetalle();
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'Error al eliminar', 'danger');
            }
        } catch (error) {
            console.error('Error al eliminar:', error);
            KaiToast.show('Error al eliminar', 'danger');
        }
    });

    // ── Filtros ────────────────────────────────────────────────────
    btnToggleFiltros.addEventListener('click', () => {
        const expanded = btnToggleFiltros.getAttribute('aria-expanded') === 'true';
        btnToggleFiltros.setAttribute('aria-expanded', !expanded);
        formFiltros.hidden = expanded;
    });

    formFiltros.addEventListener('submit', (e) => {
        e.preventDefault();
        paginaActual = 1;
        cargarDeudas();
    });

    btnLimpiarFiltros.addEventListener('click', () => {
        formFiltros.reset();
        paginaActual = 1;
        cargarDeudas();
    });

    // ── Helpers ─────────────────────────────────────────────────────
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }

    // ── Inicialización ─────────────────────────────────────────────
    document.getElementById('dFechaInicio').value = today;
    poblarSelectsCuentas();
    cargarDeudas();

    // Llegada desde otra pantalla (ej. Compras, tras confirmar un pago
    // con cheque) con ?ver=<pk> — abre el detalle de esa deuda directo.
    const verPk = new URLSearchParams(window.location.search).get('ver');
    if (verPk) window.verDeuda(parseInt(verPk, 10));
});
