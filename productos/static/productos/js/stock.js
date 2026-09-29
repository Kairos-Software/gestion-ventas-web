// "1 unidad" / "15 unidades": la fila trae las dos formas (antes decía
// siempre "Unidad", el nombre del choice).
function _unidadPara(row, cantidad) {
    return cantidad === 1 ? row.dataset.unidad : (row.dataset.unidadPlural || row.dataset.unidad);
}

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
    const unidad = _unidadPara(row, parseFloat(row.dataset.stock));
    const costoReferencia = row.dataset.costo || '';

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
    document.getElementById('modalAjusteStock').textContent  = `Stock actual: ${parseFloat(stock).toLocaleString('es-AR', { maximumFractionDigits: 3 })} ${unidad}`;
    document.getElementById('ajusteTipo').value              = '';
    document.getElementById('ajusteCantidad').value          = '';
    document.getElementById('ajusteMotivo').value            = '';
    document.getElementById('ajusteCosto').value              = costoReferencia;
    document.getElementById('ajusteCostoWrap').style.display  = 'none';
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
    // El costo solo tiene sentido al SUMAR unidades (stock que ya se
    // tenía) — al restar no se genera ningún lote nuevo, no hay nada
    // que costear.
    document.getElementById('ajusteCostoWrap').style.display =
        btn.dataset.tipo === 'ajuste_pos' ? 'block' : 'none';
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
        if (tipo === 'ajuste_pos') {
            const costo = document.getElementById('ajusteCosto').value;
            payload.costo_unitario = costo === '' ? null : parseFloat(costo);
        }

        const res  = await fetch(URLS.ajuste, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
            body:    JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.ok) {
            const filaAjustada = document.querySelector(`tr[data-pk="${pk}"]`);
            const estadoAntes  = filaAjustada ? _estadoStockFila(filaAjustada) : null;

            // Actualizar stock total (qty, barra de progreso, badge de estado)
            actualizarFilaStock(pk, data.stock_actual, data.stock_bajo);

            // KPIs del header: un ajuste solo cambia el estado de ESTE producto.
            if (filaAjustada) moverKPIs(estadoAntes, _estadoStockFila(filaAjustada));

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
    const fmt    = val.toLocaleString('es-AR', { maximumFractionDigits: 3 });

    // Actualizar dataset del row
    row.dataset.stock = nuevoStock;

    // Actualizar qty badge
    const el = document.getElementById(`stockQty-${pk}`);
    if (el) {
        el.textContent = `${fmt} ${_unidadPara(row, val)}`;
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

// Estado de stock de una fila: 'sin' | 'bajo' | 'ok' (mismo criterio que
// los KPI que calcula el server en views_stock.py).
function _estadoStockFila(row) {
    const stock  = parseFloat(row.dataset.stock);
    const minimo = parseFloat(row.dataset.minimo) || 0;
    if (stock <= 0) return 'sin';
    return stock <= minimo ? 'bajo' : 'ok';
}

// Mueve los contadores "stock bajo" / "sin stock" según cómo estaba y cómo
// quedó el producto ajustado. Antes se recontaban las filas de la página
// visible, y el total ("con control de stock", que incluye a los que están
// en 0) pasaba de 17 a 15 con cualquier ajuste; con más de 25 productos o un
// filtro puesto, los tres números quedaban mal.
function moverKPIs(antes, despues) {
    if (antes === despues) return;
    const ids = { bajo: 'kpiBajo', sin: 'kpiSinStock' };
    [[antes, -1], [despues, +1]].forEach(([estado, delta]) => {
        const el = ids[estado] && document.getElementById(ids[estado]);
        if (!el) return;
        const n = Math.max(0, (parseInt(el.textContent, 10) || 0) + delta);
        el.textContent = n;
        el.style.color = n > 0 ? 'var(--danger)' : '';
    });
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
//  MODAL "VER TODAS LAS COMBINACIONES"
//  (producto con más de 4 — ver regla nth-child en stock.css)
// ═══════════════════════════════════════════

function verTodasCombinaciones(pk, nombre) {
    const row = document.querySelector(`tr[data-pk="${pk}"]`);
    let combinaciones = [];
    try {
        combinaciones = JSON.parse(row?.dataset.colores || '[]');
    } catch { combinaciones = []; }

    document.getElementById('modalCombinacionesTitle').textContent = `Combinaciones — ${nombre}`;
    document.getElementById('modalCombinacionesBody').innerHTML =
        '<div class="stock-combinaciones" style="max-width:none;">' +
        combinaciones.map(c => {
            const val = parseFloat(c.stock_actual);
            const fmt = (val % 1 === 0 ? parseInt(val) : val).toString();
            return `
            <span class="stock-combinacion-chip">
                <span class="chip-nombre">${c.descripcion_combinacion}:</span>
                <span class="chip-stock">${fmt}</span>
            </span>`;
        }).join('') +
        '</div>';
    document.getElementById('modalCombinaciones').classList.add('visible');
}

function cerrarModalCombinaciones() {
    document.getElementById('modalCombinaciones').classList.remove('visible');
}

document.getElementById('modalCombinaciones').addEventListener('click', function (e) {
    if (e.target === this) cerrarModalCombinaciones();
});