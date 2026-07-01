/**
 * historial_editor.js
 * Panel de edición inline de una compra ANULADA.
 *
 * Replica el sistema de distribución de colores de compras.js:
 *   - fila principal por producto + fila secundaria de chips por color
 *   - cantidad total = suma de la distribución
 *   - al guardar, expande en 1 item de payload por cada color > 0
 *
 * Depende de:
 *   historial_utils.js  (_esc, fmtMoneda, fmtPeso, formatMoney, postAccion, toasts, icons)
 *   historial_docs.js   (buildDocumentosEditor, bindDocumentosEditorEvents)
 */
'use strict';

let editState = null;

/* ════════════════════════════════════════════════════════════════
   ABRIR EDICIÓN
════════════════════════════════════════════════════════════════ */
function accionEditar(pk, compraData, listaContainer) {
    if (editState) cerrarEdicion(listaContainer);

    const row = listaContainer.querySelector(`.compra-row[data-pk="${pk}"]`);
    if (!row) return;
    row.classList.add('open');

    // ── Reconstruir carrito agrupando items por producto_pk ──────────
    // El backend guarda 1 ItemCompra por combinación; aquí los colapsamos de
    // vuelta en 1 entrada de carrito con combinaciones_dist, igual que en
    // nueva_compra donde el usuario carga 1 fila con chips de combinación.
    const carritoMap = new Map();

    for (const item of (compraData.items || [])) {
        const key = String(item.producto_pk || `nokey_${item.producto_nombre}`);

        if (!carritoMap.has(key)) {
            carritoMap.set(key, {
                id:               carritoMap.size,
                producto_pk:      item.producto_pk,
                nombre:           item.producto_nombre,
                codigo:           item.producto_cod,
                unidad:           '',
                proveedor_pk:     item.proveedor_pk || '',
                proveedor_nombre: item.proveedor    || '',
                tiene_combinaciones: false,
                combinaciones_lista: [],
                combinaciones_dist:  {},
                cantidad:         0,
                costo:            parseFloat(item.costo_unitario) || 0,
                moneda:           item.moneda  || 'ARS',
                descuento:        parseFloat(item.descuento_pct) || 0,
                condicion:        _condicionRaw(item.condicion_pago),
                referencia:       item.referencia || '',
            });
        }

        const entry = carritoMap.get(key);

        if (item.tiene_combinacion && item.combinacion_pk) {
            // Producto con combinaciones → acumular en combinaciones_dist
            entry.tiene_combinaciones = true;
            entry.combinaciones_dist[item.combinacion_pk] = (entry.combinaciones_dist[item.combinacion_pk] || 0)
                + (parseFloat(item.cantidad) || 0);
            // Agregar a combinaciones_lista si no está
            if (!entry.combinaciones_lista.find(c => String(c.pk) === String(item.combinacion_pk))) {
                entry.combinaciones_lista.push({
                    pk:           item.combinacion_pk,
                    descripcion_combinacion: item.combinacion_descripcion || `Combinación ${item.combinacion_pk}`,
                    stock_actual: 0,
                });
            }
        } else {
            // Producto sin combinaciones → cantidad directa
            entry.cantidad += parseFloat(item.cantidad) || 0;
        }
    }

    // Calcular cantidad_total para items con combinaciones
    for (const entry of carritoMap.values()) {
        if (entry.tiene_combinaciones) {
            entry.cantidad = Object.values(entry.combinaciones_dist)
                .reduce((s, v) => s + (parseFloat(v) || 0), 0);
        }
    }

    const carrito = Array.from(carritoMap.values());

    editState = {
        pk,
        carrito,
        nextId:           carrito.length,
        provTimers:       {},
        provGlobalDD:     null,
        provActiveInput:  null,
        provActiveItemId: null,
    };

    const detalle = row.querySelector('.compra-detalle');
    detalle.innerHTML = _buildEditorHTML(compraData);
    _renderEditCarrito();
    _bindEditorEvents(row, compraData, listaContainer);

    // Enriquecer combinaciones con datos reales del servidor (stock)
    carrito.forEach(item => {
        if (item.tiene_combinaciones && item.producto_pk) {
            _cargarCombinacionesProducto(item.producto_pk, item.id);
        }
    });
}

function cerrarEdicion(listaContainer) {
    if (!editState) return;
    if (editState.provGlobalDD) {
        editState.provGlobalDD.remove();
        editState.provGlobalDD = null;
    }
    editState = null;
}

/* ════════════════════════════════════════════════════════════════
   CARGAR COMBINACIONES DEL SERVIDOR
════════════════════════════════════════════════════════════════ */
async function _cargarCombinacionesProducto(productoPk, itemId) {
    if (!editState) return;
    try {
        const res    = await fetch(`${HISTORIAL_URLS.buscarProducto}?pk=${encodeURIComponent(productoPk)}`);
        const data   = await res.json();
        const combinaciones = data.combinaciones || [];

        const item = editState.carrito.find(i => i.id === itemId);
        if (!item) return;

        // Enriquecer combinaciones ya conocidos con stock
        item.combinaciones_lista = item.combinaciones_lista.map(local => {
            const srv = combinaciones.find(c => String(c.pk) === String(local.pk));
            return srv ? { ...local, stock_actual: srv.stock_actual || 0 }
                       : local;
        });
        // Agregar combinaciones del servidor que no estén en la dist (para poder cargarlas)
        for (const c of combinaciones) {
            if (!item.combinaciones_lista.find(l => String(l.pk) === String(c.pk))) {
                item.combinaciones_lista.push({ pk: c.pk, descripcion_combinacion: c.descripcion_combinacion, stock_actual: c.stock_actual || 0 });
                if (!(c.pk in item.combinaciones_dist)) {
                    item.combinaciones_dist[c.pk] = 0;
                }
            }
        }

        _actualizarFilaCombinaciones(itemId);
    } catch {
        // silencioso
    }
}

/* ════════════════════════════════════════════════════════════════
   HTML PANEL EDITOR
════════════════════════════════════════════════════════════════ */
function _buildEditorHTML(c) {
    return `
    <div class="edit-panel">
        <div class="edit-panel-header">
            ${iconEditar()}
            <span>Editando <strong>${_esc(c.numero)}</strong></span>
            <span class="edit-panel-aviso">
                Compra anulada. Guardá para re-confirmar y actualizar el stock.
            </span>
        </div>

        <div class="edit-cabecera">
            <div class="edit-field">
                <label>Fecha</label>
                <input type="date" id="editFecha_${c.pk}" class="cmp-control" value="${c.fecha_iso || ''}">
            </div>
            <div class="edit-field edit-field--grow">
                <label>Notas</label>
                <input type="text" id="editNotas_${c.pk}" class="cmp-control"
                       placeholder="Observaciones…" value="${_esc(c.notas || '')}">
            </div>
        </div>

        <div class="edit-search-wrap">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" stroke-width="1.3"/>
                <path d="M10 10L14 14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
            </svg>
            <input type="text" id="editSearch_${c.pk}" class="edit-search-input"
                   placeholder="Buscá un producto para agregar…" autocomplete="off">
            <div id="editSearchDD_${c.pk}" class="cmp-dropdown"></div>
        </div>

        <div class="cmp-table-wrap" style="margin-top:0.5rem;">
            <table class="cmp-table">
                <thead>
                    <tr>
                        <th>Producto</th>
                        <th>Proveedor</th>
                        <th>Cant.</th>
                        <th>Costo unit.</th>
                        <th>Moneda</th>
                        <th>Desc. %</th>
                        <th>Cond. pago</th>
                        <th>Referencia</th>
                        <th>Subtotal</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="editCartBody_${c.pk}"></tbody>
            </table>
            <div id="editCartEmpty_${c.pk}" class="cmp-empty" style="display:none;">
                <p>Agregá al menos un producto para poder guardar.</p>
            </div>
        </div>

        <div id="editDocumentos_${c.pk}"></div>

        <div class="edit-footer">
            <div class="edit-total">
                <span>Total estimado:</span>
                <strong id="editTotal_${c.pk}">$ 0,00</strong>
            </div>
            <div class="edit-footer-btns">
                <button class="cmp-btn cmp-btn-ghost edit-btn-cancelar" data-pk="${c.pk}">
                    Cancelar
                </button>
                <button class="cmp-btn cmp-btn-primary edit-btn-guardar" data-pk="${c.pk}">
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                        <path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6"
                              stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    Guardar y re-confirmar
                </button>
            </div>
        </div>
    </div>`;
}

/* ════════════════════════════════════════════════════════════════
   RENDER CARRITO
════════════════════════════════════════════════════════════════ */
function _renderEditCarrito() {
    if (!editState) return;
    const { pk, carrito } = editState;

    const tbody   = document.getElementById(`editCartBody_${pk}`);
    const emptyEl = document.getElementById(`editCartEmpty_${pk}`);
    const totalEl = document.getElementById(`editTotal_${pk}`);
    if (!tbody) return;

    if (!carrito.length) {
        tbody.innerHTML = '';
        if (emptyEl) emptyEl.style.display = 'block';
    } else {
        if (emptyEl) emptyEl.style.display = 'none';

        tbody.innerHTML = carrito.map(item => {
            const sub          = _calcEditSub(item);
            const combinacionWarning = item.tiene_combinaciones && !_combinacionesValidas(item)
                ? `<span class="cmp-color-warning" title="Distribuí todas las combinaciones">
                       <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                           <circle cx="6" cy="6" r="5" stroke="currentColor" stroke-width="1.3"/>
                           <path d="M6 4V6.5M6 8H6.01" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                       </svg>
                   </span>` : '';

            const filaCombinaciones = item.tiene_combinaciones ? _renderFilaCombinaciones(item) : '';

            return `
            <tr data-edit-id="${item.id}" class="cmp-row-main">
                <td>
                    <div class="cmp-prod-cell">
                        <span class="cmp-prod-nombre">${_esc(item.nombre)}</span>
                        <span class="cmp-prod-meta">${_esc(item.codigo)}</span>
                        ${item.tiene_combinaciones
                            ? `<span class="cmp-prod-badge-colores">
                                   <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                       <rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                                       <circle cx="3" cy="3" r="1" fill="currentColor"/>
                                       <circle cx="7" cy="7" r="1" fill="currentColor"/>
                                   </svg>
                                   ${item.combinaciones_lista.length} combinación${item.combinaciones_lista.length !== 1 ? 'es' : ''}
                               </span>` : ''}
                    </div>
                </td>
                <td>
                    <div class="cmp-prov-wrap">
                        <input type="text"
                               class="cmp-input-inline w-lg edit-prov-input"
                               placeholder="Buscar proveedor…"
                               value="${_esc(item.proveedor_nombre)}"
                               autocomplete="off"
                               data-edit-id="${item.id}">
                    </div>
                </td>
                <td>
                    <input type="number" min="0.001" step="any"
                           class="cmp-input-inline w-xs edit-field-input"
                           value="${item.cantidad}"
                           data-edit-id="${item.id}" data-campo="cantidad"
                           ${item.tiene_combinaciones ? 'readonly title="Se calcula automáticamente"' : ''}>
                    ${combinacionWarning}
                </td>
                <td>
                    <input type="number" min="0" step="any"
                           class="cmp-input-inline w-sm edit-field-input"
                           value="${item.costo}"
                           data-edit-id="${item.id}" data-campo="costo">
                </td>
                <td>
                    <select class="cmp-select-inline edit-field-input"
                            data-edit-id="${item.id}" data-campo="moneda">
                        <option value="ARS" ${item.moneda==='ARS'?'selected':''}>ARS</option>
                        <option value="USD" ${item.moneda==='USD'?'selected':''}>USD</option>
                        <option value="EUR" ${item.moneda==='EUR'?'selected':''}>EUR</option>
                    </select>
                </td>
                <td>
                    <input type="number" min="0" max="100" step="0.01"
                           class="cmp-input-inline w-xs edit-field-input"
                           value="${item.descuento}"
                           data-edit-id="${item.id}" data-campo="descuento">
                </td>
                <td>
                    <select class="cmp-select-inline edit-field-input"
                            data-edit-id="${item.id}" data-campo="condicion">
                        <option value="contado"  ${item.condicion==='contado'?'selected':''}>Contado</option>
                        <option value="15"       ${item.condicion==='15'?'selected':''}>15 días</option>
                        <option value="30"       ${item.condicion==='30'?'selected':''}>30 días</option>
                        <option value="60"       ${item.condicion==='60'?'selected':''}>60 días</option>
                        <option value="90"       ${item.condicion==='90'?'selected':''}>90 días</option>
                        <option value="convenir" ${item.condicion==='convenir'?'selected':''}>A convenir</option>
                    </select>
                </td>
                <td>
                    <input type="text"
                           class="cmp-input-inline w-md edit-field-input"
                           placeholder="Nº remito / factura"
                           value="${_esc(item.referencia)}"
                           data-edit-id="${item.id}" data-campo="referencia">
                </td>
                <td class="cmp-subtotal-cell" id="editSub_${pk}_${item.id}">
                    ${fmtMoneda(sub, item.moneda)}
                </td>
                <td>
                    <button class="cmp-btn-remove edit-btn-remove" data-edit-id="${item.id}">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                        </svg>
                    </button>
                </td>
            </tr>
            ${filaColores}`;
        }).join('');

        _bindCartBodyEvents(tbody);
    }

    if (totalEl) {
        const t = carrito.reduce((s, i) => s + _calcEditSub(i), 0);
        totalEl.textContent = fmtPeso(t);
    }
}

/* ════════════════════════════════════════════════════════════════
   FILA DE COMBINACIONES — idéntica a compras.js
════════════════════════════════════════════════════════════════ */
function _renderFilaCombinaciones(item) {
    const totalAsignado = _totalCombinacionesDist(item);
    const totalItem     = parseFloat(item.cantidad) || 0;
    const ok            = Math.abs(totalAsignado - totalItem) < 0.001;

    const chips = item.combinaciones_lista.map(c => {
        const val = item.combinaciones_dist[c.pk] || 0;
        return `
        <div class="cmp-color-chip">
            <span class="cmp-color-chip-nombre">${_esc(c.descripcion_combinacion)}</span>
            <span class="cmp-color-chip-stock">(stock: ${parseFloat(c.stock_actual||0).toLocaleString('es-AR')})</span>
            <input type="number" min="0" step="any"
                   class="cmp-input-inline w-xs cmp-color-qty"
                   value="${val}"
                   data-edit-id="${item.id}"
                   data-combinacion-pk="${c.pk}">
        </div>`;
    }).join('');

    return `
    <tr class="cmp-row-colores" data-combinacion-row="${item.id}">
        <td colspan="10">
            <div class="cmp-colores-panel">
                <div class="cmp-colores-panel-header">
                    <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                        <rect x="1" y="1" width="11" height="11" rx="1" stroke="currentColor" stroke-width="1.3"/>
                        <circle cx="3" cy="3" r="1" fill="currentColor"/>
                        <circle cx="10" cy="10" r="1" fill="currentColor"/>
                    </svg>
                    <span>Distribuir por combinación</span>
                    <span class="cmp-colores-panel-resumen ${ok ? 'ok' : 'error'}"
                          id="editColres_${editState.pk}_${item.id}">
                        ${ok
                            ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                   <path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                               </svg> Distribución completa`
                            : `Asignado: <strong>${totalAsignado.toLocaleString('es-AR')}</strong> / Total: <strong>${totalItem.toLocaleString('es-AR')}</strong>`
                        }
                    </span>
                </div>
                <div class="cmp-colores-chips">${chips}</div>
            </div>
        </td>
    </tr>`;
}

function _actualizarFilaCombinaciones(itemId) {
    if (!editState) return;
    const item  = editState.carrito.find(i => i.id === itemId);
    if (!item || !item.tiene_combinaciones) return;
    const tbody = document.getElementById(`editCartBody_${editState.pk}`);
    if (!tbody) return;

    const filaVieja = tbody.querySelector(`tr[data-combinacion-row="${itemId}"]`);
    const nuevaHTML = _renderFilaCombinaciones(item);
    if (filaVieja) {
        filaVieja.outerHTML = nuevaHTML;
    } else {
        const filaMain = tbody.querySelector(`tr[data-edit-id="${itemId}"]`);
        if (filaMain) filaMain.insertAdjacentHTML('afterend', nuevaHTML);
    }

    // Re-bind inputs de combinación
    tbody.querySelectorAll(`.cmp-color-qty[data-edit-id="${itemId}"]`).forEach(input => {
        input.addEventListener('change', () =>
            _updateCombinacionDist(parseInt(input.dataset.editId, 10), input.dataset.combinacionPk, input.value));
    });
}

/* ════════════════════════════════════════════════════════════════
   COMBINACION HELPERS
════════════════════════════════════════════════════════════════ */
function _totalCombinacionesDist(item) {
    return Object.values(item.combinaciones_dist).reduce((s, v) => s + (parseFloat(v) || 0), 0);
}
function _combinacionesValidas(item) {
    if (!item.tiene_combinaciones) return true;
    return Math.abs(_totalCombinacionesDist(item) - (parseFloat(item.cantidad) || 0)) < 0.001;
}

function _updateCombinacionDist(itemId, combinacionPk, valor) {
    if (!editState) return;
    const item = editState.carrito.find(i => i.id === itemId);
    if (!item) return;

    item.combinaciones_dist[combinacionPk] = parseFloat(valor) || 0;
    const totalAsignado = _totalCombinacionesDist(item);
    item.cantidad = totalAsignado;

    const { pk } = editState;

    // Actualizar input cantidad (readonly)
    const mainRow = document.querySelector(`#editCartBody_${pk} tr[data-edit-id="${itemId}"]`);
    if (mainRow) {
        const cantInput = mainRow.querySelector('input[data-campo="cantidad"]');
        if (cantInput) cantInput.value = totalAsignado;
        mainRow.querySelector('.cmp-color-warning')?.remove();
    }

    // Resumen distribución
    const resEl = document.getElementById(`editColres_${pk}_${itemId}`);
    if (resEl) {
        resEl.className = 'cmp-colores-panel-resumen ok';
        resEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg> Distribución completa`;
    }

    // Subtotal fila
    const subEl = document.getElementById(`editSub_${pk}_${itemId}`);
    if (subEl) subEl.textContent = fmtMoneda(_calcEditSub(item), item.moneda);

    // Total general
    const totalEl = document.getElementById(`editTotal_${pk}`);
    if (totalEl) {
        totalEl.textContent = fmtPeso(editState.carrito.reduce((s, i) => s + _calcEditSub(i), 0));
    }
}

/* ════════════════════════════════════════════════════════════════
   BIND EVENTOS TBODY
════════════════════════════════════════════════════════════════ */
function _bindCartBodyEvents(tbody) {
    tbody.querySelectorAll('.edit-field-input').forEach(el => {
        el.addEventListener('change', () =>
            _editUpdateField(parseInt(el.dataset.editId, 10), el.dataset.campo, el.value));
    });
    tbody.querySelectorAll('.cmp-color-qty').forEach(input => {
        input.addEventListener('change', () =>
            _updateColorDist(parseInt(input.dataset.editId, 10), input.dataset.colorPk, input.value));
    });
    tbody.querySelectorAll('.edit-btn-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            editState.carrito = editState.carrito.filter(i => i.id !== parseInt(btn.dataset.editId, 10));
            _renderEditCarrito();
        });
    });
    tbody.querySelectorAll('.edit-prov-input').forEach(input => {
        input.addEventListener('input', () => _editOnProvInput(input));
        input.addEventListener('blur',  () => _editOnProvBlur(input));
    });
}

function _editUpdateField(id, campo, valor) {
    if (!editState) return;
    const item = editState.carrito.find(i => i.id === id);
    if (!item) return;
    if (['cantidad','costo','descuento'].includes(campo)) item[campo] = parseFloat(valor) || 0;
    else item[campo] = valor;

    const { pk } = editState;
    const subEl  = document.getElementById(`editSub_${pk}_${id}`);
    if (subEl) subEl.textContent = fmtMoneda(_calcEditSub(item), item.moneda);

    if (campo === 'cantidad' && item.tiene_combinaciones) {
        const resEl = document.getElementById(`editColres_${pk}_${id}`);
        if (resEl) {
            const ta = _totalCombinacionesDist(item), ti = parseFloat(item.cantidad) || 0;
            const ok = Math.abs(ta - ti) < 0.001;
            resEl.className = `cmp-colores-panel-resumen ${ok ? 'ok' : 'error'}`;
            resEl.innerHTML = ok
                ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg> Distribución completa`
                : `Asignado: <strong>${ta.toLocaleString('es-AR')}</strong> / Total: <strong>${ti.toLocaleString('es-AR')}</strong>`;
        }
    }

    const totalEl = document.getElementById(`editTotal_${pk}`);
    if (totalEl) totalEl.textContent = fmtPeso(editState.carrito.reduce((s, i) => s + _calcEditSub(i), 0));
}

function _calcEditSub(item) {
    const base = item.cantidad * item.costo;
    return item.descuento ? base * (1 - item.descuento / 100) : base;
}

/* ════════════════════════════════════════════════════════════════
   PROVEEDOR AUTOCOMPLETE
════════════════════════════════════════════════════════════════ */
function _editGetProvDD() {
    if (!editState) return null;
    if (!editState.provGlobalDD) {
        const dd = document.createElement('div');
        dd.className = 'cmp-prov-dropdown';
        document.body.appendChild(dd);
        editState.provGlobalDD = dd;
    }
    return editState.provGlobalDD;
}
function _editCerrarProvDD() {
    if (!editState) return;
    const dd = editState.provGlobalDD;
    if (dd) { dd.classList.remove('open'); dd.innerHTML = ''; }
    editState.provActiveInput = null; editState.provActiveItemId = null;
}
function _editPosProvDD(input) {
    const dd = _editGetProvDD(), rect = input.getBoundingClientRect(), below = window.innerHeight - rect.bottom;
    dd.style.cssText = `position:fixed;left:${rect.left}px;width:${Math.max(rect.width,220)}px;
        max-height:${Math.min(200,Math.max(below-8,120))}px;z-index:9000;
        ${below<120?`bottom:${window.innerHeight-rect.top+4}px;top:auto;`:`top:${rect.bottom+4}px;bottom:auto;`}`;
}
function _editOnProvInput(input) {
    if (!editState) return;
    const itemId = parseInt(input.dataset.editId, 10);
    editState.provActiveInput = input; editState.provActiveItemId = itemId;
    const item = editState.carrito.find(i => i.id === itemId);
    if (item) { item.proveedor_pk = ''; item.proveedor_nombre = input.value; }
    clearTimeout(editState.provTimers[itemId]);
    const dd = _editGetProvDD(), q = input.value.trim();
    if (!q) { _editCerrarProvDD(); return; }
    editState.provTimers[itemId] = setTimeout(async () => {
        try {
            const res = await fetch(`${HISTORIAL_URLS.buscarProveedor}?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            const results = data.results || [];
            dd.innerHTML = results.length
                ? results.map(p => `<div class="cmp-prov-option" data-pk="${p.pk}" data-nombre="${_esc(p.nombre)}">
                        <div class="cmp-prov-option-nombre">${_esc(p.nombre)}</div>
                        ${p.cuit?`<div class="cmp-prov-option-meta">CUIT: ${_esc(p.cuit)}</div>`:''}
                    </div>`).join('')
                : `<div class="cmp-prov-option" style="color:var(--text-muted);cursor:default">Sin resultados</div>`;
            dd.querySelectorAll('.cmp-prov-option[data-pk]').forEach(el => {
                el.addEventListener('mousedown', e => {
                    e.preventDefault();
                    input.value = el.dataset.nombre;
                    const it = editState.carrito.find(i => i.id === itemId);
                    if (it) { it.proveedor_pk = el.dataset.pk; it.proveedor_nombre = el.dataset.nombre; }
                    _editCerrarProvDD();
                });
            });
            _editPosProvDD(input); dd.classList.add('open');
        } catch { _editCerrarProvDD(); }
    }, 250);
}
function _editOnProvBlur(input) {
    setTimeout(() => { if (editState && editState.provActiveInput === input) _editCerrarProvDD(); }, 200);
}
document.addEventListener('mousedown', () => { if (editState && editState.provActiveInput) _editCerrarProvDD(); });

/* ════════════════════════════════════════════════════════════════
   BUSCADOR DE PRODUCTOS EN EL EDITOR
════════════════════════════════════════════════════════════════ */
function _bindEditorEvents(row, compraData, listaContainer) {
    const pk       = compraData.pk;
    const searchIn = document.getElementById(`editSearch_${pk}`);
    const searchDD = document.getElementById(`editSearchDD_${pk}`);
    let   timer;

    searchIn.addEventListener('input', () => {
        clearTimeout(timer);
        const q = searchIn.value.trim();
        if (q.length < 1) { searchDD.classList.remove('open'); searchDD.innerHTML = ''; return; }
        timer = setTimeout(async () => {
            try {
                const res  = await fetch(`${HISTORIAL_URLS.buscarProducto}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                const results = data.results || [];
                if (!results.length) {
                    searchDD.innerHTML = '<div class="cmp-dropdown-empty">Sin resultados</div>';
                } else {
                    searchDD.innerHTML = results.map(p => {
                        const tieneColores = p.tiene_variantes_color && p.colores && p.colores.length > 0;
                        const coloresAttr  = tieneColores
                            ? `data-colores="${_esc(btoa(unescape(encodeURIComponent(JSON.stringify(p.colores)))))}"` : '';
                        return `
                        <div class="cmp-dropdown-item"
                             data-pk="${p.pk}"
                             data-nombre="${_esc(p.nombre)}"
                             data-codigo="${_esc(p.codigo)}"
                             data-unidad="${_esc(p.unidad_medida||'')}"
                             data-prov-pk="${p.proveedor_pk||''}"
                             data-prov-nombre="${_esc(p.proveedor||'')}"
                             data-tiene-colores="${tieneColores?'1':'0'}"
                             ${coloresAttr}>
                            <div class="cmp-dropdown-item-top">
                                <span class="cmp-dropdown-item-nombre">${_esc(p.nombre)}</span>
                                <span class="cmp-dropdown-item-codigo">${_esc(p.codigo)}</span>
                            </div>
                            <div class="cmp-dropdown-item-meta">
                                <span class="cmp-meta-chip">Stock: <strong>${parseFloat(p.stock_actual||0).toLocaleString('es-AR')}</strong></span>
                                ${p.proveedor?`<span class="cmp-meta-chip">Prov: <strong>${_esc(p.proveedor)}</strong></span>`:''}
                                ${tieneColores?`<span class="cmp-meta-chip cmp-meta-chip--colores">
                                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                        <circle cx="5" cy="5" r="3.5" stroke="currentColor" stroke-width="1.2"/>
                                        <circle cx="5" cy="5" r="1.2" fill="currentColor"/>
                                    </svg>
                                    <strong>${p.colores.length} color${p.colores.length!==1?'es':''}</strong>
                                </span>`:''}
                            </div>
                        </div>`;
                    }).join('');
                    searchDD.querySelectorAll('.cmp-dropdown-item').forEach(el => {
                        el.addEventListener('click', () => {
                            let colores = [];
                            if (el.dataset.colores) {
                                try { colores = JSON.parse(decodeURIComponent(escape(atob(el.dataset.colores)))); }
                                catch { colores = []; }
                            }
                            _editAgregarItem(el.dataset, colores);
                            searchDD.classList.remove('open'); searchDD.innerHTML = ''; searchIn.value = '';
                        });
                    });
                }
                searchDD.classList.add('open');
            } catch { searchDD.classList.remove('open'); }
        }, 260);
    });

    searchIn.addEventListener('keydown', e => {
        if (e.key === 'Escape') { searchDD.classList.remove('open'); searchIn.value = ''; }
    });
    document.addEventListener('click', function ddClose(e) {
        if (!searchIn.contains(e.target) && !searchDD.contains(e.target)) searchDD.classList.remove('open');
    });

    row.querySelector('.edit-btn-cancelar').addEventListener('click', () => {
        cerrarEdicion(listaContainer);
        if (typeof fetchCompras === 'function') fetchCompras(window._currentPage || 1);
    });
    row.querySelector('.edit-btn-guardar').addEventListener('click', () => _guardarEdicion(compraData));

    // Documentos (solo en modo edición)
    const docsEl = document.getElementById(`editDocumentos_${pk}`);
    if (docsEl) {
        docsEl.innerHTML = buildDocumentosEditor(compraData);
        bindDocumentosEditorEvents(docsEl, pk);
    }
}

function _editAgregarItem(d, combinaciones) {
    if (!editState) return;
    const tieneCombinaciones = d['tiene-combinaciones'] === '1' && combinaciones && combinaciones.length > 0;
    const newId = editState.nextId++;
    editState.carrito.push({
        id:               newId,
        producto_pk:      d.pk,
        nombre:           d.nombre,
        codigo:           d.codigo || '',
        unidad:           d.unidad || '',
        proveedor_pk:     d['prov-pk'] || '',
        proveedor_nombre: d['prov-nombre'] || '',
        tiene_combinaciones: tieneCombinaciones,
        combinaciones_lista: tieneCombinaciones ? combinaciones : [],
        combinaciones_dist: tieneCombinaciones ? Object.fromEntries(combinaciones.map(c => [c.pk, 0])) : {},
        cantidad:         tieneCombinaciones ? 0 : 1,
        costo:            0,
        moneda:           'ARS',
        descuento:        0,
        condicion:        'contado',
        referencia:       '',
    });
    _renderEditCarrito();
}

/* ════════════════════════════════════════════════════════════════
   GUARDAR — expande colores en items individuales
════════════════════════════════════════════════════════════════ */
function _guardarEdicion(compraData) {
    if (!editState) return;
    const { pk, carrito } = editState;

    if (!carrito.length) { mostrarToastError('La compra debe tener al menos un ítem.'); return; }

    const pendientes = carrito.filter(i => i.tiene_combinaciones && !_combinacionesValidas(i));
    if (pendientes.length) {
        mostrarToastError(`Distribuí todos las combinaciones antes de guardar. Pendientes: ${pendientes.map(i => i.nombre).join(', ')}`);
        return;
    }

    const fechaEl = document.getElementById(`editFecha_${pk}`);
    const notasEl = document.getElementById(`editNotas_${pk}`);
    const fecha   = fechaEl ? fechaEl.value : compraData.fecha_iso || '';
    const notas   = notasEl ? notasEl.value.trim() : '';
    if (!fecha) { mostrarToastError('La fecha es requerida.'); return; }

    const btnGuardar = document.querySelector(`.edit-btn-guardar[data-pk="${pk}"]`);
    if (btnGuardar) {
        btnGuardar.disabled  = true;
        btnGuardar.innerHTML = `<svg class="cmp-spin" width="15" height="15" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Guardando…`;
    }

    // Expandir combinaciones → 1 item por combinación con cantidad > 0
    const itemsPayload = [];
    for (const item of carrito) {
        if (item.tiene_combinaciones) {
            for (const [combinacionPk, cant] of Object.entries(item.combinaciones_dist)) {
                const cantidad = parseFloat(cant) || 0;
                if (cantidad <= 0) continue;
                itemsPayload.push({
                    producto_pk:    item.producto_pk,
                    proveedor_pk:   item.proveedor_pk || null,
                    combinacion_pk: parseInt(combinacionPk, 10),
                    cantidad,
                    costo_unitario: item.costo,
                    moneda:         item.moneda,
                    descuento_pct:  item.descuento,
                    condicion_pago: item.condicion,
                    referencia:     item.referencia,
                });
            }
        } else {
            itemsPayload.push({
                producto_pk:    item.producto_pk,
                proveedor_pk:   item.proveedor_pk || null,
                combinacion_pk: null,
                cantidad:       item.cantidad,
                costo_unitario: item.costo,
                moneda:         item.moneda,
                descuento_pct:  item.descuento,
                condicion_pago: item.condicion,
                referencia:     item.referencia,
            });
        }
    }

    postAccion(
        HISTORIAL_URLS.editar,
        { pk, fecha, notas, items: itemsPayload },
        (data) => {
            mostrarToastExito(`Compra ${data.numero} actualizada y re-confirmada. Total: ${formatMoney(data.total)}`);
            cerrarEdicion(listaContainer);
            if (typeof fetchCompras === 'function') fetchCompras(window._currentPage || 1);
        },
        (msg) => {
            mostrarToastError(msg);
            if (btnGuardar) {
                btnGuardar.disabled  = false;
                btnGuardar.innerHTML = `<svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                    <path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg> Guardar y re-confirmar`;
            }
        }
    );
}

function _condicionRaw(label) {
    const map = {'Contado':'contado','A convenir':'convenir','15 días':'15','30 días':'30','60 días':'60','90 días':'90'};
    return map[label] || label || 'contado';
}