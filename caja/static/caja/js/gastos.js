document.addEventListener('DOMContentLoaded', function () {
    const urls = window.gastosUrls;
    const today = window.gastosToday;

    // ── Cuentas (para los selects, filtrado por moneda) ─────────────
    const cuentasDataEl = document.getElementById('cuentas-data');
    const CUENTAS = cuentasDataEl ? JSON.parse(cuentasDataEl.textContent) : [];

    function poblarCuentasEnSelect(selectEl, moneda, seleccionarPk) {
        const disponibles = CUENTAS.filter(c => c.moneda === moneda);
        selectEl.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            disponibles.map(c => `<option value="${c.pk}">${c.nombre}${c.titular ? ' · ' + c.titular : ''}${c.es_credito ? ' · crédito' : ''}</option>`).join('');
        // Si no viene una cuenta puntual (caso: carga nueva), se
        // preselecciona la cuenta principal del negocio si está en la
        // lista (Configuración → Cuentas de caja).
        if (!seleccionarPk) {
            const principal = disponibles.find(c => c.preferida);
            if (principal) seleccionarPk = principal.pk;
        }
        if (seleccionarPk) {
            selectEl.value = String(seleccionarPk);
        }
    }

    // Construir URLs base reemplazando el placeholder 0 (pk al final)
    const urlEditarBase = urls.editar.replace('/0/', '/');
    const urlEliminarBase = urls.eliminar.replace('/0/', '/');

    let paginaActual = 1;
    let porPagina = 50;

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }

    // ══════════════════════════════════════════════════════════════
    //  PESTAÑAS
    // ══════════════════════════════════════════════════════════════
    const tabButtons = document.querySelectorAll('.gastos-tab-btn');
    const tabPanels = {
        historial: document.getElementById('panelHistorial'),
        pendientes: document.getElementById('panelPendientes'),
        programados: document.getElementById('panelProgramados'),
    };
    function activarTab(tab) {
        tabButtons.forEach(btn => btn.classList.toggle('gastos-tab-btn--active', btn.dataset.tab === tab));
        Object.entries(tabPanels).forEach(([key, panel]) => { panel.hidden = key !== tab; });
    }
    tabButtons.forEach(btn => btn.addEventListener('click', () => activarTab(btn.dataset.tab)));

    // ── Elementos DOM — Historial ────────────────────────────────────
    const btnNuevoGasto = document.getElementById('btnNuevoGasto');
    const btnToggleFiltros = document.getElementById('btnToggleFiltros');
    const formFiltros = document.getElementById('formFiltros');
    const btnLimpiarFiltros = document.getElementById('btnLimpiarFiltros');
    const gastosBody = document.getElementById('gastosBody');
    const paginacionContainer = document.getElementById('paginacionContainer');

    // ── Cargar movimientos ───────────────────────────────────────────
    async function cargarGastos() {
        const params = new URLSearchParams({
            pagina: paginaActual,
            por_pagina: porPagina,
            ...getFiltrosActivos(),
        });

        try {
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();

            renderizarGastos(data.results);
            renderizarPaginacion(data.total, data.pagina, data.por_pagina);
        } catch (error) {
            console.error('Error al cargar movimientos:', error);
            gastosBody.innerHTML = '<tr><td colspan="9" class="gastos-tabla-loading">Error al cargar movimientos</td></tr>';
        }
    }

    function getFiltrosActivos() {
        const desde = document.getElementById('fDesde').value;
        const hasta = document.getElementById('fHasta').value;
        const tipo = document.getElementById('fTipo').value;
        const cuenta = document.getElementById('fCuenta').value;
        const moneda = document.getElementById('fMoneda').value;
        const q = document.getElementById('fQ').value;

        const filtros = {};
        if (desde) filtros.desde = desde;
        if (hasta) filtros.hasta = hasta;
        if (tipo) filtros.tipo = tipo;
        if (cuenta) filtros.cuenta = cuenta;
        if (moneda) filtros.moneda = moneda;
        if (q) filtros.q = q;

        return filtros;
    }

    function renderizarGastos(gastos) {
        if (!gastos || gastos.length === 0) {
            gastosBody.innerHTML = '<tr><td colspan="9" class="gastos-tabla-loading">No hay movimientos registrados</td></tr>';
            return;
        }

        gastosBody.innerHTML = gastos.map(g => `
            <tr>
                <td>${g.fecha}</td>
                <td>${g.hora}</td>
                <td><span class="gastos-badge-tipo gastos-badge-tipo--${g.tipo}">${g.tipo === 'ingreso' ? 'Ingreso' : 'Egreso'}</span></td>
                <td>${g.descripcion || '-'}</td>
                <td>${g.cuenta_nombre || '-'}</td>
                <td class="gastos-monto gastos-monto--${g.tipo}">${g.monto}</td>
                <td>${g.moneda}</td>
                <td>${g.creado_por || '-'}</td>
                <td>
                    <div class="gastos-tabla-acciones">
                        <button type="button" class="icon-btn" onclick="editarGasto(${g.pk})" title="Editar">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M2.5 13.5L13.5 2.5M13.5 2.5V7.5M13.5 2.5H8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        </button>
                        <button type="button" class="icon-btn" onclick="eliminarGasto(${g.pk})" title="Eliminar">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M3 3L13 13M3 13L13 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    function renderizarPaginacion(total, pagina, porPagina) {
        const totalPaginas = Math.ceil(total / porPagina);

        if (totalPaginas <= 1) {
            paginacionContainer.innerHTML = '';
            return;
        }

        let html = '<span class="gastos-paginacion-info">Página ' + pagina + ' de ' + totalPaginas + ' (' + total + ' registros)</span>';

        html += '<div class="gastos-paginacion-botones">';

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
        cargarGastos();
    };

    // ── Filtros ────────────────────────────────────────────────────
    btnToggleFiltros.addEventListener('click', () => {
        const expanded = btnToggleFiltros.getAttribute('aria-expanded') === 'true';
        btnToggleFiltros.setAttribute('aria-expanded', !expanded);
        formFiltros.hidden = expanded;
    });

    formFiltros.addEventListener('submit', (e) => {
        e.preventDefault();
        paginaActual = 1;
        cargarGastos();
    });

    btnLimpiarFiltros.addEventListener('click', () => {
        formFiltros.reset();
        paginaActual = 1;
        cargarGastos();
    });

    window.eliminarGasto = async function (pk) {
        if (!await KaiConfirm('¿Estás seguro de eliminar este movimiento?', { danger: true, confirmText: 'Eliminar' })) {
            return;
        }

        try {
            const response = await fetch(`${urlEliminarBase}${pk}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                },
            });

            const result = await response.json();

            if (result.success) {
                cargarGastos();
            } else {
                KaiToast.show(result.error || 'Error al eliminar', 'danger');
            }
        } catch (error) {
            console.error('Error al eliminar:', error);
            KaiToast.show('Error al eliminar', 'danger');
        }
    };

    // ══════════════════════════════════════════════════════════════
    //  MODAL ÚNICO — Nuevo/editar movimiento (único o recurrente)
    // ══════════════════════════════════════════════════════════════
    const modalMovimiento = document.getElementById('modalMovimiento');
    const modalMovBackdrop = document.getElementById('modalMovBackdrop');
    const btnCerrarModalMov = document.getElementById('btnCerrarModalMov');
    const btnCancelarModalMov = document.getElementById('btnCancelarModalMov');
    const formMovimiento = document.getElementById('formMovimiento');
    const modalMovTitle = document.getElementById('modalMovTitle');
    const btnGuardarMov = document.getElementById('btnGuardarMov');

    const movPk = document.getElementById('movPk');
    const movEditKind = document.getElementById('movEditKind');
    const movModoInput = document.getElementById('movModo');
    const movTipo = document.getElementById('movTipo');
    const movTipoMonto = document.getElementById('movTipoMonto');
    const movMoneda = document.getElementById('movMoneda');
    const movCuenta = document.getElementById('movCuenta');

    const wrapModo = document.getElementById('wrapModo');
    const wrapUnico = document.getElementById('wrapUnico');
    const wrapRecurrente = document.getElementById('wrapRecurrente');
    const wrapMontoFijo = document.getElementById('wrapMontoFijo');
    const movDescReq = document.getElementById('movDescReq');

    const movFecha = document.getElementById('movFecha');
    const movMonto = document.getElementById('movMonto');
    const movFrecuencia = document.getElementById('movFrecuencia');
    const movProximaFecha = document.getElementById('movProximaFecha');
    const movMontoFijo = document.getElementById('movMontoFijo');
    const movDescripcion = document.getElementById('movDescripcion');

    function setTipo(tipo) {
        movTipo.value = tipo;
        formMovimiento.querySelectorAll('.gastos-tipo-btn[data-tipo]').forEach(btn => {
            btn.classList.toggle('gastos-tipo-btn--active', btn.dataset.tipo === tipo);
        });
    }
    formMovimiento.querySelectorAll('.gastos-tipo-btn[data-tipo]').forEach(btn => {
        btn.addEventListener('click', () => setTipo(btn.dataset.tipo));
    });

    function setTipoMonto(tipoMonto) {
        movTipoMonto.value = tipoMonto;
        formMovimiento.querySelectorAll('.pg-toggle-btn[data-pgmonto]').forEach(btn => {
            btn.classList.toggle('pg-toggle-btn--active', btn.dataset.pgmonto === tipoMonto);
        });
        wrapMontoFijo.hidden = tipoMonto !== 'fijo';
        movMontoFijo.required = tipoMonto === 'fijo';
    }
    formMovimiento.querySelectorAll('.pg-toggle-btn[data-pgmonto]').forEach(btn => {
        btn.addEventListener('click', () => setTipoMonto(btn.dataset.pgmonto));
    });

    function setModo(modo) {
        movModoInput.value = modo;
        formMovimiento.querySelectorAll('.pg-toggle-btn[data-modo]').forEach(btn => {
            btn.classList.toggle('pg-toggle-btn--active', btn.dataset.modo === modo);
        });
        wrapUnico.hidden = modo !== 'unico';
        wrapRecurrente.hidden = modo !== 'recurrente';

        movFecha.required = modo === 'unico';
        movMonto.required = modo === 'unico';
        movFrecuencia.required = modo === 'recurrente';
        movProximaFecha.required = modo === 'recurrente';
        movDescripcion.required = modo === 'recurrente';
        movDescReq.hidden = modo !== 'recurrente';

        if (modo === 'recurrente') {
            setTipoMonto(movTipoMonto.value || 'variable');
        }
    }
    formMovimiento.querySelectorAll('.pg-toggle-btn[data-modo]').forEach(btn => {
        btn.addEventListener('click', () => setModo(btn.dataset.modo));
    });

    movMoneda?.addEventListener('change', () => poblarCuentasEnSelect(movCuenta, movMoneda.value));

    function abrirModalMov(titulo) {
        modalMovTitle.textContent = titulo;
        modalMovimiento.hidden = false;
        document.body.style.overflow = 'hidden';
    }
    function cerrarModalMov() {
        modalMovimiento.hidden = true;
        document.body.style.overflow = '';
        formMovimiento.reset();
        movPk.value = '';
        movEditKind.value = '';
        wrapModo.hidden = false;
        setTipo('egreso');
        setModo('unico');
    }

    btnNuevoGasto?.addEventListener('click', () => {
        cerrarModalMov();
        movFecha.value = today;
        poblarCuentasEnSelect(movCuenta, movMoneda.value);
        abrirModalMov('Nuevo movimiento');
    });

    btnCerrarModalMov.addEventListener('click', cerrarModalMov);
    btnCancelarModalMov.addEventListener('click', cerrarModalMov);
    modalMovBackdrop.addEventListener('click', cerrarModalMov);

    formMovimiento.addEventListener('submit', async (e) => {
        e.preventDefault();

        const pk = movPk.value;
        const editKind = movEditKind.value;
        const modo = movModoInput.value;
        const formData = new FormData(formMovimiento);
        const data = Object.fromEntries(formData.entries());

        let url;
        if (editKind === 'gasto') {
            url = `${urlEditarBase}${pk}/`;
        } else if (editKind === 'programado') {
            url = urls.editarProgramado.replace('/0/', `/${pk}/`);
        } else if (modo === 'unico') {
            url = urls.crear;
        } else {
            url = urls.crearProgramado;
        }

        btnGuardarMov.disabled = true;
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify(data),
            });

            const result = await response.json();

            if (result.success) {
                cerrarModalMov();
                cargarGastos();
                cargarProgramados();
            } else {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar:', error);
            KaiToast.show('Error al guardar', 'danger');
        } finally {
            btnGuardarMov.disabled = false;
        }
    });

    window.editarGasto = async function (pk) {
        try {
            const params = new URLSearchParams(getFiltrosActivos());
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();

            const gasto = data.results.find(g => g.pk === pk);
            if (!gasto) {
                KaiToast.show('Movimiento no encontrado', 'danger');
                return;
            }

            movPk.value = gasto.pk;
            movEditKind.value = 'gasto';
            movFecha.value = gasto.fecha;
            movMonto.value = gasto.monto;
            movMoneda.value = gasto.moneda;
            poblarCuentasEnSelect(movCuenta, gasto.moneda, gasto.cuenta_pk);
            movDescripcion.value = gasto.descripcion;
            setTipo(gasto.tipo);
            setModo('unico');
            wrapModo.hidden = true;

            abrirModalMov('Editar movimiento');
        } catch (error) {
            console.error('Error al cargar movimiento:', error);
            KaiToast.show('Error al cargar movimiento', 'danger');
        }
    };

    // ══════════════════════════════════════════════════════════════
    //  MOVIMIENTOS PROGRAMADOS + PENDIENTES
    // ══════════════════════════════════════════════════════════════
    let PROGRAMADOS = [];
    let PENDIENTES = [];

    const programadosBody = document.getElementById('programadosBody');
    const pendientesBody = document.getElementById('pendientesBody');
    const pendientesCount = document.getElementById('pendientesCount');

    window.editarProgramado = function (pk) {
        const p = PROGRAMADOS.find(x => x.pk === pk);
        if (!p) return;

        movPk.value = p.pk;
        movEditKind.value = 'programado';
        movDescripcion.value = p.descripcion;
        movFrecuencia.value = p.frecuencia;
        movProximaFecha.value = p.proxima_fecha;
        movMontoFijo.value = p.monto_fijo || '';
        movMoneda.value = p.moneda;
        setTipo(p.tipo);
        setModo('recurrente');
        setTipoMonto(p.tipo_monto);
        poblarCuentasEnSelect(movCuenta, p.moneda, p.cuenta_pk);
        wrapModo.hidden = true;

        abrirModalMov('Editar movimiento programado');
    };

    window.toggleActivoProgramado = async function (pk) {
        try {
            const url = urls.toggleProgramado.replace('/0/', `/${pk}/`);
            const response = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') } });
            const result = await response.json();
            if (result.success) {
                cargarProgramados();
            } else {
                KaiToast.show(result.error || 'Error', 'danger');
            }
        } catch (error) {
            console.error('Error al pausar/reactivar:', error);
            KaiToast.show('Error de conexión', 'danger');
        }
    };

    window.eliminarProgramado = async function (pk) {
        if (!await KaiConfirm('¿Eliminar este movimiento programado? No borra los movimientos ya confirmados, solo deja de generar nuevos pendientes.', { danger: true, confirmText: 'Eliminar' })) {
            return;
        }
        try {
            const url = urls.eliminarProgramado.replace('/0/', `/${pk}/`);
            const response = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') } });
            const result = await response.json();
            if (result.success) {
                cargarProgramados();
            } else {
                KaiToast.show(result.error || 'Error al eliminar', 'danger');
            }
        } catch (error) {
            console.error('Error al eliminar programado:', error);
            KaiToast.show('Error al eliminar', 'danger');
        }
    };

    function renderizarProgramados(programados) {
        if (!programados || programados.length === 0) {
            programadosBody.innerHTML = '<tr><td colspan="8" class="gastos-tabla-loading">No hay movimientos programados</td></tr>';
            return;
        }
        programadosBody.innerHTML = programados.map(p => `
            <tr class="${p.activo ? '' : 'gastos-programado-pausado'}">
                <td>${p.descripcion}</td>
                <td><span class="gastos-badge-tipo gastos-badge-tipo--${p.tipo}">${p.tipo === 'ingreso' ? 'Ingreso' : 'Egreso'}</span></td>
                <td>${p.tipo_monto === 'fijo' ? '$' + p.monto_fijo : 'Variable'}</td>
                <td>${p.frecuencia_display}</td>
                <td>${p.proxima_fecha}</td>
                <td>${p.cuenta_nombre || '-'}</td>
                <td><span class="gastos-badge-estado gastos-badge-estado--${p.activo ? 'activo' : 'pausado'}">${p.activo ? 'Activo' : 'Pausado'}</span></td>
                <td>
                    <div class="gastos-tabla-acciones">
                        <button type="button" class="icon-btn" onclick="editarProgramado(${p.pk})" title="Editar">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M2.5 13.5L13.5 2.5M13.5 2.5V7.5M13.5 2.5H8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        </button>
                        <button type="button" class="icon-btn" onclick="toggleActivoProgramado(${p.pk})" title="${p.activo ? 'Pausar' : 'Reactivar'}">
                            ${p.activo
                                ? '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="4" y="3" width="3" height="10" rx="0.5" fill="currentColor"/><rect x="9" y="3" width="3" height="10" rx="0.5" fill="currentColor"/></svg>'
                                : '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 3L13 8L4 13V3Z" fill="currentColor"/></svg>'}
                        </button>
                        <button type="button" class="icon-btn" onclick="eliminarProgramado(${p.pk})" title="Eliminar">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M3 3L13 13M3 13L13 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    function renderizarPendientes(pendientes) {
        if (!pendientes || pendientes.length === 0) {
            pendientesCount.hidden = true;
            pendientesBody.innerHTML = '<tr><td colspan="6" class="gastos-tabla-loading">No hay pendientes de confirmar</td></tr>';
            return;
        }
        pendientesCount.hidden = false;
        pendientesCount.textContent = pendientes.length;
        pendientesBody.innerHTML = pendientes.map(i => `
            <tr>
                <td>${i.fecha_vencimiento}</td>
                <td><span class="gastos-badge-tipo gastos-badge-tipo--${i.tipo}">${i.tipo === 'ingreso' ? 'Ingreso' : 'Egreso'}</span></td>
                <td>${i.descripcion}</td>
                <td>${i.tipo_monto === 'fijo' ? '$' + i.monto : 'A cargar'}</td>
                <td>${i.cuenta_nombre || '-'}</td>
                <td>
                    <div class="gastos-tabla-acciones">
                        <button type="button" class="btn btn-primary btn--sm" onclick="abrirConfirmarInstancia(${i.pk})">Confirmar</button>
                        <button type="button" class="icon-btn" onclick="anularInstancia(${i.pk})" title="Anular">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M3 3L13 13M3 13L13 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    async function cargarProgramados() {
        try {
            const response = await fetch(urls.listarProgramados);
            const data = await response.json();
            PROGRAMADOS = data.programados || [];
            PENDIENTES = data.pendientes || [];
            renderizarProgramados(PROGRAMADOS);
            renderizarPendientes(PENDIENTES);
        } catch (error) {
            console.error('Error al cargar programados:', error);
            programadosBody.innerHTML = '<tr><td colspan="8" class="gastos-tabla-loading">Error al cargar</td></tr>';
        }
    }

    // ── Confirmar instancia pendiente ────────────────────────────────
    const modalConfirmarInstancia = document.getElementById('modalConfirmarInstancia');
    const modalConfirmarBackdrop = document.getElementById('modalConfirmarBackdrop');
    const btnCerrarModalConfirmar = document.getElementById('btnCerrarModalConfirmar');
    const btnCancelarModalConfirmar = document.getElementById('btnCancelarModalConfirmar');
    const formConfirmarInstancia = document.getElementById('formConfirmarInstancia');
    const btnGuardarConfirmarInstancia = document.getElementById('btnGuardarConfirmarInstancia');
    const ciCuenta = document.getElementById('ciCuenta');

    function cerrarModalConfirmar() {
        modalConfirmarInstancia.hidden = true;
        document.body.style.overflow = '';
        formConfirmarInstancia.reset();
    }
    btnCerrarModalConfirmar.addEventListener('click', cerrarModalConfirmar);
    btnCancelarModalConfirmar.addEventListener('click', cerrarModalConfirmar);
    modalConfirmarBackdrop.addEventListener('click', cerrarModalConfirmar);

    window.abrirConfirmarInstancia = function (pk) {
        const i = PENDIENTES.find(x => x.pk === pk);
        if (!i) return;
        document.getElementById('ciPk').value = i.pk;
        document.getElementById('ciDescripcion').textContent = `${i.tipo === 'ingreso' ? 'Ingreso' : 'Egreso'} — ${i.descripcion} (vencía el ${i.fecha_vencimiento})`;
        document.getElementById('ciFecha').value = today;
        document.getElementById('ciMonto').value = i.monto || '';
        poblarCuentasEnSelect(ciCuenta, i.moneda, i.cuenta_pk);
        modalConfirmarInstancia.hidden = false;
        document.body.style.overflow = 'hidden';
    };

    window.anularInstancia = async function (pk) {
        if (!await KaiConfirm('¿Anular esta instancia pendiente? No se genera ningún movimiento de caja para esta fecha.', { danger: true, confirmText: 'Anular' })) {
            return;
        }
        try {
            const url = urls.anularInstancia.replace('/0/', `/${pk}/`);
            const response = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') } });
            const result = await response.json();
            if (result.success) {
                cargarProgramados();
            } else {
                KaiToast.show(result.error || 'Error al anular', 'danger');
            }
        } catch (error) {
            console.error('Error al anular instancia:', error);
            KaiToast.show('Error de conexión', 'danger');
        }
    };

    formConfirmarInstancia.addEventListener('submit', async (e) => {
        e.preventDefault();
        const pk = document.getElementById('ciPk').value;
        const formData = new FormData(formConfirmarInstancia);
        const data = Object.fromEntries(formData.entries());

        btnGuardarConfirmarInstancia.disabled = true;
        try {
            const url = urls.confirmarInstancia.replace('/0/', `/${pk}/`);
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify(data),
            });
            const result = await response.json();
            if (result.success) {
                cerrarModalConfirmar();
                cargarProgramados();
                cargarGastos();
                KaiToast.show('Movimiento confirmado.');
            } else {
                KaiToast.show(result.error || 'Error al confirmar', 'danger');
            }
        } catch (error) {
            console.error('Error al confirmar instancia:', error);
            KaiToast.show('Error de conexión', 'danger');
        } finally {
            btnGuardarConfirmarInstancia.disabled = false;
        }
    });

    // ── Inicialización ─────────────────────────────────────────────
    activarTab('historial');
    cargarGastos();
    cargarProgramados();
});
