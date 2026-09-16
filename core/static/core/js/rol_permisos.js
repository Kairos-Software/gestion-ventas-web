/* core/static/core/js/rol_permisos.js
 * Pantalla de un perfil de permisos (core/templates/core/rol_permisos.html) —
 * misma interacción que permisos_usuario.js (buscador, filtros, colapsar
 * módulos, "incluir área", resumen) para que armar un perfil se sienta
 * exactamente igual a tocar los permisos de un usuario. Lo único distinto es
 * qué se guarda: acá no hay "fuente" (rol/override), un perfil es una lista
 * plana de permisos incluidos/no incluidos.
 */
document.addEventListener('DOMContentLoaded', function () {
    let filtroActivo = 'todos';
    const buscarInput = document.getElementById('buscarPermiso');

    function normalizar(texto) {
        return (texto || '')
            .toLocaleLowerCase('es')
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')
            .trim();
    }

    function establecerModuloColapsado(moduloCard, colapsado) {
        const boton = moduloCard.querySelector('.modulo-collapse');
        moduloCard.classList.toggle('is-collapsed', colapsado);
        if (boton) boton.setAttribute('aria-expanded', colapsado ? 'false' : 'true');
    }

    document.querySelectorAll('.modulo-card').forEach(function (moduloCard, indice) {
        const boton = moduloCard.querySelector('.modulo-collapse');
        boton?.addEventListener('click', function () {
            establecerModuloColapsado(moduloCard, !moduloCard.classList.contains('is-collapsed'));
        });

        if (window.matchMedia('(max-width: 600px)').matches && indice > 0) {
            establecerModuloColapsado(moduloCard, true);
        }
    });

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
            if (visiblesModulo > 0 && (termino || filtroActivo !== 'todos')) {
                establecerModuloColapsado(moduloCard, false);
            }
            visiblesTotales += visiblesModulo;
        });

        const vacio = document.getElementById('permisosVacio');
        if (vacio) vacio.hidden = visiblesTotales !== 0;
    }

    function actualizarModuloCheckbox(moduloCard) {
        const selectAll = moduloCard.querySelector('.modulo-select-all-check');
        if (!selectAll) return;
        const checks = Array.from(moduloCard.querySelectorAll('.permiso-row input[type="checkbox"]:not(:disabled)'));
        const todos = Array.from(moduloCard.querySelectorAll('.permiso-row input[type="checkbox"]'));
        const concedidos = todos.filter(function (c) { return c.checked; }).length;
        const count = moduloCard.querySelector('.modulo-count');
        if (count) {
            count.textContent = concedidos + '/' + todos.length;
            count.title = concedidos + ' de ' + todos.length + ' permisos incluidos';
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

    document.querySelectorAll('.permiso-row input[type="checkbox"]').forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            const row = this.closest('.permiso-row');
            row.classList.toggle('concedido', this.checked);
            row.classList.toggle('denegado', !this.checked);

            actualizarModuloCheckbox(this.closest('.modulo-card'));
            actualizarResumen();
            if (filtroActivo !== 'todos') aplicarFiltros();
        });
    });

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

    function mostrarAlerta(texto, tipo) {
        const alerta = document.getElementById('alertGuardado');
        alerta.textContent = texto;
        alerta.className = 'alerta-guardado ' + tipo;
        alerta.style.display = 'block';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function getCookie(name) {
        let value = null;
        document.cookie.split(';').forEach(function (c) {
            const [k, v] = c.trim().split('=');
            if (k === name) value = decodeURIComponent(v);
        });
        return value;
    }

    async function guardar() {
        const nombre = document.getElementById('perfilNombre').value.trim();
        if (!nombre) {
            mostrarAlerta('Ponele un nombre al perfil.', 'fail');
            return;
        }
        const descripcion = document.getElementById('perfilDescripcion').value.trim();
        const permisos = Array.from(document.querySelectorAll(
            '#formPermisos input[type="checkbox"]:not(:disabled):not(.modulo-select-all-check):checked'
        )).map(function (cb) { return cb.name; });

        const body = { nombre, descripcion, permisos };
        if (window.rolPk) body.pk = window.rolPk;

        try {
            const response = await fetch(window.rolGuardarUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify(body),
            });
            const data = await response.json();

            if (data.error) {
                mostrarAlerta(data.error, 'fail');
                return;
            }

            try {
                sessionStorage.setItem('kai_perfil_guardado', '1');
            } catch { /* almacenamiento no disponible, no es crítico */ }
            window.location.href = window.rolVolverUrl;
        } catch (err) {
            mostrarAlerta('Error de conexión.', 'fail');
            console.error(err);
        }
    }

    document.getElementById('btnGuardar').addEventListener('click', guardar);
    document.getElementById('btnGuardarBottom').addEventListener('click', guardar);
});
