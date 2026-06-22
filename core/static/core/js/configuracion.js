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
});