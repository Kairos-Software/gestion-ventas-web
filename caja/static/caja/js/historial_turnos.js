/* ══════════════════════════════════════════════════════════════════
   REABRIR TURNO — vuelve un turno cerrado a estado abierto para
   corregirlo. Ver TurnoCaja.reabrir() en caja/models.py.
   ══════════════════════════════════════════════════════════════════ */
(function () {
    const overlay = document.getElementById('htReabrirOverlay');
    if (!overlay) return;

    const numEl = document.getElementById('htReabrirNum');
    const efEl = document.getElementById('htReabrirEfectivo');
    const ventanaEl = document.getElementById('htReabrirVentana');
    const motivoEl = document.getElementById('htReabrirMotivo');
    const btnOk = document.getElementById('htReabrirConfirmar');
    const btnCancel = document.getElementById('htReabrirCancelar');
    let pkActual = null;

    function abrir(btn) {
        pkActual = btn.dataset.turnoPk;
        numEl.textContent = '#' + btn.dataset.turnoNumero;
        // data-efectivo ya viene formateado por el server (floatformat)
        efEl.textContent = '$ ' + btn.dataset.efectivo;
        ventanaEl.hidden = btn.dataset.esUltimo === '1';
        motivoEl.value = '';
        btnOk.disabled = false;
        overlay.hidden = false;
        document.body.style.overflow = 'hidden';
        setTimeout(() => motivoEl.focus(), 50);
    }
    function cerrar() {
        overlay.hidden = true;
        document.body.style.overflow = '';
        pkActual = null;
    }

    document.querySelectorAll('.ht-reabrir-btn').forEach((b) => {
        b.addEventListener('click', () => abrir(b));
    });
    btnCancel.addEventListener('click', cerrar);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) cerrar(); });
    document.addEventListener('keydown', (e) => {
        if (!overlay.hidden && e.key === 'Escape') cerrar();
    });

    btnOk.addEventListener('click', async () => {
        const motivo = motivoEl.value.trim();
        if (!motivo) {
            KaiToast.show('Escribí el motivo para reabrir el turno.', 'warning');
            motivoEl.focus();
            return;
        }
        btnOk.disabled = true;
        try {
            const res = await fetch(HT_URLS.reabrirBase.replace('/0/', '/' + pkActual + '/'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': HT_URLS.csrf },
                body: JSON.stringify({ motivo }),
            });
            const data = await res.json();
            if (res.ok && data.ok) {
                KaiToast.show(data.mensaje || 'Turno reabierto.', 'success', 6000);
                setTimeout(() => location.reload(), 1600);
            } else {
                btnOk.disabled = false;
                KaiToast.show(data.error || 'No se pudo reabrir el turno.', 'danger', 6000);
            }
        } catch (e) {
            btnOk.disabled = false;
            KaiToast.show('Error de conexión.', 'danger');
        }
    });
})();


async function htEliminarHistorial() {
    const cantidad = HT_URLS.cantidadTurnos;
    const ok = await KaiConfirm(
        `Se van a eliminar ${cantidad} turnos de forma permanente. Esta acción no se puede deshacer.`,
        { title: '¿Eliminar todo el historial?', danger: true, confirmText: 'Eliminar todo' }
    );
    if (!ok) return;

    fetch(HT_URLS.eliminar, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': HT_URLS.csrf
        }
    })
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                KaiToast.show(data.mensaje, 'success');
                setTimeout(() => location.reload(), 1400);
            } else {
                KaiToast.show(data.error || 'Error al eliminar historial', 'danger');
            }
        })
        .catch(() => KaiToast.show('Error de conexión', 'danger'));
}
