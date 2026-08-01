document.addEventListener('DOMContentLoaded', function () {
    const urls = window.cxcUrls;
    const puedeConfirmar = window.cxcPuedeConfirmar;
    const puedeEditar = window.cxcPuedeEditar;
    const today = window.cxcToday;

    // ── Cuentas reales (para el select de "confirmar cobro") ──
    const cuentasDataEl = document.getElementById('cuentas-data');
    const CUENTAS = cuentasDataEl ? JSON.parse(cuentasDataEl.textContent) : [];

    function cuentasPorMoneda(moneda) {
        return CUENTAS.filter(c => c.moneda === moneda);
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

    let paginaActual = 1;
    let porPagina = 50;
    let cxcDetalleActual = null;

    // ── Elementos DOM ───────────────────────────────────────────────
    const btnToggleFiltros = document.getElementById('btnToggleFiltros');
    const formFiltros = document.getElementById('formFiltros');
    const btnLimpiarFiltros = document.getElementById('btnLimpiarFiltros');
    const cxcBody = document.getElementById('cxcBody');
    const paginacionContainer = document.getElementById('paginacionContainer');

    // Modal detalle
    const modalDetalle = document.getElementById('modalDetalle');
    const modalDetalleBackdrop = document.getElementById('modalDetalleBackdrop');
    const btnCerrarDetalle = document.getElementById('btnCerrarDetalle');
    const detalleResumen = document.getElementById('detalleResumen');
    const detNotas = document.getElementById('detNotas');
    const cuotasBody = document.getElementById('cuotasBody');
    const btnGuardarNotas = document.getElementById('btnGuardarNotas');
    const btnEliminarCxc = document.getElementById('btnEliminarCxc');

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
        } catch (error) {
            console.error('Error al cargar cuentas por cobrar:', error);
            cxcBody.innerHTML = '<tr><td colspan="7" class="cxc-tabla-loading">Error al cargar</td></tr>';
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

    function renderizarCxc(items) {
        if (!items || items.length === 0) {
            cxcBody.innerHTML = '<tr><td colspan="7" class="cxc-tabla-loading">No hay cuentas por cobrar registradas</td></tr>';
            return;
        }

        cxcBody.innerHTML = items.map(c => `
            <tr>
                <td>${c.cliente_nombre || '-'}</td>
                <td>${c.venta_numero || c.descripcion || '-'}</td>
                <td class="cxc-monto">${fmtMoneda(c.monto_total, c.moneda)}</td>
                <td class="cxc-monto">${fmtMoneda(c.saldo_pendiente, c.moneda)}</td>
                <td>${c.cuotas_cobradas}/${c.cantidad_cuotas}</td>
                <td><span class="cxc-badge-estado cxc-badge-estado--${c.estado}">${c.estado_display}</span></td>
                <td>
                    <div class="cxc-tabla-acciones">
                        <button type="button" class="btn btn-ghost btn--sm" onclick="verCxc(${c.pk})">Ver cuotas</button>
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

    function renderizarDetalle(d) {
        detalleResumen.innerHTML = `
            <div class="cxc-resumen-row"><span>Cliente</span><strong>${d.cliente_nombre || '-'}</strong></div>
            <div class="cxc-resumen-row"><span>Venta</span><strong>${d.venta_numero || d.descripcion || '-'}</strong></div>
            <div class="cxc-resumen-row"><span>Monto original</span><strong>${fmtMoneda(d.monto_original, d.moneda)}</strong></div>
            <div class="cxc-resumen-row"><span>Interés</span><strong>${d.porcentaje_interes}%</strong></div>
            <div class="cxc-resumen-row"><span>Monto total</span><strong>${fmtMoneda(d.monto_total, d.moneda)}</strong></div>
            <div class="cxc-resumen-row"><span>Saldo pendiente</span><strong>${fmtMoneda(d.saldo_pendiente, d.moneda)}</strong></div>
            <div class="cxc-resumen-row"><span>Estado</span><span class="cxc-badge-estado cxc-badge-estado--${d.estado}">${d.estado_display}</span></div>
        `;

        detNotas.value = d.notas || '';
        detNotas.disabled = !puedeEditar;
        if (btnGuardarNotas) btnGuardarNotas.disabled = !puedeEditar;
        if (btnEliminarCxc) btnEliminarCxc.disabled = d.cuotas.some(c => c.estado === 'confirmada');

        const cuentasCobro = cuentasPorMoneda(d.moneda);

        cuotasBody.innerHTML = d.cuotas.map(c => {
            let accion = '-';
            if (c.estado === 'pendiente' && puedeConfirmar && c.habilitada) {
                accion = `
                    <div class="cxc-cuota-confirmar">
                        <select id="cuentaCuota${c.pk}" class="cxc-cuota-select"
                                onchange="onCuentaCuotaChange(this, ${c.pk}, ${c.monto}, '${d.moneda}', false)">
                            ${cuentasCobro.map(cta => `<option value="${cta.pk}">${cta.nombre}</option>`).join('')}
                            <option value="__cheque__">— Cobrar con cheque —</option>
                        </select>
                        <button type="button" class="btn btn-primary btn--sm" onclick="confirmarCuotaCobro(${c.pk})">Confirmar</button>
                    </div>`;
            } else if (c.estado === 'pendiente' && !c.habilitada && puedeConfirmar) {
                accion = `
                    <div class="cxc-cuota-confirmar">
                        <select id="cuentaCuota${c.pk}" class="cxc-cuota-select"
                                onchange="onCuentaCuotaChange(this, ${c.pk}, ${c.monto}, '${d.moneda}', true)">
                            ${cuentasCobro.map(cta => `<option value="${cta.pk}">${cta.nombre}</option>`).join('')}
                            <option value="__cheque__">— Cobrar con cheque —</option>
                        </select>
                        <button type="button" class="btn btn-secondary btn--sm" onclick="confirmarCuotaCobro(${c.pk}, true)">Adelantar cobro</button>
                        <span class="cxc-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>
                    </div>`;
            } else if (c.estado === 'pendiente' && !c.habilitada) {
                accion = `<span class="cxc-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>`;
            } else if (c.estado === 'confirmada' && c.cheque_pk) {
                accion = `Cheque #${c.cheque_numero} (${c.cheque_estado}) <span class="cxc-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            } else if (c.estado === 'confirmada') {
                accion = `${c.cuenta_cobro_nombre} <span class="cxc-cuota-fecha">(${c.fecha_confirmacion ? c.fecha_confirmacion.slice(0, 10) : ''})</span>`;
            }
            return `
                <tr>
                    <td>${c.numero}</td>
                    <td>${c.fecha_vencimiento}</td>
                    <td class="cxc-monto">${fmtMoneda(c.monto, d.moneda)}</td>
                    <td><span class="cxc-badge-estado cxc-badge-estado--${c.estado === 'confirmada' ? 'activa' : c.estado === 'anulada' ? 'anulada' : 'pendiente'}">${c.estado}</span></td>
                    <td>${accion}</td>
                </tr>`;
        }).join('');
    }

    window.confirmarCuotaCobro = async function (cuotaPk, adelantar = false) {
        const select = document.getElementById(`cuentaCuota${cuotaPk}`);
        const cuentaPk = select ? select.value : '';
        if (!cuentaPk) {
            KaiToast.show('Elegí la cuenta a la que entra el cobro.', 'warning');
            return;
        }
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
                body: JSON.stringify({ cuenta_pk: cuentaPk, adelantar }),
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
    let chequeCuotaActual = null; // { cuotaPk, adelantar, monto }

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

    window.abrirModalChequeCuota = function (cuotaPk, monto, moneda, adelantar) {
        chequeCuotaActual = { cuotaPk, adelantar, monto };
        document.getElementById('cchcMontoLabel').textContent = fmtMoneda(monto, moneda);
        document.getElementById('cchc_numero_cheque').value = '';
        document.getElementById('cchc_fecha_emision').value = today;
        document.getElementById('cchc_fecha_cobro').value = today;
        document.getElementById('cchc_emisor').value = '';
        document.getElementById('cchc_banco').value = '';
        document.getElementById('cchcMsg').textContent = '';

        modalChequeCuota.hidden = false;
        document.body.style.overflow = 'hidden';
    };

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

        if (!await KaiConfirm('¿Cobrar esta cuota con este cheque? La cuota queda confirmada ya mismo; el ingreso real de caja se genera recién cuando confirmes/deposites el cheque desde la pantalla de Cheques.')) return;

        btnGuardarChequeCuota.disabled = true;
        try {
            const response = await fetch(urlConfirmarCuota(chequeCuotaActual.cuotaPk), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    adelantar: chequeCuotaActual.adelantar,
                    cheque: {
                        numero_cheque: document.getElementById('cchc_numero_cheque').value,
                        monto: chequeCuotaActual.monto,
                        fecha_emision: fechaEmision,
                        fecha_cobro: fechaCobro,
                        emisor: document.getElementById('cchc_emisor').value,
                        banco: document.getElementById('cchc_banco').value,
                    },
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

    btnGuardarNotas?.addEventListener('click', async () => {
        if (!cxcDetalleActual) return;
        try {
            const response = await fetch(`${urlEditarBase}${cxcDetalleActual.pk}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ notas: detNotas.value }),
            });
            const result = await response.json();
            if (result.success) {
                cargarCxc();
            } else {
                KaiToast.show(result.error || 'Error al guardar', 'danger');
            }
        } catch (error) {
            console.error('Error al guardar notas:', error);
            KaiToast.show('Error al guardar notas', 'danger');
        }
    });

    btnEliminarCxc?.addEventListener('click', async () => {
        if (!cxcDetalleActual) return;
        if (!await KaiConfirm('¿Estás seguro de eliminar esta cuenta por cobrar?', { danger: true, confirmText: 'Eliminar' })) return;

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
    cargarCxc();
});
