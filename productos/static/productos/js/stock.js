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

    // Combinaciones del producto: JSON inyectado en data-colores del <tr>.
    // Si el producto no tiene variantes, el array estará vacío.
    let combinaciones = [];
    try {
        combinaciones = JSON.parse(row.dataset.colores || '[]');
    } catch (e) {
        combinaciones = [];
    }

    // ── Resetear campos ────────────────────────────────────────────
    document.getElementById('ajustePk').value                = pk;
    document.getElementById('modalAjusteTitulo').textContent = nombre;
    document.getElementById('modalAjusteStock').textContent  = `Stock actual: ${stock} ${unidad}`;
    document.getElementById('ajusteTipo').value              = '';
    document.getElementById('ajusteCantidad').value          = '';
    document.getElementById('ajusteMotivo').value            = '';
    document.getElementById('ajusteFeedback').style.display  = 'none';
    document.querySelectorAll('.tipo-btn').forEach(b => b.classList.remove('selected'));

    // Resetear botón por si quedó deshabilitado de una operación anterior
    const btnAjuste = document.getElementById('btnAjuste');
    btnAjuste.disabled    = false;
    btnAjuste.textContent = 'Confirmar ajuste';

    // ── Selector de combinación ───────────────────────────────────────────
    const combinacionWrap   = document.getElementById('ajusteCombinacionWrap');
    const combinacionSelect = document.getElementById('ajusteCombinacionSelect');

    if (combinaciones.length > 0) {
        combinacionSelect.innerHTML =
            '<option value="">— Seleccioná una combinación —</option>' +
            combinaciones.map(c => {
                const stockCombinacion = parseFloat(c.stock_actual);
                const stockFmt         = (stockCombinacion % 1 === 0 ? parseInt(stockCombinacion) : stockCombinacion).toString();
                return `<option value="${c.pk}">${c.descripcion_combinacion} (stock: ${stockFmt})</option>`;
            }).join('');
        combinacionWrap.style.display = 'block';
    } else {
        combinacionSelect.innerHTML   = '';
        combinacionWrap.style.display = 'none';
    }

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

    // combinacion_pk: presente solo si el producto tiene variantes y el select está visible
    const combinacionWrap   = document.getElementById('ajusteCombinacionWrap');
    const combinacionSelect = document.getElementById('ajusteCombinacionSelect');
    const combinacionPk     = (combinacionWrap.style.display !== 'none' && combinacionSelect.value)
                                ? combinacionSelect.value
                                : null;

    // ── Validaciones cliente ────────────────────────────────────────
    if (!tipo) {
        return mostrarFeedbackAjuste('Seleccioná el tipo de ajuste.', false);
    }
    if (!cantidad || parseFloat(cantidad) <= 0) {
        return mostrarFeedbackAjuste('Ingresá una cantidad válida.', false);
    }
    if (combinacionWrap.style.display !== 'none' && !combinacionPk) {
        return mostrarFeedbackAjuste('Seleccioná la combinación a ajustar.', false);
    }

    const btn = document.getElementById('btnAjuste');
    // Bloquear el botón para evitar doble envío
    btn.disabled    = true;
    btn.textContent = 'Registrando…';

    try {
        const payload = {
            producto_pk: pk,
            tipo,
            cantidad:    parseFloat(cantidad),
            motivo,
        };
        if (combinacionPk) payload.combinacion_pk = combinacionPk;

        const res  = await fetch(URLS.ajuste, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
            body:    JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.ok) {
            // Actualizar stock total (qty, barra de progreso, badge de estado)
            actualizarFilaStock(pk, data.stock_actual, data.stock_bajo);

            // Actualizar KPIs del header (stock bajo, sin stock, total)
            actualizarKPIs();

            // Si el ajuste fue por combinación, actualizar stock en memoria y chip visual
            if (data.combinacion_pk != null && data.combinacion_stock != null) {
                actualizarStockCombinacionEnRow(pk, data.combinacion_pk, data.combinacion_stock);
                actualizarChipCombinacion(pk, data.combinacion_pk, data.combinacion_stock);
            }

            mostrarFeedbackAjuste(`✓ Stock: ${data.stock_anterior} → ${data.stock_posterior}`, true);

            // Cerrar rápido (600ms) y re-habilitar el botón DESPUÉS de cerrar
            // para que no se pueda hacer doble clic mientras el modal sigue abierto
            setTimeout(() => {
                cerrarModalAjuste();
                btn.disabled    = false;
                btn.textContent = 'Confirmar ajuste';
            }, 600);

        } else {
            mostrarFeedbackAjuste(data.error || 'Error al registrar.', false);
            btn.disabled    = false;
            btn.textContent = 'Confirmar ajuste';
        }
    } catch {
        mostrarFeedbackAjuste('Error de red.', false);
        btn.disabled    = false;
        btn.textContent = 'Confirmar ajuste';
    }
}

function mostrarFeedbackAjuste(msg, ok) {
    const el = document.getElementById('ajusteFeedback');
    el.textContent   = msg;
    el.className     = `feedback ${ok ? 'ok' : 'error'}`;
    el.style.display = 'block';
}

// Actualiza el stock total visible en la fila: qty, barra de progreso y badge de estado
function actualizarFilaStock(pk, nuevoStock, stockBajo) {
    const row = document.querySelector(`tr[data-pk="${pk}"]`);
    if (!row) return;

    const val    = parseFloat(nuevoStock);
    const esBajo = val <= 0 || stockBajo;
    const clase  = esBajo ? 'danger' : 'ok';
    const fmt    = (val % 1 === 0 ? parseInt(val) : val).toString();

    // Actualizar dataset del row
    row.dataset.stock = nuevoStock;

    // Actualizar qty badge
    const el = document.getElementById(`stockQty-${pk}`);
    if (el) {
        el.textContent = `${fmt} ${row.dataset.unidad}`;
        el.className   = `stock-qty ${clase}`;
    }

    // Actualizar barra de progreso
    const fill = row.querySelector('.stock-bar-fill');
    if (fill) {
        fill.className = `stock-bar-fill ${clase}`;
        if (val <= 0) {
            fill.style.width = '3%';
        } else if (stockBajo) {
            fill.style.width = '25%';
        } else {
            // Recalcular porcentaje con los datos disponibles
            const minimo  = parseFloat(row.dataset.minimo) || 0;
            const maximo  = parseFloat(row.dataset.maximo) || 0;
            let pct = 60; // fallback
            if (maximo > 0)       pct = Math.min(100, Math.round((val / maximo) * 100));
            else if (minimo > 0)  pct = Math.min(100, Math.round((val / minimo) * 200));
            fill.style.width = `${pct}%`;
        }
    }

    // Actualizar badge de estado (columna Estado)
    // Usamos .badge-alerta que es la clase base del CSS, más danger/ok según estado
    const estadoBadge = row.querySelector('.badge-alerta');
    if (estadoBadge) {
        if (val <= 0) {
            estadoBadge.textContent = 'Sin stock';
            estadoBadge.className   = 'badge-alerta danger';
        } else if (stockBajo) {
            estadoBadge.textContent = 'Stock bajo';
            estadoBadge.className   = 'badge-alerta danger';
        } else {
            estadoBadge.textContent = 'OK';
            estadoBadge.className   = 'badge-alerta ok';
        }
    }
}

// Recalcula y actualiza los KPI cards del header contando las filas de la tabla
function actualizarKPIs() {
    const filas = document.querySelectorAll('#tablaStock tbody tr[data-pk]');
    let totalActivos = 0, stockBajoCount = 0, sinStockCount = 0;

    filas.forEach(row => {
        const stock  = parseFloat(row.dataset.stock);
        const minimo = parseFloat(row.dataset.minimo) || 0;
        if (stock <= 0) {
            sinStockCount++;
        } else {
            totalActivos++;
            if (minimo > 0 && stock <= minimo) stockBajoCount++;
        }
    });

    // Actualizar valores en los KPI cards
    const kpiTotal    = document.getElementById('kpiTotal');
    const kpiBajo     = document.getElementById('kpiBajo');
    const kpiSinStock = document.getElementById('kpiSinStock');

    if (kpiTotal)    kpiTotal.textContent    = totalActivos;
    if (kpiBajo)     kpiBajo.textContent     = stockBajoCount;
    if (kpiSinStock) kpiSinStock.textContent = sinStockCount;

    // Colorear en rojo si hay alertas
    if (kpiBajo)     kpiBajo.style.color     = stockBajoCount > 0 ? 'var(--danger)' : '';
    if (kpiSinStock) kpiSinStock.style.color = sinStockCount  > 0 ? 'var(--danger)' : '';
}

// Actualiza el stock de una combinación en el dataset del row (estado en memoria)
function actualizarStockCombinacionEnRow(productoPk, combinacionPk, nuevoStock) {
    const row = document.querySelector(`tr[data-pk="${productoPk}"]`);
    if (!row) return;
    try {
        const combinaciones = JSON.parse(row.dataset.colores || '[]');
        const c = combinaciones.find(x => String(x.pk) === String(combinacionPk));
        if (c) {
            c.stock_actual = nuevoStock;
            row.dataset.colores = JSON.stringify(combinaciones);
        }
    } catch { /* ignorar */ }
}

// Actualiza el chip visual de la combinación en la columna "Stock actual"
function actualizarChipCombinacion(productoPk, combinacionPk, nuevoStock) {
    const chip = document.getElementById(`combinacionChip-${productoPk}-${combinacionPk}`);
    if (!chip) return;
    const val = parseFloat(nuevoStock);
    const fmt = (val % 1 === 0 ? parseInt(val) : val).toString();
    chip.dataset.stock = nuevoStock;
    const stockSpan = chip.querySelector('.chip-stock');
    if (stockSpan) stockSpan.textContent = fmt;
    chip.style.display = val <= 0 ? 'none' : '';
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