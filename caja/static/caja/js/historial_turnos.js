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
