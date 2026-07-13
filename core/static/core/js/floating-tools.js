// floating-tools.js — Kai-Cart
// Herramientas rápidas flotantes: Contador de billetes y Calculadora de
// vuelto. Son ventanas arrastrables (no modales): no bloquean el resto
// de la pantalla, se pueden mover a cualquier lugar y quedan disponibles
// en cualquier sección del sistema. Se cierran solo con el botón × o
// repitiendo el atajo — nunca con click afuera ni con Escape.
//
// Persistencia entre navegaciones: como cada sección es una carga de
// página nueva (no es una SPA), guardamos en sessionStorage si la
// ventana estaba abierta/minimizada para volver a abrirla apenas carga
// la página siguiente. Usamos sessionStorage (no localStorage) para que
// se "reinicien" solas al cerrar la pestaña/navegador, no para siempre.
//
// Atajos:
//   Ctrl+Alt+B → Contador de billetes
//   Ctrl+Alt+U → Calculadora de vuelto  (la "V" ya la usa Ventas)

(function () {

    // ── Utilidad: formateo de montos ────────────────────────────────────
    function formatearMonto(num) {
        return '$' + num.toLocaleString('es-AR', { maximumFractionDigits: 2 });
    }

    // ── Persistencia de estado (abierta / minimizada / cerrada) ─────────
    const ESTADO_VENTANAS_KEY = 'floatingToolsEstado';

    function leerEstadoVentanas() {
        try {
            return JSON.parse(sessionStorage.getItem(ESTADO_VENTANAS_KEY) || '{}');
        } catch (e) { return {}; }
    }

    function guardarEstadoVentana(id, estado) {
        const actual = leerEstadoVentanas();
        actual[id] = estado; // 'open' | 'minimized' | 'closed'
        sessionStorage.setItem(ESTADO_VENTANAS_KEY, JSON.stringify(actual));
    }

    // ── Arrastrar y persistir posición ──────────────────────────────────
    function hacerArrastrable(el, storageKey) {
        const handle = el.querySelector('[data-drag-handle]');
        if (!handle) return;

        function aplicarPosicion(top, left) {
            const maxTop  = window.innerHeight - 50;
            const maxLeft = window.innerWidth - 50;
            top  = Math.max(0, Math.min(top, maxTop));
            left = Math.max(0, Math.min(left, maxLeft));
            el.style.top = top + 'px';
            el.style.left = left + 'px';
            el.style.right = 'auto';
            el.style.bottom = 'auto';
        }

        try {
            const guardada = JSON.parse(localStorage.getItem(storageKey) || 'null');
            if (guardada) aplicarPosicion(guardada.top, guardada.left);
        } catch (e) { /* posición por defecto (CSS / inline inicial) */ }

        let arrastrando = false;
        let offsetX = 0, offsetY = 0;

        handle.addEventListener('pointerdown', function (e) {
            if (e.target.closest('.floating-tool-btn')) return;

            arrastrando = true;
            el.classList.add('dragging');
            traerAlFrente(el);

            const rect = el.getBoundingClientRect();
            offsetX = e.clientX - rect.left;
            offsetY = e.clientY - rect.top;
            handle.setPointerCapture(e.pointerId);
        });

        handle.addEventListener('pointermove', function (e) {
            if (!arrastrando) return;
            aplicarPosicion(e.clientY - offsetY, e.clientX - offsetX);
        });

        function terminarArrastre(e) {
            if (!arrastrando) return;
            arrastrando = false;
            el.classList.remove('dragging');
            localStorage.setItem(storageKey, JSON.stringify({
                top: parseInt(el.style.top, 10),
                left: parseInt(el.style.left, 10)
            }));
        }
        handle.addEventListener('pointerup', terminarArrastre);
        handle.addEventListener('pointercancel', terminarArrastre);
    }

    let zIndexActual = 950;
    function traerAlFrente(el) {
        zIndexActual += 1;
        el.style.zIndex = zIndexActual;
    }

    function posicionInicial(el, offset) {
        if (el.style.top || el.style.left) return;
        el.style.top = (70 + offset) + 'px';
        el.style.right = (24 + offset) + 'px';
    }

    function marcarNavItemActivo(id, activo) {
        const btn = document.querySelector('[data-tool-trigger="' + id + '"]');
        if (btn) btn.classList.toggle('active', activo);
    }

    // ══════════════════════════════════════════════════════════════════
    // CONTADOR DE BILLETES
    // ══════════════════════════════════════════════════════════════════
    const BILLETES_KEY = 'contadorBilletesDenominaciones';

    // Orden de mayor a menor (antes estaba de menor a mayor).
    function ordenDescendente(a, b) { return b.valor - a.valor; }

    function leerBilletes() {
        try {
            const data = JSON.parse(localStorage.getItem(BILLETES_KEY) || '[]');
            return Array.isArray(data) ? data : [];
        } catch (e) { return []; }
    }

    function guardarBilletes(lista) {
        localStorage.setItem(BILLETES_KEY, JSON.stringify(lista));
    }

    function renderBilletes() {
        const cont = document.getElementById('billetesFilas');
        if (!cont) return;

        const lista = leerBilletes().sort(ordenDescendente);
        cont.innerHTML = '';

        if (lista.length === 0) {
            cont.innerHTML = '<p class="billetes-vacio">Todavía no cargaste ninguna denominación. Agregá la primera abajo.</p>';
        }

        let total = 0;

        lista.forEach(function (item, index) {
            total += item.valor * item.cantidad;

            const fila = document.createElement('div');
            fila.className = 'billete-fila';
            fila.innerHTML =
                '<span class="billete-valor">' + formatearMonto(item.valor) + '</span>' +
                '<input type="number" class="billete-cantidad-input" min="0" step="1" value="' + item.cantidad + '" data-index="' + index + '" aria-label="Cantidad de billetes de ' + formatearMonto(item.valor) + '">' +
                '<span class="billete-subtotal">' + formatearMonto(item.valor * item.cantidad) + '</span>' +
                '<button type="button" class="billete-eliminar" data-index="' + index + '" aria-label="Quitar esta denominación">×</button>';
            cont.appendChild(fila);
        });

        const totalEl = document.getElementById('billetesTotal');
        if (totalEl) totalEl.textContent = formatearMonto(total);

        cont.querySelectorAll('.billete-cantidad-input').forEach(function (input) {
            input.addEventListener('input', function () {
                const idx = parseInt(this.dataset.index, 10);
                const listaActual = leerBilletes().sort(ordenDescendente);
                const cantidad = parseInt(this.value, 10);
                listaActual[idx].cantidad = isNaN(cantidad) ? 0 : cantidad;
                guardarBilletes(listaActual);
                renderBilletes();
            });
        });

        cont.querySelectorAll('.billete-eliminar').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const idx = parseInt(this.dataset.index, 10);
                const listaActual = leerBilletes().sort(ordenDescendente);
                listaActual.splice(idx, 1);
                guardarBilletes(listaActual);
                renderBilletes();
            });
        });
    }

    window.agregarDenominacion = function () {
        const valorInput = document.getElementById('billeteNuevoValor');
        const cantidadInput = document.getElementById('billeteNuevaCantidad');

        const valor = parseFloat(valorInput.value);
        const cantidad = parseInt(cantidadInput.value, 10) || 0;

        if (!valor || valor <= 0) {
            KaiToast.show('Ingresá un valor de billete válido.', 'warning');
            valorInput.focus();
            return;
        }

        const lista = leerBilletes();
        const existente = lista.find(function (b) { return b.valor === valor; });
        if (existente) {
            existente.cantidad += cantidad;
        } else {
            lista.push({ valor: valor, cantidad: cantidad });
        }

        guardarBilletes(lista);
        valorInput.value = '';
        cantidadInput.value = '0';
        renderBilletes();
        valorInput.focus();
    };

    // Reemplaza al viejo "Borrar todo" (que eliminaba las denominaciones
    // cargadas). Ahora solo pone las cantidades en 0 — las denominaciones
    // quedan guardadas, porque eso casi no cambia y no tiene sentido
    // volver a cargarlas cada vez. Para sacar una denominación puntual
    // sigue estando el × de cada fila.
    window.reiniciarContadorBilletes = async function () {
        const lista = leerBilletes();
        if (lista.length === 0) return;
        if (!await KaiConfirm('¿Poner todas las cantidades en 0? Las denominaciones cargadas se mantienen.')) return;
        lista.forEach(function (item) { item.cantidad = 0; });
        guardarBilletes(lista);
        renderBilletes();
    };

    // Botón "+" discreto: el formulario de alta queda oculto por defecto
    // y se despliega solo cuando se lo pide, ya que se usa muy poco.
    window.toggleFormAgregarBillete = function (forzarEstado) {
        const form = document.getElementById('billetesAgregarForm');
        const btn  = document.getElementById('btnToggleAgregarBillete');
        if (!form) return;
        const mostrar = typeof forzarEstado === 'boolean' ? forzarEstado : form.classList.contains('oculto');
        form.classList.toggle('oculto', !mostrar);
        if (btn) btn.textContent = mostrar ? '– Ocultar' : '+ Agregar denominación';
        if (mostrar) {
            const valorInput = document.getElementById('billeteNuevoValor');
            if (valorInput) valorInput.focus();
        }
    };

    window.toggleFloatingBilletes = function (forzarEstado) {
        const win = document.getElementById('floatingBilletes');
        if (!win) return;
        const abrir = typeof forzarEstado === 'boolean' ? forzarEstado : !win.classList.contains('open');
        win.classList.toggle('open', abrir);
        marcarNavItemActivo('floatingBilletes', abrir);
        guardarEstadoVentana('floatingBilletes', abrir ? 'open' : 'closed');
        if (abrir) {
            win.classList.remove('minimized');
            traerAlFrente(win);
            renderBilletes();
        }
    };

    // ══════════════════════════════════════════════════════════════════
    // CALCULADORA DE VUELTO
    // ══════════════════════════════════════════════════════════════════
    window.calcularVuelto = function () {
        const recibidoInput = document.getElementById('vueltoRecibido');
        const aCobrarInput  = document.getElementById('vueltoACobrar');
        const montoEl       = document.getElementById('vueltoMonto');
        const labelEl       = document.querySelector('#vueltoResultado span:first-child');
        if (!recibidoInput || !aCobrarInput || !montoEl || !labelEl) return;

        const recibido = parseFloat(recibidoInput.value) || 0;
        const aCobrar  = parseFloat(aCobrarInput.value) || 0;
        const vuelto   = recibido - aCobrar;

        if (vuelto < 0) {
            labelEl.textContent = 'Falta';
            montoEl.classList.add('vuelto-negativo');
        } else {
            labelEl.textContent = 'Vuelto';
            montoEl.classList.remove('vuelto-negativo');
        }
        montoEl.textContent = formatearMonto(Math.abs(vuelto));
    };

    window.toggleFloatingVuelto = function (forzarEstado) {
        const win = document.getElementById('floatingVuelto');
        if (!win) return;
        const abrir = typeof forzarEstado === 'boolean' ? forzarEstado : !win.classList.contains('open');
        win.classList.toggle('open', abrir);
        marcarNavItemActivo('floatingVuelto', abrir);
        guardarEstadoVentana('floatingVuelto', abrir ? 'open' : 'closed');
        if (abrir) {
            win.classList.remove('minimized');
            traerAlFrente(win);
            document.getElementById('vueltoRecibido').value = '';
            document.getElementById('vueltoACobrar').value = '';
            calcularVuelto();
            setTimeout(function () {
                const el = document.getElementById('vueltoACobrar');
                if (el) el.focus();
            }, 50);
        }
    };

    // ── Minimizar (cualquiera de las dos ventanas) ──────────────────────
    window.minimizarFloatingTool = function (id) {
        const win = document.getElementById(id);
        if (!win) return;
        win.classList.toggle('minimized');
        guardarEstadoVentana(id, win.classList.contains('minimized') ? 'minimized' : 'open');
    };

    // Restaura, sin resetear campos ni robar foco, el estado que tenían
    // las ventanas antes de navegar a esta página.
    function restaurarEstadoVentanas(billetesWin, vueltoWin) {
        const estado = leerEstadoVentanas();

        [['floatingBilletes', billetesWin], ['floatingVuelto', vueltoWin]].forEach(function (par) {
            const id = par[0];
            const win = par[1];
            if (!win) return;
            const guardado = estado[id];
            if (guardado !== 'open' && guardado !== 'minimized') return;

            win.classList.add('open');
            traerAlFrente(win);
            marcarNavItemActivo(id, true);
            if (guardado === 'minimized') win.classList.add('minimized');
            if (id === 'floatingBilletes') renderBilletes();
        });
    }

    // ── Inicialización ───────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        const billetesWin = document.getElementById('floatingBilletes');
        const vueltoWin   = document.getElementById('floatingVuelto');

        if (billetesWin) {
            posicionInicial(billetesWin, 0);
            hacerArrastrable(billetesWin, 'floatingBilletesPos');
        }
        if (vueltoWin) {
            posicionInicial(vueltoWin, 40);
            hacerArrastrable(vueltoWin, 'floatingVueltoPos');
        }

        restaurarEstadoVentanas(billetesWin, vueltoWin);

        const vueltoRecibido = document.getElementById('vueltoRecibido');
        const vueltoACobrar  = document.getElementById('vueltoACobrar');
        if (vueltoRecibido && vueltoACobrar) {
            vueltoRecibido.addEventListener('input', calcularVuelto);
            vueltoACobrar.addEventListener('input', calcularVuelto);
        }

        document.addEventListener('keydown', function (e) {
            if (!e.ctrlKey || !e.altKey || e.shiftKey) return;
            const key = (e.key || '').toLowerCase();

            if (key === 'b') { e.preventDefault(); toggleFloatingBilletes(); return; }
            if (key === 'u') { e.preventDefault(); toggleFloatingVuelto(); return; }
        });
    });

})();