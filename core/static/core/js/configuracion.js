document.addEventListener('DOMContentLoaded', function () {
    // Sidebar default toggle — sincroniza con localStorage
    const toggleSidebar = document.getElementById('toggleSidebarDefault');
    if (toggleSidebar) {
        toggleSidebar.checked = localStorage.getItem('sidebarCollapsed') === 'true';
        toggleSidebar.addEventListener('change', function () {
            localStorage.setItem('sidebarCollapsed', this.checked);
            const sidebar = document.querySelector('.sidebar');
            if (sidebar) sidebar.classList.toggle('collapsed', this.checked);
        });
    }

    // Formulario de Datos de la empresa
    const formEmpresa = document.getElementById('formEmpresa');
    if (formEmpresa) {
        const csrf = () => formEmpresa.querySelector('[name=csrfmiddlewaretoken]').value;
        const urls = window.CONFIG_EMPRESA_URLS || {};

        formEmpresa.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('empresaMsg');
            fetch(urls.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                body: JSON.stringify({
                    nombre_comercial: document.getElementById('idNombreComercial').value,
                    razon_social:     document.getElementById('idRazonSocial').value,
                    cuit:             document.getElementById('idCuit').value,
                    condicion_iva:    document.getElementById('idCondicionIva').value,
                    domicilio:        document.getElementById('idDomicilio').value,
                    telefono:         document.getElementById('idTelefono').value,
                    email:            document.getElementById('idEmail').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                msg.style.color = data.error ? '#e11d48' : 'var(--success)';
                msg.textContent = data.error || 'Guardado.';
            });
        });

        document.getElementById('inputLogo').addEventListener('change', function () {
            if (!this.files[0]) return;
            const fd = new FormData();
            fd.append('logo', this.files[0]);
            fetch(urls.logo, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrf() },
                body: fd,
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    document.getElementById('logoPreviewBox').innerHTML =
                        `<img src="${data.logo_url}" alt="Logo">`;
                    document.getElementById('btnEliminarLogo').style.display = 'inline-block';
                }
            });
        });

        document.getElementById('btnEliminarLogo')?.addEventListener('click', function () {
            fetch(urls.logo, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': csrf() },
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    document.getElementById('logoPreviewBox').innerHTML =
                        '<span style="font-size:0.7rem; color:var(--text-muted);">Sin logo</span>';
                    this.style.display = 'none';
                }
            });
        });
    }

    // ── Cuentas de caja (tarjetas/billeteras/bancos) ────────────────
    const formCuenta = document.getElementById('formCuenta');
    if (formCuenta) {
        const urls = window.CONFIG_CUENTAS_URLS || {};
        const csrf = () => formCuenta.querySelector('[name=csrfmiddlewaretoken]').value;
        const modalEl = document.getElementById('cuentaModal');
        const modal = window.bootstrap ? new bootstrap.Modal(modalEl) : null;
        const campoCredito = document.getElementById('cuentaEsCredito');
        const camposCredito = document.getElementById('cuentaCreditoFields');

        function toggleCamposCredito() {
            camposCredito.style.display = campoCredito.checked ? 'flex' : 'none';
        }
        campoCredito.addEventListener('change', toggleCamposCredito);

        function limpiarForm() {
            document.getElementById('cuentaPk').value = '';
            document.getElementById('cuentaNombre').value = '';
            document.getElementById('cuentaMoneda').selectedIndex = 0;
            document.getElementById('cuentaTitular').value = '';
            document.getElementById('cuentaTerminadaEn').value = '';
            campoCredito.checked = false;
            document.getElementById('cuentaDiaCierre').value = '';
            document.getElementById('cuentaDiaVencimiento').value = '';
            document.getElementById('cuentaMsg').textContent = '';
            toggleCamposCredito();
        }

        document.getElementById('btnNuevaCuenta')?.addEventListener('click', function () {
            limpiarForm();
            document.getElementById('cuentaModalLabel').textContent = 'Nueva cuenta';
        });

        document.querySelectorAll('.btn-editar-cuenta').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.cuenta-row');
                limpiarForm();
                document.getElementById('cuentaModalLabel').textContent = 'Editar cuenta';
                document.getElementById('cuentaPk').value = row.dataset.pk;
                document.getElementById('cuentaNombre').value = row.dataset.nombre;
                document.getElementById('cuentaMoneda').value = row.dataset.moneda;
                document.getElementById('cuentaTitular').value = row.dataset.titular;
                document.getElementById('cuentaTerminadaEn').value = row.dataset.terminadaEn;
                campoCredito.checked = row.dataset.esCredito === '1';
                document.getElementById('cuentaDiaCierre').value = row.dataset.diaCierre;
                document.getElementById('cuentaDiaVencimiento').value = row.dataset.diaVencimiento;
                toggleCamposCredito();
                if (modal) modal.show();
            });
        });

        document.querySelectorAll('.btn-baja-cuenta').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.cuenta-row');
                const accion = row.dataset.activa === '1' ? 'dar de baja' : 'reactivar';
                const ok = await KaiConfirm(`¿Seguro que querés ${accion} la cuenta "${row.dataset.nombre}"?`);
                if (!ok) return;
                fetch(urls.baja, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    window.location.reload();
                });
            });
        });

        formCuenta.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('cuentaMsg');
            fetch(urls.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                body: JSON.stringify({
                    pk:               document.getElementById('cuentaPk').value || null,
                    nombre:           document.getElementById('cuentaNombre').value,
                    moneda:           document.getElementById('cuentaMoneda').value,
                    titular:          document.getElementById('cuentaTitular').value,
                    terminada_en:     document.getElementById('cuentaTerminadaEn').value,
                    es_credito:       campoCredito.checked,
                    dia_cierre:       document.getElementById('cuentaDiaCierre').value,
                    dia_vencimiento:  document.getElementById('cuentaDiaVencimiento').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                window.location.reload();
            });
        });
    }
});