document.addEventListener('DOMContentLoaded', function () {
    let filtroActivo = 'todos';
    const buscarInput = document.getElementById('buscarPermiso');

    function normalizar(texto) {
        return (texto || '')
            .toLocaleLowerCase('es')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .trim();
    }

    function actualizarResumen() {
        const editables = Array.from(document.querySelectorAll(
            '#formPermisos .permiso-row input[type="checkbox"]:not(:disabled)'
        ));
        const concedidos = editables.filter(function (cb) { return cb.checked; }).length;
        const concedidosEl = document.getElementById('permisosConcedidos');
        const editablesEl = document.getElementById('permisosEditables');
        if (concedidosEl) concedidosEl.textContent = concedidos;
        if (editablesEl) editablesEl.textContent = editables.length;
    }

    function aplicarFiltros() {
        const termino = normalizar(buscarInput ? buscarInput.value : '');
        let visiblesTotales = 0;

        document.querySelectorAll('.modulo-card').forEach(function (moduloCard) {
            let visiblesModulo = 0;
            moduloCard.querySelectorAll('.permiso-row').forEach(function (row) {
                const checkbox = row.querySelector('input[type="checkbox"]');
                const coincideTexto = !termino || normalizar(row.dataset.search).includes(termino);
                const coincideEstado = filtroActivo === 'todos'
                    || (filtroActivo === 'permitidos' && checkbox.checked)
                    || (filtroActivo === 'sin-permiso' && !checkbox.checked);
                const visible = coincideTexto && coincideEstado;
                row.hidden = !visible;
                if (visible) visiblesModulo += 1;
            });
            moduloCard.hidden = visiblesModulo === 0;
            visiblesTotales += visiblesModulo;
        });

        const vacio = document.getElementById('permisosVacio');
        if (vacio) vacio.hidden = visiblesTotales !== 0;
    }

    // Sincroniza el checkbox "Todo" del módulo con el estado de sus permisos
    // editables (marcado si están todos tildados, indeterminado si hay mezcla).
    function actualizarModuloCheckbox(moduloCard) {
        const selectAll = moduloCard.querySelector('.modulo-select-all-check');
        if (!selectAll) return;
        const checks = Array.from(moduloCard.querySelectorAll('.permiso-row input[type="checkbox"]:not(:disabled)'));
        const todos = Array.from(moduloCard.querySelectorAll('.permiso-row input[type="checkbox"]'));
        const concedidos = todos.filter(function (c) { return c.checked; }).length;
        const count = moduloCard.querySelector('.modulo-count');
        if (count) {
            count.textContent = concedidos + '/' + todos.length;
            count.title = concedidos + ' de ' + todos.length + ' permisos activos';
        }
        if (!checks.length) {
            selectAll.checked = false;
            selectAll.indeterminate = false;
            selectAll.disabled = true;
            return;
        }
        const marcados = checks.filter(function (c) { return c.checked; });
        selectAll.checked = marcados.length === checks.length;
        selectAll.indeterminate = marcados.length > 0 && marcados.length < checks.length;
    }

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

            actualizarModuloCheckbox(this.closest('.modulo-card'));
            actualizarResumen();
            if (filtroActivo !== 'todos') aplicarFiltros();
        });
    });

    // Checkbox "Todo" de cada módulo — marca/desmarca solo los permisos
    // editables de esa tarjeta (los bloqueados por candado quedan como están).
    document.querySelectorAll('.modulo-select-all-check').forEach(function (selectAll) {
        const moduloCard = selectAll.closest('.modulo-card');
        actualizarModuloCheckbox(moduloCard);
        selectAll.addEventListener('change', function () {
            const valor = this.checked;
            moduloCard.querySelectorAll('.permiso-row input[type="checkbox"]:not(:disabled)').forEach(function (cb) {
                if (cb.checked !== valor) {
                    cb.checked = valor;
                    cb.dispatchEvent(new Event('change'));
                }
            });
        });
    });

    actualizarResumen();

    if (buscarInput) {
        buscarInput.addEventListener('input', aplicarFiltros);
        buscarInput.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && this.value) {
                this.value = '';
                aplicarFiltros();
            }
        });
    }

    document.querySelectorAll('.permiso-filtro').forEach(function (boton) {
        boton.addEventListener('click', function () {
            filtroActivo = this.dataset.filter;
            document.querySelectorAll('.permiso-filtro').forEach(function (otro) {
                const activo = otro === boton;
                otro.classList.toggle('active', activo);
                otro.setAttribute('aria-pressed', activo ? 'true' : 'false');
            });
            aplicarFiltros();
        });
        boton.setAttribute('aria-pressed', boton.classList.contains('active') ? 'true' : 'false');
    });

    document.addEventListener('keydown', function (event) {
        const target = event.target;
        const escribiendo = target.matches('input, textarea, select, [contenteditable="true"]');
        if (event.key === '/' && !escribiendo && buscarInput) {
            event.preventDefault();
            buscarInput.focus();
        }
    });

    async function guardar() {
        const checkboxes = document.querySelectorAll('#formPermisos input[type="checkbox"]:not(:disabled):not(.modulo-select-all-check)');
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

    // Seleccionar/deseleccionar todo — solo toca los permisos editables
    // (los bloqueados por candado quedan como están, no se pueden tocar
    // desde acá igual que uno por uno).
    function marcarTodos(valor) {
        document.querySelectorAll('#formPermisos input[type="checkbox"]:not(:disabled):not(.modulo-select-all-check)').forEach(function (cb) {
            if (cb.checked !== valor) {
                cb.checked = valor;
                cb.dispatchEvent(new Event('change'));
            }
        });
        actualizarResumen();
        aplicarFiltros();
    }

    document.getElementById('btnSeleccionarTodo').addEventListener('click', function () {
        marcarTodos(true);
    });
    document.getElementById('btnDeseleccionarTodo').addEventListener('click', function () {
        marcarTodos(false);
    });

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
