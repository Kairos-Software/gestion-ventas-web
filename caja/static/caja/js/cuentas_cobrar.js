document.addEventListener('DOMContentLoaded', function () {
    const urls = window.cxcUrls;
    const today = window.cxcToday;
    const puedeConfirmar = window.cxcPuedeConfirmar;
    const puedeEditar = window.cxcPuedeEditar;

    // ── Cuentas (para los selects, filtradas por moneda) ──
    const cuentasDataEl = document.getElementById('cuentas-data');
    const CUENTAS = cuentasDataEl ? JSON.parse(cuentasDataEl.textContent) : [];

    function cuentasPorMoneda(moneda) {
        return CUENTAS.filter(c => c.moneda === moneda);
    }

    // pk de la cuenta principal del negocio si está dentro de `lista`
    // (Configuración → Cuentas de caja). Sirve para preseleccionarla en
    // los selects sin obligar a elegirla. '' si no aplica.
    function cuentaPrincipalEn(lista) {
        const p = (lista || CUENTAS).find(c => c.preferida);
        return p ? String(p.pk) : '';
    }

    // Depositar un cheque histórico (informativo) solo tiene sentido en una
    // cuenta bancaria real — mismo criterio que en Deudas/Cheques.
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

    function urlRegistrarAbono(cxcPk) {
        return urls.registrarAbono.replace('/0/', `/${cxcPk}/`);
    }

    function urlEditarComprobanteCuota(cuotaPk) {
        return urls.editarComprobanteCuota.replace('/0/', `/${cuotaPk}/`);
    }

    let paginaActual = 1;
    let porPagina = 50;
    let cxcDetalleActual = null;

    // ── Elementos DOM ───────────────────────────────────────────────
    const btnNuevaCxc = document.getElementById('btnNuevaCxc');
    const btnToggleFiltros = document.getElementById('btnToggleFiltros');
    const formFiltros = document.getElementById('formFiltros');
    const btnLimpiarFiltros = document.getElementById('btnLimpiarFiltros');
    const cxcBody = document.getElementById('cxcBody');
    const paginacionContainer = document.getElementById('paginacionContainer');
    const cxcTotales = document.getElementById('cxcTotales');

    // Modal alta
    const modalCxc = document.getElementById('modalCxc');
    const modalBackdrop = document.getElementById('modalBackdrop');
    const btnCerrarModal = document.getElementById('btnCerrarModal');
    const btnCancelarModal = document.getElementById('btnCancelarModal');
    const formCxc = document.getElementById('formCxc');
    const btnGuardarCxc = document.getElementById('btnGuardarCxc');
    const cMoneda = document.getElementById('cMoneda');
    const cCargaInicial = document.getElementById('cCargaInicial');
    const cxcCuotasHistoricas = document.getElementById('cxcCuotasHistoricas');
    const cxcCuotasHistoricasBody = document.getElementById('cxcCuotasHistoricasBody');
    const cMonto = document.getElementById('cMonto');
    const cInteres = document.getElementById('cInteres');
    const cCuotas = document.getElementById('cCuotas');
    const cFechaInicio = document.getElementById('cFechaInicio');

    // Buscador de cliente
    const cClienteBusqueda = document.getElementById('cClienteBusqueda');
    const cClientePk = document.getElementById('cClientePk');
    const cClienteResultados = document.getElementById('cClienteResultados');
    const cClienteSeleccionado = document.getElementById('cClienteSeleccionado');

    // Toggle cuotas fijas/libres (checkbox estilo switch: tildado = libre)
    const cModoCuotas = document.getElementById('cModoCuotas');
    const cModoCuotasHint = document.getElementById('cModoCuotasHint');
    const gridPlanFijo = document.getElementById('gridPlanFijo');
    const cTotalLibrePreview = document.getElementById('cTotalLibrePreview');
    const cxcAbonosHistoricos = document.getElementById('cxcAbonosHistoricos');
    const cxcAbonosHistoricosWrap = document.getElementById('cxcAbonosHistoricosWrap');
    const btnAgregarAbonoHistorico = document.getElementById('btnAgregarAbonoHistorico');
    const cxcAbonosHistoricosTotal = document.getElementById('cxcAbonosHistoricosTotal');

    // Modal detalle
    const modalDetalle = document.getElementById('modalDetalle');
    const modalDetalleBackdrop = document.getElementById('modalDetalleBackdrop');
    const btnCerrarDetalle = document.getElementById('btnCerrarDetalle');
    const detalleResumen = document.getElementById('detalleResumen');
    const detNotas = document.getElementById('detNotas');
    const cuotasBody = document.getElementById('cuotasBody');
    const cuotasTitle = document.getElementById('cuotasTitle');
    const btnGuardarNotas = document.getElementById('btnGuardarNotas');
    const btnEliminarCxc = document.getElementById('btnEliminarCxc');
    const btnImprimirCxc = document.getElementById('btnImprimirCxc');
    const cxcRegistrarAbono = document.getElementById('cxcRegistrarAbono');
    const raMonto = document.getElementById('raMonto');
    const raFecha = document.getElementById('raFecha');
    const raCuenta = document.getElementById('raCuenta');
    const raComprobante = document.getElementById('raComprobante');
    const raMsg = document.getElementById('raMsg');
    const btnAbonar = document.getElementById('btnAbonar');
    const btnAbonarCheque = document.getElementById('btnAbonarCheque');

    // ── Buscador de cliente ───────────────────────────────────────
    let clienteBusquedaTimeout = null;

    function seleccionarCliente(cliente) {
        cClientePk.value = cliente.pk;
        cClienteBusqueda.value = '';
        cClienteResultados.hidden = true;
        cClienteResultados.innerHTML = '';
        cClienteSeleccionado.hidden = false;
        cClienteSeleccionado.innerHTML = `<strong>${_cxcEscInput(cliente.nombre)}</strong>
            <button type="button" class="cxc-cliente-cambiar" id="btnCambiarCliente">Cambiar</button>`;
        document.getElementById('btnCambiarCliente').addEventListener('click', limpiarClienteSeleccionado);
        cClienteBusqueda.hidden = true;
    }

    function limpiarClienteSeleccionado() {
        cClientePk.value = '';
        cClienteSeleccionado.hidden = true;
        cClienteSeleccionado.innerHTML = '';
        cClienteBusqueda.hidden = false;
        cClienteBusqueda.value = '';
        cClienteBusqueda.focus();
    }

    cClienteBusqueda?.addEventListener('input', () => {
        clearTimeout(clienteBusquedaTimeout);
        const q = cClienteBusqueda.value.trim();
        if (q.length < 2) {
            cClienteResultados.hidden = true;
            cClienteResultados.innerHTML = '';
            return;
        }
        clienteBusquedaTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`${urls.buscarCliente}?q=${encodeURIComponent(q)}`);
                const data = await response.json();
                const resultados = data.results || [];
                if (!resultados.length) {
                    cClienteResultados.hidden = false;
                    cClienteResultados.innerHTML = '<div class="cxc-cliente-resultado-item">Sin resultados.</div>';
                    return;
                }
                cClienteResultados.hidden = false;
                cClienteResultados.innerHTML = resultados.map(c => `
                    <div class="cxc-cliente-resultado-item" data-pk="${c.pk}" data-nombre="${_cxcEscInput(c.nombre)}">
                        <span>${_cxcEscInput(c.nombre)}</span><span>${_cxcEscInput(c.doc || c.codigo || '')}</span>
                    </div>`).join('');
                cClienteResultados.querySelectorAll('.cxc-cliente-resultado-item[data-pk]').forEach(item => {
                    item.addEventListener('click', () => {
                        seleccionarCliente({ pk: item.dataset.pk, nombre: item.dataset.nombre });
                    });
                });
            } catch (error) {
                console.error('Error al buscar cliente:', error);
            }
        }, 300);
    });

    document.addEventListener('click', (e) => {
        if (cClienteResultados && !cClienteResultados.hidden &&
            !cClienteResultados.contains(e.target) && e.target !== cClienteBusqueda) {
            cClienteResultados.hidden = true;
        }
    });

    // ── Toggle cuotas fijas/libres ────────────────────────────────
    const HINT_FIJAS = 'Cuotas fijas: se reparte el total en N cuotas iguales con vencimiento mensual.';
    const HINT_LIBRE = 'Cuotas libres: no hay plan — se van registrando cobros de cualquier monto y fecha hasta cubrir el total.';

    function esModoLibre() {
        return cModoCuotas.checked;
    }

    function actualizarTotalLibrePreview() {
        if (!esModoLibre()) return;
        const monto = parseFloat(cMonto.value) || 0;
        const interes = parseFloat(cInteres.value) || 0;
        const total = monto * (1 + interes / 100);
        cTotalLibrePreview.textContent = `Total a cobrar: ${fmtMoneda(total, cMoneda.value)}`;
    }

    function setModoCuotas(modo) {
        const libre = modo === 'libre';
        cModoCuotas.checked = libre;
        gridPlanFijo.hidden = libre;
        cTotalLibrePreview.hidden = !libre;
        cModoCuotasHint.textContent = libre ? HINT_LIBRE : HINT_FIJAS;
        if (libre) {
            actualizarTotalLibrePreview();
        }
        // Si "carga inicial" está tildado, cambiar de bloque de históricos.
        if (cCargaInicial.checked) {
            if (libre) {
                cxcCuotasHistoricas.hidden = true;
                cxcAbonosHistoricos.hidden = false;
                if (!cxcAbonosHistoricosWrap.children.length) agregarFilaAbonoHistorico();
            } else {
                cxcAbonosHistoricos.hidden = true;
                cxcCuotasHistoricas.hidden = false;
                actualizarPrevisualizacionCuotas();
            }
        }
    }
    cModoCuotas?.addEventListener('change', () => setModoCuotas(cModoCuotas.checked ? 'libre' : 'fijas'));

    // ── Carga inicial: previsualización de cuotas ya cobradas (fijas) /
    //    lista libre de abonos ya cobrados (libre) ────────────────────
    let previsualizacionTimeout = null;

    function limpiarCuotasHistoricas() {
        cxcCuotasHistoricasBody.innerHTML = '';
        cxcCuotasHistoricas.hidden = true;
        cxcAbonosHistoricosWrap.innerHTML = '';
        cxcAbonosHistoricosTotal.textContent = '';
        cxcAbonosHistoricos.hidden = true;
    }

    cCargaInicial?.addEventListener('change', () => {
        if (cCargaInicial.checked) {
            if (esModoLibre()) {
                cxcAbonosHistoricos.hidden = false;
                if (!cxcAbonosHistoricosWrap.children.length) agregarFilaAbonoHistorico();
            } else {
                cxcCuotasHistoricas.hidden = false;
                actualizarPrevisualizacionCuotas();
            }
        } else {
            limpiarCuotasHistoricas();
        }
    });

    [cMonto, cInteres, cCuotas, cFechaInicio].forEach(el => {
        el?.addEventListener('input', () => {
            actualizarTotalLibrePreview();
            if (!cCargaInicial.checked || esModoLibre()) return;
            clearTimeout(previsualizacionTimeout);
            previsualizacionTimeout = setTimeout(actualizarPrevisualizacionCuotas, 400);
        });
    });

    // ── Cómo se cobró una cuota/abono histórico: cuenta real (informativa),
    //    cheque real (crea un Cheque es_historico=True A_COBRAR) u otro (nota) ──
    function opcionesMedioPago() {
        const cuentas = cuentasPorMoneda(cMoneda.value);
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
            const bancos = cuentasBancariasPorMoneda(cMoneda.value);
            return `
                <div class="ph-cheque-campos">
                    <input type="text" class="ph-cheque-numero" placeholder="N° cheque">
                    <select class="ph-cheque-cuenta">
                        <option value="">— Depositado en (opcional) —</option>
                        ${bancos.map(c => `<option value="${c.pk}">${c.nombre}${c.titular ? ' · ' + c.titular : ''}</option>`).join('')}
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
        const contenedor = select.closest('tr, .cxc-abono-historico-fila');
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
                cuenta_destino_pk: contenedor.querySelector('.ph-cheque-cuenta')?.value || '',
                fecha_emision: contenedor.querySelector('.ph-cheque-emision')?.value || '',
                banco: contenedor.querySelector('.ph-cheque-banco')?.value || '',
            };
        } else if (medio === 'otro') {
            resultado.medio_pago = contenedor.querySelector('.ph-nota')?.value || '';
        }
        return resultado;
    }

    // ── Carga inicial (modo libre): filas de abono ya cobrado ────────
    function agregarFilaAbonoHistorico() {
        const fila = document.createElement('div');
        fila.className = 'cxc-abono-historico-fila';
        fila.innerHTML = `
            <div class="cxc-abono-historico-fila-linea">
                <input type="number" class="dah-monto" step="0.01" min="0.01" placeholder="Monto">
                <input type="date" class="dah-fecha" value="${today}" max="${today}">
                <select class="ph-medio" onchange="onPhMedioChange(this)">${opcionesMedioPago()}</select>
                <button type="button" class="cxc-abono-historico-quitar" aria-label="Quitar">&times;</button>
            </div>
            <div class="ph-detalle"></div>
        `;
        fila.querySelector('.dah-monto').addEventListener('input', actualizarTotalAbonosHistoricos);
        fila.querySelector('.cxc-abono-historico-quitar').addEventListener('click', () => {
            fila.remove();
            actualizarTotalAbonosHistoricos();
        });
        cxcAbonosHistoricosWrap.appendChild(fila);
    }
    btnAgregarAbonoHistorico?.addEventListener('click', agregarFilaAbonoHistorico);

    function actualizarTotalAbonosHistoricos() {
        const montos = Array.from(cxcAbonosHistoricosWrap.querySelectorAll('.dah-monto'))
            .map(inp => parseFloat(inp.value) || 0);
        const totalAbonado = montos.reduce((a, b) => a + b, 0);
        const monto = parseFloat(cMonto.value) || 0;
        const interes = parseFloat(cInteres.value) || 0;
        const totalCuenta = monto * (1 + interes / 100);
        const excede = totalAbonado > totalCuenta + 0.01;
        cxcAbonosHistoricosTotal.textContent =
            `Total ya cobrado: ${fmtMoneda(totalAbonado, cMoneda.value)} de ${fmtMoneda(totalCuenta, cMoneda.value)}`;
        cxcAbonosHistoricosTotal.style.color = excede ? '#dc2626' : '';
    }

    function recolectarAbonosHistoricos() {
        if (!cCargaInicial.checked || !esModoLibre()) return [];
        return Array.from(cxcAbonosHistoricosWrap.querySelectorAll('.cxc-abono-historico-fila'))
            .map(fila => ({
                monto: fila.querySelector('.dah-monto').value,
                fecha_pago: fila.querySelector('.dah-fecha').value,
                ...recolectarPagoHistorico(fila),
            }))
            .filter(ab => parseFloat(ab.monto) > 0 && ab.fecha_pago);
    }

    async function actualizarPrevisualizacionCuotas() {
        const monto = parseFloat(cMonto.value);
        const cantidadCuotas = parseInt(cCuotas.value, 10);
        const fechaInicio = cFechaInicio.value;
        if (!monto || monto <= 0 || !cantidadCuotas || cantidadCuotas < 1 || !fechaInicio) {
            cxcCuotasHistoricasBody.innerHTML = '<tr><td colspan="7" class="cxc-tabla-loading">Completá monto, cuotas y fecha de inicio para ver el plan.</td></tr>';
            return;
        }

        try {
            const response = await fetch(urls.previsualizarCuotas, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    monto_original: cMonto.value,
                    porcentaje_interes: cInteres.value || 0,
                    cantidad_cuotas: cCuotas.value,
                    fecha_inicio: fechaInicio,
                }),
            });
            const data = await response.json();
            if (!data.cuotas) {
                cxcCuotasHistoricasBody.innerHTML = `<tr><td colspan="7" class="cxc-tabla-loading">${data.error || 'No se pudo calcular el plan de cuotas.'}</td></tr>`;
                return;
            }
            cxcCuotasHistoricasBody.innerHTML = data.cuotas.map(c => `
                <tr>
                    <td>${c.numero}</td>
                    <td>${c.fecha_vencimiento}</td>
                    <td class="cxc-monto">${fmtMoneda(c.monto, cMoneda.value)}</td>
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
        if (!cCargaInicial.checked || esModoLibre()) return [];
        return Array.from(cxcCuotasHistoricasBody.querySelectorAll('.dch-pagada:checked')).map(chk => {
            const fila = chk.closest('tr');
            return {
                numero: parseInt(chk.dataset.numero, 10),
                fecha_pago: fila.querySelector('.dch-fecha').value,
                ...recolectarPagoHistorico(fila),
            };
        });
    }

    // ── Cargar cuentas por cobrar ─────────────────────────────────
    async function cargarCxc() {
        const params = new URLSearchParams({
            pagina: paginaActual,
            por_pagina: porPagina,
            ...getFiltrosActivos(),
        });

        try {
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();

            renderizarCxc(data.results);
            renderizarPaginacion(data.total, data.pagina, data.por_pagina);
            renderizarTotales(data.totales_pendientes);
        } catch (error) {
            console.error('Error al cargar cuentas por cobrar:', error);
            cxcBody.innerHTML = '<tr><td colspan="8" class="cxc-tabla-loading">Error al cargar</td></tr>';
        }
    }

    function getFiltrosActivos() {
        const estado = document.getElementById('fEstado').value;
        const moneda = document.getElementById('fMoneda').value;
        const q = document.getElementById('fQ').value;

        const filtros = {};
        if (estado) filtros.estado = estado;
        if (moneda) filtros.moneda = moneda;
        if (q) filtros.q = q;

        return filtros;
    }

    function fmtMoneda(v, moneda) {
        return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${moneda || ''}`.trim();
    }

    function _cxcEscInput(str) {
        return String(str == null ? '' : str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    function renderizarCxc(items) {
        if (!items || items.length === 0) {
            cxcBody.innerHTML = '<tr><td colspan="8" class="cxc-tabla-loading">No hay cuentas por cobrar registradas</td></tr>';
            return;
        }

        cxcBody.innerHTML = items.map(c => `
            <tr>
                <td>${c.cliente_nombre || '-'}</td>
                <td>${c.venta_numero || c.descripcion || '-'}</td>
                <td>${c.numero_comprobante || '-'}</td>
                <td class="cxc-monto">${fmtMoneda(c.monto_total, c.moneda)}</td>
                <td class="cxc-monto">${fmtMoneda(c.saldo_pendiente, c.moneda)}</td>
                <td>${c.modo_cuotas === 'libre' ? `${c.cuotas_cobradas} abono${c.cuotas_cobradas === 1 ? '' : 's'}` : `${c.cuotas_cobradas}/${c.cantidad_cuotas}`}</td>
                <td><span class="cxc-badge-estado cxc-badge-estado--${c.estado}">${c.estado_display}</span></td>
                <td>
                    <div class="cxc-tabla-acciones">
                        <button type="button" class="btn btn-ghost btn--sm" onclick="verCxc(${c.pk})">Ver cuotas</button>
                        <button type="button" class="btn btn-ghost btn--sm btn--icon" onclick="imprimirCxcDesdeLista(${c.pk})" title="Imprimir" aria-label="Imprimir">
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
        if (!cxcTotales) return;
        const entradas = Object.entries(totalesPendientes || {});
        const filtros = getFiltrosActivos();
        const hayFiltros = Object.keys(filtros).length > 0;
        const etiqueta = hayFiltros ? 'Total filtrado' : 'Te deben en total';
        if (entradas.length === 0) {
            cxcTotales.innerHTML = `
                <div class="cxc-total-card cxc-total-card--zero">
                    <span class="cxc-total-label">${etiqueta}</span>
                    <span class="cxc-total-monto">${fmtMoneda(0, filtros.moneda || '')}</span>
                </div>`;
            return;
        }
        cxcTotales.innerHTML = entradas.map(([moneda, total]) => `
            <div class="cxc-total-card">
                <span class="cxc-total-label">${etiqueta}</span>
                <span class="cxc-total-monto">${fmtMoneda(total, moneda)}</span>
            </div>
        `).join('');
    }

    function renderizarPaginacion(total, pagina, porPagina) {
        const totalPaginas = Math.ceil(total / porPagina);

        if (totalPaginas <= 1) {
            paginacionContainer.innerHTML = '';
            return;
        }

        let html = '<span class="cxc-paginacion-info">Página ' + pagina + ' de ' + totalPaginas + ' (' + total + ' registros)</span>';
        html += '<div class="cxc-paginacion-botones">';
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
        cargarCxc();
    };

    // ── Modal alta ────────────────────────────────────────────────
    function abrirModal() {
        modalCxc.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function cerrarModal() {
        modalCxc.hidden = true;
        document.body.style.overflow = '';
        formCxc.reset();
        cFechaInicio.value = today;
        setModoCuotas('fijas');
        limpiarCuotasHistoricas();
        limpiarClienteSeleccionado();
    }

    btnNuevaCxc?.addEventListener('click', () => {
        cFechaInicio.value = today;
        setModoCuotas('fijas');
        abrirModal();
    });

    btnCerrarModal?.addEventListener('click', cerrarModal);
    btnCancelarModal?.addEventListener('click', cerrarModal);
    modalBackdrop?.addEventListener('click', cerrarModal);

    formCxc?.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (!cClientePk.value) {
            KaiToast.show('Elegí un cliente.', 'warning');
            return;
        }

        const formData = new FormData(formCxc);
        const data = Object.fromEntries(formData.entries());
        data.cuotas_historicas = recolectarCuotasHistoricas();
        data.abonos_historicos = recolectarAbonosHistoricos();

        btnGuardarCxc.disabled = true;

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
                cargarCxc();
            } else {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar:', error);
            KaiToast.show('Error al guardar', 'danger');
        } finally {
            btnGuardarCxc.disabled = false;
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
        cxcDetalleActual = null;
    }

    btnCerrarDetalle.addEventListener('click', cerrarDetalle);
    modalDetalleBackdrop.addEventListener('click', cerrarDetalle);

    window.verCxc = async function (pk) {
        try {
            const response = await fetch(`${urlDetalleBase}${pk}/`);
            const data = await response.json();

            if (!data.cuenta_cobrar) {
                KaiToast.show('Cuenta por cobrar no encontrada', 'danger');
                return;
            }

            cxcDetalleActual = data.cuenta_cobrar;
            renderizarDetalle(data.cuenta_cobrar);
            abrirDetalle();
        } catch (error) {
            console.error('Error al cargar cuenta por cobrar:', error);
            KaiToast.show('Error al cargar', 'danger');
        }
    };

    // El listado no trae `cuotas`/`documentos` (eso solo lo da el
    // detalle) — hay que pedirlo antes de poder armar la impresión. La
    // ventana se abre ACÁ, en blanco, antes del `await`: si se abriera
    // recién después del fetch, ya no cuenta como gesto directo del
    // usuario y el navegador la bloquea sin avisar.
    window.imprimirCxcDesdeLista = async function (pk) {
        const ventana = window.open('', '_blank', 'width=800,height=950');
        if (!ventana) {
            KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio e intentá de nuevo.', 'warning', 6000);
            return;
        }
        try {
            const response = await fetch(`${urlDetalleBase}${pk}/`);
            const data = await response.json();
            if (!data.cuenta_cobrar) {
                ventana.close();
                KaiToast.show('Cuenta por cobrar no encontrada', 'danger');
                return;
            }
            if (typeof cxcImprimir === 'function') {
                cxcImprimir(data.cuenta_cobrar, ventana);
            } else {
                ventana.close();
                console.error('cuentas_cobrar_imprimir.js no está cargado.');
            }
        } catch (error) {
            ventana.close();
            console.error('Error al cargar cuenta por cobrar para imprimir:', error);
            KaiToast.show('Error al cargar la cuenta por cobrar', 'danger');
        }
    };

    function renderizarDetalle(d) {
        // "Ya se empezó a cobrar" cuenta también las cuotas históricas —
        // una vez que hay algo confirmado (real o de carga inicial), el
        // monto/interés/cuotas/fecha quedan fijos: cambiarlos desalinearía
        // lo que ya se registró e imprimió. Si la cuenta nació de una venta
        // real (pago_venta), el plan queda bloqueado siempre.
        const hayPagos = d.cuotas.some(c => c.estado === 'confirmada');
        const puedeEditarPlan = puedeEditar && !hayPagos && !d.venta_numero;

        const item = (label, valor, wide, highlight) => `<div class="cxc-resumen-item${wide ? ' cxc-resumen-item--wide' : ''}${highlight ? ' cxc-resumen-item--highlight' : ''}"><span class="cxc-resumen-label">${label}</span><div class="cxc-resumen-value">${valor}</div></div>`;

        detalleResumen.innerHTML = `
            <div class="cxc-resumen-grid">
                ${item('Cliente', d.cliente_nombre
                    ? `${_cxcEscInput(d.cliente_nombre)} <a href="${urls.clientePerfilBase}${d.cliente_pk}/" class="cxc-cliente-ficha-link" target="_blank" rel="noopener">Ver ficha completa del cliente →</a>`
                    : '-')}
                ${item('Venta', d.venta_numero || '-')}
                ${item('Descripción', puedeEditar
                    ? `<input type="text" id="detDescripcion" value="${_cxcEscInput(d.descripcion)}">`
                    : (d.descripcion || '-'), true)}
                ${item('N° de comprobante', (puedeEditar && !d.venta_numero)
                    ? `<input type="text" id="detNumeroComprobante" placeholder="Opcional" value="${_cxcEscInput(d.numero_comprobante)}">`
                    : (d.numero_comprobante || '-'))}
                ${item('N° de pagaré', puedeEditar
                    ? `<input type="text" id="detNumeroPagare" placeholder="Opcional" value="${_cxcEscInput(d.numero_pagare)}">`
                    : (d.numero_pagare || '-'))}
                ${item('Moneda', puedeEditarPlan
                    ? `<select id="detMoneda">${cMoneda.innerHTML}</select>`
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
                    : `${d.cuotas_cobradas}/${d.cantidad_cuotas}`)}
                ${item('Vencimiento 1° cuota', puedeEditarPlan
                    ? `<input type="date" id="detFechaInicio" value="${d.fecha_inicio}">`
                    : d.fecha_inicio)}`}
                ${item('Monto total', fmtMoneda(d.monto_total, d.moneda))}
                ${item('Saldo pendiente', fmtMoneda(d.saldo_pendiente, d.moneda), false, true)}
                ${item('Estado', `<span class="cxc-badge-estado cxc-badge-estado--${d.estado}">${d.estado_display}</span>${d.es_carga_inicial ? ` <span class="cxc-badge-carga-inicial">Carga inicial</span>` : ''}`)}
            </div>
            ${hayPagos && puedeEditar ? `<p class="cxc-edicion-nota">Esta cuenta ya tiene cuotas confirmadas — el monto, interés, cantidad de cuotas, fecha de inicio y moneda ya no se pueden editar.</p>` : ''}
            ${!hayPagos && d.venta_numero && puedeEditar ? `<p class="cxc-edicion-nota">Esta cuenta nació de una venta — su plan de cobro no se puede editar acá.</p>` : ''}
        `;

        detNotas.value = d.notas || '';
        detNotas.disabled = !puedeEditar;
        if (btnGuardarNotas) btnGuardarNotas.disabled = !puedeEditar;
        // Se puede eliminar aunque ya tenga cuotas cobradas (reales o
        // históricas) — el aviso fuerte de qué implica eso va en el
        // confirm al hacer click, no acá.

        if (typeof renderizarDocumentosCxc === 'function') renderizarDocumentosCxc(d);
        if (typeof renderizarPagareCxc === 'function') renderizarPagareCxc(d);

        if (cuotasTitle) cuotasTitle.textContent = d.modo_cuotas === 'libre' ? 'Abonos' : 'Cuotas';

        const saldoPendienteNum = parseFloat(d.saldo_pendiente) || 0;
        const mostrarRegistrarAbono = d.modo_cuotas === 'libre' && d.estado === 'activa'
            && saldoPendienteNum > 0 && puedeConfirmar;
        if (cxcRegistrarAbono) {
            cxcRegistrarAbono.hidden = !mostrarRegistrarAbono;
            if (mostrarRegistrarAbono) {
                raMonto.value = d.saldo_pendiente;
                raMonto.max = d.saldo_pendiente;
                raFecha.value = today;
                raFecha.max = today;
                const cuentasAbono = cuentasPorMoneda(d.moneda);
                poblarSelect(raCuenta, cuentasAbono, cuentaPrincipalEn(cuentasAbono));
                if (raComprobante) raComprobante.value = '';
                raMsg.textContent = '';
            }
        }

        const cuentasCobro = cuentasPorMoneda(d.moneda);
        const princCuota = cuentaPrincipalEn(cuentasCobro);
        const cuentaCuotaOpts = () => cuentasCobro.map(cta =>
            `<option value="${cta.pk}"${princCuota && String(cta.pk) === princCuota ? ' selected' : ''}>${cta.nombre}${cta.titular ? ' · ' + cta.titular : ''}</option>`
        ).join('');

        cuotasBody.innerHTML = d.cuotas.map(c => {
            let accion = '-';
            // Mientras el cheque que cobra esta cuota siga pendiente o ya
            // esté depositado, la cuota sigue "pendiente" pero no se puede
            // volver a cobrar — mostrar el cheque en trámite en vez de los
            // controles de cobro (el backend ya lo bloquea, esto es para
            // que no se vea como si no se hubiera hecho nada).
            const chequeActivo = c.cheque_pk && (c.cheque_estado === 'pendiente' || c.cheque_estado === 'confirmado');
            // Si en cambio el cheque más reciente rebotó, la cuota volvió
            // a estar realmente pendiente — se puede cobrar de nuevo, pero
            // con una referencia visible al cheque rechazado.
            const notaChequeRechazado = (c.cheque_pk && c.cheque_estado === 'rechazado' && c.estado === 'pendiente')
                ? `<span class="cxc-cuota-fecha">Cheque #${c.cheque_numero} rechazado — </span>`
                : '';
            if (c.estado === 'pendiente' && chequeActivo) {
                accion = `Cheque #${c.cheque_numero} (${c.cheque_estado}) <span class="cxc-cuota-fecha">en trámite</span>`;
            } else if (c.estado === 'pendiente' && puedeConfirmar && c.habilitada) {
                accion = notaChequeRechazado + `
                    <div class="cxc-cuota-confirmar">
                        <select id="cuentaCuota${c.pk}" class="cxc-cuota-select"
                                onchange="onCuentaCuotaChange(this, ${c.pk}, ${c.monto}, '${d.moneda}', false)">
                            ${cuentaCuotaOpts()}
                            <option value="__cheque__">— Cobrar con cheque —</option>
                        </select>
                        <button type="button" class="btn btn-primary btn--sm" onclick="confirmarCuotaCobro(${c.pk})">Confirmar</button>
                    </div>`;
            } else if (c.estado === 'pendiente' && !c.habilitada && puedeConfirmar) {
                accion = notaChequeRechazado + `
                    <div class="cxc-cuota-confirmar">
                        <select id="cuentaCuota${c.pk}" class="cxc-cuota-select"
                                onchange="onCuentaCuotaChange(this, ${c.pk}, ${c.monto}, '${d.moneda}', true)">
                            ${cuentaCuotaOpts()}
                            <option value="__cheque__">— Cobrar con cheque —</option>
                        </select>
                        <button type="button" class="btn btn-secondary btn--sm" onclick="confirmarCuotaCobro(${c.pk}, true)">Adelantar cobro</button>
                        <span class="cxc-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>
                    </div>`;
            } else if (c.estado === 'pendiente' && !c.habilitada) {
                accion = notaChequeRechazado + `<span class="cxc-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>`;
            } else if (c.estado === 'anulada' && c.cheque_pk) {
                // Abono de cuotas libres cuyo cheque rebotó: queda como
                // referencia histórica nada más — no cuenta para el saldo
                // y no se puede volver a cobrar esta fila (hay que
                // registrar un abono nuevo).
                accion = `<span class="cxc-cuota-fecha">Cheque #${c.cheque_numero} rechazado — no cuenta</span>`;
            } else if (c.estado === 'confirmada' && c.es_historica) {
                let detallePago = '';
                if (c.cheque_pk && c.cheque_es_historico) {
                    detallePago = `Cheque #${c.cheque_numero}`;
                } else if (c.cuenta_pago_historica_nombre) {
                    detallePago = _cxcEscInput(c.cuenta_pago_historica_nombre);
                } else if (c.medio_pago_historico) {
                    detallePago = _cxcEscInput(c.medio_pago_historico);
                }
                accion = `<span class="cxc-badge-carga-inicial">Carga inicial (no afectó caja)</span>` +
                    (detallePago ? ` <span class="cxc-cuota-fecha">${detallePago}</span>` : '') +
                    ` <span class="cxc-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            } else if (c.estado === 'confirmada' && c.cheque_pk) {
                accion = `Cheque #${c.cheque_numero} (${c.cheque_estado}) <span class="cxc-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            } else if (c.estado === 'confirmada') {
                accion = `${c.cuenta_cobro_nombre} <span class="cxc-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            }

            let comprobanteCelda = '-';
            if (c.estado === 'confirmada' && !c.es_historica) {
                const valor = c.numero_comprobante ? _cxcEscInput(c.numero_comprobante) : '-';
                comprobanteCelda = `<span id="comprobanteView${c.pk}">${valor}` +
                    (puedeEditar ? ` <button type="button" class="cxc-cuota-comprobante-editar" onclick="editarComprobanteCuota(${c.pk})" aria-label="Editar N° de comprobante">✎</button>` : '') +
                    `</span>`;
            } else if (c.estado === 'pendiente' && puedeConfirmar && !chequeActivo) {
                comprobanteCelda = `<input type="text" id="cuotaComprobante${c.pk}" class="cxc-cuota-comprobante-input" placeholder="Opcional">`;
            }

            return `
                <tr>
                    <td>${c.numero}</td>
                    <td>${c.fecha_vencimiento}</td>
                    <td class="cxc-monto">${fmtMoneda(c.monto, d.moneda)}</td>
                    <td><span class="cxc-badge-estado cxc-badge-estado--${c.estado === 'confirmada' ? 'activa' : c.estado === 'anulada' ? 'anulada' : 'pendiente'}">${c.estado}</span></td>
                    <td>${comprobanteCelda}</td>
                    <td>${accion}</td>
                </tr>`;
        }).join('');
    }

    window.editarComprobanteCuota = function (cuotaPk) {
        const cuota = (cxcDetalleActual && cxcDetalleActual.cuotas || []).find(c => c.pk === cuotaPk);
        const celda = document.getElementById(`comprobanteView${cuotaPk}`)?.closest('td');
        if (!celda) return;
        celda.innerHTML = `
            <input type="text" id="comprobanteEdit${cuotaPk}" class="cxc-cuota-comprobante-input" value="${_cxcEscInput(cuota ? cuota.numero_comprobante : '')}">
            <button type="button" class="btn btn-primary btn--sm" onclick="guardarComprobanteCuota(${cuotaPk})">Guardar</button>`;
    };

    window.guardarComprobanteCuota = async function (cuotaPk) {
        const input = document.getElementById(`comprobanteEdit${cuotaPk}`);
        const numeroComprobante = input ? input.value : '';
        try {
            const response = await fetch(urlEditarComprobanteCuota(cuotaPk), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ numero_comprobante: numeroComprobante }),
            });
            const result = await response.json();
            if (result.success) {
                window.verCxc(cxcDetalleActual.pk);
            } else {
                KaiToast.show(result.error || 'Error al guardar el comprobante.', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar comprobante:', error);
            KaiToast.show('Error al guardar el comprobante.', 'danger');
        }
    };

    window.confirmarCuotaCobro = async function (cuotaPk, adelantar = false) {
        const select = document.getElementById(`cuentaCuota${cuotaPk}`);
        const cuentaPk = select ? select.value : '';
        if (!cuentaPk) {
            KaiToast.show('Elegí la cuenta a la que entra el cobro.', 'warning');
            return;
        }
        const comprobanteInput = document.getElementById(`cuotaComprobante${cuotaPk}`);
        const numeroComprobante = comprobanteInput ? comprobanteInput.value : '';
        const mensaje = adelantar
            ? '¿Adelantar el cobro de esta cuota antes de su fecha habilitada? Esto va a impactar la caja.'
            : '¿Confirmar el cobro de esta cuota? Esto va a impactar la caja.';
        if (!await KaiConfirm(mensaje)) return;

        try {
            const response = await fetch(urlConfirmarCuota(cuotaPk), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ cuenta_pk: cuentaPk, adelantar, numero_comprobante: numeroComprobante }),
            });
            const result = await response.json();

            if (result.success) {
                window.verCxc(cxcDetalleActual.pk);
                cargarCxc();
            } else {
                KaiToast.show(result.error || 'Error al confirmar el cobro', 'danger');
            }
        } catch (error) {
            console.error('Error al confirmar cobro:', error);
            KaiToast.show('Error al confirmar el cobro', 'danger');
        }
    };

    // ── Modal "Cobrar cuota con cheque" ──────────────────────────────
    const modalChequeCuota = document.getElementById('modalChequeCuota');
    const modalChequeCuotaBackdrop = document.getElementById('modalChequeCuotaBackdrop');
    const btnCerrarChequeCuota = document.getElementById('btnCerrarChequeCuota');
    const btnCancelarChequeCuota = document.getElementById('btnCancelarChequeCuota');
    const btnGuardarChequeCuota = document.getElementById('btnGuardarChequeCuota');
    let chequeCuotaActual = null; // { modoAbono, cuotaPk, adelantar, monto } | { modoAbono: true, cxcPk, monto, fecha }

    // Elegir "— Cobrar con cheque —" en el select de cuenta abre el modal
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
        document.getElementById('cchc_emisor').value = '';
        document.getElementById('cchc_banco').value = '';
        document.getElementById('cchc_numero_comprobante').value = '';
        document.getElementById('cchcMsg').textContent = '';

        modalChequeCuota.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    window.abrirModalChequeCuota = function (cuotaPk, monto, moneda, adelantar) {
        chequeCuotaActual = { modoAbono: false, cuotaPk, adelantar, monto };
        _prepararModalChequeComun(monto, moneda);
    };

    function abrirModalChequeAbono(monto, moneda, fecha) {
        chequeCuotaActual = { modoAbono: true, cxcPk: cxcDetalleActual.pk, monto, fecha };
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
        const fechaEmision = document.getElementById('cchc_fecha_emision').value;
        const fechaCobro = document.getElementById('cchc_fecha_cobro').value;
        if (!fechaEmision || !fechaCobro) { msg.textContent = 'Indicá fecha de emisión y de cobro.'; return; }

        const mensajeConfirmacion = chequeCuotaActual.modoAbono
            ? '¿Registrar este abono con este cheque? Queda confirmado ya mismo; el ingreso real de caja se genera recién cuando confirmes/deposites el cheque desde la pantalla de Cheques.'
            : '¿Cobrar esta cuota con este cheque? La cuota queda confirmada ya mismo; el ingreso real de caja se genera recién cuando confirmes/deposites el cheque desde la pantalla de Cheques.';
        if (!await KaiConfirm(mensajeConfirmacion)) return;

        const chequeData = {
            numero_cheque: document.getElementById('cchc_numero_cheque').value,
            monto: chequeCuotaActual.monto,
            fecha_emision: fechaEmision,
            fecha_cobro: fechaCobro,
            emisor: document.getElementById('cchc_emisor').value,
            banco: document.getElementById('cchc_banco').value,
        };
        const numeroComprobante = document.getElementById('cchc_numero_comprobante').value;

        btnGuardarChequeCuota.disabled = true;
        try {
            const response = chequeCuotaActual.modoAbono
                ? await fetch(urlRegistrarAbono(chequeCuotaActual.cxcPk), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({
                        monto: chequeCuotaActual.monto,
                        fecha: chequeCuotaActual.fecha,
                        cheque: chequeData,
                        numero_comprobante: numeroComprobante,
                    }),
                })
                : await fetch(urlConfirmarCuota(chequeCuotaActual.cuotaPk), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({
                        adelantar: chequeCuotaActual.adelantar, cheque: chequeData,
                        numero_comprobante: numeroComprobante,
                    }),
                });
            const result = await response.json();
            if (result.success) {
                cerrarModalChequeCuota();
                window.verCxc(cxcDetalleActual.pk);
                cargarCxc();
            } else {
                msg.textContent = result.error || 'Error al confirmar el cobro con cheque.';
            }
        } catch (error) {
            console.error('Error al confirmar cobro con cheque:', error);
            msg.textContent = 'Error al confirmar el cobro con cheque.';
        } finally {
            btnGuardarChequeCuota.disabled = false;
        }
    });

    // ── Registrar abono (modo_cuotas=libre) ──────────────────────────
    btnAbonar?.addEventListener('click', async () => {
        if (!cxcDetalleActual) return;
        raMsg.textContent = '';
        const monto = parseFloat(raMonto.value);
        const fecha = raFecha.value;
        const cuentaPk = raCuenta.value;
        if (!monto || monto <= 0) { raMsg.textContent = 'Indicá el monto a cobrar.'; return; }
        if (!cuentaPk) { raMsg.textContent = 'Elegí la cuenta a la que entra el cobro.'; return; }

        if (!await KaiConfirm('¿Confirmar este abono? Esto va a impactar la caja.')) return;

        btnAbonar.disabled = true;
        try {
            const response = await fetch(urlRegistrarAbono(cxcDetalleActual.pk), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    monto, fecha, cuenta_pk: cuentaPk,
                    numero_comprobante: raComprobante ? raComprobante.value : '',
                }),
            });
            const result = await response.json();
            if (result.success) {
                window.verCxc(cxcDetalleActual.pk);
                cargarCxc();
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
        if (!cxcDetalleActual) return;
        raMsg.textContent = '';
        const monto = parseFloat(raMonto.value);
        const fecha = raFecha.value;
        if (!monto || monto <= 0) { raMsg.textContent = 'Indicá el monto a cobrar.'; return; }
        abrirModalChequeAbono(monto, cxcDetalleActual.moneda, fecha);
    });

    btnGuardarNotas?.addEventListener('click', async () => {
        if (!cxcDetalleActual) return;

        const payload = { notas: detNotas.value };
        const detDescripcion = document.getElementById('detDescripcion');
        const detNumeroComprobante = document.getElementById('detNumeroComprobante');
        const detNumeroPagare = document.getElementById('detNumeroPagare');
        if (detDescripcion) payload.descripcion = detDescripcion.value;
        if (detNumeroComprobante) payload.numero_comprobante = detNumeroComprobante.value;
        if (detNumeroPagare) payload.numero_pagare = detNumeroPagare.value;

        // Estos campos solo existen en el DOM si todavía no hay cuotas
        // confirmadas y la cuenta no nació de una venta (ver
        // renderizarDetalle) — si no están, no se tocan.
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

        try {
            const response = await fetch(`${urlEditarBase}${cxcDetalleActual.pk}/`, {
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
                cxcDetalleActual = result.cuenta_cobrar;
                renderizarDetalle(result.cuenta_cobrar);
                cargarCxc();
            } else {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar cambios:', error);
            KaiToast.show('Error al guardar cambios', 'danger');
        }
    });

    btnImprimirCxc?.addEventListener('click', () => {
        if (!cxcDetalleActual) return;
        if (typeof cxcImprimir === 'function') {
            cxcImprimir(cxcDetalleActual);
        } else {
            console.error('cuentas_cobrar_imprimir.js no está cargado.');
        }
    });

    btnEliminarCxc?.addEventListener('click', async () => {
        if (!cxcDetalleActual) return;
        const tieneCuotasReales = cxcDetalleActual.cuotas.some(c => c.estado === 'confirmada' && !c.es_historica);
        const mensaje = tieneCuotasReales
            ? 'Esta cuenta ya tiene cuotas cobradas de verdad — al eliminarla también se borran esos ingresos de la caja. ¿Eliminar de todas formas?'
            : '¿Estás seguro de eliminar esta cuenta por cobrar?';
        if (!await KaiConfirm(mensaje, { danger: true, confirmText: 'Eliminar' })) return;

        try {
            const response = await fetch(`${urlEliminarBase}${cxcDetalleActual.pk}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const result = await response.json();

            if (result.success) {
                cerrarDetalle();
                cargarCxc();
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
        cargarCxc();
    });

    btnLimpiarFiltros.addEventListener('click', () => {
        formFiltros.reset();
        paginaActual = 1;
        cargarCxc();
    });

    // ── Helpers ─────────────────────────────────────────────────────
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }

    // ── Inicialización ─────────────────────────────────────────────
    if (cFechaInicio) cFechaInicio.value = today;

    // Deep-link de filtros: permite llegar acá desde otra pantalla
    // (ej. "Pendiente de Cobro" en Caja Diaria) ya filtrado por
    // ?estado=activa, sin tener que tocar nada.
    const paramsUrl = new URLSearchParams(window.location.search);
    let hayFiltroPorUrl = false;
    ['estado', 'moneda', 'q'].forEach((campo) => {
        const valor = paramsUrl.get(campo);
        if (valor) {
            const idCampo = `f${campo.charAt(0).toUpperCase()}${campo.slice(1)}`;
            const el = document.getElementById(idCampo);
            if (el) {
                el.value = valor;
                hayFiltroPorUrl = true;
            }
        }
    });
    if (hayFiltroPorUrl) {
        btnToggleFiltros.setAttribute('aria-expanded', 'true');
        formFiltros.hidden = false;
    }

    cargarCxc();
});
