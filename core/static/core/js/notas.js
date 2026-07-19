/* core/static/core/js/notas.js — Anotador (Herramientas) */
'use strict';

(function () {
    const tbody       = document.getElementById('notasTbody');
    if (!tbody) return; // sin permiso para ver, no hay tabla

    const contador    = document.getElementById('notasContador');
    const buscar      = document.getElementById('notasBuscar');
    const btnNueva    = document.getElementById('btnNuevaNota');

    const modalEl     = document.getElementById('notaModal');
    const modal       = new bootstrap.Modal(modalEl);
    const modalTitulo = document.getElementById('notaModalTitulo');
    const notaPk       = document.getElementById('notaPk');
    const notaTitulo   = document.getElementById('notaTitulo');
    const notaMeta     = document.getElementById('notaMeta');
    const notaContenido = document.getElementById('notaContenido');
    const notaPrivadaWrap = document.getElementById('notaPrivadaWrap');
    const notaPrivada  = document.getElementById('notaPrivada');
    const notaMsg      = document.getElementById('notaMsg');
    const btnGuardar   = document.getElementById('btnGuardarNota');
    const btnEliminar  = document.getElementById('btnEliminarNota');

    let notas = [];

    function escapeHtml(s) {
        return (s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    function iniciales(nombre) {
        const partes = (nombre || '').trim().split(/\s+/).filter(Boolean);
        if (!partes.length || partes[0] === '—') return '?';
        return (partes[0][0] + (partes[1] ? partes[1][0] : '')).toUpperCase();
    }

    function autorHtml(nombre) {
        if (!nombre) return '<span class="nota-sin-dato">—</span>';
        return `<span class="nota-autor"><span class="nota-avatar">${escapeHtml(iniciales(nombre))}</span>${escapeHtml(nombre)}</span>`;
    }

    async function cargarNotas() {
        const params = new URLSearchParams();
        if (buscar.value.trim()) params.set('q', buscar.value.trim());
        const resp = await fetch(`${NOTAS_URLS.listar}?${params.toString()}`);
        const data = await resp.json();
        if (data.error) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">${escapeHtml(data.error)}</td></tr>`;
            return;
        }
        notas = data.results;
        contador.textContent = notas.length;
        renderTabla();
    }

    function renderTabla() {
        if (!notas.length) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">Todavía no hay notas.</td></tr>`;
            return;
        }
        tbody.innerHTML = notas.map((n) => `
            <tr data-pk="${n.pk}">
                <td>
                    <span class="nota-titulo-cell">
                        <svg class="nota-icono" width="14" height="14" viewBox="0 0 16 16" fill="none">
                            <path d="M4 2H10.5L13 4.5V14H4V2Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
                            <path d="M10.5 2V4.5H13" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
                        </svg>
                        ${escapeHtml(n.titulo)}
                        ${n.es_privada ? `<span class="nota-badge-privada"><svg width="9" height="9" viewBox="0 0 12 12" fill="none"><rect x="2.5" y="5.5" width="7" height="5" rx="1" stroke="currentColor" stroke-width="1.1"/><path d="M4 5.5V3.8C4 2.8 4.9 2 6 2C7.1 2 8 2.8 8 3.8V5.5" stroke="currentColor" stroke-width="1.1"/></svg>Privada</span>` : ''}
                    </span>
                </td>
                <td>${autorHtml(n.creado_por)}</td>
                <td class="nota-fecha">${n.fecha_alta}</td>
                <td class="nota-fecha">${n.fecha_modificacion}</td>
                <td>${autorHtml(n.modificado_por)}</td>
                <td class="notas-acciones-cell">
                    ${n.puede_eliminar ? `<button type="button" class="btn-ghost-sm btn-eliminar-nota" data-pk="${n.pk}" title="Eliminar">
                        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 4H11M4.5 4V3H8.5V4M5 6.5V10M8 6.5V10M2.8 4L3.5 11H9.5L10.2 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </button>` : ''}
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('tr').forEach((tr) => {
            tr.addEventListener('click', (e) => {
                if (e.target.closest('.btn-eliminar-nota')) return;
                abrirNota(parseInt(tr.dataset.pk, 10));
            });
        });
        tbody.querySelectorAll('.btn-eliminar-nota').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                eliminarNota(parseInt(btn.dataset.pk, 10));
            });
        });
    }

    function abrirNota(pk) {
        const n = notas.find((x) => x.pk === pk);
        if (!n) return;

        modalTitulo.textContent = 'Nota';
        notaPk.value = n.pk;
        notaTitulo.value = n.titulo;
        notaTitulo.disabled = !n.puede_editar;
        notaContenido.value = n.contenido;
        notaContenido.disabled = !n.puede_editar;
        notaMeta.style.display = '';
        notaMeta.textContent = `Creada por ${n.creado_por} el ${n.fecha_alta}` +
            (n.modificado_por ? ` — última edición de ${n.modificado_por} el ${n.fecha_modificacion}` : '');

        notaPrivadaWrap.style.display = (NOTAS_PUEDE_CREAR_PRIVADAS || n.es_privada) ? 'flex' : 'none';
        notaPrivada.checked = n.es_privada;
        notaPrivada.disabled = !n.puede_editar || !NOTAS_PUEDE_CREAR_PRIVADAS;

        btnGuardar.style.display = n.puede_editar ? '' : 'none';
        btnEliminar.style.display = n.puede_eliminar ? '' : 'none';
        btnEliminar.dataset.pk = n.pk;
        notaMsg.style.display = 'none';

        modal.show();
    }

    if (btnNueva) {
        btnNueva.addEventListener('click', () => {
            modalTitulo.textContent = 'Nueva nota';
            notaPk.value = '';
            notaTitulo.value = '';
            notaTitulo.disabled = false;
            notaContenido.value = '';
            notaContenido.disabled = false;
            notaMeta.style.display = 'none';
            notaPrivadaWrap.style.display = NOTAS_PUEDE_CREAR_PRIVADAS ? 'flex' : 'none';
            notaPrivada.checked = false;
            notaPrivada.disabled = false;
            btnGuardar.style.display = '';
            btnEliminar.style.display = 'none';
            notaMsg.style.display = 'none';
            modal.show();
        });
    }

    btnGuardar.addEventListener('click', async () => {
        const titulo = notaTitulo.value.trim();
        if (!titulo) {
            notaMsg.textContent = 'Ponele un título a la nota.';
            notaMsg.style.display = '';
            return;
        }
        const contenido = notaContenido.value.trim();
        if (!contenido) {
            notaMsg.textContent = 'La nota no puede estar vacía.';
            notaMsg.style.display = '';
            return;
        }
        const body = {
            titulo,
            contenido,
            es_privada: notaPrivada.checked,
        };
        if (notaPk.value) body.pk = notaPk.value;

        const resp = await fetch(NOTAS_URLS.acciones, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            notaMsg.textContent = data.error || 'No se pudo guardar la nota.';
            notaMsg.style.display = '';
            return;
        }
        modal.hide();
        KaiToast.show(notaPk.value ? 'Nota actualizada.' : 'Nota creada.', 'success');
        cargarNotas();
    });

    btnEliminar.addEventListener('click', async () => {
        const pk = btnEliminar.dataset.pk;
        modal.hide();
        eliminarNota(parseInt(pk, 10));
    });

    async function eliminarNota(pk) {
        const ok = await KaiConfirm('¿Eliminar esta nota? No se puede deshacer.', { danger: true, confirmText: 'Eliminar' });
        if (!ok) return;

        const resp = await fetch(NOTAS_URLS.eliminar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ pk }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            KaiToast.show(data.error || 'No se pudo eliminar la nota.', 'danger');
            return;
        }
        KaiToast.show('Nota eliminada.', 'success');
        cargarNotas();
    }

    let buscarDebounce = null;
    buscar.addEventListener('input', () => {
        clearTimeout(buscarDebounce);
        buscarDebounce = setTimeout(cargarNotas, 300);
    });

    cargarNotas();
})();
