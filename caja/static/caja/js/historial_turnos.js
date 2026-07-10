function htEliminarHistorial() {
    const cantidad = HT_URLS.cantidadTurnos;
    if (!confirm('¿Estás seguro de eliminar TODO el historial de turnos? Esta acción no se puede deshacer.')) return;
    if (!confirm('Esta acción eliminará ' + cantidad + ' turnos. ¿Continuar?')) return;

    fetch(HT_URLS.eliminar, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': HT_URLS.csrf
        }
    })
        .then(res => res.json())
        .then(data => {
            if (data.ok) { alert(data.mensaje); location.reload(); }
            else { alert(data.error || 'Error al eliminar historial'); }
        })
        .catch(() => alert('Error de conexión'));
}
