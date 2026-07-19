/**
 * paquetes.js
 * Página propia de Paquetes (dentro de Catálogo).
 * CSRF y URLS se inyectan desde el template (const CSRF, const URLS).
 */
'use strict';

let _cachePaquetes = [];
let _pqComponentesSeleccionados = []; // [{producto_pk, nombre, codigo, cantidad}, ...]

cargarPaquetes();

function abrirModal(id) {
    document.getElementById(id).classList.add('prd-modal-overlay--open');
    document.body.style.overflow = 'hidden';
}

function cerrarModal(id) {
    document.getElementById(id).classList.remove('prd-modal-overlay--open');
    document.body.style.overflow = '';
}

document.getElementById('btnNuevoPaquete')?.addEventListener('click', () => {
    _resetFormPaquete();
    abrirModal('modalPaquete');
});

function _pqEsc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Dibuja el código de barras (Code128) en la vista previa del formulario. */
function _mostrarBarcodePreview(codigo) {
    const wrap = document.getElementById('pqBarcodePreviewWrap');
    if (!codigo) {
        wrap.style.display = 'none';
        return;
    }
    if (typeof JsBarcode === 'undefined') {
        wrap.style.display = 'none';
        KaiToast.show('No se pudo cargar el generador de códigos de barras (revisá la conexión a internet).', 'danger');
        return;
    }
    wrap.style.display = 'flex';
    try {
        JsBarcode('#pqBarcodeSvg', codigo, { format: 'CODE128', width: 2, height: 50, fontSize: 12, margin: 4 });
    } catch (err) {
        console.error('Error al dibujar el código de barras:', err);
        wrap.style.display = 'none';
        KaiToast.show('Error al dibujar el código de barras.', 'danger');
    }
}

/** Imprime una etiqueta con nombre + precio + código de barras — mismo
 *  mecanismo que la etiqueta de balanza (JsBarcode + window.print()
 *  sobre un área oculta que solo se muestra durante la impresión). */
function _imprimirCodigoBarras(nombre, precioVenta, codigo) {
    if (!codigo) {
        KaiToast.show('Todavía no hay código de barras para imprimir.', 'warning');
        return;
    }
    if (typeof JsBarcode === 'undefined') {
        KaiToast.show('No se pudo cargar el generador de códigos de barras (revisá la conexión a internet) y volvé a intentar.', 'danger');
        return;
    }
    try {
        let area = document.getElementById('pq-print-area');
        if (area) area.remove();
        area = document.createElement('div');
        area.id = 'pq-print-area';
        area.innerHTML = `
            <div class="pq-etiqueta-preview">
                <div class="pq-etiqueta-nombre">${_pqEsc(nombre)}</div>
                <div class="pq-etiqueta-precio">${KaiFormat.moneda(precioVenta)}</div>
                <svg id="pqBarcodeSvgPrint"></svg>
            </div>`;
        document.body.appendChild(area);
        JsBarcode('#pqBarcodeSvgPrint', codigo, { format: 'CODE128', width: 2, height: 55, fontSize: 13, margin: 4 });
        window.onafterprint = () => { area.remove(); window.onafterprint = null; };
        setTimeout(() => window.print(), 50);
    } catch (err) {
        console.error('Error al imprimir código de barras:', err);
        KaiToast.show('Error al generar el código de barras para imprimir.', 'danger');
    }
}

function _imprimirCodigoPaquete(pk) {
    const p = _cachePaquetes.find(x => x.pk === pk);
    if (!p) return;
    _imprimirCodigoBarras(p.nombre, p.precio_venta, p.codigo_barras);
}

document.getElementById('btnImprimirCodigoModal')?.addEventListener('click', () => {
    _imprimirCodigoBarras(
        document.getElementById('pqNombre').value,
        document.getElementById('pqPrecioVenta').value,
        document.getElementById('pqCodigoBarras').value,
    );
});

async function cargarPaquetes() {
    const res  = await fetch(URLS.paqueteLista);
    const data = await res.json();
    _cachePaquetes = data.results || [];
    _renderPaquetes();
}

function _alcanceComponentesTexto(p) {
    const n = p.componentes.length;
    return `${n} componente${n !== 1 ? 's' : ''}`;
}

function _renderPaquetes() {
    const cont  = document.getElementById('paqueteLista');
    const empty = document.getElementById('pqEmptyMsg');
    if (!cont) return;

    if (!_cachePaquetes.length) {
        cont.innerHTML = '';
        empty.style.display = '';
        return;
    }
    empty.style.display = 'none';

    cont.innerHTML = _cachePaquetes.map(p => `
        <div class="prd-ld-row ${p.activo ? '' : 'prd-ld-row--inactiva'}">
            <div class="prd-ld-row-pct">$${p.precio_venta}</div>
            <div class="prd-ld-row-info">
                <span class="prd-ld-row-nombre">${p.nombre}</span>
                <span class="prd-badge ${p.activo ? 'prd-badge--tipo' : ''}">${p.activo ? 'Activo' : 'Inactivo'}</span>
                <span class="prd-of-row-meta">${_alcanceComponentesTexto(p)} · Se pueden armar ${p.stock_disponible} ahora${p.codigo_barras ? ` · Código: ${p.codigo_barras}` : ''}</span>
            </div>
            <div class="prd-ld-row-actions">
                <button type="button" class="prd-ld-icon-btn" title="Imprimir código de barras" onclick="_imprimirCodigoPaquete(${p.pk})">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M4 2.5H11V5.5H4V2.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
                        <path d="M2.5 5.5H12.5V10.5H2.5V5.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
                        <path d="M4 10.5H11V12.5H4V10.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
                    </svg>
                </button>
                <button type="button" class="prd-ld-icon-btn" title="Editar" onclick="_editarPaquete(${p.pk})">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M10.5 2L13 4.5L5 12.5H2.5V10L10.5 2Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <button type="button" class="prd-ld-icon-btn prd-ld-icon-btn--danger" title="Eliminar" onclick="_eliminarPaquete(${p.pk}, '${p.nombre.replace(/'/g, "\\'")}')">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M2.5 4H12.5M5.5 4V3H9.5V4M6 6.5V10.5M9 6.5V10.5M3.5 4L4.3 12H10.7L11.5 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');
}

function _resetFormPaquete() {
    document.getElementById('pqPk').value = '';
    document.getElementById('pqNombre').value = '';
    document.getElementById('pqPrecioVenta').value = '';
    document.getElementById('pqCodigoBarras').value = '';
    document.getElementById('pqDescripcion').value = '';
    document.getElementById('pqActivo').checked = true;
    _pqComponentesSeleccionados = [];
    _renderComponentes();
    document.getElementById('pqComponenteBuscar').value = '';
    document.getElementById('pqComponenteDropdown').innerHTML = '';
    document.getElementById('btnGuardarPaqueteTxt').textContent = 'Agregar';
    document.getElementById('modalPaqueteTitulo').textContent = 'Nuevo paquete';
    document.getElementById('pqFormError').style.display = 'none';
    document.getElementById('btnCancelarPaquete').textContent = 'Cancelar';
    _mostrarBarcodePreview('');
}

function _editarPaquete(pk) {
    const p = _cachePaquetes.find(x => x.pk === pk);
    if (!p) return;
    document.getElementById('pqPk').value = p.pk;
    document.getElementById('pqNombre').value = p.nombre;
    document.getElementById('pqPrecioVenta').value = p.precio_venta;
    document.getElementById('pqCodigoBarras').value = p.codigo_barras || '';
    document.getElementById('pqDescripcion').value = p.descripcion || '';
    document.getElementById('pqActivo').checked = p.activo;
    _pqComponentesSeleccionados = p.componentes.map(c => ({
        producto_pk: c.producto_pk, nombre: c.nombre, codigo: c.codigo, cantidad: c.cantidad,
    }));
    _renderComponentes();
    document.getElementById('btnGuardarPaqueteTxt').textContent = 'Guardar cambios';
    document.getElementById('modalPaqueteTitulo').textContent = 'Editar paquete';
    document.getElementById('pqFormError').style.display = 'none';
    document.getElementById('btnCancelarPaquete').textContent = 'Cerrar';
    _mostrarBarcodePreview(p.codigo_barras);
    abrirModal('modalPaquete');
}

function _renderComponentes() {
    const cont  = document.getElementById('pqComponentesLista');
    const empty = document.getElementById('pqComponentesVacio');
    if (!_pqComponentesSeleccionados.length) {
        cont.innerHTML = '';
        empty.style.display = '';
        return;
    }
    empty.style.display = 'none';
    cont.innerHTML = _pqComponentesSeleccionados.map(c => `
        <div class="pq-componente-row">
            <div class="pq-componente-info">
                <span class="pq-componente-nombre">${c.nombre}</span>
                <span class="pq-componente-codigo">${c.codigo || ''}</span>
            </div>
            <input type="number" class="pq-componente-cantidad" min="0.001" step="0.001"
                   value="${c.cantidad}" data-pk="${c.producto_pk}" title="Cantidad de este componente por paquete">
            <button type="button" class="pq-componente-quitar" data-pk="${c.producto_pk}" title="Quitar">✕</button>
        </div>
    `).join('');

    cont.querySelectorAll('.pq-componente-cantidad').forEach(el => {
        el.addEventListener('input', () => {
            const comp = _pqComponentesSeleccionados.find(c => String(c.producto_pk) === el.dataset.pk);
            if (comp) comp.cantidad = parseFloat(el.value) || 0;
        });
    });
    cont.querySelectorAll('.pq-componente-quitar').forEach(btn => {
        btn.addEventListener('click', () => {
            _pqComponentesSeleccionados = _pqComponentesSeleccionados.filter(
                c => String(c.producto_pk) !== btn.dataset.pk
            );
            _renderComponentes();
        });
    });
}

let _pqBuscarTimer;
document.getElementById('pqComponenteBuscar')?.addEventListener('input', (e) => {
    clearTimeout(_pqBuscarTimer);
    const q = e.target.value.trim();
    const dropdown = document.getElementById('pqComponenteDropdown');
    if (!q) {
        dropdown.innerHTML = '';
        return;
    }
    _pqBuscarTimer = setTimeout(async () => {
        const res  = await fetch(`${URLS.productoBuscar}?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        const pkPaqueteActual = document.getElementById('pqPk').value;
        const results = (data.results || []).filter(p =>
            !_pqComponentesSeleccionados.some(sel => String(sel.producto_pk) === String(p.pk)) &&
            String(p.pk) !== String(pkPaqueteActual)
        );
        dropdown.innerHTML = results.length
            ? results.map(p => `
                <div class="prd-of-dropdown-option" data-pk="${p.pk}" data-nombre="${p.nombre.replace(/"/g, '&quot;')}" data-codigo="${p.codigo}">
                    [${p.codigo}] ${p.nombre}
                </div>`).join('')
            : '<div class="prd-of-dropdown-option">Sin resultados</div>';
        dropdown.querySelectorAll('.prd-of-dropdown-option[data-pk]').forEach(el => {
            el.addEventListener('click', () => {
                _pqComponentesSeleccionados.push({
                    producto_pk: parseInt(el.dataset.pk, 10),
                    nombre: el.dataset.nombre,
                    codigo: el.dataset.codigo,
                    cantidad: 1,
                });
                _renderComponentes();
                dropdown.innerHTML = '';
                document.getElementById('pqComponenteBuscar').value = '';
            });
        });
    }, 260);
});

function _payloadPaquete() {
    return {
        nombre:        document.getElementById('pqNombre').value.trim(),
        precio_venta:  document.getElementById('pqPrecioVenta').value,
        descripcion:   document.getElementById('pqDescripcion').value.trim(),
        activo:        document.getElementById('pqActivo').checked,
        componentes:   _pqComponentesSeleccionados.map(c => ({ producto_pk: c.producto_pk, cantidad: c.cantidad })),
    };
}

async function guardarPaquete() {
    const pk     = document.getElementById('pqPk').value;
    const errBox = document.getElementById('pqFormError');
    errBox.style.display = 'none';

    const body = _payloadPaquete();
    if (!body.nombre || body.precio_venta === '') {
        errBox.textContent   = 'Completá el nombre y el precio de venta.';
        errBox.style.display = '';
        return;
    }
    if (!body.componentes.length) {
        errBox.textContent   = 'Agregá al menos un producto componente.';
        errBox.style.display = '';
        return;
    }
    if (pk) body.pk = pk;

    const res  = await fetch(URLS.paqueteAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!data.ok) {
        errBox.textContent = Object.values(data.errors || {}).flat().join(' ') || 'Error al guardar.';
        errBox.style.display = '';
        return;
    }

    KaiToast.show(`Paquete "${data.nombre}" ${data.creado ? 'creado' : 'actualizado'}.`, 'success');
    // No se cierra el modal solo: se deja el código de barras a la
    // vista (y listo para imprimir) hasta que el usuario lo cierre.
    document.getElementById('pqPk').value = data.pk;
    document.getElementById('pqCodigoBarras').value = data.data.codigo_barras || '';
    document.getElementById('btnGuardarPaqueteTxt').textContent = 'Guardar cambios';
    document.getElementById('modalPaqueteTitulo').textContent = 'Editar paquete';
    document.getElementById('btnCancelarPaquete').textContent = 'Cerrar';
    _mostrarBarcodePreview(data.data.codigo_barras);
    await cargarPaquetes();
}

async function _eliminarPaquete(pk, nombre) {
    if (!await KaiConfirm(`¿Eliminar el paquete "${nombre}"? Esta acción no se puede deshacer.`, { danger: true })) return;
    const res  = await fetch(URLS.paqueteEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        KaiToast.show(`Paquete "${data.nombre}" eliminado.`, 'success');
        _resetFormPaquete();
        await cargarPaquetes();
    } else {
        KaiToast.show(data.error || 'Error', 'danger');
    }
}

// ESC cierra modales
document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.prd-modal-overlay--open').forEach(overlay => cerrarModal(overlay.id));
});
