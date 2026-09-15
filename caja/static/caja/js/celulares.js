/* caja/static/caja/js/celulares.js — Celulares (SIM + recargas) */
'use strict';

(function () {
    const tbody = document.getElementById('celularesTbody');
    if (!tbody) return; // sin permiso para ver, no hay tabla

    const buscar         = document.getElementById('celularesBuscar');
    const filtroEstado   = document.getElementById('celularesFiltroEstado');
    const chipPendientes = document.getElementById('celularesChipPendientes');
    const btnNuevo       = document.getElementById('btnNuevoCelular');

    // ── Modal A: datos del celular ──────────────────────────────────
    const modalEl           = document.getElementById('celularModal');
    const modal              = new bootstrap.Modal(modalEl);
    const modalTitulo        = document.getElementById('celularModalTitulo');
    const celularPk          = document.getElementById('celularPk');
    const celularNumero      = document.getElementById('celularNumero');
    const celularTitular     = document.getElementById('celularTitular');
    const celularCompania    = document.getElementById('celularCompania');
    const celularFechaActivacion = document.getElementById('celularFechaActivacion');
    const celularPin         = document.getElementById('celularPin');
    const celularPuk         = document.getElementById('celularPuk');
    const celularIccid       = document.getElementById('celularIccid');
    const celularImei        = document.getElementById('celularImei');
    const celularFrecuencia  = document.getElementById('celularFrecuencia');
    const celularNotas       = document.getElementById('celularNotas');
    const celularActivoWrap  = document.getElementById('celularActivoWrap');
    const celularActivo      = document.getElementById('celularActivo');
    const celularMeta        = document.getElementById('celularMeta');
    const celularMsg         = document.getElementById('celularMsg');
    const btnGuardar         = document.getElementById('btnGuardarCelular');
    const btnEliminar        = document.getElementById('btnEliminarCelular');

    // ── Modal B: historial y carga de recargas ──────────────────────
    const recargasModalEl     = document.getElementById('recargasModal');
    const recargasModal        = new bootstrap.Modal(recargasModalEl);
    const recargasModalTitulo  = document.getElementById('recargasModalTitulo');
    const recargaProximaBadge  = document.getElementById('recargaProximaBadge');
    const recargaCelularPk     = document.getElementById('recargaCelularPk');
    const recargaPk            = document.getElementById('recargaPk');
    const recargaFormGrid      = document.getElementById('recargaFormGrid');
    const recargaFecha         = document.getElementById('recargaFecha');
    const recargaMonto         = document.getElementById('recargaMonto');
    const recargaCuenta        = document.getElementById('recargaCuenta');
    const btnGuardarRecarga    = document.getElementById('btnGuardarRecarga');
    const btnCancelarEdicionRecarga = document.getElementById('btnCancelarEdicionRecarga');
    const recargaMsg           = document.getElementById('recargaMsg');
    const recargasTbody        = document.getElementById('recargasTbody');

    let celulares = [];
    const camposEditables = [
        celularNumero, celularTitular, celularCompania, celularFechaActivacion,
        celularPin, celularPuk, celularIccid, celularImei, celularFrecuencia, celularNotas,
    ];

    function escapeHtml(s) {
        return (s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    function moneda(valor) {
        const num = (window.KaiFormat && KaiFormat.moneda) ? KaiFormat.moneda(valor) : valor;
        return `$${num}`;
    }

    function fechaCorta(iso) {
        if (!iso) return '';
        const [y, m, d] = iso.split('-');
        return `${d}/${m}/${y}`;
    }

    // Evita doble submit (doble click, doble tap) mientras un fetch está
    // en vuelo — importante acá porque cada recarga genera un egreso real.
    // Solo togglea `disabled`: no toca el texto del botón, porque en el
    // caso de la recarga el propio flujo de éxito lo cambia (Registrar
    // ⇄ Guardar cambios) y no queremos pisar ese estado al terminar.
    async function conBotonBloqueado(btn, fn) {
        if (btn.disabled) return;
        btn.disabled = true;
        try {
            await fn();
        } finally {
            btn.disabled = false;
        }
    }

    function urlRecargas(pk) { return CELULARES_URLS.recargasListarTpl.replace('999999999', pk); }
    function urlRecargaAcciones(pk) { return CELULARES_URLS.recargaAccionesTpl.replace('999999999', pk); }
    function urlRecargaEliminar(pk) { return CELULARES_URLS.recargaEliminarTpl.replace('999999999', pk); }

    function badgeRecordatorio(c) {
        if (c.dias_para_recarga === null || c.dias_para_recarga === undefined) {
            return '<span class="celular-sin-dato">Sin recordatorio</span>';
        }
        const d = c.dias_para_recarga;
        if (d < 0) return `<span class="celular-badge celular-badge--danger">Vencida hace ${Math.abs(d)}d</span>`;
        if (d === 0) return '<span class="celular-badge celular-badge--danger">Hoy</span>';
        if (d <= 3) return `<span class="celular-badge celular-badge--danger">${d}d</span>`;
        if (d <= 7) return `<span class="celular-badge celular-badge--warning">${d}d</span>`;
        return `<span class="celular-badge celular-badge--ok">${d}d</span>`;
    }

    function actualizarChipPendientes() {
        const pendientes = celulares.filter((c) => c.activo && c.dias_para_recarga !== null && c.dias_para_recarga <= 7);
        if (!pendientes.length) {
            chipPendientes.style.display = 'none';
            return;
        }
        chipPendientes.style.display = '';
        chipPendientes.textContent = pendientes.length === 1
            ? '1 línea para recargar'
            : `${pendientes.length} líneas para recargar`;
    }

    async function cargarCelulares() {
        const params = new URLSearchParams();
        if (buscar.value.trim()) params.set('q', buscar.value.trim());
        params.set('estado', filtroEstado.value);

        const resp = await fetch(`${CELULARES_URLS.listar}?${params.toString()}`);
        const data = await resp.json();
        if (data.error) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">${escapeHtml(data.error)}</td></tr>`;
            return;
        }
        celulares = data.results;
        renderTabla();
        actualizarChipPendientes();
    }

    function iconoHistorial() {
        return '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8.5" r="6" stroke="currentColor" stroke-width="1.3"/><path d="M8 5.3V8.5L10.2 9.8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M4.5 2.3L2.7 3.7M11.5 2.3L13.3 3.7" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>';
    }
    function iconoEditar() {
        return '<svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M11.3 2.3a1.4 1.4 0 0 1 2 2L5.5 12.1l-2.8.7.7-2.8 7.9-7.7Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>';
    }
    function iconoEliminar() {
        return '<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 4H11M4.5 4V3H8.5V4M5 6.5V10M8 6.5V10M2.8 4L3.5 11H9.5L10.2 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    }

    function renderTabla() {
        if (!celulares.length) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">Todavía no cargaste ningún celular.</td></tr>`;
            return;
        }
        tbody.innerHTML = celulares.map((c) => `
            <tr data-pk="${c.pk}" class="${c.activo ? '' : 'celular-fila-inactiva'}">
                <td class="celular-numero-cell">${escapeHtml(c.numero)}</td>
                <td>${c.titular ? escapeHtml(c.titular) : '<span class="celular-sin-dato">—</span>'}</td>
                <td>${c.compania ? escapeHtml(c.compania) : '<span class="celular-sin-dato">—</span>'}</td>
                <td>${c.ultima_recarga_fecha ? `${moneda(c.ultima_recarga_monto)} <span class="celular-sin-dato">(${fechaCorta(c.ultima_recarga_fecha)})</span>` : '<span class="celular-sin-dato">—</span>'}</td>
                <td>${badgeRecordatorio(c)}</td>
                <td>${c.activo ? '<span class="celulares-badge-activo">Activo</span>' : '<span class="celulares-badge-inactivo">De baja</span>'}</td>
                <td class="col-actions celular-acciones-cell">
                    <button type="button" class="btn-ghost-sm btn-historial-celular" data-pk="${c.pk}" title="Historial de recargas">${iconoHistorial()}</button>
                    ${CELULARES_PUEDE_EDITAR ? `<button type="button" class="btn-ghost-sm btn-editar-celular" data-pk="${c.pk}" title="Editar">${iconoEditar()}</button>` : ''}
                    ${CELULARES_PUEDE_ELIMINAR ? `<button type="button" class="btn-ghost-sm btn-eliminar-celular" data-pk="${c.pk}" title="Eliminar">${iconoEliminar()}</button>` : ''}
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.btn-historial-celular').forEach((btn) => {
            btn.addEventListener('click', () => abrirRecargas(parseInt(btn.dataset.pk, 10)));
        });
        tbody.querySelectorAll('.btn-editar-celular').forEach((btn) => {
            btn.addEventListener('click', () => abrirCelular(parseInt(btn.dataset.pk, 10)));
        });
        tbody.querySelectorAll('.btn-eliminar-celular').forEach((btn) => {
            btn.addEventListener('click', () => conBotonBloqueado(btn, () => eliminarCelular(parseInt(btn.dataset.pk, 10))));
        });
    }

    // ══════════════════════════════════════════════════════════════
    //  Modal A — datos del celular
    // ══════════════════════════════════════════════════════════════

    function limpiarFormulario() {
        celularPk.value = '';
        celularNumero.value = '';
        celularTitular.value = '';
        celularCompania.value = '';
        celularFechaActivacion.value = '';
        celularPin.value = '';
        celularPin.type = 'password';
        celularPuk.value = '';
        celularPuk.type = 'password';
        celularIccid.value = '';
        celularImei.value = '';
        celularFrecuencia.value = '';
        celularNotas.value = '';
        celularActivoWrap.style.display = 'none';
        celularActivo.checked = true;
        camposEditables.forEach((el) => { el.disabled = false; });
        celularMeta.style.display = 'none';
        celularMsg.style.display = 'none';
        btnEliminar.style.display = 'none';
    }

    function abrirCelular(pk) {
        const c = celulares.find((x) => x.pk === pk);
        if (!c) return;

        modalTitulo.textContent = c.numero;
        celularPk.value = c.pk;
        celularNumero.value = c.numero;
        celularTitular.value = c.titular;
        celularCompania.value = c.compania;
        celularFechaActivacion.value = c.fecha_activacion;
        celularPin.value = c.pin;
        celularPin.type = 'password';
        celularPuk.value = c.puk;
        celularPuk.type = 'password';
        celularIccid.value = c.iccid;
        celularImei.value = c.imei;
        celularFrecuencia.value = c.frecuencia_recarga_dias || '';
        celularNotas.value = c.notas;
        camposEditables.forEach((el) => { el.disabled = !CELULARES_PUEDE_EDITAR; });

        celularActivoWrap.style.display = 'flex';
        celularActivo.checked = c.activo;
        celularActivo.disabled = !CELULARES_PUEDE_EDITAR;

        celularMeta.style.display = '';
        celularMeta.textContent = `Cargado por ${c.creado_por} el ${c.fecha_alta}` +
            (c.modificado_por ? ` — última edición de ${c.modificado_por} el ${c.fecha_modificacion}` : '');

        btnGuardar.style.display = CELULARES_PUEDE_EDITAR ? '' : 'none';
        btnEliminar.style.display = CELULARES_PUEDE_ELIMINAR ? '' : 'none';
        btnEliminar.dataset.pk = c.pk;
        celularMsg.style.display = 'none';

        modal.show();
    }

    if (btnNuevo) {
        btnNuevo.addEventListener('click', () => {
            modalTitulo.textContent = 'Nuevo celular';
            limpiarFormulario();
            btnGuardar.style.display = '';
            modal.show();
        });
    }

    modalEl.querySelectorAll('.celular-btn-ver').forEach((btn) => {
        btn.addEventListener('click', () => {
            const input = document.getElementById(btn.dataset.target);
            input.type = input.type === 'password' ? 'text' : 'password';
        });
    });

    btnGuardar.addEventListener('click', () => conBotonBloqueado(btnGuardar, async () => {
        const numero = celularNumero.value.trim();
        if (!numero) {
            celularMsg.textContent = 'Ponele el número de línea.';
            celularMsg.style.display = '';
            return;
        }
        const body = {
            numero,
            titular: celularTitular.value.trim(),
            compania: celularCompania.value.trim(),
            fecha_activacion: celularFechaActivacion.value,
            pin: celularPin.value.trim(),
            puk: celularPuk.value.trim(),
            iccid: celularIccid.value.trim(),
            imei: celularImei.value.trim(),
            frecuencia_recarga_dias: celularFrecuencia.value,
            notas: celularNotas.value.trim(),
            activo: celularActivo.checked,
        };
        const esNuevo = !celularPk.value;
        if (!esNuevo) body.pk = celularPk.value;

        const resp = await fetch(CELULARES_URLS.acciones, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            celularMsg.textContent = data.error || 'No se pudo guardar el celular.';
            celularMsg.style.display = '';
            return;
        }

        modal.hide();
        KaiToast.show(esNuevo ? 'Celular cargado.' : 'Celular actualizado.', 'success');
        cargarCelulares();
    }));

    btnEliminar.addEventListener('click', () => conBotonBloqueado(btnEliminar, async () => {
        const pk = btnEliminar.dataset.pk;
        modal.hide();
        await eliminarCelular(parseInt(pk, 10));
    }));

    async function eliminarCelular(pk) {
        const ok = await KaiConfirm('¿Eliminar este celular? También se borran sus recargas y los egresos que generaron en caja. No se puede deshacer.', { danger: true, confirmText: 'Eliminar' });
        if (!ok) return;

        const resp = await fetch(CELULARES_URLS.eliminar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ pk }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            KaiToast.show(data.error || 'No se pudo eliminar el celular.', 'danger');
            return;
        }
        KaiToast.show('Celular eliminado.', 'success');
        cargarCelulares();
    }

    // ══════════════════════════════════════════════════════════════
    //  Modal B — historial y carga de recargas
    // ══════════════════════════════════════════════════════════════

    function salirModoEdicionRecarga() {
        recargaPk.value = '';
        recargaFecha.value = CELULARES_HOY;
        recargaMonto.value = '';
        btnGuardarRecarga.textContent = 'Registrar';
        btnCancelarEdicionRecarga.style.display = 'none';
        recargaMsg.style.display = 'none';
    }

    function abrirRecargas(pk) {
        const c = celulares.find((x) => x.pk === pk);
        if (!c) return;

        recargasModalTitulo.textContent = `Recargas de ${c.numero}`;
        recargaProximaBadge.innerHTML = (c.dias_para_recarga === null || c.dias_para_recarga === undefined)
            ? '' : badgeRecordatorio(c);
        recargaCelularPk.value = c.pk;

        const puedeUsarForm = CELULARES_PUEDE_CREAR || CELULARES_PUEDE_EDITAR;
        recargaFormGrid.style.display = puedeUsarForm ? '' : 'none';
        recargaCuenta.disabled = !puedeUsarForm;
        salirModoEdicionRecarga();

        cargarRecargas(pk);
        recargasModal.show();
    }

    async function cargarRecargas(celularPkVal) {
        recargasTbody.innerHTML = '<tr><td colspan="5" class="celulares-tabla-loading">Cargando...</td></tr>';
        const resp = await fetch(urlRecargas(celularPkVal));
        const data = await resp.json();
        if (data.error || !data.results) {
            recargasTbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-3">${escapeHtml(data.error || 'No se pudieron cargar las recargas.')}</td></tr>`;
            return;
        }
        if (!data.results.length) {
            recargasTbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">Todavía no se registraron recargas.</td></tr>';
            return;
        }
        recargasTbody.innerHTML = data.results.map((r) => `
            <tr data-pk="${r.pk}" data-fecha="${r.fecha}" data-monto="${r.monto}" data-cuenta-pk="${r.cuenta_pk || ''}">
                <td>${fechaCorta(r.fecha)}</td>
                <td>${moneda(r.monto)}</td>
                <td>${r.sin_egreso ? '<span class="celular-sin-dato" title="El egreso de caja de esta recarga se borró aparte, desde Ingresos y egresos">Sin egreso</span>' : escapeHtml(r.cuenta_nombre)}</td>
                <td class="celular-sin-dato">${escapeHtml(r.creado_por)}</td>
                <td class="col-actions celular-acciones-cell">
                    ${CELULARES_PUEDE_EDITAR ? `<button type="button" class="btn-ghost-sm btn-editar-recarga" title="Editar">${iconoEditar()}</button>` : ''}
                    ${CELULARES_PUEDE_ELIMINAR ? `<button type="button" class="btn-ghost-sm btn-eliminar-recarga" title="Eliminar">${iconoEliminar()}</button>` : ''}
                </td>
            </tr>
        `).join('');

        recargasTbody.querySelectorAll('.btn-editar-recarga').forEach((btn) => {
            btn.addEventListener('click', () => {
                const tr = btn.closest('tr');
                recargaPk.value = tr.dataset.pk;
                recargaFecha.value = tr.dataset.fecha;
                recargaMonto.value = tr.dataset.monto;
                if (tr.dataset.cuentaPk) recargaCuenta.value = tr.dataset.cuentaPk;
                btnGuardarRecarga.textContent = 'Guardar cambios';
                btnCancelarEdicionRecarga.style.display = '';
                recargaMsg.style.display = 'none';
                recargaFecha.focus();
            });
        });
        recargasTbody.querySelectorAll('.btn-eliminar-recarga').forEach((btn) => {
            btn.addEventListener('click', () => conBotonBloqueado(btn, async () => {
                const tr = btn.closest('tr');
                const ok = await KaiConfirm('¿Eliminar esta recarga? También se borra el egreso que generó en caja. No se puede deshacer.', { danger: true, confirmText: 'Eliminar' });
                if (!ok) return;

                const pkCelular = parseInt(recargaCelularPk.value, 10);
                const resp2 = await fetch(urlRecargaEliminar(pkCelular), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({ pk: tr.dataset.pk }),
                });
                const data2 = await resp2.json();
                if (!resp2.ok || data2.error) {
                    KaiToast.show(data2.error || 'No se pudo eliminar la recarga.', 'danger');
                    return;
                }
                if (recargaPk.value === tr.dataset.pk) salirModoEdicionRecarga();
                KaiToast.show('Recarga eliminada.', 'success');
                cargarRecargas(pkCelular);
                cargarCelulares();
            }));
        });
    }

    btnCancelarEdicionRecarga.addEventListener('click', salirModoEdicionRecarga);

    btnGuardarRecarga.addEventListener('click', () => conBotonBloqueado(btnGuardarRecarga, async () => {
        const pkCelular = parseInt(recargaCelularPk.value, 10);
        if (!pkCelular) return;

        const fecha = recargaFecha.value;
        const monto = recargaMonto.value;
        const cuentaPk = recargaCuenta.value;
        if (!fecha || !monto || Number(monto) <= 0) {
            recargaMsg.textContent = 'Completá fecha y monto de la recarga.';
            recargaMsg.style.display = '';
            return;
        }
        if (!cuentaPk) {
            recargaMsg.textContent = 'Elegí de qué cuenta sale la plata.';
            recargaMsg.style.display = '';
            return;
        }
        recargaMsg.style.display = 'none';

        const body = { fecha, monto, cuenta_pk: cuentaPk };
        const esEdicion = !!recargaPk.value;
        if (esEdicion) body.pk = recargaPk.value;

        const resp = await fetch(urlRecargaAcciones(pkCelular), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            recargaMsg.textContent = data.error || 'No se pudo guardar la recarga.';
            recargaMsg.style.display = '';
            return;
        }

        KaiToast.show(esEdicion ? 'Recarga actualizada.' : 'Recarga registrada y cargada como egreso.', 'success');
        salirModoEdicionRecarga();
        cargarRecargas(pkCelular);
        cargarCelulares();
    }));

    let buscarDebounce = null;
    buscar.addEventListener('input', () => {
        clearTimeout(buscarDebounce);
        buscarDebounce = setTimeout(cargarCelulares, 300);
    });
    filtroEstado.addEventListener('change', cargarCelulares);

    cargarCelulares();
})();
