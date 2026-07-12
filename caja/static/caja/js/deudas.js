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
    const botonesTipo = document.querySelectorAll('.deudas-tipo-btn');

    // Modal detalle
    const modalDetalle = document.getElementById('modalDetalle');
    const modalDetalleBackdrop = document.getElementById('modalDetalleBackdrop');
    const btnCerrarDetalle = document.getElementById('btnCerrarDetalle');
    const detalleResumen = document.getElementById('detalleResumen');
    const detNotas = document.getElementById('detNotas');
    const cuotasBody = document.getElementById('cuotasBody');
    const btnGuardarNotas = document.getElementById('btnGuardarNotas');
    const btnEliminarDeuda = document.getElementById('btnEliminarDeuda');

    // ── Toggle tipo compra_credito/prestamo ──────────────────────────
    function setTipo(tipo) {
        dTipo.value = tipo;
        botonesTipo.forEach(btn => {
            btn.classList.toggle('deudas-tipo-btn--active', btn.dataset.tipo === tipo);
        });
        const esCredito = tipo === 'compra_credito';
        campoTarjeta.hidden = !esCredito;
        campoAcreditacion.hidden = esCredito;
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
        } catch (error) {
            console.error('Error al cargar deudas:', error);
            deudasBody.innerHTML = '<tr><td colspan="6" class="deudas-tabla-loading">Error al cargar deudas</td></tr>';
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

    function renderizarDeudas(deudas) {
        if (!deudas || deudas.length === 0) {
            deudasBody.innerHTML = '<tr><td colspan="6" class="deudas-tabla-loading">No hay deudas registradas</td></tr>';
            return;
        }

        deudasBody.innerHTML = deudas.map(d => `
            <tr>
                <td><span class="deudas-badge-tipo deudas-badge-tipo--${d.tipo}">${d.tipo_display}</span></td>
                <td>${d.descripcion || d.compra_numero || '-'}</td>
                <td class="deudas-monto">${fmtMoneda(d.monto_total, d.moneda)}</td>
                <td>${d.cuotas_pagadas}/${d.cantidad_cuotas}</td>
                <td><span class="deudas-badge-estado deudas-badge-estado--${d.estado}">${d.estado_display}</span></td>
                <td>
                    <div class="deudas-tabla-acciones">
                        <button type="button" class="btn btn-ghost btn--sm" onclick="verDeuda(${d.pk})">Ver cuotas</button>
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
    }

    btnNuevaDeuda?.addEventListener('click', () => {
        document.getElementById('dFechaInicio').value = today;
        setTipo('compra_credito');
        abrirModal();
    });

    btnCerrarModal.addEventListener('click', cerrarModal);
    btnCancelarModal.addEventListener('click', cerrarModal);
    modalBackdrop.addEventListener('click', cerrarModal);

    formDeuda.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData(formDeuda);
        const data = Object.fromEntries(formData.entries());

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
                alert(result.error || 'Error al guardar');
            }
        } catch (error) {
            console.error('Error al guardar:', error);
            alert('Error al guardar');
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
                alert('Deuda no encontrada');
                return;
            }

            deudaDetalleActual = data.deuda;
            renderizarDetalle(data.deuda);
            abrirDetalle();
        } catch (error) {
            console.error('Error al cargar deuda:', error);
            alert('Error al cargar deuda');
        }
    };

    function renderizarDetalle(d) {
        const cuentaLabel = d.tipo === 'compra_credito' ? 'Tarjeta' : 'Cuenta acreditada';
        const cuentaValor = d.tipo === 'compra_credito'
            ? (d.cuenta_tarjeta_nombre || '-')
            : (d.cuenta_acreditacion_nombre || '-');

        detalleResumen.innerHTML = `
            <div class="deudas-resumen-row"><span>Tipo</span><strong>${d.tipo_display}</strong></div>
            <div class="deudas-resumen-row"><span>Descripción</span><strong>${d.descripcion || d.compra_numero || '-'}</strong></div>
            <div class="deudas-resumen-row"><span>${cuentaLabel}</span><strong>${cuentaValor}</strong></div>
            <div class="deudas-resumen-row"><span>Monto original</span><strong>${fmtMoneda(d.monto_original, d.moneda)}</strong></div>
            <div class="deudas-resumen-row"><span>Interés</span><strong>${d.porcentaje_interes}%</strong></div>
            <div class="deudas-resumen-row"><span>Monto total</span><strong>${fmtMoneda(d.monto_total, d.moneda)}</strong></div>
            <div class="deudas-resumen-row"><span>Saldo pendiente</span><strong>${fmtMoneda(d.saldo_pendiente, d.moneda)}</strong></div>
            <div class="deudas-resumen-row"><span>Estado</span><span class="deudas-badge-estado deudas-badge-estado--${d.estado}">${d.estado_display}</span></div>
        `;

        detNotas.value = d.notas || '';
        detNotas.disabled = !puedeEditar;
        if (btnGuardarNotas) btnGuardarNotas.disabled = !puedeEditar;
        if (btnEliminarDeuda) btnEliminarDeuda.disabled = d.cuotas.some(c => c.estado === 'confirmada');

        const cuentasPago = cuentasPorMoneda(d.moneda, false);

        cuotasBody.innerHTML = d.cuotas.map(c => {
            let accion = '-';
            if (c.estado === 'pendiente' && puedeConfirmar && c.habilitada) {
                accion = `
                    <div class="deudas-cuota-confirmar">
                        <select id="cuentaCuota${c.pk}" class="deudas-cuota-select">
                            ${cuentasPago.map(cta => `<option value="${cta.pk}">${cta.nombre}</option>`).join('')}
                        </select>
                        <button type="button" class="btn btn-primary btn--sm" onclick="confirmarCuota(${c.pk})">Confirmar</button>
                    </div>`;
            } else if (c.estado === 'pendiente' && !c.habilitada) {
                accion = `<span class="deudas-cuota-fecha">Se habilita el ${c.fecha_vencimiento}</span>`;
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

    window.confirmarCuota = async function (cuotaPk) {
        const select = document.getElementById(`cuentaCuota${cuotaPk}`);
        const cuentaPk = select ? select.value : '';
        if (!cuentaPk) {
            alert('Elegí la cuenta de la que sale el pago.');
            return;
        }
        if (!confirm('¿Confirmar el pago de esta cuota? Esto va a impactar la caja.')) return;

        try {
            const response = await fetch(urlConfirmarCuota(cuotaPk), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ cuenta_pk: cuentaPk }),
            });
            const result = await response.json();

            if (result.success) {
                window.verDeuda(deudaDetalleActual.pk);
                cargarDeudas();
            } else {
                alert(result.error || 'Error al confirmar la cuota');
            }
        } catch (error) {
            console.error('Error al confirmar cuota:', error);
            alert('Error al confirmar la cuota');
        }
    };

    btnGuardarNotas?.addEventListener('click', async () => {
        if (!deudaDetalleActual) return;
        try {
            const response = await fetch(`${urlEditarBase}${deudaDetalleActual.pk}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ notas: detNotas.value, descripcion: deudaDetalleActual.descripcion }),
            });
            const result = await response.json();
            if (result.success) {
                cargarDeudas();
            } else {
                alert(result.error || 'Error al guardar');
            }
        } catch (error) {
            console.error('Error al guardar notas:', error);
            alert('Error al guardar notas');
        }
    });

    btnEliminarDeuda?.addEventListener('click', async () => {
        if (!deudaDetalleActual) return;
        if (!confirm('¿Estás seguro de eliminar esta deuda?')) return;

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
                alert(result.error || 'Error al eliminar');
            }
        } catch (error) {
            console.error('Error al eliminar:', error);
            alert('Error al eliminar');
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
