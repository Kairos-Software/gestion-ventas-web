document.addEventListener('DOMContentLoaded', function () {
    const urls = window.gastosUrls;
    const today = window.gastosToday;

    // ── Cuentas (para el select del modal, filtrado por moneda) ─────
    const cuentasDataEl = document.getElementById('cuentas-data');
    const CUENTAS = cuentasDataEl ? JSON.parse(cuentasDataEl.textContent) : [];
    const gMoneda = document.getElementById('gMoneda');
    const gCuenta = document.getElementById('gCuenta');

    function poblarCuentas(moneda, seleccionarPk) {
        const disponibles = CUENTAS.filter(c => c.moneda === moneda);
        gCuenta.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            disponibles.map(c => `<option value="${c.pk}">${c.nombre}${c.es_credito ? ' · crédito' : ''}</option>`).join('');
        if (seleccionarPk) {
            gCuenta.value = String(seleccionarPk);
        }
    }

    gMoneda?.addEventListener('change', () => poblarCuentas(gMoneda.value));

    // Construir URLs base reemplazando el placeholder 0
    const urlEditarBase = urls.editar.replace('/0/', '/');
    const urlEliminarBase = urls.eliminar.replace('/0/', '/');

    let paginaActual = 1;
    let porPagina = 50;

    // ── Elementos DOM ───────────────────────────────────────────────
    const btnNuevoGasto = document.getElementById('btnNuevoGasto');
    const btnToggleFiltros = document.getElementById('btnToggleFiltros');
    const formFiltros = document.getElementById('formFiltros');
    const btnLimpiarFiltros = document.getElementById('btnLimpiarFiltros');
    const gastosBody = document.getElementById('gastosBody');
    const paginacionContainer = document.getElementById('paginacionContainer');

    // Modal
    const modalGasto = document.getElementById('modalGasto');
    const modalBackdrop = document.getElementById('modalBackdrop');
    const btnCerrarModal = document.getElementById('btnCerrarModal');
    const btnCancelarModal = document.getElementById('btnCancelarModal');
    const formGasto = document.getElementById('formGasto');
    const modalTitle = document.getElementById('modalTitle');
    const btnGuardarGasto = document.getElementById('btnGuardarGasto');
    const gTipo = document.getElementById('gTipo');
    const botonesTipo = document.querySelectorAll('.gastos-tipo-btn');

    // ── Toggle tipo ingreso/egreso ───────────────────────────────────
    function setTipo(tipo) {
        gTipo.value = tipo;
        botonesTipo.forEach(btn => {
            btn.classList.toggle('gastos-tipo-btn--active', btn.dataset.tipo === tipo);
        });
    }
    botonesTipo.forEach(btn => {
        btn.addEventListener('click', () => setTipo(btn.dataset.tipo));
    });

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

    // ── Modal ───────────────────────────────────────────────────────
    function abrirModal(titulo = 'Nuevo movimiento') {
        modalTitle.textContent = titulo;
        modalGasto.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function cerrarModal() {
        modalGasto.hidden = true;
        document.body.style.overflow = '';
        formGasto.reset();
        document.getElementById('gastoPk').value = '';
        document.getElementById('gFecha').value = today;
        setTipo('egreso');
    }

    btnNuevoGasto?.addEventListener('click', () => {
        document.getElementById('gFecha').value = today;
        setTipo('egreso');
        poblarCuentas(gMoneda.value);
        abrirModal('Nuevo movimiento');
    });

    btnCerrarModal.addEventListener('click', cerrarModal);
    btnCancelarModal.addEventListener('click', cerrarModal);
    modalBackdrop.addEventListener('click', cerrarModal);

    // ── Crear/Editar ───────────────────────────────────────────────
    formGasto.addEventListener('submit', async (e) => {
        e.preventDefault();

        const pk = document.getElementById('gastoPk').value;
        const formData = new FormData(formGasto);
        const data = Object.fromEntries(formData.entries());

        btnGuardarGasto.disabled = true;

        try {
            const url = pk ? `${urlEditarBase}${pk}/` : urls.crear;
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
                cerrarModal();
                cargarGastos();
            } else {
                alert(result.error || 'Error al guardar');
            }
        } catch (error) {
            console.error('Error al guardar:', error);
            alert('Error al guardar');
        } finally {
            btnGuardarGasto.disabled = false;
        }
    });

    window.editarGasto = async function (pk) {
        try {
            const params = new URLSearchParams(getFiltrosActivos());
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();

            const gasto = data.results.find(g => g.pk === pk);
            if (!gasto) {
                alert('Movimiento no encontrado');
                return;
            }

            document.getElementById('gastoPk').value = gasto.pk;
            document.getElementById('gFecha').value = gasto.fecha;
            document.getElementById('gMonto').value = gasto.monto;
            gMoneda.value = gasto.moneda;
            poblarCuentas(gasto.moneda, gasto.cuenta_pk);
            document.getElementById('gDescripcion').value = gasto.descripcion;
            setTipo(gasto.tipo);

            abrirModal('Editar movimiento');
        } catch (error) {
            console.error('Error al cargar movimiento:', error);
            alert('Error al cargar movimiento');
        }
    };

    window.eliminarGasto = async function (pk) {
        if (!confirm('¿Estás seguro de eliminar este movimiento?')) {
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
                alert(result.error || 'Error al eliminar');
            }
        } catch (error) {
            console.error('Error al eliminar:', error);
            alert('Error al eliminar');
        }
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

    // ── Helpers ─────────────────────────────────────────────────────
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }

    // ── Inicialización ─────────────────────────────────────────────
    cargarGastos();
});
