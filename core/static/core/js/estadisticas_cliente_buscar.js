/**
 * estadisticas_cliente_buscar.js
 * ─────────────────────────────────────────────────────────────────
 * Buscador de cliente en Estadísticas → Clientes: autocomplete que al
 * elegir un cliente redirige a su ficha individual
 * (estadisticas_cliente_perfil). Mismo patrón de debounce que el
 * buscador de cliente en caja/static/caja/js/cuentas_cobrar.js, pero
 * consumiendo core:cliente_buscar (que ya usa gestion_clientes.html)
 * en vez de un endpoint nuevo.
 *
 * Expone: initBuscadorClienteEstadisticas(inputEl, resultadosEl, urlBuscar, urlPerfilBase)
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _ecEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function initBuscadorClienteEstadisticas(inputEl, resultadosEl, urlBuscar, urlPerfilBase) {
    if (!inputEl || !resultadosEl) return;

    let timeout = null;
    let busquedaActual = 0;

    function ocultar() {
        resultadosEl.hidden = true;
        resultadosEl.innerHTML = '';
    }

    inputEl.addEventListener('input', () => {
        clearTimeout(timeout);
        const numeroBusqueda = ++busquedaActual;
        const q = inputEl.value.trim();
        if (q.length < 2) {
            ocultar();
            return;
        }
        timeout = setTimeout(async () => {
            try {
                const resp = await fetch(`${urlBuscar}?q=${encodeURIComponent(q)}`);
                const data = await resp.json();
                if (numeroBusqueda !== busquedaActual) return;
                const clientes = data.clientes || [];
                if (!clientes.length) {
                    resultadosEl.innerHTML = '<div class="cp-buscador-item-vacio">Sin resultados</div>';
                    resultadosEl.hidden = false;
                    return;
                }
                resultadosEl.innerHTML = clientes.map(c => `
                    <a class="cp-buscador-item" href="${urlPerfilBase}${encodeURIComponent(c.id)}/">
                        <span>${_ecEsc(c.label)}</span>
                    </a>`).join('');
                resultadosEl.hidden = false;
            } catch (err) {
                console.error('Error buscando cliente:', err);
            }
        }, 300);
    });

    inputEl.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') ocultar();
        if (ev.key === 'Enter' && !resultadosEl.hidden) {
            const primero = resultadosEl.querySelector('a.cp-buscador-item');
            if (primero) { ev.preventDefault(); primero.click(); }
        }
        if (ev.key === 'ArrowDown' && !resultadosEl.hidden) {
            const primero = resultadosEl.querySelector('a.cp-buscador-item');
            if (primero) { ev.preventDefault(); primero.focus(); }
        }
    });

    resultadosEl.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') { ocultar(); inputEl.focus(); return; }
        if (ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp') return;
        const enlaces = Array.from(resultadosEl.querySelectorAll('a.cp-buscador-item'));
        const actual = enlaces.indexOf(document.activeElement);
        const siguiente = ev.key === 'ArrowDown' ? actual + 1 : actual - 1;
        ev.preventDefault();
        if (siguiente < 0) inputEl.focus();
        else enlaces[Math.min(siguiente, enlaces.length - 1)]?.focus();
    });

    document.addEventListener('click', (ev) => {
        if (!inputEl.contains(ev.target) && !resultadosEl.contains(ev.target)) ocultar();
    });
}
