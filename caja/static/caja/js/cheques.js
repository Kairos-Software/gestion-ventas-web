document.addEventListener('DOMContentLoaded', function () {
    const urls = window.chequesUrls;
    const today = window.chequesToday;
    const puedeEditar = window.chequesPuedeEditar;
    const puedeEliminar = window.chequesPuedeEliminar;
    const puedeConfirmar = window.chequesPuedeConfirmar;

    // ── Cuentas propias (caja grande, sin tarjetas) ──────────────────
    const cuentasDataEl = document.getElementById('cuentas-data');
    const CUENTAS = cuentasDataEl ? JSON.parse(cuentasDataEl.textContent) : [];

    function cuentasPorMoneda(moneda) {
        return CUENTAS.filter(c => c.moneda === moneda);
    }

    function poblarSelect(select, opciones, seleccionarPk) {
        select.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            opciones.map(c => `<option value="${c.pk}">${c.nombre}</option>`).join('');
        if (seleccionarPk) select.value = String(seleccionarPk);
    }

    // Construir URLs base reemplazando el placeholder 0
    const urlEditarBase = urls.editar.replace('/0/', '/');
    const urlEliminarBase = urls.eliminar.replace('/0/', '/');

    // confirmar/rechazar tienen el placeholder en el medio (.../0/confirmar/),
    // no al final — no sirve el patrón base+pk, hay que reemplazar el 0 por el pk real.
    function urlConfirmarCheque(pk) {
        return urls.confirmar.replace('/0/', `/${pk}/`);
    }
    function urlRechazarCheque(pk) {
        return urls.rechazar.replace('/0/', `/${pk}/`);
    }

    let paginaActual = 1;
    let porPagina = 50;
    let chequeConfirmarActual = null;

    // ── Elementos DOM ───────────────────────────────────────────────
    const btnNuevoCheque = document.getElementById('btnNuevoCheque');
    const btnToggleFiltros = document.getElementById('btnToggleFiltros');
    const formFiltros = document.getElementById('formFiltros');
    const btnLimpiarFiltros = document.getElementById('btnLimpiarFiltros');
    const chequesBody = document.getElementById('chequesBody');
    const paginacionContainer = document.getElementById('paginacionContainer');

    // Modal alta/edición
    const modalCheque = document.getElementById('modalCheque');
    const modalBackdrop = document.getElementById('modalBackdrop');
    const btnCerrarModal = document.getElementById('btnCerrarModal');
    const btnCancelarModal = document.getElementById('btnCancelarModal');
    const formCheque = document.getElementById('formCheque');
    const modalChequeTitulo = document.getElementById('modalChequeTitulo');
    const btnGuardarCheque = document.getElementById('btnGuardarCheque');
    const f_tipo = document.getElementById('f_tipo');
    const f_moneda = document.getElementById('f_moneda');
    const f_cuenta_origen = document.getElementById('f_cuenta_origen');
    const campoCuentaOrigen = document.getElementById('campoCuentaOrigen');
    const camposLibrador = document.getElementById('camposLibrador');
    const botonesTipo = document.querySelectorAll('.chq-tipo-btn');

    // Modal confirmar cobro
    const modalConfirmarCheque = document.getElementById('modalConfirmarCheque');
    const modalConfirmarBackdrop = document.getElementById('modalConfirmarBackdrop');
    const btnCerrarConfirmar = document.getElementById('btnCerrarConfirmar');
    const btnCancelarConfirmar = document.getElementById('btnCancelarConfirmar');
    const btnConfirmarCobro = document.getElementById('btnConfirmarCobro');
    const conf_cuenta_destino = document.getElementById('conf_cuenta_destino');

    // ── Toggle a_cobrar / a_pagar ─────────────────────────────────────
    function setTipo(tipo) {
        f_tipo.value = tipo;
        botonesTipo.forEach(btn => {
            btn.classList.toggle('chq-tipo-btn--active', btn.dataset.tipo === tipo);
        });
        const esPagar = tipo === 'a_pagar';
        campoCuentaOrigen.hidden = !esPagar;
        camposLibrador.hidden = esPagar;
        if (esPagar) poblarSelect(f_cuenta_origen, cuentasPorMoneda(f_moneda.value));
    }
    botonesTipo.forEach(btn => {
        btn.addEventListener('click', () => setTipo(btn.dataset.tipo));
    });
    f_moneda?.addEventListener('change', () => {
        if (f_tipo.value === 'a_pagar') poblarSelect(f_cuenta_origen, cuentasPorMoneda(f_moneda.value));
    });

    // ── Cargar cheques ────────────────────────────────────────────
    async function cargarCheques() {
        const params = new URLSearchParams({
            pagina: paginaActual,
            por_pagina: porPagina,
            ...getFiltrosActivos(),
        });

        try {
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();

            renderizarCheques(data.results);
            renderizarPaginacion(data.total, data.pagina, data.por_pagina);
        } catch (error) {
            console.error('Error al cargar cheques:', error);
            chequesBody.innerHTML = '<tr><td colspan="7" class="chq-tabla-loading">Error al cargar cheques</td></tr>';
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

    let CHEQUES_CACHE = [];

    function renderizarCheques(cheques) {
        CHEQUES_CACHE = cheques || [];

        if (!cheques || cheques.length === 0) {
            chequesBody.innerHTML = '<tr><td colspan="7" class="chq-tabla-loading">No hay cheques registrados</td></tr>';
            return;
        }

        const ICONO_CONFIRMAR = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        const ICONO_RECHAZAR = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4"/><path d="M4.5 11.5L11.5 4.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`;
        const ICONO_EDITAR = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2.5 13.5L13.5 2.5M13.5 2.5V7.5M13.5 2.5H8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        const ICONO_ELIMINAR = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3 3L13 13M3 13L13 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;

        chequesBody.innerHTML = cheques.map(c => {
            const acciones = [];
            if (c.estado === 'pendiente' && puedeConfirmar) {
                acciones.push(`<button type="button" class="icon-btn icon-btn--success" onclick="confirmarCheque(${c.pk})" title="Confirmar">${ICONO_CONFIRMAR}</button>`);
            }
            if ((c.estado === 'pendiente' || c.estado === 'confirmado') && puedeConfirmar) {
                acciones.push(`<button type="button" class="icon-btn icon-btn--danger" onclick="rechazarCheque(${c.pk})" title="Rechazar">${ICONO_RECHAZAR}</button>`);
            }
            if (puedeEditar) {
                acciones.push(`<button type="button" class="icon-btn" onclick="editarCheque(${c.pk})" title="Editar">${ICONO_EDITAR}</button>`);
            }
            if (puedeEliminar && c.estado !== 'confirmado') {
                acciones.push(`<button type="button" class="icon-btn" onclick="eliminarCheque(${c.pk})" title="Eliminar">${ICONO_ELIMINAR}</button>`);
            }
            return `
            <tr>
                <td><span class="chq-badge-tipo chq-badge-tipo--${c.tipo}">${c.tipo_display}</span></td>
                <td>${c.numero_cheque || '-'}</td>
                <td>${c.contraparte || (c.tipo === 'a_cobrar' ? c.titular_librador : '') || '-'}</td>
                <td class="chq-monto">${fmtMoneda(c.monto, c.moneda)}</td>
                <td>${c.fecha_cobro}</td>
                <td><span class="chq-badge-estado chq-badge-estado--${c.estado}">${c.estado_display}</span></td>
                <td><div class="chq-tabla-acciones">${acciones.join('')}</div></td>
            </tr>`;
        }).join('');
    }

    function renderizarPaginacion(total, pagina, porPagina) {
        const totalPaginas = Math.ceil(total / porPagina);

        if (totalPaginas <= 1) {
            paginacionContainer.innerHTML = '';
            return;
        }

        let html = '<span class="chq-paginacion-info">Página ' + pagina + ' de ' + totalPaginas + ' (' + total + ' registros)</span>';
        html += '<div class="chq-paginacion-botones">';
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
        cargarCheques();
    };

    // ── Modal alta/edición ───────────────────────────────────────────
    function abrirModal() {
        modalCheque.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function cerrarModal() {
        modalCheque.hidden = true;
        document.body.style.overflow = '';
        formCheque.reset();
        document.getElementById('chqPk').value = '';
        document.getElementById('f_fecha_emision').value = today;
        document.getElementById('f_fecha_cobro').value = today;
        setTipo('a_cobrar');
    }

    btnNuevoCheque?.addEventListener('click', () => {
        modalChequeTitulo.textContent = 'Nuevo cheque';
        document.getElementById('f_fecha_emision').value = today;
        document.getElementById('f_fecha_cobro').value = today;
        setTipo('a_cobrar');
        abrirModal();
    });

    btnCerrarModal.addEventListener('click', cerrarModal);
    btnCancelarModal.addEventListener('click', cerrarModal);
    modalBackdrop.addEventListener('click', cerrarModal);

    formCheque.addEventListener('submit', async (e) => {
        e.preventDefault();

        const pk = document.getElementById('chqPk').value;
        const data = {
            tipo: f_tipo.value,
            numero_cheque: document.getElementById('f_numero_cheque').value,
            monto: document.getElementById('f_monto').value,
            moneda: f_moneda.value,
            fecha_emision: document.getElementById('f_fecha_emision').value,
            fecha_cobro: document.getElementById('f_fecha_cobro').value,
            contraparte: document.getElementById('f_contraparte').value,
            notas: document.getElementById('f_notas').value,
        };
        if (f_tipo.value === 'a_pagar') {
            data.cuenta_origen_pk = f_cuenta_origen.value;
        } else {
            data.banco_librador = document.getElementById('f_banco_librador').value;
            data.titular_librador = document.getElementById('f_titular_librador').value;
        }

        btnGuardarCheque.disabled = true;

        try {
            const url = pk ? `${urlEditarBase}${pk}/` : urls.crear;
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify(data),
            });
            const result = await response.json();

            if (result.success) {
                cerrarModal();
                cargarCheques();
            } else {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar:', error);
            KaiToast.show('Error al guardar', 'danger');
        } finally {
            btnGuardarCheque.disabled = false;
        }
    });

    window.editarCheque = function (pk) {
        const cheque = CHEQUES_CACHE.find(c => c.pk === pk);
        if (!cheque) return;

        modalChequeTitulo.textContent = 'Editar cheque';
        document.getElementById('chqPk').value = cheque.pk;
        setTipo(cheque.tipo);
        document.getElementById('f_numero_cheque').value = cheque.numero_cheque || '';
        document.getElementById('f_monto').value = cheque.monto;
        f_moneda.value = cheque.moneda;
        document.getElementById('f_fecha_emision').value = cheque.fecha_emision;
        document.getElementById('f_fecha_cobro').value = cheque.fecha_cobro;
        document.getElementById('f_contraparte').value = cheque.contraparte || '';
        document.getElementById('f_notas').value = cheque.notas || '';
        if (cheque.tipo === 'a_pagar') {
            poblarSelect(f_cuenta_origen, cuentasPorMoneda(cheque.moneda), cheque.cuenta_origen_pk);
        } else {
            document.getElementById('f_banco_librador').value = cheque.banco_librador || '';
            document.getElementById('f_titular_librador').value = cheque.titular_librador || '';
        }

        if (cheque.estado !== 'pendiente') {
            [...formCheque.querySelectorAll('input, select, button.chq-tipo-btn')].forEach(el => {
                if (el.id !== 'f_notas') el.disabled = true;
            });
        } else {
            [...formCheque.querySelectorAll('input, select, button.chq-tipo-btn')].forEach(el => { el.disabled = false; });
        }

        abrirModal();
    };

    window.eliminarCheque = async function (pk) {
        if (!await KaiConfirm('¿Estás seguro de eliminar este cheque?', { danger: true, confirmText: 'Eliminar' })) return;

        try {
            const response = await fetch(`${urlEliminarBase}${pk}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const result = await response.json();

            if (result.success) {
                cargarCheques();
            } else {
                KaiToast.show(result.error || 'Error al eliminar', 'danger');
            }
        } catch (error) {
            console.error('Error al eliminar:', error);
            KaiToast.show('Error al eliminar', 'danger');
        }
    };

    // ── Confirmar / Rechazar ─────────────────────────────────────────
    window.confirmarCheque = async function (pk) {
        const cheque = CHEQUES_CACHE.find(c => c.pk === pk);
        if (!cheque) return;

        if (cheque.tipo === 'a_pagar') {
            if (!await KaiConfirm('¿Confirmar el pago de este cheque? Esto va a impactar la caja.')) return;
            _confirmarChequeRequest(pk, null);
            return;
        }

        // a_cobrar: pedir la cuenta de destino
        chequeConfirmarActual = pk;
        poblarSelect(conf_cuenta_destino, cuentasPorMoneda(cheque.moneda));
        modalConfirmarCheque.hidden = false;
        document.body.style.overflow = 'hidden';
    };

    function cerrarModalConfirmar() {
        modalConfirmarCheque.hidden = true;
        document.body.style.overflow = '';
        chequeConfirmarActual = null;
    }
    btnCerrarConfirmar.addEventListener('click', cerrarModalConfirmar);
    btnCancelarConfirmar.addEventListener('click', cerrarModalConfirmar);
    modalConfirmarBackdrop.addEventListener('click', cerrarModalConfirmar);

    btnConfirmarCobro.addEventListener('click', () => {
        const cuentaPk = conf_cuenta_destino.value;
        if (!cuentaPk) {
            KaiToast.show('Elegí la cuenta donde vas a depositar el cheque.', 'warning');
            return;
        }
        const pk = chequeConfirmarActual;
        cerrarModalConfirmar();
        _confirmarChequeRequest(pk, cuentaPk);
    });

    async function _confirmarChequeRequest(pk, cuentaPk) {
        try {
            const response = await fetch(urlConfirmarCheque(pk), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify(cuentaPk ? { cuenta_pk: cuentaPk } : {}),
            });
            const result = await response.json();

            if (result.success) {
                cargarCheques();
            } else {
                KaiToast.show(result.error || 'Error al confirmar el cheque', 'danger');
            }
        } catch (error) {
            console.error('Error al confirmar:', error);
            KaiToast.show('Error al confirmar el cheque', 'danger');
        }
    }

    window.rechazarCheque = async function (pk) {
        if (!await KaiConfirm('¿Marcar este cheque como rechazado? Si ya estaba confirmado, se revierte el movimiento de caja.', { danger: true, confirmText: 'Rechazar' })) return;

        try {
            const response = await fetch(urlRechazarCheque(pk), {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const result = await response.json();

            if (result.success) {
                cargarCheques();
            } else {
                KaiToast.show(result.error || 'Error al rechazar el cheque', 'danger');
            }
        } catch (error) {
            console.error('Error al rechazar:', error);
            KaiToast.show('Error al rechazar el cheque', 'danger');
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
        cargarCheques();
    });

    btnLimpiarFiltros.addEventListener('click', () => {
        formFiltros.reset();
        paginaActual = 1;
        cargarCheques();
    });

    // ── Helpers ─────────────────────────────────────────────────────
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }

    // ── Inicialización ─────────────────────────────────────────────
    document.getElementById('f_fecha_emision').value = today;
    document.getElementById('f_fecha_cobro').value = today;
    cargarCheques();
});
