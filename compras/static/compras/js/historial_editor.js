/**
 * historial_editor.js
 * Panel de edición inline de una compra ANULADA.
 *
 * Cada ItemCompra guardado en el backend es UNA fila del carrito de
 * edición, identificada por producto_pk + combinacion_pk (igual que en
 * nueva_compra.js). Ya no se agrupan variantes de un mismo producto en
 * una sola entrada con distribución manual — cada variante es su propia
 * unidad: dos algodones de tamaño distinto son dos productos distintos
 * para el carrito.
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

    // ── Reconstruir carrito: 1 fila del carrito por cada ItemCompra ──
    // El backend guarda 1 ItemCompra por variante — se respeta tal cual,
    // sin agrupar. Dos variantes del mismo producto_pk son dos filas.
    const carrito = (compraData.items || []).map((item, idx) => ({
        id:               idx,
        producto_pk:      item.producto_pk,
        combinacion_pk:   item.tiene_combinacion && item.combinacion_pk ? item.combinacion_pk : null,
        producto_nombre:  item.producto_nombre,
        variante_desc:    item.combinacion_descripcion || '',
        nombre:           item.combinacion_descripcion
                               ? `${item.producto_nombre} — ${item.combinacion_descripcion}`
                               : item.producto_nombre,
        codigo:           item.producto_cod || '',
        proveedor_pk:     item.proveedor_pk || '',
        proveedor_nombre: item.proveedor    || '',
        cantidad:         parseFloat(item.cantidad) || 0,
        costo:            parseFloat(item.costo_unitario) || 0,
        moneda:           item.moneda  || 'ARS',
        descuento:        parseFloat(item.descuento_pct) || 0,
        condicion:        _condicionRaw(item.condicion_pago),
        referencia:       item.referencia || '',
        fecha_vencimiento: item.fecha_vencimiento || '',
        // Si el backend de historial no manda el flag es_perecedero, lo
        // inferimos: si ya tenía fecha de vencimiento cargada, es porque
        // en su momento el modelo exigió que fuera perecedero para guardarla.
        es_perecedero:    !!item.es_perecedero || !!item.fecha_vencimiento,
    }));

    editState = {
        pk,
        carrito,
        nextId:           carrito.length,
        provTimers:       {},
        provGlobalDD:     null,
        provActiveInput:  null,
        provActiveItemId: null,
        lastResults:      [],
    };

    const detalle = row.querySelector('.compra-detalle');
    detalle.innerHTML = _buildEditorHTML(compraData);
    _renderEditCarrito();
    _bindEditorEvents(row, compraData, listaContainer);

    // Documentos (solo en modo edición)
    const docsEl = document.getElementById(`editDocumentos_${pk}`);
    if (docsEl) {
        docsEl.innerHTML = buildDocumentosEditor(compraData);
        bindDocumentosEditorEvents(docsEl, pk);
    }
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
                   placeholder="Buscá o escaneá un producto para agregar…" autocomplete="off">
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
                        <th>Vencimiento</th>
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
            const sub = _calcEditSub(item);

            return `
            <tr data-edit-id="${item.id}" class="cmp-row-main">
                <td>
                    <div class="cmp-prod-cell">
                        <span class="cmp-prod-nombre">${_esc(item.producto_nombre)}</span>
                        <span class="cmp-prod-meta">${_esc(item.codigo)}</span>
                        ${item.variante_desc
                            ? `<span class="cmp-prod-badge-colores">
                                   <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                       <rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                                       <circle cx="3" cy="3" r="1" fill="currentColor"/>
                                   </svg>
                                   ${_esc(item.variante_desc)}
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
                           data-edit-id="${item.id}" data-campo="cantidad">
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
                <td>
                    ${item.es_perecedero
                        ? `<input type="date"
                               class="cmp-input-inline w-md edit-field-input${!item.fecha_vencimiento ? ' cmp-input-required-empty' : ''}"
                               value="${item.fecha_vencimiento || ''}"
                               data-edit-id="${item.id}" data-campo="fecha_vencimiento"
                               title="Requerido: este producto es perecedero">`
                        : `<span class="cmp-td-na" title="Este producto no es perecedero">— No aplica —</span>`
                    }
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
            </tr>`;
        }).join('');

        _bindCartBodyEvents(tbody);
    }

    if (totalEl) {
        const t = carrito.reduce((s, i) => s + _calcEditSub(i), 0);
        totalEl.textContent = fmtPeso(t);
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

    if (campo === 'fecha_vencimiento') {
        const inputEl = document.querySelector(
            `#editCartBody_${pk} input[data-edit-id="${id}"][data-campo="fecha_vencimiento"]`
        );
        if (inputEl) inputEl.classList.toggle('cmp-input-required-empty', !valor);
    }

    const totalEl = document.getElementById(`editTotal_${pk}`);
    if (totalEl) totalEl.textContent = fmtPeso(editState.carrito.reduce((s, i) => s + _calcEditSub(i), 0));
}

function _calcEditSub(item) {
    const base = item.cantidad * item.costo;
    return item.descuento ? base * (1 - item.descuento / 100) : base;
}

/* ════════════════════════════════════════════════════════════════
   AGREGAR ÍTEM AL CARRITO (desde el buscador)
   `fila` ya es una unidad resuelta: producto solo, o producto+variante
   puntual, tal como la devuelve BuscarProductoAjax.
════════════════════════════════════════════════════════════════ */
function _editAgregarItem(fila) {
    if (!editState) return;

    const existente = editState.carrito.find(i =>
        String(i.producto_pk) === String(fila.producto_pk) &&
        (i.combinacion_pk || null) === (fila.combinacion_pk || null)
    );
    if (existente) {
        existente.cantidad = (parseFloat(existente.cantidad) || 0) + 1;
        _renderEditCarrito();
        mostrarToastExito(`Cantidad actualizada: ${fila.nombre}`);
        return;
    }

    editState.carrito.push({
        id:               editState.nextId++,
        producto_pk:      fila.producto_pk,
        combinacion_pk:   fila.combinacion_pk || null,
        producto_nombre:  fila.producto_nombre,
        variante_desc:    fila.variante_desc || '',
        nombre:           fila.nombre,
        codigo:           fila.codigo || '',
        proveedor_pk:     fila.proveedor_pk || '',
        proveedor_nombre: fila.proveedor || '',
        cantidad:         1,
        costo:            0,
        moneda:           'ARS',
        descuento:        0,
        condicion:        'contado',
        referencia:       '',
        fecha_vencimiento: '',
        es_perecedero:    !!fila.es_perecedero,
    });
    _renderEditCarrito();
    mostrarToastExito(`Producto agregado: ${fila.nombre}`);
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
   Mismo formato de resultados que nueva_compra.js: cada fila ya es
   una unidad agregable (producto o producto+variante puntual).
════════════════════════════════════════════════════════════════ */
function _bindEditorEvents(row, compraData, listaContainer) {
    const pk       = compraData.pk;
    const searchIn = document.getElementById(`editSearch_${pk}`);
    const searchDD = document.getElementById(`editSearchDD_${pk}`);
    let   timer;

    async function ejecutarBusqueda(q, { forzarAgregado = false } = {}) {
        if (!q) { searchDD.classList.remove('open'); searchDD.innerHTML = ''; return; }
        try {
            const res     = await fetch(`${HISTORIAL_URLS.buscarProducto}?q=${encodeURIComponent(q)}`);
            const data    = await res.json();
            const results = data.results || [];
            editState.lastResults = results;

            const debeAgregarDirecto =
                (results.length === 1 && results[0].match_exacto) ||
                (forzarAgregado && results.length === 1);

            if (debeAgregarDirecto) {
                _editAgregarItem(results[0]);
                searchDD.classList.remove('open'); searchDD.innerHTML = ''; searchIn.value = '';
                return;
            }

            if (!results.length) {
                searchDD.innerHTML = forzarAgregado
                    ? '<div class="cmp-dropdown-empty">No se encontró ningún producto con ese código.</div>'
                    : '<div class="cmp-dropdown-empty">Sin resultados</div>';
            } else {
                searchDD.innerHTML = results.map((r, idx) => `
                    <div class="cmp-dropdown-item" data-idx="${idx}">
                        <div class="cmp-dropdown-item-top">
                            <span class="cmp-dropdown-item-nombre">${_esc(r.producto_nombre)}</span>
                            <span class="cmp-dropdown-item-codigo">${_esc(r.codigo)}</span>
                        </div>
                        <div class="cmp-dropdown-item-meta">
                            <span class="cmp-meta-chip cmp-meta-chip--stock${parseFloat(r.stock_actual||0) <= 0 ? ' cmp-meta-chip--stock-vacio' : ''}">
                                <span class="cmp-meta-label">Stock</span>
                                <strong>${parseFloat(r.stock_actual||0).toLocaleString('es-AR')}</strong>
                            </span>
                            ${r.proveedor ? `<span class="cmp-meta-chip cmp-meta-chip--prov">
                                <span class="cmp-meta-label">Prov.</span>
                                <strong>${_esc(r.proveedor)}</strong>
                            </span>` : ''}
                            ${r.variante_desc ? `<span class="cmp-meta-chip cmp-meta-chip--variante">
                                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                    <rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                                    <circle cx="3" cy="3" r="1" fill="currentColor"/>
                                </svg>
                                <strong>${_esc(r.variante_desc)}</strong>
                            </span>` : ''}
                        </div>
                    </div>`
                ).join('');

                searchDD.querySelectorAll('.cmp-dropdown-item[data-idx]').forEach(el => {
                    el.addEventListener('click', () => {
                        const fila = editState.lastResults[parseInt(el.dataset.idx, 10)];
                        if (fila) _editAgregarItem(fila);
                        searchDD.classList.remove('open'); searchDD.innerHTML = ''; searchIn.value = '';
                    });
                });
            }
            searchDD.classList.add('open');
        } catch { searchDD.classList.remove('open'); }
    }

    searchIn.addEventListener('input', () => {
        clearTimeout(timer);
        const q = searchIn.value.trim();
        if (q.length < 1) { searchDD.classList.remove('open'); searchDD.innerHTML = ''; return; }
        timer = setTimeout(() => ejecutarBusqueda(q), 260);
    });

    searchIn.addEventListener('keydown', e => {
        if (e.key === 'Escape') { searchDD.classList.remove('open'); searchIn.value = ''; return; }
        if (e.key === 'Enter') {
            // Igual que en nueva_compra.js: bloqueamos el submit que un
            // lector de código de barras pudiera disparar y agregamos ya.
            e.preventDefault();
            clearTimeout(timer);
            const q = searchIn.value.trim();
            if (q) ejecutarBusqueda(q, { forzarAgregado: true });
        }
    });

    document.addEventListener('click', function ddClose(e) {
        if (!searchIn.contains(e.target) && !searchDD.contains(e.target)) searchDD.classList.remove('open');
    });

    row.querySelector('.edit-btn-cancelar').addEventListener('click', () => {
        cerrarEdicion(listaContainer);
        if (typeof fetchCompras === 'function') fetchCompras(window._currentPage || 1);
    });
    row.querySelector('.edit-btn-guardar').addEventListener('click', () => _guardarEdicion(compraData, listaContainer));
}

/* ════════════════════════════════════════════════════════════════
   GUARDAR — cada fila del carrito ya es un ítem resuelto,
   se envía tal cual (sin expandir combinaciones)
════════════════════════════════════════════════════════════════ */
function _guardarEdicion(compraData, listaContainer) {
    if (!editState) return;
    const { pk, carrito } = editState;

    if (!carrito.length) { mostrarToastError('La compra debe tener al menos un ítem.'); return; }

    const pendientesVencimiento = carrito.filter(i => i.es_perecedero && !i.fecha_vencimiento);
    if (pendientesVencimiento.length) {
        mostrarToastError(
            `Faltan fechas de vencimiento (productos perecederos): ${pendientesVencimiento.map(i => i.nombre).join(', ')}`
        );
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

    const itemsPayload = carrito.map(item => ({
        producto_pk:    item.producto_pk,
        proveedor_pk:   item.proveedor_pk || null,
        combinacion_pk: item.combinacion_pk || null,
        cantidad:       item.cantidad,
        costo_unitario: item.costo,
        moneda:         item.moneda,
        descuento_pct:  item.descuento,
        condicion_pago: item.condicion,
        referencia:     item.referencia,
        fecha_vencimiento: item.fecha_vencimiento || null,
    }));

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