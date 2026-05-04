// ═══════════════════════════════════════════
//  stock.js
//  Archivo: productos/static/productos/js/stock.js
//
//  Depende de las variables globales inyectadas en el template:
//    const URLS = { ajuste: '...', historial: '...' };
//    const CSRF = '...';
// ═══════════════════════════════════════════


// ═══════════════════════════════════════════
//  MODAL AJUSTE MANUAL
// ═══════════════════════════════════════════

function abrirAjuste(btn) {
    const row    = btn.closest('tr');
    const pk     = row.dataset.pk;
    const nombre = row.dataset.nombre;
    const stock  = row.dataset.stock;
    const unidad = row.dataset.unidad;

    document.getElementById('ajustePk').value          = pk;
    document.getElementById('modalAjusteTitulo').textContent = nombre;
    document.getElementById('modalAjusteStock').textContent  = `Stock actual: ${stock} ${unidad}`;
    document.getElementById('ajusteTipo').value         = '';
    document.getElementById('ajusteCantidad').value     = '';
    document.getElementById('ajusteMotivo').value       = '';
    document.getElementById('ajusteFeedback').style.display = 'none';
    document.querySelectorAll('.tipo-btn').forEach(b => b.classList.remove('selected'));

    document.getElementById('modalAjuste').classList.add('visible');
    document.getElementById('ajusteCantidad').focus();
}

function cerrarModalAjuste() {
    document.getElementById('modalAjuste').classList.remove('visible');
}

function seleccionarTipoAjuste(btn) {
    document.querySelectorAll('.tipo-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    document.getElementById('ajusteTipo').value = btn.dataset.tipo;
}

async function registrarAjuste() {
    const pk       = document.getElementById('ajustePk').value;
    const tipo     = document.getElementById('ajusteTipo').value;
    const cantidad = document.getElementById('ajusteCantidad').value;
    const motivo   = document.getElementById('ajusteMotivo').value;

    if (!tipo)                            return mostrarFeedbackAjuste('Seleccioná el tipo de ajuste.', false);
    if (!cantidad || parseFloat(cantidad) <= 0) return mostrarFeedbackAjuste('Ingresá una cantidad válida.', false);

    const btn = document.getElementById('btnAjuste');
    btn.disabled    = true;
    btn.textContent = 'Registrando…';

    try {
        const res  = await fetch(URLS.ajuste, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
            body:    JSON.stringify({ producto_pk: pk, tipo, cantidad: parseFloat(cantidad), motivo }),
        });
        const data = await res.json();

        if (data.ok) {
            actualizarFilaStock(pk, data.stock_actual, data.stock_bajo);
            mostrarFeedbackAjuste(`✓ Stock: ${data.stock_anterior} → ${data.stock_posterior}`, true);
            setTimeout(cerrarModalAjuste, 1800);
        } else {
            mostrarFeedbackAjuste(data.error || 'Error al registrar.', false);
        }
    } catch {
        mostrarFeedbackAjuste('Error de red.', false);
    }

    btn.disabled    = false;
    btn.textContent = 'Confirmar ajuste';
}

function mostrarFeedbackAjuste(msg, ok) {
    const el = document.getElementById('ajusteFeedback');
    el.textContent   = msg;
    el.className     = `feedback ${ok ? 'ok' : 'error'}`;
    el.style.display = 'block';
}

function actualizarFilaStock(pk, nuevoStock, stockBajo) {
    const el = document.getElementById(`stockQty-${pk}`);
    if (!el) return;

    const row = document.querySelector(`tr[data-pk="${pk}"]`);
    if (row) row.dataset.stock = nuevoStock;

    const val   = parseFloat(nuevoStock);
    const clase = val <= 0 ? 'danger' : (stockBajo ? 'warning' : 'ok');
    el.textContent = (val % 1 === 0 ? parseInt(val) : val).toString()
                     + ' ' + (row ? row.dataset.unidad : '');
    el.className   = `stock-qty ${clase}`;
}

// Cerrar modal al hacer clic fuera
document.getElementById('modalAjuste').addEventListener('click', function (e) {
    if (e.target === this) cerrarModalAjuste();
});


// ═══════════════════════════════════════════
//  MODAL HISTORIAL
// ═══════════════════════════════════════════

async function verHistorial(pk, nombre) {
    document.getElementById('modalHistorialTitle').textContent = `Historial — ${nombre}`;
    document.getElementById('modalHistorialBody').innerHTML    = '<div class="empty-state">Cargando…</div>';
    document.getElementById('modalHistorial').classList.add('visible');
    await cargarHistorial(pk, 1);
}

async function cargarHistorial(pk, pagina) {
    const res  = await fetch(`${URLS.historial}?producto_pk=${pk}&page=${pagina}`);
    const data = await res.json();

    if (!data.movimientos.length) {
        document.getElementById('modalHistorialBody').innerHTML =
            '<div class="empty-state"><p>Este producto no tiene movimientos registrados.</p></div>';
        return;
    }

    let html = '<div class="mov-list">';
    data.movimientos.forEach(m => {
        const signo = m.es_entrada ? '+' : '−';
        html += `
            <div class="mov-item">
                <div class="mov-dot ${m.es_entrada ? 'entrada' : 'salida'}">${signo}</div>
                <div class="mov-body">
                    <div class="mov-tipo">${m.tipo_display}</div>
                    <div class="mov-prod">
                        ${m.stock_anterior} → ${m.stock_posterior}
                        ${m.referencia ? ' · Ref: ' + m.referencia : ''}
                        ${m.motivo     ? ' · ' + m.motivo          : ''}
                    </div>
                </div>
                <div class="mov-right">
                    <div class="mov-qty ${m.es_entrada ? 'entrada' : 'salida'}">${signo}${m.cantidad}</div>
                    <div class="mov-meta">${m.usuario} · ${m.fecha}</div>
                </div>
            </div>`;
    });
    html += '</div>';

    if (data.paginas > 1) {
        html += '<div class="paginacion">';
        if (data.tiene_anterior)
            html += `<button class="pag-btn" onclick="cargarHistorial(${pk}, ${data.pagina - 1})">‹</button>`;
        for (let i = 1; i <= data.paginas; i++)
            html += `<button class="pag-btn ${i === data.pagina ? 'active' : ''}" onclick="cargarHistorial(${pk}, ${i})">${i}</button>`;
        if (data.tiene_siguiente)
            html += `<button class="pag-btn" onclick="cargarHistorial(${pk}, ${data.pagina + 1})">›</button>`;
        html += '</div>';
    }

    document.getElementById('modalHistorialBody').innerHTML = html;
}

function cerrarModalHistorial() {
    document.getElementById('modalHistorial').classList.remove('visible');
}

document.getElementById('modalHistorial').addEventListener('click', function (e) {
    if (e.target === this) cerrarModalHistorial();
});