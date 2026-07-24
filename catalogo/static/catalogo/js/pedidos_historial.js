/* catalogo/pedidos_historial.js — acciones sobre la fila de un pedido
   en el historial (vender, descartar, reactivar, eliminar). Usa los
   mismos KaiToast/KaiConfirm globales que el resto del sistema interno
   (ver core/static/core/js/notify.js) y getCookie() de base.js. */
(function () {
    'use strict';

    const URLS = window.PEDIDOS_HISTORIAL_URLS;
    if (!URLS) return;

    function fila(pk) {
        return document.querySelector(`.ped-row[data-pk="${pk}"]`);
    }

    function actualizarContador(delta) {
        const el = document.getElementById('pedHistorialCount');
        if (!el) return;
        const restante = Math.max(0, parseInt(el.textContent, 10) + delta);
        el.textContent = `${restante} pedido${restante === 1 ? '' : 's'}`;
    }

    async function post(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body || {}),
        });
        let data = {};
        try { data = await res.json(); } catch (e) { /* respuesta sin cuerpo */ }
        return { ok: res.ok, data };
    }

    document.getElementById('pedHistorialBody').addEventListener('click', async function (e) {
        const btnVender = e.target.closest('[data-pedido-vender]');
        if (btnVender) {
            btnVender.disabled = true;
            const { ok, data } = await post(URLS.venderBase + btnVender.dataset.pedidoVender + '/vender/');
            if (ok && data.ok) {
                window.location.href = data.redirect;
            } else {
                KaiToast.show(data.error || 'No se pudo cargar la venta.', 'danger');
                btnVender.disabled = false;
            }
            return;
        }

        const btnDescartar = e.target.closest('[data-pedido-descartar]');
        if (btnDescartar) {
            const okConfirm = await KaiConfirm('¿Descartar este pedido? Vas a poder reactivarlo después si te arrepentís.', { title: 'Descartar pedido' });
            if (!okConfirm) return;
            const pk = btnDescartar.dataset.pedidoDescartar;
            const { ok, data } = await post(URLS.cambiarEstadoBase + pk + '/cambiar-estado/', { accion: 'descartar' });
            if (ok && data.ok) {
                window.location.reload();
            } else {
                KaiToast.show(data.error || 'No se pudo descartar el pedido.', 'danger');
            }
            return;
        }

        const btnReactivar = e.target.closest('[data-pedido-reactivar]');
        if (btnReactivar) {
            const pk = btnReactivar.dataset.pedidoReactivar;
            const { ok, data } = await post(URLS.cambiarEstadoBase + pk + '/cambiar-estado/', { accion: 'reactivar' });
            if (ok && data.ok) {
                window.location.reload();
            } else {
                KaiToast.show(data.error || 'No se pudo reactivar el pedido.', 'danger');
            }
            return;
        }

        const btnEliminar = e.target.closest('[data-pedido-eliminar]');
        if (btnEliminar) {
            const nombre = btnEliminar.dataset.pedidoNombre || 'este pedido';
            const okConfirm = await KaiConfirm(
                `¿Eliminar el pedido de ${nombre}? Esto borra solo el registro del pedido — si ya se convirtió en venta, la venta no se toca.`,
                { title: 'Eliminar pedido', danger: true, confirmText: 'Eliminar' },
            );
            if (!okConfirm) return;
            const pk = btnEliminar.dataset.pedidoEliminar;
            const { ok, data } = await post(URLS.eliminarBase + pk + '/eliminar/');
            if (ok && data.ok) {
                const row = fila(pk);
                if (row) row.remove();
                actualizarContador(-1);
                KaiToast.show('Pedido eliminado.', 'success');
            } else {
                KaiToast.show(data.error || 'No se pudo eliminar el pedido.', 'danger');
            }
        }
    });
})();
