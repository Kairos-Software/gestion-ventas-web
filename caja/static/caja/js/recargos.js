'use strict';

(function () {
    const urls = window.recargosUrls || {};
    const MEDIO_CREDITO = window.recargosMedioCredito || 'credito';
    const TARJETAS = window.recargosTarjetas || [];
    const CAMPO_ACEPTA = {
        debito: 'acepta_debito',
        credito: 'acepta_credito',
        qr: 'acepta_qr',
        transferencia: 'acepta_transferencia',
    };

    function getCookie(name) {
        const value = '; ' + document.cookie;
        const parts = value.split('; ' + name + '=');
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    function _tarjetaPorPk(pk) {
        return TARJETAS.find(t => String(t.pk) === String(pk));
    }

    function _urlConPk(base, pk) {
        return base.replace('/0/', '/' + pk + '/');
    }

    /* ════════════════════════════════════════════════════════════
       PILLS "Acepta" — toggle qué medios cobra cada tarjeta
    ════════════════════════════════════════════════════════════ */
    document.querySelectorAll('.rec-medio-pill').forEach(pill => {
        if (pill.disabled) return;
        pill.addEventListener('click', async () => {
            const tarjetaPk = pill.dataset.tarjetaPk;
            const medio = pill.dataset.medio;
            const campo = CAMPO_ACEPTA[medio];
            const nuevoValor = !pill.classList.contains('rec-medio-pill--on');

            pill.disabled = true;
            try {
                const resp = await fetch(urls.tarjetaMedios, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({ tarjeta_pk: tarjetaPk, [campo]: nuevoValor }),
                });
                const data = await resp.json();
                if (!resp.ok || data.error) {
                    alert(data.error || 'No se pudo actualizar.');
                    return;
                }
                window.location.reload();
            } catch (e) {
                alert('Error de conexión.');
            } finally {
                pill.disabled = false;
            }
        });
    });

    /* ════════════════════════════════════════════════════════════
       MODAL — nueva tarjeta/billetera
    ════════════════════════════════════════════════════════════ */
    const modalTarjeta = document.getElementById('modalTarjeta');
    if (modalTarjeta) {
        const formTarjeta = document.getElementById('formTarjeta');
        const campoNombre = document.getElementById('t_nombre');

        function _abrirModalTarjeta() {
            formTarjeta.reset();
            modalTarjeta.hidden = false;
            document.body.style.overflow = 'hidden';
        }
        function _cerrarModalTarjeta() {
            modalTarjeta.hidden = true;
            document.body.style.overflow = '';
        }

        const btnNuevaTarjeta = document.getElementById('btnNuevaTarjeta');
        if (btnNuevaTarjeta) btnNuevaTarjeta.addEventListener('click', _abrirModalTarjeta);
        document.getElementById('btnCerrarModalTarjeta').addEventListener('click', _cerrarModalTarjeta);
        document.getElementById('btnCancelarModalTarjeta').addEventListener('click', _cerrarModalTarjeta);
        document.getElementById('modalTarjetaBackdrop').addEventListener('click', _cerrarModalTarjeta);

        formTarjeta.addEventListener('submit', async (ev) => {
            ev.preventDefault();
            const btn = formTarjeta.querySelector('button[type="submit"]');
            btn.disabled = true;
            try {
                const resp = await fetch(urls.tarjetaGuardar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({ nombre: campoNombre.value.trim() }),
                });
                const data = await resp.json();
                if (!resp.ok || data.error) {
                    alert(data.error || 'No se pudo crear la tarjeta.');
                    return;
                }
                window.location.reload();
            } catch (e) {
                alert('Error de conexión al crear la tarjeta.');
            } finally {
                btn.disabled = false;
            }
        });
    }

    /* ════════════════════════════════════════════════════════════
       MODAL — crear/editar recargo
    ════════════════════════════════════════════════════════════ */
    const modal = document.getElementById('modalRecargo');
    if (!modal) return; // sin permiso de edición: no hay modales en el DOM

    const form          = document.getElementById('formRecargo');
    const campoPk        = document.getElementById('r_pk');
    const campoTarjeta    = document.getElementById('r_tarjeta');
    const campoMedio      = document.getElementById('r_medio');
    const campoMedioHint  = document.getElementById('r_medio_hint');
    const campoCantidad   = document.getElementById('r_cantidad_pagos');
    const campoNombrePlan = document.getElementById('r_nombre_plan');
    const campoPct        = document.getElementById('r_recargo_pct');
    const campoActivo     = document.getElementById('r_activo');
    const wrapCredito    = document.getElementById('campoCredito');
    const wrapActivo     = document.getElementById('campoActivo');
    const titulo          = document.getElementById('modalRecargoTitulo');

    /** Deshabilita (y marca) las <option> de medio que la tarjeta elegida
     *  no acepta, para que quede claro por qué no se pueden tildar —
     *  en vez de simplemente ocultarlas (más confuso: "¿y dónde está
     *  Crédito?"). Si el medio actualmente seleccionado deja de ser
     *  válido, lo desmarca. */
    function _actualizarOpcionesMedio() {
        const tarjeta = _tarjetaPorPk(campoTarjeta.value);
        let medioInvalido = false;
        Array.from(campoMedio.options).forEach(opt => {
            if (!opt.value) return;
            const acepta = tarjeta ? !!tarjeta[CAMPO_ACEPTA[opt.value]] : true;
            opt.disabled = !acepta;
            opt.textContent = acepta ? _labelMedio(opt.value) : `${_labelMedio(opt.value)} (no habilitado en esta tarjeta)`;
            if (!acepta && campoMedio.value === opt.value) medioInvalido = true;
        });
        if (medioInvalido) {
            campoMedio.value = '';
            _toggleCampoCredito();
        }
        campoMedioHint.hidden = true;
    }

    const LABELS_MEDIO = {};
    Array.from(campoMedio.options).forEach(opt => { if (opt.value) LABELS_MEDIO[opt.value] = opt.textContent; });
    function _labelMedio(v) { return LABELS_MEDIO[v] || v; }

    campoTarjeta.addEventListener('change', _actualizarOpcionesMedio);

    function _toggleCampoCredito() {
        wrapCredito.hidden = campoMedio.value !== MEDIO_CREDITO;
    }
    campoMedio.addEventListener('change', _toggleCampoCredito);

    function _abrirModal() {
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
    }
    function _cerrarModal() {
        modal.hidden = true;
        document.body.style.overflow = '';
    }

    function _resetForm() {
        form.reset();
        campoPk.value = '';
        wrapActivo.hidden = true;
        _actualizarOpcionesMedio();
        _toggleCampoCredito();
    }

    function _abrirNuevo(tarjetaPk) {
        _resetForm();
        titulo.textContent = 'Nuevo recargo';
        if (tarjetaPk) campoTarjeta.value = tarjetaPk;
        _actualizarOpcionesMedio();
        _abrirModal();
    }

    function _abrirEditar(fila) {
        _resetForm();
        titulo.textContent = 'Editar recargo';
        campoPk.value = fila.dataset.pk;
        campoTarjeta.value = fila.dataset.tarjetaPk;
        _actualizarOpcionesMedio();
        campoMedio.value = fila.dataset.medio;
        campoCantidad.value = fila.dataset.cantidadPagos;
        campoNombrePlan.value = fila.dataset.nombrePlan || '';
        campoPct.value = fila.dataset.recargoPct;
        campoActivo.checked = fila.dataset.activo === '1';
        wrapActivo.hidden = false;
        _toggleCampoCredito();
        _abrirModal();
    }

    const btnNuevo = document.getElementById('btnNuevoRecargo');
    if (btnNuevo) btnNuevo.addEventListener('click', () => _abrirNuevo(null));

    document.querySelectorAll('.rec-btn-agregar').forEach(btn => {
        btn.addEventListener('click', () => _abrirNuevo(btn.dataset.tarjetaPk));
    });

    document.querySelectorAll('.rec-btn-editar').forEach(btn => {
        btn.addEventListener('click', () => _abrirEditar(btn.closest('tr')));
    });

    document.getElementById('btnCerrarModal').addEventListener('click', _cerrarModal);
    document.getElementById('btnCancelarModal').addEventListener('click', _cerrarModal);
    document.getElementById('modalBackdrop').addEventListener('click', _cerrarModal);

    form.addEventListener('submit', async (ev) => {
        ev.preventDefault();

        const tarjeta = _tarjetaPorPk(campoTarjeta.value);
        if (campoMedio.value && tarjeta && !tarjeta[CAMPO_ACEPTA[campoMedio.value]]) {
            campoMedioHint.hidden = false;
            return;
        }

        const payload = {
            pk: campoPk.value || null,
            tarjeta_pk: campoTarjeta.value,
            medio: campoMedio.value,
            cantidad_pagos: campoMedio.value === MEDIO_CREDITO ? (campoCantidad.value || 1) : 1,
            nombre_plan: campoMedio.value === MEDIO_CREDITO ? campoNombrePlan.value.trim() : '',
            recargo_pct: campoPct.value,
        };
        if (!wrapActivo.hidden) payload.activo = campoActivo.checked;

        const btn = document.getElementById('btnGuardarRecargo');
        btn.disabled = true;
        try {
            const resp = await fetch(urls.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (!resp.ok || data.error) {
                alert(data.error || 'No se pudo guardar el recargo.');
                return;
            }
            window.location.reload();
        } catch (e) {
            alert('Error de conexión al guardar el recargo.');
        } finally {
            btn.disabled = false;
        }
    });

    document.querySelectorAll('.rec-btn-toggle').forEach(btn => {
        btn.addEventListener('click', async () => {
            const fila = btn.closest('tr');
            const url = _urlConPk(urls.baja, fila.dataset.pk);
            btn.disabled = true;
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCookie('csrftoken') },
                });
                const data = await resp.json();
                if (!resp.ok || data.error) {
                    alert(data.error || 'No se pudo cambiar el estado.');
                    return;
                }
                window.location.reload();
            } catch (e) {
                alert('Error de conexión.');
            } finally {
                btn.disabled = false;
            }
        });
    });

    document.querySelectorAll('.rec-btn-eliminar').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm('¿Eliminar este recargo? Esta acción no se puede deshacer.')) return;
            const fila = btn.closest('tr');
            const url = _urlConPk(urls.eliminar, fila.dataset.pk);
            btn.disabled = true;
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCookie('csrftoken') },
                });
                const data = await resp.json();
                if (!resp.ok || data.error) {
                    alert(data.error || 'No se pudo eliminar el recargo.');
                    return;
                }
                window.location.reload();
            } catch (e) {
                alert('Error de conexión.');
            } finally {
                btn.disabled = false;
            }
        });
    });
})();
