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

    // La chequera de un pago con cheque solo puede ser una cuenta
    // bancaria real (no efectivo, no billetera) — mismo criterio que
    // en Cheques/Compras.
    function cuentasBancariasPorMoneda(moneda) {
        return CUENTAS.filter(c => c.moneda === moneda && c.tipo === 'banco');
    }

    function poblarSelect(select, opciones, seleccionarPk) {
        select.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            opciones.map(c => `<option value="${c.pk}">${c.nombre}</option>`).join('');
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
    const dTipo = document.getElementById('dTipo');
    const dMoneda = document.getElementById('dMoneda');
    const dCuentaTarjeta = document.getElementById('dCuentaTarjeta');
    const dCuentaAcreditacion = document.getElementById('dCuentaAcreditacion');
    const campoTarjeta = document.getElementById('campoTarjeta');
    const campoAcreditacion = document.getElementById('campoAcreditacion');
    const botonesTipo = document.querySelectorAll('.deudas-tipo-btn[data-tipo]');
    const dCargaInicial = document.getElementById('dCargaInicial');
    const deudasCuotasHistoricas = document.getElementById('deudasCuotasHistoricas');
    const deudasCuotasHistoricasBody = document.getElementById('deudasCuotasHistoricasBody');
    const deudasTotales = document.getElementById('deudasTotales');
    const dMonto = document.getElementById('dMonto');
    const dInteres = document.getElementById('dInteres');
    const dCuotas = document.getElementById('dCuotas');
    const dFechaInicio = document.getElementById('dFechaInicio');

    // Toggle cuotas fijas/libres (checkbox estilo switch: tildado = libre)
    const dModoCuotas = document.getElementById('dModoCuotas');
    const dModoCuotasHint = document.getElementById('dModoCuotasHint');
    const gridPlanFijo = document.getElementById('gridPlanFijo');
    const dTotalLibrePreview = document.getElementById('dTotalLibrePreview');
    const deudasAbonosHistoricos = document.getElementById('deudasAbonosHistoricos');
    const deudasAbonosHistoricosWrap = document.getElementById('deudasAbonosHistoricosWrap');
    const btnAgregarAbonoHistorico = document.getElementById('btnAgregarAbonoHistorico');
    const deudasAbonosHistoricosTotal = document.getElementById('deudasAbonosHistoricosTotal');

    // Modal detalle
    const modalDetalle = document.getElementById('modalDetalle');
    const modalDetalleBackdrop = document.getElementById('modalDetalleBackdrop');
    const btnCerrarDetalle = document.getElementById('btnCerrarDetalle');
    const detalleResumen = document.getElementById('detalleResumen');
    const detNotas = document.getElementById('detNotas');
    const cuotasBody = document.getElementById('cuotasBody');
    const cuotasTitle = document.getElementById('cuotasTitle');
    const btnGuardarNotas = document.getElementById('btnGuardarNotas');
    const btnEliminarDeuda = document.getElementById('btnEliminarDeuda');
    const btnImprimirDeuda = document.getElementById('btnImprimirDeuda');
    const deudasDocumentos = document.getElementById('deudasDocumentos');
    const deudasRegistrarAbono = document.getElementById('deudasRegistrarAbono');
    const raMonto = document.getElementById('raMonto');
    const raFecha = document.getElementById('raFecha');
    const raCuenta = document.getElementById('raCuenta');
    const raMsg = document.getElementById('raMsg');
    const btnAbonar = document.getElementById('btnAbonar');
    const btnAbonarCheque = document.getElementById('btnAbonarCheque');

    // ── Toggle tipo compra_credito/prestamo/cheque ────────────────────
    function setTipo(tipo) {
        dTipo.value = tipo;
        botonesTipo.forEach(btn => {
            btn.classList.toggle('deudas-tipo-btn--active', btn.dataset.tipo === tipo);
        });
        // Cheque no necesita tarjeta ni cuenta de acreditación: cada
        // cuota se paga sola después, con cheque real o cuenta.
        campoTarjeta.hidden = tipo !== 'compra_credito';
        campoAcreditacion.hidden = tipo !== 'prestamo';
        poblarSelectsCuentas();
    }
    botonesTipo.forEach(btn => {
        btn.addEventListener('click', () => setTipo(btn.dataset.tipo));
    });

    function poblarSelectsCuentas(tarjetaPk, acreditacionPk) {
        poblarSelect(dCuentaTarjeta, cuentasPorMoneda(dMoneda.value, true), tarjetaPk);
        poblarSelect(dCuentaAcreditacion, cuentasPorMoneda(dMoneda.value, false), acreditacionPk);
    }
    dMoneda?.addEventListener('change', () => poblarSelectsCuentas());

    // ── Toggle cuotas fijas/libres ────────────────────────────────
    const HINT_FIJAS = 'Cuotas fijas: se reparte el total en N cuotas iguales con vencimiento mensual.';
    const HINT_LIBRE = 'Cuotas libres: no hay plan — se van registrando pagos de cualquier monto y fecha hasta cubrir el total.';

    function esModoLibre() {
        return dModoCuotas.checked;
    }

    function actualizarTotalLibrePreview() {
        if (!esModoLibre()) return;
        const monto = parseFloat(dMonto.value) || 0;
        const interes = parseFloat(dInteres.value) || 0;
        const total = monto * (1 + interes / 100);
        dTotalLibrePreview.textContent = `Total a pagar: ${fmtMoneda(total, dMoneda.value)}`;
    }

    function setModoCuotas(modo) {
        const libre = modo === 'libre';
        dModoCuotas.checked = libre;
        gridPlanFijo.hidden = libre;
        dTotalLibrePreview.hidden = !libre;
        dModoCuotasHint.textContent = libre ? HINT_LIBRE : HINT_FIJAS;
        if (libre) {
            actualizarTotalLibrePreview();
        }
        // Si "carga inicial" está tildado, cambiar de bloque de históricos.
        if (dCargaInicial.checked) {
            if (libre) {
                deudasCuotasHistoricas.hidden = true;
                deudasAbonosHistoricos.hidden = false;
                if (!deudasAbonosHistoricosWrap.children.length) agregarFilaAbonoHistorico();
            } else {
                deudasAbonosHistoricos.hidden = true;
                deudasCuotasHistoricas.hidden = false;
                actualizarPrevisualizacionCuotas();
            }
        }
    }
    dModoCuotas?.addEventListener('change', () => setModoCuotas(dModoCuotas.checked ? 'libre' : 'fijas'));

    // ── Carga inicial: previsualización de cuotas ya pagadas (fijas) /
    //    lista libre de abonos ya pagados (libre) ────────────────────
    let previsualizacionTimeout = null;

    function limpiarCuotasHistoricas() {
        deudasCuotasHistoricasBody.innerHTML = '';
        deudasCuotasHistoricas.hidden = true;
        deudasAbonosHistoricosWrap.innerHTML = '';
        deudasAbonosHistoricosTotal.textContent = '';
        deudasAbonosHistoricos.hidden = true;
    }

    dCargaInicial?.addEventListener('change', () => {
        if (dCargaInicial.checked) {
            if (esModoLibre()) {
                deudasAbonosHistoricos.hidden = false;
                if (!deudasAbonosHistoricosWrap.children.length) agregarFilaAbonoHistorico();
            } else {
                deudasCuotasHistoricas.hidden = false;
                actualizarPrevisualizacionCuotas();
            }
        } else {
            limpiarCuotasHistoricas();
        }
    });

    [dMonto, dInteres, dCuotas, dFechaInicio].forEach(el => {
        el?.addEventListener('input', () => {
            actualizarTotalLibrePreview();
            if (!dCargaInicial.checked || esModoLibre()) return;
            clearTimeout(previsualizacionTimeout);
            previsualizacionTimeout = setTimeout(actualizarPrevisualizacionCuotas, 400);
        });
    });

    // ── Cómo se pagó una cuota/abono histórico: cuenta real (informativa),
    //    cheque real (crea un Cheque es_historico=True) u otro (nota) ────
    function opcionesMedioPago() {
        const cuentas = cuentasPorMoneda(dMoneda.value, false);
        let html = '<option value="">— Sin especificar —</option>';
        html += cuentas.map(c => `<option value="cuenta:${c.pk}">${c.nombre}</option>`).join('');
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
                        ${chequeras.map(c => `<option value="${c.pk}">${c.nombre}</option>`).join('')}
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
        const contenedor = select.closest('tr, .deudas-abono-historico-fila');
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
                <td>${d.modo_cuotas === 'libre' ? `${d.cuotas_pagadas} abono${d.cuotas_pagadas === 1 ? '' : 's'}` : `${d.cuotas_pagadas}/${d.cantidad_cuotas}`}</td>
                <td><span class="deudas-badge-estado deudas-badge-estado--${d.estado}">${d.estado_display}</span></td>
                <td>
                    <div class="deudas-tabla-acciones">
                        <button type="button" class="btn btn-ghost btn--sm" onclick="verDeuda(${d.pk})">Ver cuotas</button>
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
    }

    function cerrarModal() {
        modalDeuda.hidden = true;
        document.body.style.overflow = '';
        formDeuda.reset();
        document.getElementById('dFechaInicio').value = today;
        setTipo('compra_credito');
        setModoCuotas('fijas');
        limpiarCuotasHistoricas();
    }

    btnNuevaDeuda?.addEventListener('click', () => {
        document.getElementById('dFechaInicio').value = today;
        setTipo('compra_credito');
        setModoCuotas('fijas');
        abrirModal();
    });

    btnCerrarModal.addEventListener('click', cerrarModal);
    btnCancelarModal.addEventListener('click', cerrarModal);
    modalBackdrop.addEventListener('click', cerrarModal);

    formDeuda.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData(formDeuda);
        const data = Object.fromEntries(formData.entries());
        data.cuotas_historicas = recolectarCuotasHistoricas();
        data.abonos_historicos = recolectarAbonosHistoricos();

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
    modalDetalleBackdrop.addEventListener('click', cerrarDetalle);

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
        // Cheque no tiene una cuenta propia asociada a la deuda (ni
        // tarjeta ni acreditación) — cada cuota se paga sola con un
        // cheque real o una cuenta, así que no hay nada que mostrar acá.
        const tieneCuentaPropia = d.tipo !== 'cheque';
        const cuentaLabel = d.tipo === 'compra_credito' ? 'Tarjeta' : 'Cuenta acreditada';
        const cuentaValor = d.tipo === 'compra_credito'
            ? (d.cuenta_tarjeta_nombre || '-')
            : (d.cuenta_acreditacion_nombre || '-');
        // "Ya se empezó a pagar" cuenta también las cuotas históricas —
        // una vez que hay algo confirmado (real o de carga inicial), el
        // monto/interés/cuotas/fecha/cuenta quedan fijos: cambiarlos
        // desalinearía lo que ya se registró e imprimió.
        const hayPagos = d.cuotas.some(c => c.estado === 'confirmada');
        const puedeEditarPlan = puedeEditar && !hayPagos;

        const cuentaEditable = (puedeEditarPlan && tieneCuentaPropia)
            ? cuentasPorMoneda(d.moneda, d.tipo === 'compra_credito') : [];
        const cuentaActualPk = d.tipo === 'compra_credito' ? d.cuenta_tarjeta_pk : d.cuenta_acreditacion_pk;

        const item = (label, valor, wide, highlight) => `<div class="deudas-resumen-item${wide ? ' deudas-resumen-item--wide' : ''}${highlight ? ' deudas-resumen-item--highlight' : ''}"><span class="deudas-resumen-label">${label}</span><div class="deudas-resumen-value">${valor}</div></div>`;

        detalleResumen.innerHTML = `
            <div class="deudas-resumen-grid">
                ${item('Tipo', d.tipo_display)}
                ${item('Descripción', puedeEditar
                    ? `<input type="text" id="detDescripcion" value="${_deudaEscInput(d.descripcion)}">`
                    : (d.descripcion || d.compra_numero || '-'), true)}
                ${item('N° de comprobante', puedeEditar
                    ? `<input type="text" id="detNumeroComprobante" placeholder="Opcional" value="${_deudaEscInput(d.numero_comprobante)}">`
                    : (d.numero_comprobante || '-'))}
                ${tieneCuentaPropia ? item(cuentaLabel, puedeEditarPlan
                    ? `<select id="detCuenta">${cuentaEditable.map(c => `<option value="${c.pk}" ${c.pk === cuentaActualPk ? 'selected' : ''}>${c.nombre}</option>`).join('')}</select>`
                    : cuentaValor) : ''}
                ${item('Moneda', puedeEditarPlan
                    ? `<select id="detMoneda">${dMoneda.innerHTML}</select>`
                    : d.moneda)}
                ${item('Monto original', puedeEditarPlan
                    ? `<input type="number" id="detMonto" step="0.01" min="0.01" value="${d.monto_original}">`
                    : fmtMoneda(d.monto_original, d.moneda))}
                ${item('Interés %', puedeEditarPlan
                    ? `<input type="number" id="detInteres" step="0.01" min="0" value="${d.porcentaje_interes}">`
                    : `${d.porcentaje_interes}%`)}
                ${d.modo_cuotas === 'libre' ? '' : `
                ${item('Cantidad de cuotas', puedeEditarPlan
                    ? `<input type="number" id="detCantidadCuotas" step="1" min="1" value="${d.cantidad_cuotas}">`
                    : `${d.cuotas_pagadas}/${d.cantidad_cuotas}`)}
                ${item('Inicio de débito', puedeEditarPlan
                    ? `<input type="date" id="detFechaInicio" value="${d.fecha_inicio}">`
                    : d.fecha_inicio)}`}
                ${item('Monto total', fmtMoneda(d.monto_total, d.moneda))}
                ${item('Saldo pendiente', fmtMoneda(d.saldo_pendiente, d.moneda), false, true)}
                ${item('Estado', `<span class="deudas-badge-estado deudas-badge-estado--${d.estado}">${d.estado_display}</span>${d.es_carga_inicial ? ` <span class="deudas-badge-carga-inicial">Carga inicial</span>` : ''}`)}
            </div>
            ${hayPagos && puedeEditar ? `<p class="deudas-edicion-nota">Esta deuda ya tiene cuotas confirmadas — el monto, interés, cantidad de cuotas, fecha de inicio, moneda y cuenta ya no se pueden editar.</p>` : ''}
        `;

        detNotas.value = d.notas || '';
        detNotas.disabled = !puedeEditar;
        if (btnGuardarNotas) btnGuardarNotas.disabled = !puedeEditar;
        // Se puede eliminar aunque ya tenga cuotas pagadas (reales o
        // históricas) — el aviso fuerte de qué implica eso va en el
        // confirm al hacer click, no acá.

        if (typeof renderizarDocumentosDeuda === 'function') renderizarDocumentosDeuda(d);

        if (cuotasTitle) cuotasTitle.textContent = d.modo_cuotas === 'libre' ? 'Abonos' : 'Cuotas';

        const saldoPendienteNum = parseFloat(d.saldo_pendiente) || 0;
        const mostrarRegistrarAbono = d.modo_cuotas === 'libre' && d.estado === 'activa'
            && saldoPendienteNum > 0 && puedeConfirmar;
        // Cheque no admite ningún otro medio de pago — ni cuenta propia
        // en la cuota, ni el "Pagar" directo del abono libre. Es la
        // única diferencia real con crédito/préstamo.
        const soloCheque = d.tipo === 'cheque';

        if (deudasRegistrarAbono) {
            deudasRegistrarAbono.hidden = !mostrarRegistrarAbono;
            if (mostrarRegistrarAbono) {
                raMonto.value = d.saldo_pendiente;
                raMonto.max = d.saldo_pendiente;
                raFecha.value = today;
                raFecha.max = today;
                const campoCuentaAbono = raCuenta.closest('.form-campo');
                if (campoCuentaAbono) campoCuentaAbono.hidden = soloCheque;
                if (btnAbonar) btnAbonar.hidden = soloCheque;
                if (!soloCheque) poblarSelect(raCuenta, cuentasPorMoneda(d.moneda, false));
                raMsg.textContent = '';
            }
        }

        const cuentasPago = soloCheque ? [] : cuentasPorMoneda(d.moneda, false);

        cuotasBody.innerHTML = d.cuotas.map(c => {
            let accion = '-';
            if (c.estado === 'pendiente' && puedeConfirmar && c.habilitada) {
                accion = soloCheque
                    ? `<button type="button" class="btn btn-primary btn--sm" onclick="abrirModalChequeCuota(${c.pk}, ${c.monto}, '${d.moneda}', false)">Pagar con cheque</button>`
                    : `
                    <div class="deudas-cuota-confirmar">
                        <select id="cuentaCuota${c.pk}" class="deudas-cuota-select"
                                onchange="onCuentaCuotaChange(this, ${c.pk}, ${c.monto}, '${d.moneda}', false)">
                            ${cuentasPago.map(cta => `<option value="${cta.pk}">${cta.nombre}</option>`).join('')}
                            <option value="__cheque__">— Pagar con cheque —</option>
                        </select>
                        <button type="button" class="btn btn-primary btn--sm" onclick="confirmarCuota(${c.pk})">Confirmar</button>
                    </div>`;
            } else if (c.estado === 'pendiente' && !c.habilitada && puedeConfirmar) {
                accion = soloCheque
                    ? `
                    <div class="deudas-cuota-confirmar">
                        <button type="button" class="btn btn-secondary btn--sm" onclick="abrirModalChequeCuota(${c.pk}, ${c.monto}, '${d.moneda}', true)">Adelantar pago con cheque</button>
                        <span class="deudas-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>
                    </div>`
                    : `
                    <div class="deudas-cuota-confirmar">
                        <select id="cuentaCuota${c.pk}" class="deudas-cuota-select"
                                onchange="onCuentaCuotaChange(this, ${c.pk}, ${c.monto}, '${d.moneda}', true)">
                            ${cuentasPago.map(cta => `<option value="${cta.pk}">${cta.nombre}</option>`).join('')}
                            <option value="__cheque__">— Pagar con cheque —</option>
                        </select>
                        <button type="button" class="btn btn-secondary btn--sm" onclick="confirmarCuota(${c.pk}, true)">Adelantar pago</button>
                        <span class="deudas-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>
                    </div>`;
            } else if (c.estado === 'pendiente' && !c.habilitada) {
                accion = `<span class="deudas-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>`;
            } else if (c.estado === 'confirmada' && c.es_historica) {
                let detallePago = '';
                if (c.cheque_pk && c.cheque_es_historico) {
                    detallePago = `Cheque #${c.cheque_numero}`;
                } else if (c.cuenta_pago_historica_nombre) {
                    detallePago = _deudaEscInput(c.cuenta_pago_historica_nombre);
                } else if (c.medio_pago_historico) {
                    detallePago = _deudaEscInput(c.medio_pago_historico);
                }
                accion = `<span class="deudas-badge-carga-inicial">Carga inicial (no afectó caja)</span>` +
                    (detallePago ? ` <span class="deudas-cuota-fecha">${detallePago}</span>` : '') +
                    ` <span class="deudas-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            } else if (c.estado === 'confirmada' && c.cheque_pk) {
                accion = `Cheque #${c.cheque_numero} (${c.cheque_estado}) <span class="deudas-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            } else if (c.estado === 'confirmada') {
                accion = `${c.cuenta_pago_nombre} <span class="deudas-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            }
            return `
                <tr>
                    <td>${c.numero}</td>
                    <td>${c.fecha_vencimiento}</td>
                    <td class="deudas-monto">${fmtMoneda(c.monto, d.moneda)}</td>
                    <td><span class="deudas-badge-estado deudas-badge-estado--${c.estado === 'confirmada' ? 'activa' : c.estado === 'anulada' ? 'anulada' : 'pendiente'}">${c.estado}</span></td>
                    <td>${accion}</td>
                </tr>`;
        }).join('');
    }

    window.confirmarCuota = async function (cuotaPk, adelantar = false) {
        const select = document.getElementById(`cuentaCuota${cuotaPk}`);
        const cuentaPk = select ? select.value : '';
        if (!cuentaPk) {
            KaiToast.show('Elegí la cuenta de la que sale el pago.', 'warning');
            return;
        }
        const mensaje = adelantar
            ? '¿Adelantar el pago de esta cuota antes de su fecha habilitada? Esto va a impactar la caja.'
            : '¿Confirmar el pago de esta cuota? Esto va a impactar la caja.';
        if (!await KaiConfirm(mensaje)) return;

        try {
            const response = await fetch(urlConfirmarCuota(cuotaPk), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ cuenta_pk: cuentaPk, adelantar }),
            });
            const result = await response.json();

            if (result.success) {
                window.verDeuda(deudaDetalleActual.pk);
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'Error al confirmar la cuota', 'danger');
            }
        } catch (error) {
            console.error('Error al confirmar cuota:', error);
            KaiToast.show('Error al confirmar la cuota', 'danger');
        }
    };

    // ── Modal "Pagar cuota con cheque" ───────────────────────────────
    const modalChequeCuota = document.getElementById('modalChequeCuota');
    const modalChequeCuotaBackdrop = document.getElementById('modalChequeCuotaBackdrop');
    const btnCerrarChequeCuota = document.getElementById('btnCerrarChequeCuota');
    const btnCancelarChequeCuota = document.getElementById('btnCancelarChequeCuota');
    const btnGuardarChequeCuota = document.getElementById('btnGuardarChequeCuota');
    let chequeCuotaActual = null; // { modoAbono, cuotaPk, adelantar, monto } | { modoAbono: true, deudaPk, monto, fecha }

    // Elegir "— Pagar con cheque —" en el select de cuenta abre el modal
    // directo, en vez de un botón aparte (que no entraba en la fila sin
    // hacer scroll horizontal). El select vuelve a su valor por defecto
    // así no queda pareciendo elegida una cuenta que no existe.
    window.onCuentaCuotaChange = function (select, cuotaPk, monto, moneda, adelantar) {
        if (select.value === '__cheque__') {
            select.value = '';
            abrirModalChequeCuota(cuotaPk, monto, moneda, adelantar);
        }
    };

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
            chequeras.map(c => `<option value="${c.pk}">${c.nombre}</option>`).join('');
        const financiadoras = CUENTAS.filter(c => c.moneda === moneda && !c.es_credito);
        financiadoraSelect.innerHTML = '<option value="">— No hace falta, ya tiene fondos —</option>' +
            financiadoras.map(c => `<option value="${c.pk}">${c.nombre}</option>`).join('');

        modalChequeCuota.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    window.abrirModalChequeCuota = function (cuotaPk, monto, moneda, adelantar) {
        chequeCuotaActual = { modoAbono: false, cuotaPk, adelantar, monto };
        _prepararModalChequeComun(monto, moneda);
    };

    function abrirModalChequeAbono(monto, moneda, fecha) {
        chequeCuotaActual = { modoAbono: true, deudaPk: deudaDetalleActual.pk, monto, fecha };
        _prepararModalChequeComun(monto, moneda);
    }

    function cerrarModalChequeCuota() {
        modalChequeCuota.hidden = true;
        document.body.style.overflow = '';
        chequeCuotaActual = null;
    }
    btnCerrarChequeCuota.addEventListener('click', cerrarModalChequeCuota);
    btnCancelarChequeCuota.addEventListener('click', cerrarModalChequeCuota);
    modalChequeCuotaBackdrop.addEventListener('click', cerrarModalChequeCuota);

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

    // ── Registrar abono (modo_cuotas=libre) ──────────────────────────
    btnAbonar?.addEventListener('click', async () => {
        if (!deudaDetalleActual) return;
        raMsg.textContent = '';
        const monto = parseFloat(raMonto.value);
        const fecha = raFecha.value;
        const cuentaPk = raCuenta.value;
        if (!monto || monto <= 0) { raMsg.textContent = 'Indicá el monto a abonar.'; return; }
        if (!cuentaPk) { raMsg.textContent = 'Elegí la cuenta de la que sale el pago.'; return; }

        if (!await KaiConfirm('¿Confirmar este abono? Esto va a impactar la caja.')) return;

        btnAbonar.disabled = true;
        try {
            const response = await fetch(urlRegistrarAbono(deudaDetalleActual.pk), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ monto, fecha, cuenta_pk: cuentaPk }),
            });
            const result = await response.json();
            if (result.success) {
                window.verDeuda(deudaDetalleActual.pk);
                cargarDeudas();
            } else {
                raMsg.textContent = result.error || 'Error al registrar el abono.';
            }
        } catch (error) {
            console.error('Error al registrar abono:', error);
            raMsg.textContent = 'Error al registrar el abono.';
        } finally {
            btnAbonar.disabled = false;
        }
    });

    btnAbonarCheque?.addEventListener('click', () => {
        if (!deudaDetalleActual) return;
        raMsg.textContent = '';
        const monto = parseFloat(raMonto.value);
        const fecha = raFecha.value;
        if (!monto || monto <= 0) { raMsg.textContent = 'Indicá el monto a abonar.'; return; }
        abrirModalChequeAbono(monto, deudaDetalleActual.moneda, fecha);
    });

    btnGuardarNotas?.addEventListener('click', async () => {
        if (!deudaDetalleActual) return;

        const payload = { notas: detNotas.value };
        const detDescripcion = document.getElementById('detDescripcion');
        const detNumeroComprobante = document.getElementById('detNumeroComprobante');
        if (detDescripcion) payload.descripcion = detDescripcion.value;
        if (detNumeroComprobante) payload.numero_comprobante = detNumeroComprobante.value;

        // Estos campos solo existen en el DOM si todavía no hay cuotas
        // confirmadas (ver renderizarDetalle) — si no están, no se tocan.
        const detCuenta = document.getElementById('detCuenta');
        const detMoneda = document.getElementById('detMoneda');
        const detMonto = document.getElementById('detMonto');
        const detInteres = document.getElementById('detInteres');
        const detCantidadCuotas = document.getElementById('detCantidadCuotas');
        const detFechaInicio = document.getElementById('detFechaInicio');
        if (detMonto) payload.monto_original = detMonto.value;
        if (detInteres) payload.porcentaje_interes = detInteres.value;
        if (detCantidadCuotas) payload.cantidad_cuotas = detCantidadCuotas.value;
        if (detFechaInicio) payload.fecha_inicio = detFechaInicio.value;
        if (detMoneda) payload.moneda = detMoneda.value;
        if (detCuenta) {
            if (deudaDetalleActual.tipo === 'compra_credito') payload.cuenta_tarjeta_pk = detCuenta.value;
            else payload.cuenta_acreditacion_pk = detCuenta.value;
        }

        try {
            const response = await fetch(`${urlEditarBase}${deudaDetalleActual.pk}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify(payload),
            });
            const result = await response.json();
            if (result.success) {
                KaiToast.show('Cambios guardados.', 'success');
                deudaDetalleActual = result.deuda;
                renderizarDetalle(result.deuda);
                cargarDeudas();
            } else {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar cambios:', error);
            KaiToast.show('Error al guardar cambios', 'danger');
        }
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
});
