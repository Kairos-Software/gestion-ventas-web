document.addEventListener('DOMContentLoaded', function () {

    // Actualizar clase visual de la fila al cambiar el toggle
    document.querySelectorAll('.permiso-row input[type="checkbox"]').forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            const row = this.closest('.permiso-row');
            row.classList.toggle('concedido', this.checked);
            row.classList.toggle('denegado', !this.checked);

            // Marcar visualmente que este permiso tiene cambio pendiente
            const badge = row.querySelector('.fuente-badge');
            badge.dataset.original = badge.dataset.original || badge.textContent.trim();
            badge.textContent = 'PENDIENTE';
            badge.className = 'fuente-badge fuente-sin_permiso';
        });
    });

    async function guardar() {
        const checkboxes = document.querySelectorAll('#formPermisos input[type="checkbox"]:not(:disabled)');
        const permisos = {};
        checkboxes.forEach(function (cb) {
            permisos[cb.name] = cb.checked;
        });

        const alerta = document.getElementById('alertGuardado');

        try {
            const response = await fetch(window.guardarPermisosUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ permisos }),
            });
            const data = await response.json();

            if (data.success) {
                mostrarAlerta('Permisos guardados correctamente.', 'ok');
                // Recargar para mostrar fuentes actualizadas
                setTimeout(() => location.reload(), 800);
            } else {
                mostrarAlerta('Error al guardar: ' + JSON.stringify(data.error), 'fail');
            }
        } catch (err) {
            mostrarAlerta('Error de conexión.', 'fail');
            console.error(err);
        }
    }

    function mostrarAlerta(texto, tipo) {
        const alerta = document.getElementById('alertGuardado');
        alerta.textContent = texto;
        alerta.className = 'alerta-guardado ' + tipo;
        alerta.style.display = 'block';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    document.getElementById('btnGuardar').addEventListener('click', guardar);
    document.getElementById('btnGuardarBottom').addEventListener('click', guardar);

    function getCookie(name) {
        let value = null;
        document.cookie.split(';').forEach(function (c) {
            const [k, v] = c.trim().split('=');
            if (k === name) value = decodeURIComponent(v);
        });
        return value;
    }
});