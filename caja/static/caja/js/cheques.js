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

    // La chequera de un cheque A_PAGAR solo puede ser una cuenta bancaria
    // real (no efectivo) — si no, un cheque quedaría "emitido desde
    // efectivo", que no existe en la realidad.
    function cuentasBancariasPorMoneda(moneda) {
        return CUENTAS.filter(c => c.moneda === moneda && c.tipo === 'banco');
    }

    function poblarSelect(select, opciones, seleccionarPk, placeholder) {
        select.innerHTML = `<option value="">${placeholder || '— Elegí una cuenta —'}</option>` +
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
    const f_cuenta_financiadora = document.getElementById('f_cuenta_financiadora');
    const campoFinanciadora = document.getElementById('campoFinanciadora');
    const campoBanco = document.getElementById('campoBanco');
    const f_banco = document.getElementById('f_banco');
    const lbl_emisor = document.getElementById('lbl_emisor');
    const lbl_receptor = document.getElementById('lbl_receptor');
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
        const esNuevo = !document.getElementById('chqPk').value;
        campoCuentaOrigen.hidden = !esPagar;
        campoFinanciadora.hidden = !(esPagar && esNuevo);
        campoBanco.hidden = esPagar;
        if (esPagar) f_banco.value = '';
        lbl_emisor.textContent = esPagar ? 'Emisor (opcional, firmante propio)' : 'Emisor (quién lo entregó)';
        lbl_receptor.textContent = esPagar ? 'Receptor (a quién se le paga)' : 'Receptor (opcional)';
        if (esPagar) {
            poblarSelect(f_cuenta_origen, cuentasBancariasPorMoneda(f_moneda.value));
            poblarSelect(f_cuenta_financiadora, cuentasPorMoneda(f_moneda.value), null, '— No hace falta, ya tiene fondos —');
            f_cuenta_financiadora.value = '';
        }
    }
    botonesTipo.forEach(btn => {
        btn.addEventListener('click', () => setTipo(btn.dataset.tipo));
    });
    f_moneda?.addEventListener('change', () => {
        if (f_tipo.value === 'a_pagar') {
            poblarSelect(f_cuenta_origen, cuentasBancariasPorMoneda(f_moneda.value));
            poblarSelect(f_cuenta_financiadora, cuentasPorMoneda(f_moneda.value), null, '— No hace falta, ya tiene fondos —');
        }
    });

    // ── Cargar cheques ────────────────────────────────────────────
    let ultimosCheques = [];

    async function cargarCheques() {
        const params = new URLSearchParams({
            pagina: paginaActual,
            por_pagina: porPagina,
            ...getFiltrosActivos(),
        });

        try {
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();

            ultimosCheques = data.results;
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
        const ICONO_VER = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M1 8C1 8 3.5 3 8 3C12.5 3 15 8 15 8C15 8 12.5 13 8 13C3.5 13 1 8 1 8Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.4"/></svg>`;

        chequesBody.innerHTML = cheques.map(c => {
            const acciones = [];
            if (c.estado === 'pendiente' && puedeConfirmar) {
                acciones.push(`<button type="button" class="icon-btn icon-btn--success" onclick="confirmarCheque(${c.pk})" title="Confirmar">${ICONO_CONFIRMAR}</button>`);
            }
            if (c.estado === 'pendiente' && puedeConfirmar) {
                acciones.push(`<button type="button" class="icon-btn icon-btn--danger" onclick="rechazarCheque(${c.pk})" title="Rechazar">${ICONO_RECHAZAR}</button>`);
            }
            if (c.estado === 'confirmado' && puedeConfirmar) {
                acciones.push(`<button type="button" class="icon-btn icon-btn--danger" onclick="rechazarCheque(${c.pk})" title="Marcar como rebotado (sin fondos / no se pudo cobrar)">${ICONO_RECHAZAR}</button>`);
            }
            if (puedeEditar && c.estado === 'pendiente') {
                acciones.push(`<button type="button" class="icon-btn" onclick="editarCheque(${c.pk})" title="Editar">${ICONO_EDITAR}</button>`);
            } else {
                acciones.push(`<button type="button" class="icon-btn" onclick="editarCheque(${c.pk})" title="Ver detalle">${ICONO_VER}</button>`);
            }
            if (puedeEliminar && c.estado !== 'confirmado') {
                acciones.push(`<button type="button" class="icon-btn" onclick="eliminarCheque(${c.pk})" title="Eliminar">${ICONO_ELIMINAR}</button>`);
            }
            return `
            <tr>
                <td><span class="chq-badge-tipo chq-badge-tipo--${c.tipo}">${c.tipo_display}</span></td>
                <td>${c.numero_cheque || '-'}</td>
                <td>${(c.tipo === 'a_pagar' ? c.receptor : c.emisor) || '-'}</td>
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
        [...formCheque.querySelectorAll('input, select, button.chq-tipo-btn')].forEach(el => { el.disabled = false; });
        btnGuardarCheque.hidden = false;
        btnCancelarModal.textContent = 'Cancelar';
        document.getElementById('chqPk').value = '';
        document.getElementById('f_fecha_emision').value = today;
        document.getElementById('f_fecha_cobro').value = today;
        setTipo('a_cobrar');
    }

    btnNuevoCheque?.addEventListener('click', () => {
        modalChequeTitulo.textContent = 'Nuevo cheque';
        btnGuardarCheque.hidden = false;
        btnCancelarModal.textContent = 'Cancelar';
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
        const f_monto_el = document.getElementById('f_monto');
        const f_fecha_emision_el = document.getElementById('f_fecha_emision');
        const f_fecha_cobro_el = document.getElementById('f_fecha_cobro');
        const f_numero_factura_el = document.getElementById('f_numero_factura');
        const data = {
            tipo: f_tipo.value,
            numero_cheque: document.getElementById('f_numero_cheque').value,
            emisor: document.getElementById('f_emisor').value,
            receptor: document.getElementById('f_receptor').value,
            banco: document.getElementById('f_banco').value,
            notas: document.getElementById('f_notas').value,
        };
        // Campos bloqueados por origen real (deshabilitados en editarCheque()
        // más abajo) — no se mandan, así el backend no los rechaza por venir
        // presentes aunque no hayan cambiado (ver EditarChequeAjax). Al crear
        // un cheque nuevo ninguno está deshabilitado, así que siempre viajan.
        if (!f_numero_factura_el.disabled) data.numero_factura = f_numero_factura_el.value;
        if (!f_monto_el.disabled) data.monto = f_monto_el.value;
        if (!f_moneda.disabled) data.moneda = f_moneda.value;
        if (!f_fecha_emision_el.disabled) data.fecha_emision = f_fecha_emision_el.value;
        if (!f_fecha_cobro_el.disabled) data.fecha_cobro = f_fecha_cobro_el.value;
        if (f_tipo.value === 'a_pagar') {
            if (!f_cuenta_origen.disabled) data.cuenta_origen_pk = f_cuenta_origen.value;
            if (!pk && f_cuenta_financiadora.value) {
                data.cuenta_financiadora_pk = f_cuenta_financiadora.value;
            }
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

        const soloVer = cheque.estado !== 'pendiente';
        modalChequeTitulo.textContent = soloVer ? 'Ver cheque' : 'Editar cheque';
        btnGuardarCheque.hidden = soloVer;
        btnCancelarModal.textContent = soloVer ? 'Cerrar' : 'Cancelar';
        document.getElementById('chqPk').value = cheque.pk;
        setTipo(cheque.tipo);
        document.getElementById('f_numero_cheque').value = cheque.numero_cheque || '';
        document.getElementById('f_numero_factura').value = cheque.numero_factura || '';
        document.getElementById('f_monto').value = cheque.monto;
        f_moneda.value = cheque.moneda;
        document.getElementById('f_fecha_emision').value = cheque.fecha_emision;
        document.getElementById('f_fecha_cobro').value = cheque.fecha_cobro;
        document.getElementById('f_emisor').value = cheque.emisor || '';
        document.getElementById('f_receptor').value = cheque.receptor || '';
        document.getElementById('f_banco').value = cheque.banco || '';
        document.getElementById('f_notas').value = cheque.notas || '';
        if (cheque.tipo === 'a_pagar') {
            poblarSelect(f_cuenta_origen, cuentasBancariasPorMoneda(cheque.moneda), cheque.cuenta_origen_pk);
        }

        [...formCheque.querySelectorAll('input, select, button.chq-tipo-btn')].forEach(el => {
            el.disabled = soloVer;
        });

        // Mientras está pendiente, un cheque con origen real (nació de una
        // venta/compra/cuota) sigue dejando ver el formulario completo,
        // pero el backend va a rechazar monto/moneda/fechas/cuenta si se
        // tocan (ver EditarChequeAjax) — reflejarlo acá, mismo criterio
        // que ya se aplicó en deudas.js/cuentas_cobrar.js. numero_cheque
        // (el número físico real, escrito a mano por quien lo emitió)
        // sigue editable siempre, en ambos tipos.
        if (!soloVer && cheque.tiene_origen_real) {
            document.getElementById('f_monto').disabled = true;
            f_moneda.disabled = true;
            document.getElementById('f_fecha_emision').disabled = true;
            document.getElementById('f_fecha_cobro').disabled = true;
            if (cheque.tipo === 'a_pagar') f_cuenta_origen.disabled = true;
            // numero_factura: en a_pagar es la factura real del proveedor
            // (tipeada a mano, puede corregirse) — solo se bloquea en
            // a_cobrar, donde es nuestro propio N° de venta.
            if (cheque.tipo === 'a_cobrar') {
                document.getElementById('f_numero_factura').disabled = true;
            }
        }

        abrirModal();
    };

    window.eliminarCheque = async function (pk) {
        const cheque = ultimosCheques.find(c => c.pk === pk);
        const mensaje = cheque && cheque.tiene_origen_real
            ? 'Este cheque nació de una venta/compra/cuota — si lo eliminás se pierde ese historial para siempre. ' +
              'Es mejor "Rechazar" desde acá si lo que pasó es que rebotó. ¿Eliminarlo igual?'
            : '¿Estás seguro de eliminar este cheque?';
        if (!await KaiConfirm(mensaje, { danger: true, confirmText: 'Eliminar' })) return;

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
        poblarSelect(conf_cuenta_destino, cuentasBancariasPorMoneda(cheque.moneda));
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
        const cheque = CHEQUES_CACHE.find(c => c.pk === pk);
        const mensaje = cheque && cheque.estado === 'confirmado'
            ? '¿El cheque rebotó (no se pudo cobrar / no había fondos)? Se revierte el movimiento de caja que ya se había generado.'
            : '¿Marcar este cheque como rechazado?';
        if (!await KaiConfirm(mensaje, { danger: true, confirmText: 'Rechazar' })) return;

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

    // Deep-link de filtros: permite llegar acá desde otra pantalla
    // (ej. "Pendiente de Cobro" en Caja Diaria) ya filtrado por
    // ?tipo=a_cobrar&estado=pendiente, sin tener que tocar nada.
    const paramsUrl = new URLSearchParams(window.location.search);
    let hayFiltroPorUrl = false;
    ['tipo', 'estado', 'moneda', 'q'].forEach((campo) => {
        const valor = paramsUrl.get(campo);
        if (valor) {
            const idCampo = campo === 'q' ? 'fQ' : `f${campo.charAt(0).toUpperCase()}${campo.slice(1)}`;
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

    cargarCheques();
});
