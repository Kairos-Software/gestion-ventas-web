document.addEventListener('DOMContentLoaded', function () {
    const urls = window.resumenesTarjetaUrls;
    const wrap = document.getElementById('resumenesTarjetaWrap');
    if (!urls || !wrap) return;

    const puedeConfirmar = window.resumenesTarjetaPuedeConfirmar;
    const puedeEditar = window.resumenesTarjetaPuedeEditar;

    const cuentasDataEl = document.getElementById('cuentas-data');
    const CUENTAS = cuentasDataEl ? JSON.parse(cuentasDataEl.textContent) : [];

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
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

    function esc(str) {
        return String(str == null ? '' : str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    // ── Modal detalle/pago ──────────────────────────────────────────
    const modal = document.getElementById('modalResumenTarjeta');
    const modalBackdrop = document.getElementById('modalResumenTarjetaBackdrop');
    const btnCerrar = document.getElementById('btnCerrarResumenTarjeta');
    const rtTitle = document.getElementById('rtTitle');
    const rtSubtitle = document.getElementById('rtSubtitle');
    const rtResumenTop = document.getElementById('rtResumenTop');
    const rtCuotasBody = document.getElementById('rtCuotasBody');
    const rtBloqueAjuste = document.getElementById('rtBloqueAjuste');
    const rtAjusteMonto = document.getElementById('rtAjusteMonto');
    const rtAjusteDescripcion = document.getElementById('rtAjusteDescripcion');
    const rtAjusteMsg = document.getElementById('rtAjusteMsg');
    const btnGuardarAjusteResumen = document.getElementById('btnGuardarAjusteResumen');
    const btnQuitarAjusteResumen = document.getElementById('btnQuitarAjusteResumen');
    const rtAjustePagadoNota = document.getElementById('rtAjustePagadoNota');
    const rtBloquePago = document.getElementById('rtBloquePago');
    const rtSaldoWrap = document.getElementById('rtSaldoWrap');
    const rtSaldoLabel = document.getElementById('rtSaldoLabel');
    const rtCampoCuentaPago = document.getElementById('rtCampoCuentaPago');
    const rtCuentaPago = document.getElementById('rtCuentaPago');
    const rtPagoMsg = document.getElementById('rtPagoMsg');
    const btnPagarResumen = document.getElementById('btnPagarResumen');
    const btnDeshacerPagoResumen = document.getElementById('btnDeshacerPagoResumen');

    let resumenActual = null;
    let focoAntesDelModal = null;

    // ── Filtros (solo existen en la pantalla dedicada) ──────────────
    const btnToggleFiltrosResumen = document.getElementById('btnToggleFiltrosResumen');
    const formFiltrosResumen = document.getElementById('formFiltrosResumen');
    const btnLimpiarFiltrosResumen = document.getElementById('btnLimpiarFiltrosResumen');
    const fResumenTarjeta = document.getElementById('fResumenTarjeta');
    const fResumenEstado = document.getElementById('fResumenEstado');
    const botonesVistaResumen = document.querySelectorAll('.deudas-modo-seg-btn[data-vista]');
    let vistaResumen = 'pendientes';
    let cachePendientes = [];
    let cachePagados = [];

    btnToggleFiltrosResumen?.addEventListener('click', () => {
        const expanded = btnToggleFiltrosResumen.getAttribute('aria-expanded') === 'true';
        btnToggleFiltrosResumen.setAttribute('aria-expanded', !expanded);
        formFiltrosResumen.hidden = expanded;
    });

    formFiltrosResumen?.addEventListener('submit', (e) => {
        e.preventDefault();
        cargarResumenes();
    });

    btnLimpiarFiltrosResumen?.addEventListener('click', () => {
        formFiltrosResumen.reset();
        cargarResumenes();
    });

    function abrirModal() {
        focoAntesDelModal = document.activeElement;
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
        window.requestAnimationFrame(() => modal.focus({ preventScroll: true }));
    }

    function cerrarModal() {
        modal.hidden = true;
        document.body.style.overflow = '';
        resumenActual = null;
        if (focoAntesDelModal && focoAntesDelModal.isConnected) {
            window.requestAnimationFrame(() => focoAntesDelModal.focus({ preventScroll: true }));
        }
        focoAntesDelModal = null;
    }

    btnCerrar?.addEventListener('click', cerrarModal);
    modalBackdrop?.addEventListener('click', cerrarModal);
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !modal.hidden) {
            event.preventDefault();
            cerrarModal();
        }
    });

    function poblarCuentasPago(moneda) {
        if (!rtCuentaPago) return;
        const reales = CUENTAS.filter(c => c.moneda === moneda && !c.es_credito);
        const preferida = reales.find(c => c.preferida);
        rtCuentaPago.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            reales.map(c => `<option value="${c.pk}">${esc(c.nombre)}${c.titular ? ' · ' + esc(c.titular) : ''}</option>`).join('');
        if (preferida) rtCuentaPago.value = String(preferida.pk);
    }

    function renderModal(r) {
        resumenActual = r;
        rtTitle.textContent = `Resumen ${r.periodo_label}`;
        rtSubtitle.textContent = r.cuenta_tarjeta_nombre;

        const item = (label, valor, highlight) => `<div class="deudas-resumen-item${highlight ? ' deudas-resumen-item--highlight' : ''}"><span class="deudas-resumen-label">${label}</span><div class="deudas-resumen-value">${valor}</div></div>`;
        rtResumenTop.innerHTML = `<div class="deudas-resumen-grid">${[
            item('Tarjeta', esc(r.cuenta_tarjeta_nombre)),
            item('Período', esc(r.periodo_label)),
            item('Cierra', r.fecha_cierre ? fmtFecha(r.fecha_cierre) : 'Sin configurar'),
            item('Vence', r.fecha_vencimiento ? fmtFecha(r.fecha_vencimiento) : 'Sin configurar'),
            item('Cuotas del período', fmtMoneda(r.monto_cuotas, r.moneda)),
            item('Cargo propio', fmtMoneda(r.monto_ajuste, r.moneda)),
            item('Total del resumen', fmtMoneda(r.monto_total, r.moneda)),
            item('Saldo pendiente', fmtMoneda(r.saldo_pendiente, r.moneda), true),
        ].join('')}</div>`;

        rtCuotasBody.innerHTML = (r.cuotas || []).map(c => {
            const estadoLabel = c.estado === 'confirmada' ? 'Pagada' : c.estado === 'anulada' ? 'Anulada' : 'Pendiente';
            let pagoMeta = '';
            if (c.estado === 'confirmada') {
                if (c.es_historica) {
                    pagoMeta = '<div class="deudas-cuota-pago">histórica — no afectó caja</div>';
                } else if (c.fecha_confirmacion) {
                    const cuenta = c.cuenta_pago_nombre ? ` · ${esc(c.cuenta_pago_nombre)}` : '';
                    pagoMeta = `<div class="deudas-cuota-pago">${fmtFecha(c.fecha_confirmacion.slice(0, 10))}${cuenta}</div>`;
                }
            }
            return `
            <tr class="deudas-cuota-row deudas-cuota-row--${c.estado}">
                <td data-label="Compra">${esc(c.deuda_descripcion)}${c.compra_numero ? ` (${esc(c.compra_numero)})` : ''}</td>
                <td data-label="Cuota">${c.numero}${c.cantidad_cuotas ? '/' + c.cantidad_cuotas : ''}</td>
                <td data-label="Vencimiento">${fmtFecha(c.fecha_vencimiento)}</td>
                <td data-label="Monto" class="deudas-monto">${fmtMoneda(c.monto, r.moneda)}</td>
                <td data-label="Estado"><span class="deudas-badge-estado deudas-badge-estado--${c.estado}">${estadoLabel}</span>${pagoMeta}</td>
            </tr>
        `;
        }).join('') || '<tr><td colspan="5" class="deudas-tabla-loading">Sin cuotas en este período.</td></tr>';

        if (rtBloqueAjuste) {
            rtAjusteMonto.value = parseFloat(r.monto_ajuste) ? r.monto_ajuste : '';
            rtAjusteDescripcion.value = r.descripcion_ajuste || '';
            rtAjusteMsg.textContent = '';
            const bloqueado = r.ajuste_pagado;
            rtAjusteMonto.disabled = bloqueado;
            rtAjusteDescripcion.disabled = bloqueado;
            btnGuardarAjusteResumen.hidden = bloqueado;
            if (btnQuitarAjusteResumen) btnQuitarAjusteResumen.hidden = bloqueado || !parseFloat(r.monto_ajuste);
            rtAjustePagadoNota.hidden = !bloqueado;
            if (bloqueado) {
                const cuenta = r.cuenta_pago_ajuste_nombre ? ` con ${esc(r.cuenta_pago_ajuste_nombre)}` : '';
                const fecha = r.fecha_pago_ajuste ? ` el ${fmtFecha(r.fecha_pago_ajuste.slice(0, 10))}` : '';
                rtAjustePagadoNota.textContent = `Ya se pagó el cargo de este resumen${fecha}${cuenta} — no se puede editar.`;
            }
        }

        if (rtBloquePago) {
            rtPagoMsg.textContent = '';
            const saldo = parseFloat(r.saldo_pendiente);
            const hayPagoReal = (r.cuotas || []).some(c => c.estado === 'confirmada' && !c.es_historica) || r.ajuste_pagado;
            if (saldo > 0) {
                rtSaldoLabel.textContent = fmtMoneda(r.saldo_pendiente, r.moneda);
                poblarCuentasPago(r.moneda);
                rtCampoCuentaPago.hidden = false;
                btnPagarResumen.hidden = false;
            } else {
                rtSaldoLabel.textContent = 'Ya está todo pagado';
                rtCampoCuentaPago.hidden = true;
                btnPagarResumen.hidden = true;
            }
            if (btnDeshacerPagoResumen) btnDeshacerPagoResumen.hidden = !hayPagoReal;
        }
    }

    async function abrirDetalle(pk) {
        try {
            const response = await fetch(urls.detalle.replace('/0/', `/${pk}/`));
            const data = await response.json();
            if (!data.resumen) {
                KaiToast.show(data.error || 'No se pudo cargar el resumen.', 'danger');
                return;
            }
            renderModal(data.resumen);
            abrirModal();
        } catch (error) {
            console.error('Error al abrir el resumen:', error);
            KaiToast.show('No se pudo cargar el resumen. Revisá la conexión e intentá de nuevo.', 'danger');
        }
    }
    window.verResumenTarjeta = abrirDetalle;

    btnGuardarAjusteResumen?.addEventListener('click', async () => {
        if (!resumenActual) return;
        rtAjusteMsg.textContent = '';
        try {
            const response = await fetch(urls.editarAjuste.replace('/0/', `/${resumenActual.pk}/`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    monto_ajuste: rtAjusteMonto.value || 0,
                    descripcion_ajuste: rtAjusteDescripcion.value,
                }),
            });
            const data = await response.json();
            if (data.error) {
                rtAjusteMsg.textContent = data.error;
                return;
            }
            renderModal(data.resumen);
            cargarResumenes();
        } catch (error) {
            rtAjusteMsg.textContent = 'Error de conexión.';
            console.error(error);
        }
    });

    btnQuitarAjusteResumen?.addEventListener('click', async () => {
        if (!resumenActual) return;
        if (!await KaiConfirm(
            '¿Quitar el cargo propio de este resumen? El monto y la descripción se borran y ya no suman '
            + 'al total.',
            { danger: true, confirmText: 'Quitar cargo' },
        )) return;
        rtAjusteMsg.textContent = '';
        try {
            const response = await fetch(urls.editarAjuste.replace('/0/', `/${resumenActual.pk}/`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ monto_ajuste: 0, descripcion_ajuste: '' }),
            });
            const data = await response.json();
            if (data.error) {
                rtAjusteMsg.textContent = data.error;
                return;
            }
            renderModal(data.resumen);
            cargarResumenes();
        } catch (error) {
            rtAjusteMsg.textContent = 'Error de conexión.';
            console.error(error);
        }
    });

    btnPagarResumen?.addEventListener('click', async () => {
        if (!resumenActual) return;
        if (!rtCuentaPago.value) {
            rtPagoMsg.textContent = 'Elegí con qué cuenta se paga.';
            return;
        }
        if (!await KaiConfirm(
            '¿Pagar el resumen completo? Va a impactar la caja: confirma todas las cuotas pendientes '
            + 'de este período (y el cargo propio, si tiene) con la cuenta elegida.',
        )) return;
        rtPagoMsg.textContent = '';
        btnPagarResumen.disabled = true;
        try {
            const response = await fetch(urls.pagar.replace('/0/', `/${resumenActual.pk}/`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ cuenta_pk: rtCuentaPago.value }),
            });
            const data = await response.json();
            if (data.error) {
                rtPagoMsg.textContent = data.error;
                return;
            }
            // Recarga entera: confirmar cada cuota del resumen también
            // cambia el Historial de abajo y la barra "Debés" — más simple
            // y seguro que tratar de sincronizar a mano el estado de
            // deudas.js (un módulo aparte) con lo que acaba de pagarse acá.
            window.location.reload();
        } catch (error) {
            rtPagoMsg.textContent = 'Error de conexión.';
            console.error(error);
        } finally {
            btnPagarResumen.disabled = false;
        }
    });

    btnDeshacerPagoResumen?.addEventListener('click', async () => {
        if (!resumenActual) return;
        if (!await KaiConfirm(
            '¿Deshacer el pago de este resumen? Revierte TODAS las cuotas de este período que estén '
            + 'pagadas de verdad (la plata vuelve a la cuenta con la que se pagaron, o se rechaza el '
            + 'cheque) y el cargo propio si lo habías pagado. Las cuotas históricas (carga inicial) no '
            + 'se tocan.',
            { danger: true, confirmText: 'Deshacer pago' },
        )) return;
        rtPagoMsg.textContent = '';
        btnDeshacerPagoResumen.disabled = true;
        try {
            const response = await fetch(urls.deshacerPago.replace('/0/', `/${resumenActual.pk}/`), {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            const data = await response.json();
            if (data.error) {
                rtPagoMsg.textContent = data.error;
                return;
            }
            // Misma razón que en "pagar": revertir cuotas también cambia
            // el Historial de Deudas y la barra "Debés".
            window.location.reload();
        } catch (error) {
            rtPagoMsg.textContent = 'Error de conexión.';
            console.error(error);
        } finally {
            btnDeshacerPagoResumen.disabled = false;
        }
    });

    // ── Listado: tabla, igual que Deudas, separada en Pendientes/Pagados ──
    function renderFila(r) {
        const estadoLabel = { pendiente: 'Pendiente', parcial: 'Pago parcial', pagado: 'Pagado' }[r.estado] || r.estado_display;
        return `
            <tr>
                <td data-label="Tarjeta">${esc(r.cuenta_tarjeta_nombre)}</td>
                <td data-label="Período">${esc(r.periodo_label)}</td>
                <td data-label="Cierra">${r.fecha_cierre ? fmtFecha(r.fecha_cierre) : '—'}</td>
                <td data-label="Vence">${r.fecha_vencimiento ? fmtFecha(r.fecha_vencimiento) : '—'}</td>
                <td data-label="Total" class="deudas-monto">${fmtMoneda(r.monto_total, r.moneda)}</td>
                <td data-label="Estado"><span class="deudas-badge-estado deudas-badge-estado--${r.estado}">${estadoLabel}</span></td>
                <td data-label="Acciones">
                    <div class="deudas-tabla-acciones">
                        <button type="button" class="btn btn-ghost btn--sm" onclick="verResumenTarjeta(${r.pk})">Ver detalle</button>
                    </div>
                </td>
            </tr>
        `;
    }

    function renderTabla(lista, vacioTexto) {
        return `
            <div class="deudas-tabla-wrap">
                <table class="deudas-tabla">
                    <thead>
                        <tr>
                            <th>Tarjeta</th>
                            <th>Período</th>
                            <th>Cierra</th>
                            <th>Vence</th>
                            <th class="th-monto">Total</th>
                            <th>Estado</th>
                            <th class="th-acciones">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>${lista.length ? lista.map(renderFila).join('') : `<tr><td colspan="7" class="deudas-tabla-loading">${vacioTexto}</td></tr>`}</tbody>
                </table>
            </div>
        `;
    }

    function renderVistaResumenes() {
        botonesVistaResumen.forEach(b => {
            const activo = b.dataset.vista === vistaResumen;
            b.classList.toggle('deudas-modo-seg-btn--active', activo);
            b.setAttribute('aria-pressed', String(activo));
        });
        if (vistaResumen === 'pagados') {
            wrap.innerHTML = renderTabla(cachePagados, 'Todavía no se pagó ningún resumen con estos filtros.');
        } else {
            wrap.innerHTML = renderTabla(cachePendientes, 'No hay resúmenes pendientes con estos filtros.');
        }
    }

    botonesVistaResumen.forEach(b => b.addEventListener('click', () => {
        vistaResumen = b.dataset.vista;
        renderVistaResumenes();
    }));

    async function cargarResumenes() {
        try {
            const params = new URLSearchParams();
            if (fResumenTarjeta?.value) params.set('cuenta_tarjeta_pk', fResumenTarjeta.value);
            if (fResumenEstado?.value) params.set('estado', fResumenEstado.value);
            const qs = params.toString();
            const response = await fetch(qs ? `${urls.listar}?${qs}` : urls.listar);
            const data = await response.json();
            const results = data.results || [];
            if (results.length === 0) {
                cachePendientes = [];
                cachePagados = [];
                wrap.innerHTML = '<p class="deudas-tabla-loading">No hay compras con tarjeta de crédito todavía.</p>';
                return;
            }
            cachePendientes = results.filter(r => r.estado !== 'pagado');
            cachePagados = results.filter(r => r.estado === 'pagado');
            botonesVistaResumen.forEach(b => {
                b.textContent = b.dataset.vista === 'pagados'
                    ? `Pagados (${cachePagados.length})`
                    : `Pendientes (${cachePendientes.length})`;
            });
            renderVistaResumenes();
        } catch (error) {
            wrap.innerHTML = '<p class="deudas-tabla-loading">Error al cargar los resúmenes.</p>';
            console.error('Error al cargar resúmenes de tarjeta:', error);
        }
    }

    cargarResumenes();

    // Si se llega desde el resumen compacto de Deudas (?resumen=<pk>),
    // abre directo el detalle en vez de solo mostrar la grilla.
    const resumenAAbrir = new URLSearchParams(window.location.search).get('resumen');
    if (resumenAAbrir) abrirDetalle(resumenAAbrir);
});
