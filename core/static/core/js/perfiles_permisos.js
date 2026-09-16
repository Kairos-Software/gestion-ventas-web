/* core/static/core/js/perfiles_permisos.js
 * "Perfiles de permisos" — paquetes de permisos con nombre que se eligen al
 * crear/editar un usuario (ver Rol en core/models.py). Vive en la misma
 * pantalla que Gestión de Personal (gestion_usuarios.html). Cuatro permisos
 * independientes (igual que el resto del sistema): ver_roles gatea el botón
 * y el modal de lista; crear/editar_roles gatean el link "+ Nuevo perfil" y
 * "Editar" (que llevan a la pantalla completa rol_permisos.html — misma UI
 * que la de permisos de un usuario); eliminar_roles gatea "Eliminar" acá
 * mismo. Ver window.rolesPermisos, calculado server-side.
 */
'use strict';

(function () {
    const btnAbrir = document.getElementById('btnPerfilesPermisos');
    if (!btnAbrir) return; // sin ver_roles, el botón ni existe

    const permisos = window.rolesPermisos || {};

    const perfilesModalEl   = document.getElementById('perfilesModal');
    const perfilesModal     = new bootstrap.Modal(perfilesModalEl);
    const perfilesTbody     = document.getElementById('perfilesTbody');
    const perfilesListaMsg  = document.getElementById('perfilesListaMsg');

    const eliminarModalEl    = document.getElementById('perfilEliminarModal');
    const eliminarModal       = new bootstrap.Modal(eliminarModalEl);
    const perfilNombreEliminar = document.getElementById('perfilNombreEliminar');
    const perfilEliminarMsg   = document.getElementById('perfilEliminarMsg');
    const btnConfirmarEliminarPerfil = document.getElementById('btnConfirmarEliminarPerfil');

    let roles = window.rolesIniciales || [];
    let perfilEliminandoPk = null;

    function escapeHtml(s) {
        return (s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    function urlPermisosDe(pk) {
        return window.rolesUrls.permisosBase.replace('/0/', '/' + pk + '/');
    }

    async function conBotonBloqueado(btn, fn) {
        if (btn.disabled) return;
        btn.disabled = true;
        try {
            await fn();
        } finally {
            btn.disabled = false;
        }
    }

    // ── Select de perfil en el alta/edición de usuario — se mantiene en
    //    sincro con `roles` sin recargar la página cada vez que se crea,
    //    edita o borra un perfil desde acá. ──────────────────────────────
    function refrescarSelectUsuario() {
        const select = document.getElementById('id_rol_pk');
        if (!select) return;
        const actual = select.value;
        select.innerHTML = '<option value="">Sin perfil asignado</option>' +
            roles.map(r => `<option value="${r.pk}">${escapeHtml(r.nombre)}</option>`).join('');
        select.value = roles.some(r => String(r.pk) === actual) ? actual : '';
    }

    // ══════════════════════════════════════════════════════════════
    //  Modal — lista de perfiles
    // ══════════════════════════════════════════════════════════════

    function renderizarLista() {
        if (!roles.length) {
            perfilesTbody.innerHTML = '<tr><td colspan="3" class="text-muted">Sin perfiles cargados todavía.</td></tr>';
            return;
        }
        const mostrarAcciones = permisos.editar || permisos.eliminar;
        perfilesTbody.innerHTML = roles.map(r => `
            <tr>
                <td>${escapeHtml(r.nombre)}</td>
                <td data-label="Usuarios">${r.num_usuarios}</td>
                <td class="usuario-acciones-cell">
                    ${mostrarAcciones ? `<div class="acciones-cell">
                        ${permisos.editar ? `<a href="${urlPermisosDe(r.pk)}" class="btn-accion btn-editar">Editar</a>` : ''}
                        ${permisos.eliminar ? `<button type="button" class="btn-accion btn-eliminar" data-eliminar="${r.pk}">Eliminar</button>` : ''}
                    </div>` : ''}
                </td>
            </tr>
        `).join('');

        perfilesTbody.querySelectorAll('[data-eliminar]').forEach(btn => {
            btn.addEventListener('click', () => abrirConfirmarEliminar(parseInt(btn.dataset.eliminar, 10)));
        });
    }

    async function refrescarLista() {
        try {
            // Se pide fresco cada vez: la lista que vino en el HTML inicial se
            // queda con conteos viejos apenas se crea o edita un usuario con
            // un perfil sin recargar la página.
            const resp = await fetch(window.rolesUrls.listar);
            const data = await resp.json();
            roles = data.roles || roles;
        } catch {
            // Si falla la red, seguimos con lo que ya había en memoria.
        }
        refrescarSelectUsuario();
        renderizarLista();
    }

    btnAbrir.addEventListener('click', async () => {
        perfilesListaMsg.style.display = 'none';
        perfilesModal.show();
        await refrescarLista();
    });

    // ══════════════════════════════════════════════════════════════
    //  Modal — eliminar un perfil
    // ══════════════════════════════════════════════════════════════

    function abrirConfirmarEliminar(pk) {
        const rol = roles.find(r => r.pk === pk);
        if (!rol) return;
        perfilEliminandoPk = pk;
        perfilNombreEliminar.textContent = rol.nombre;
        perfilEliminarMsg.style.display = 'none';
        eliminarModal.show();
    }

    btnConfirmarEliminarPerfil.addEventListener('click', () => conBotonBloqueado(btnConfirmarEliminarPerfil, async () => {
        const resp = await fetch(window.rolesUrls.eliminar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ pk: perfilEliminandoPk }),
        });
        const data = await resp.json();

        if (data.error) {
            perfilEliminarMsg.textContent = data.error;
            perfilEliminarMsg.style.display = '';
            return;
        }

        roles = roles.filter(r => r.pk !== perfilEliminandoPk);
        refrescarSelectUsuario();
        renderizarLista();
        eliminarModal.hide();
        if (window.KaiToast) KaiToast.show('Perfil eliminado.', 'success', 2000);
    }));

    // ── Si venimos de guardar un perfil en rol_permisos.html, mostramos el
    //    toast acá y reabrimos la lista ya actualizada. ──────────────────
    let vieneDeGuardar = false;
    try {
        vieneDeGuardar = sessionStorage.getItem('kai_perfil_guardado') === '1';
        if (vieneDeGuardar) sessionStorage.removeItem('kai_perfil_guardado');
    } catch { /* almacenamiento no disponible, no es crítico */ }

    if (vieneDeGuardar) {
        if (window.KaiToast) KaiToast.show('Perfil guardado.', 'success', 2000);
        perfilesListaMsg.style.display = 'none';
        perfilesModal.show();
        refrescarLista();
    }
})();
