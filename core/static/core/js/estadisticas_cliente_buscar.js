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

    function ocultar() {
        resultadosEl.hidden = true;
        resultadosEl.innerHTML = '';
    }

    inputEl.addEventListener('input', () => {
        clearTimeout(timeout);
        const q = inputEl.value.trim();
        if (q.length < 2) {
            ocultar();
            return;
        }
        timeout = setTimeout(async () => {
            try {
                const resp = await fetch(`${urlBuscar}?q=${encodeURIComponent(q)}`);
                const data = await resp.json();
                const clientes = data.clientes || [];
                if (!clientes.length) {
                    resultadosEl.innerHTML = '<div class="cp-buscador-item-vacio">Sin resultados</div>';
                    resultadosEl.hidden = false;
                    return;
                }
                resultadosEl.innerHTML = clientes.map(c => `
                    <div class="cp-buscador-item" data-id="${c.id}">
                        <span>${_ecEsc(c.label)}</span>
                    </div>`).join('');
                resultadosEl.hidden = false;
            } catch (err) {
                console.error('Error buscando cliente:', err);
            }
        }, 300);
    });

    resultadosEl.addEventListener('click', (ev) => {
        const item = ev.target.closest('.cp-buscador-item[data-id]');
        if (!item) return;
        window.location.href = urlPerfilBase + item.dataset.id + '/';
    });

    document.addEventListener('click', (ev) => {
        if (!inputEl.contains(ev.target) && !resultadosEl.contains(ev.target)) ocultar();
    });
}
