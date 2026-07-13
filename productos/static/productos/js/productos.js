/**
 * productos.js
 * Toda la lógica de la app Productos.
 * CSRF y URLS se inyectan desde el template (const CSRF, const URLS).
 */

'use strict';

// ════════════════════════════════════════════════════════════════════
//  TOAST
// ════════════════════════════════════════════════════════════════════
function showToast(msg, tipo = 'ok') {
    const t = document.getElementById('prdToast');
    t.textContent = msg;
    t.className = `prd-toast prd-toast--${tipo} prd-toast--show`;
    setTimeout(() => t.classList.remove('prd-toast--show'), 3200);
}

// ════════════════════════════════════════════════════════════════════
//  MODALES
// ════════════════════════════════════════════════════════════════════
function abrirModal(id) {
    document.getElementById(id).classList.add('prd-modal-overlay--open');
    document.body.style.overflow = 'hidden';
}

function cerrarModal(id) {
    document.getElementById(id).classList.remove('prd-modal-overlay--open');
    document.body.style.overflow = '';
}

document.querySelectorAll('.prd-modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
        if (e.target === overlay) cerrarModal(overlay.id);
    });
});

// ════════════════════════════════════════════════════════════════════
//  TABS
// ════════════════════════════════════════════════════════════════════
document.querySelectorAll('.prd-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.prd-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.prd-tab-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    });
});

// ════════════════════════════════════════════════════════════════════
//  PRECIO — toggle Manual / Automático
// ════════════════════════════════════════════════════════════════════
function setModoPrecio(modo) {
    document.getElementById('f_modo_precio').value = modo;
    document.querySelectorAll('.prd-precio-toggle-btn').forEach(btn => {
        btn.classList.toggle('prd-precio-toggle-btn--active', btn.dataset.modo === modo);
    });

    const esAutomatico = modo === 'automatico';
    document.getElementById('campo_porcentaje_ganancia').hidden = !esAutomatico;

    const inputPrecio = document.getElementById('f_precio_venta');
    inputPrecio.readOnly = esAutomatico;
    inputPrecio.classList.toggle('prd-input--readonly', esAutomatico);
}

function actualizarBadgeCosto(costoActual) {
    const badge = document.getElementById('badge_costo_actual');
    if (!costoActual) {
        badge.textContent = 'Sin compras registradas todavía.';
        return;
    }
    badge.textContent = `Último costo de compra: $${parseFloat(costoActual).toFixed(2)}`;
}

document.querySelectorAll('.prd-precio-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => setModoPrecio(btn.dataset.modo));
});

// ════════════════════════════════════════════════════════════════════
//  NUEVO PRODUCTO
// ════════════════════════════════════════════════════════════════════
document.getElementById('btnNuevoProducto').addEventListener('click', () => {
    limpiarFormProducto();
    document.getElementById('modalProductoTitulo').textContent = 'Nuevo producto';
    document.getElementById('prdPk').value = '';
    document.querySelector('.prd-tab[data-tab="identificacion"]').click();
    document.getElementById('imgNuevoAviso').style.display = '';
    document.getElementById('imgPanel').style.display = 'none';
    _actualizarPanelVariantes(false);
    abrirModal('modalProducto');
});

function limpiarFormProducto() {
    [
        'f_codigo','f_sku','f_codigo_barras','f_nombre','f_nombre_corto',
        'f_marca','f_modelo','f_fabricante','f_pais_origen',
        'f_contenido_neto','f_descripcion','f_descripcion_publica',
        'f_precio_venta','f_porcentaje_ganancia',
        'f_notas','f_tags',
        'f_peso_kg','f_alto_cm','f_ancho_cm','f_profundidad_cm',
        'f_stock_minimo', 'f_posicion_deposito',
    ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });

    document.getElementById('f_unidad_medida').value    = 'unidad';
    document.getElementById('f_estado').value           = 'activo';
    document.getElementById('f_categoria').value        = '';
    document.getElementById('f_tipo').value             = '';

    ['f_destacado','f_requiere_refrigeracion','f_es_fragil',
     'f_es_peligroso','f_gestiona_variantes',
     'f_gestiona_stock','f_permite_stock_negativo'].forEach(id => {
        document.getElementById(id).checked = false;
    });

    document.getElementById('f_precio_incluye_iva') && (document.getElementById('f_precio_incluye_iva').checked = true); // compatibilidad
    document.getElementById('f_gestiona_stock').checked       = true;  // default: siempre gestiona stock
    document.getElementById('prdFormError').style.display   = 'none';
    document.getElementById('categManager').style.display   = 'none';
    document.getElementById('tipoManager').style.display    = 'none';
    document.getElementById('varianteTipoManager').style.display = 'none';
    document.getElementById('varianteValorManager').style.display = 'none';
    document.getElementById('combinacionWarningMovimientos').style.display = 'none';
    // Limpiar lista de combinaciones para que no queden las del producto anterior
    const combinacionLista = document.getElementById('combinacionLista');
    if (combinacionLista) combinacionLista.innerHTML = '<div class="prd-manager-loading">Cargando combinaciones...</div>';
    document.getElementById('combinacionStockTotal').textContent = '0';
    const badge = document.getElementById('tabCombinacionCount');
    badge.textContent = '0'; badge.style.display = 'none';
    cancelarFormCombinacion();
    _actualizarPanelVariantes(false);
    _actualizarCampoCodigoBarras(false);
    setModoPrecio('manual');
    actualizarBadgeCosto(null);
}

// ════════════════════════════════════════════════════════════════════
//  EDITAR PRODUCTO
// ════════════════════════════════════════════════════════════════════
async function abrirEditar(pk) {
    limpiarFormProducto();
    abrirModal('modalProducto');
    document.getElementById('modalProductoTitulo').textContent = 'Editando producto...';

    const res  = await fetch(`${URLS.productoAcciones}?pk=${pk}`);
    const data = await res.json();
    if (!res.ok) {
        showToast('Error al cargar producto', 'error');
        cerrarModal('modalProducto');
        return;
    }

    document.getElementById('prdPk').value                     = data.pk;
    document.getElementById('modalProductoTitulo').textContent  = `Editar: ${data.nombre}`;
    document.getElementById('f_codigo').value                  = data.codigo || '';
    document.getElementById('f_sku').value                     = data.sku || '';
    document.getElementById('f_codigo_barras').value           = data.codigo_barras || '';
    document.getElementById('f_nombre').value                  = data.nombre || '';
    document.getElementById('f_nombre_corto').value            = data.nombre_corto || '';
    document.getElementById('f_marca').value                   = data.marca || '';
    document.getElementById('f_modelo').value                  = data.modelo || '';
    document.getElementById('f_fabricante').value              = data.fabricante || '';
    document.getElementById('f_pais_origen').value             = data.pais_origen || '';
    document.getElementById('f_unidad_medida').value           = data.unidad_medida || 'unidad';
    document.getElementById('f_contenido_neto').value          = data.contenido_neto || '';
    document.getElementById('f_descripcion').value             = data.descripcion || '';
    document.getElementById('f_descripcion_publica').value     = data.descripcion_publica || '';
    document.getElementById('f_categoria').value               = data.categoria || '';
    document.getElementById('f_tipo').value                    = data.tipo || '';
    document.getElementById('f_estado').value                  = data.estado || 'activo';
    document.getElementById('f_tags').value                    = data.tags || '';
    document.getElementById('f_precio_venta').value            = data.precio_venta || '';
    setModoPrecio(data.modo_precio || 'manual');
    document.getElementById('f_porcentaje_ganancia').value     = data.porcentaje_ganancia || '';
    actualizarBadgeCosto(data.costo_actual);
    document.getElementById('f_notas').value                   = data.notas || '';
    document.getElementById('f_peso_kg').value                 = data.peso_kg || '';
    document.getElementById('f_alto_cm').value                 = data.alto_cm || '';
    document.getElementById('f_ancho_cm').value                = data.ancho_cm || '';
    document.getElementById('f_profundidad_cm').value          = data.profundidad_cm || '';
    document.getElementById('f_stock_minimo').value            = data.stock_minimo || '0';
    document.getElementById('f_posicion_deposito').value       = data.posicion_deposito || '';
    document.getElementById('f_destacado').checked             = data.destacado;
    document.getElementById('f_requiere_refrigeracion').checked = data.requiere_refrigeracion;
    document.getElementById('f_es_fragil').checked             = data.es_fragil;
    document.getElementById('f_es_peligroso').checked          = data.es_peligroso;
    document.getElementById('f_gestiona_variantes').checked  = data.gestiona_variantes;
    document.getElementById('f_gestiona_stock').checked          = data.gestiona_stock;
    document.getElementById('f_permite_stock_negativo').checked  = data.permite_stock_negativo;

    if (data.tiene_movimientos) {
        document.getElementById('combinacionWarningMovimientos').style.display = '';
    }

    _actualizarPanelVariantes(data.gestiona_variantes);
    _actualizarCampoCodigoBarras(data.gestiona_variantes);
    if (data.gestiona_variantes) {
        await cargarCatalogoVariantes();
        document.getElementById('combinacionNuevoAviso').style.display = 'none';
        cargarCombinaciones(data.pk);
    }

    document.getElementById('imgNuevoAviso').style.display = 'none';
    document.getElementById('imgPanel').style.display      = '';
    cargarImagenes(data.pk);
    document.querySelector('.prd-tab[data-tab="identificacion"]').click();
}

// ════════════════════════════════════════════════════════════════════
//  GUARDAR PRODUCTO
// ════════════════════════════════════════════════════════════════════
async function guardarProducto() {
    const btn    = document.getElementById('btnGuardarProducto');
    const txt    = document.getElementById('btnGuardarTxt');
    const spin   = document.getElementById('btnGuardarSpin');
    const errBox = document.getElementById('prdFormError');

    btn.disabled = true;
    txt.style.display  = 'none';
    spin.style.display = '';
    errBox.style.display = 'none';

    const tieneVariantes = document.getElementById('f_gestiona_variantes').checked;

    const payload = {
        pk:                     document.getElementById('prdPk').value || null,
        codigo:                 document.getElementById('f_codigo').value,
        sku:                    document.getElementById('f_sku').value,
        codigo_barras:          document.getElementById('f_codigo_barras').value,
        nombre:                 document.getElementById('f_nombre').value,
        nombre_corto:           document.getElementById('f_nombre_corto').value,
        descripcion:            document.getElementById('f_descripcion').value,
        descripcion_publica:    document.getElementById('f_descripcion_publica').value,
        categoria:              document.getElementById('f_categoria').value || null,
        tipo:                   document.getElementById('f_tipo').value || null,
        marca:                  document.getElementById('f_marca').value,
        modelo:                 document.getElementById('f_modelo').value,
        fabricante:             document.getElementById('f_fabricante').value,
        pais_origen:            document.getElementById('f_pais_origen').value,
        unidad_medida:          document.getElementById('f_unidad_medida').value,
        contenido_neto:         document.getElementById('f_contenido_neto').value || null,
        peso_kg:                document.getElementById('f_peso_kg').value || null,
        alto_cm:                document.getElementById('f_alto_cm').value || null,
        ancho_cm:               document.getElementById('f_ancho_cm').value || null,
        profundidad_cm:         document.getElementById('f_profundidad_cm').value || null,
        precio_venta:           document.getElementById('f_precio_venta').value || null,
        modo_precio:            document.getElementById('f_modo_precio').value,
        porcentaje_ganancia:    document.getElementById('f_porcentaje_ganancia').value || null,
        estado:                 document.getElementById('f_estado').value,
        destacado:              document.getElementById('f_destacado').checked,
        requiere_refrigeracion: document.getElementById('f_requiere_refrigeracion').checked,
        es_fragil:              document.getElementById('f_es_fragil').checked,
        es_peligroso:           document.getElementById('f_es_peligroso').checked,
        notas:                  document.getElementById('f_notas').value,
        tags:                   document.getElementById('f_tags').value,
        gestiona_variantes:     tieneVariantes,
        es_perecedero:          document.getElementById('f_es_perecedero').checked,
        gestiona_stock:         document.getElementById('f_gestiona_stock').checked,
        permite_stock_negativo: document.getElementById('f_permite_stock_negativo').checked,
        stock_minimo:           parseInt(document.getElementById('f_stock_minimo').value) || 0,
        stock_maximo:           document.getElementById('f_stock_maximo') ? (document.getElementById('f_stock_maximo').value || null) : null,
        posicion_deposito:      document.getElementById('f_posicion_deposito').value,
    };

    const esNuevo = !payload.pk;

    try {
        const res  = await fetch(URLS.productoAcciones, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.ok) {
            if (esNuevo) {
                // Producto recién creado: actualizar PK y habilitar imágenes/colores
                // sin cerrar el modal — el usuario puede seguir completando
                document.getElementById('prdPk').value                    = data.pk;
                document.getElementById('modalProductoTitulo').textContent = `Editar: ${data.nombre}`;
                document.getElementById('f_codigo').value                  = data.codigo;

                // Habilitar imágenes silenciosamente
                document.getElementById('imgNuevoAviso').style.display = 'none';
                document.getElementById('imgPanel').style.display      = '';
                cargarImagenes(data.pk);

                // Habilitar variantes si corresponde
                if (tieneVariantes) {
                    document.getElementById('combinacionNuevoAviso').style.display = 'none';
                    await cargarCatalogoVariantes();
                    cargarCombinaciones(data.pk);
                }
                _actualizarCampoCodigoBarras(tieneVariantes);

                // Agregar la fila nueva a la tabla sin recargar
                agregarFilaTabla(data);
                actualizarContadoresStats(1, data.estado === 'activo' ? 1 : 0, 0);

                showToast(`Producto "${data.nombre}" creado. Podés seguir completando los detalles.`);
            } else {
                // Actualizar la fila existente en la tabla sin recargar
                actualizarFilaTabla(data);
                showToast(`Producto "${data.nombre}" actualizado.`);
                cerrarModal('modalProducto');
            }
        } else {
            const msgs = Object.entries(data.errors || {})
                .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                .join('\n');
            errBox.textContent   = msgs || 'Error al guardar.';
            errBox.style.display = 'block';
        }
    } catch {
        errBox.textContent   = 'Error de conexión.';
        errBox.style.display = 'block';
    } finally {
        btn.disabled       = false;
        txt.style.display  = '';
        spin.style.display = 'none';
    }
}

// ════════════════════════════════════════════════════════════════════
//  ELIMINAR PRODUCTO
// ════════════════════════════════════════════════════════════════════
let _eliminarPk = null;

function confirmarEliminar(pk, nombre) {
    _eliminarPk = pk;
    document.getElementById('eliminarNombre').textContent = nombre;
    abrirModal('modalEliminar');
}

document.getElementById('btnConfirmarEliminar').addEventListener('click', async () => {
    if (!_eliminarPk) return;
    const res  = await fetch(URLS.productoEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk: _eliminarPk }),
    });
    const data = await res.json();
    if (data.ok) {
        cerrarModal('modalEliminar');
        showToast('Producto eliminado.', 'ok');
        document.querySelector(`tr[data-pk="${_eliminarPk}"]`)?.remove();
    } else {
        showToast(data.error || 'Error al eliminar.', 'error');
    }
    _eliminarPk = null;
});

// ════════════════════════════════════════════════════════════════════
//  TOGGLE PUBLICAR / DESPUBLICAR
// ════════════════════════════════════════════════════════════════════
async function togglePublicar(pk, publicadoActual, btn) {
    const nuevoEstado = !publicadoActual;
    try {
        const res  = await fetch(`${URLS.productoAcciones}?pk=${pk}`);
        const data = await res.json();
        const fullPayload = {
            ...data,
            publicado:            nuevoEstado,
            categoria:            data.categoria || null,
            tipo:                 data.tipo || null,
            gestiona_variantes: data.gestiona_variantes,
        };
        const res2  = await fetch(URLS.productoAcciones, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
            body: JSON.stringify(fullPayload),
        });
        const data2 = await res2.json();
        if (data2.ok) {
            btn.classList.toggle('prd-action-btn--publicado', nuevoEstado);
            btn.title = nuevoEstado ? 'Despublicar del catálogo' : 'Publicar en catálogo';
            btn.setAttribute('onclick', `togglePublicar(${pk}, ${nuevoEstado}, this)`);
            showToast(nuevoEstado ? 'Producto publicado.' : 'Producto despublicado.', 'ok');
        } else {
            showToast('Error al cambiar estado de publicación.', 'error');
        }
    } catch {
        showToast('Error de conexión.', 'error');
    }
}

// ════════════════════════════════════════════════════════════════════
//  MANAGER INLINE — CATEGORÍAS Y TIPOS
//  El botón + abre un pequeño dropdown solo con input + agregar.
//  El botón de papelera elimina la opción actualmente seleccionada.
// ════════════════════════════════════════════════════════════════════
function toggleInlineManager(id) {
    const el      = document.getElementById(id);
    const abierto = el.style.display !== 'none';
    ['categManager', 'tipoManager', 'varianteTipoManager', 'varianteValorManager'].forEach(mid => {
        const node = document.getElementById(mid);
        if (node) node.style.display = 'none';
    });
    if (!abierto) el.style.display = '';
}

async function crearCategoria() {
    const input  = document.getElementById('nuevaCategNombre');
    const nombre = input.value.trim();
    if (!nombre) return;
    const res  = await fetch(URLS.categoriaAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ nombre }),
    });
    const data = await res.json();
    if (data.ok) {
        input.value = '';
        document.getElementById('categManager').style.display = 'none';
        showToast(`Categoría "${data.nombre}" creada.`);
        const sel = document.getElementById('f_categoria');
        const opt = document.createElement('option');
        opt.value = data.pk; opt.textContent = data.nombre; opt.selected = true;
        sel.appendChild(opt);
    } else {
        showToast(data.errors?.nombre?.[0] || data.error || 'Error', 'error');
    }
}

async function eliminarCategoriaSeleccionada() {
    const sel = document.getElementById('f_categoria');
    const pk  = sel.value;
    const nombre = sel.options[sel.selectedIndex]?.text;
    if (!pk) { showToast('Seleccioná una categoría para eliminar.', 'error'); return; }
    if (!confirm(`¿Eliminar la categoría "${nombre}"? Solo se puede si no tiene productos asociados.`)) return;
    const res  = await fetch(URLS.categoriaEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Categoría "${nombre}" eliminada.`);
        sel.options[sel.selectedIndex].remove();
        sel.value = '';
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

async function crearTipo() {
    const input  = document.getElementById('nuevoTipoNombre');
    const nombre = input.value.trim();
    if (!nombre) return;
    const res  = await fetch(URLS.tipoAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ nombre }),
    });
    const data = await res.json();
    if (data.ok) {
        input.value = '';
        document.getElementById('tipoManager').style.display = 'none';
        showToast(`Tipo "${data.nombre}" creado.`);
        const sel = document.getElementById('f_tipo');
        const opt = document.createElement('option');
        opt.value = data.pk; opt.textContent = data.nombre; opt.selected = true;
        sel.appendChild(opt);
    } else {
        showToast(data.errors?.nombre?.[0] || data.error || 'Error', 'error');
    }
}

async function eliminarTipoSeleccionado() {
    const sel = document.getElementById('f_tipo');
    const pk  = sel.value;
    const nombre = sel.options[sel.selectedIndex]?.text;
    if (!pk) { showToast('Seleccioná un tipo para eliminar.', 'error'); return; }
    if (!confirm(`¿Eliminar el tipo "${nombre}"? Solo se puede si no tiene productos asociados.`)) return;
    const res  = await fetch(URLS.tipoEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Tipo "${nombre}" eliminado.`);
        sel.options[sel.selectedIndex].remove();
        sel.value = '';
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

document.getElementById('nuevaCategNombre').addEventListener('keydown', e => { if (e.key === 'Enter') crearCategoria(); });
document.getElementById('nuevoTipoNombre').addEventListener('keydown',  e => { if (e.key === 'Enter') crearTipo(); });

// ════════════════════════════════════════════════════════════════════
//  IMÁGENES
// ════════════════════════════════════════════════════════════════════
function cargarImagenes(pk) {
    const grid = document.getElementById('imgGrid');
    grid.innerHTML = '<p style="font-size:.8rem;color:var(--text-muted);padding:.5rem 0">Las imágenes existentes se muestran arriba en la tabla. Subí nuevas desde aquí.</p>';
    actualizarBadgeImagenes();
}

function actualizarBadgeImagenes() {
    const items = document.querySelectorAll('.prd-img-item').length;
    const badge = document.getElementById('tabImagenCount');
    badge.textContent   = items;
    badge.style.display = items > 0 ? '' : 'none';
}

const imgFileInput  = document.getElementById('imgFileInput');
const imgUploadZone = document.getElementById('imgUploadZone');

imgFileInput.addEventListener('change', () => subirImagenes(imgFileInput.files));
imgUploadZone.addEventListener('dragover',  e => { e.preventDefault(); imgUploadZone.classList.add('prd-img-upload-zone--over'); });
imgUploadZone.addEventListener('dragleave', () => imgUploadZone.classList.remove('prd-img-upload-zone--over'));
imgUploadZone.addEventListener('drop', e => {
    e.preventDefault();
    imgUploadZone.classList.remove('prd-img-upload-zone--over');
    subirImagenes(e.dataTransfer.files);
});

async function subirImagenes(files) {
    const pk = document.getElementById('prdPk').value;
    if (!pk) { showToast('Guardá el producto primero.', 'error'); return; }
    for (const file of files) {
        if (!file.type.startsWith('image/')) continue;
        if (file.size > 5 * 1024 * 1024) { showToast(`"${file.name}" supera 5 MB.`, 'error'); continue; }
        const fd = new FormData();
        fd.append('producto_pk', pk);
        fd.append('imagen', file);
        try {
            const res  = await fetch(URLS.imagenSubir, { method: 'POST', headers: { 'X-CSRFToken': CSRF }, body: fd });
            const data = await res.json();
            if (data.ok) {
                agregarImagenAlGrid(data.imagen_pk, data.url, data.es_portada);
                showToast(`Imagen "${file.name}" subida.`);
            } else {
                showToast(data.errors?.imagen?.[0] || 'Error al subir imagen.', 'error');
            }
        } catch { showToast('Error de conexión al subir imagen.', 'error'); }
    }
    imgFileInput.value = '';
}

function agregarImagenAlGrid(pk, url, esPortada) {
    const grid = document.getElementById('imgGrid');
    grid.querySelectorAll('p').forEach(p => p.remove());
    const item = document.createElement('div');
    item.className = 'prd-img-item' + (esPortada ? ' prd-img-item--portada' : '');
    item.id = `img-${pk}`;
    item.innerHTML = `
        <img src="${url}" alt="" class="prd-img-thumb">
        ${esPortada ? '<span class="prd-img-portada-badge">Portada</span>' : ''}
        <div class="prd-img-actions">
            ${!esPortada ? `<button class="prd-img-btn" title="Marcar como portada" onclick="marcarPortada(${pk})">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1l1.5 3 3.5.5-2.5 2.5.5 3.5L6.5 9 3 10.5l.5-3.5L1 4.5 4.5 4z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
            </button>` : ''}
            <button class="prd-img-btn prd-img-btn--del" onclick="eliminarImagen(${pk})">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 2L11 11M11 2L2 11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
            </button>
        </div>`;
    grid.appendChild(item);
    actualizarBadgeImagenes();
}

async function marcarPortada(pk) {
    const res  = await fetch(URLS.imagenPortada, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        document.querySelectorAll('.prd-img-item').forEach(el => {
            el.classList.remove('prd-img-item--portada');
            el.querySelector('.prd-img-portada-badge')?.remove();
        });
        const item = document.getElementById(`img-${pk}`);
        if (item) {
            item.classList.add('prd-img-item--portada');
            const badge = document.createElement('span');
            badge.className   = 'prd-img-portada-badge';
            badge.textContent = 'Portada';
            item.prepend(badge);
            item.querySelector('.prd-img-btn:not(.prd-img-btn--del)')?.remove();
        }
        showToast('Imagen de portada actualizada.');
    }
}

async function eliminarImagen(pk) {
    if (!confirm('¿Eliminar esta imagen?')) return;
    const res  = await fetch(URLS.imagenEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        document.getElementById(`img-${pk}`)?.remove();
        actualizarBadgeImagenes();
        showToast('Imagen eliminada.');
    } else {
        showToast('Error al eliminar imagen.', 'error');
    }
}

// ════════════════════════════════════════════════════════════════════
//  VARIANTES — CATÁLOGO GLOBAL (tipos y valores)
// ════════════════════════════════════════════════════════════════════
let _cacheVariantes = [];
let _cacheOpciones  = [];
let _combinacionesCache = {};

async function cargarCatalogoVariantes() {
    try {
        const [resVar, resOpc] = await Promise.all([
            fetch(URLS.varianteLista),
            fetch(URLS.opcionLista),
        ]);
        const dataVar = await resVar.json();
        const dataOpc = await resOpc.json();
        _cacheVariantes = dataVar.results || [];
        _cacheOpciones  = dataOpc.results || [];
        poblarSelectVariantes(document.getElementById('f_variante_tipo'));
        actualizarSelectValoresCatalogo();
        _renderCatalogoResumen();
        renderBulkDimensiones();
        renderBulkPreview();
    } catch {
        showToast('Error al cargar el catálogo de variantes.', 'error');
    }
}

function poblarSelectVariantes(selectEl, selectedPk = '') {
    if (!selectEl) return;
    const prev = selectedPk || selectEl.value;
    selectEl.innerHTML = '<option value="">— Seleccionar tipo —</option>';
    _cacheVariantes.filter(v => v.activo).forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.pk;
        opt.textContent = v.nombre;
        selectEl.appendChild(opt);
    });
    if (prev) selectEl.value = String(prev);
}

function opcionesDeVariante(variantePk) {
    return _cacheOpciones.filter(
        o => o.activo && String(o.variante_pk) === String(variantePk),
    );
}

function poblarSelectOpciones(selectEl, variantePk, selectedPk = '') {
    if (!selectEl) return;
    const prev = selectedPk || selectEl.value;
    selectEl.innerHTML = '<option value="">— Seleccionar valor —</option>';
    if (!variantePk) {
        selectEl.disabled = true;
        selectEl.innerHTML = '<option value="">— Primero elegí un tipo —</option>';
        return;
    }
    selectEl.disabled = false;
    opcionesDeVariante(variantePk).forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.pk;
        opt.textContent = o.nombre;
        selectEl.appendChild(opt);
    });
    if (prev) selectEl.value = String(prev);
}

function actualizarSelectValoresCatalogo() {
    const tipoPk = document.getElementById('f_variante_tipo').value;
    poblarSelectOpciones(document.getElementById('f_variante_valor'), tipoPk);
}

document.getElementById('f_variante_tipo')?.addEventListener('change', actualizarSelectValoresCatalogo);

function _renderCatalogoResumen() {
    const cont = document.getElementById('catalogoValoresResumen');
    if (!cont) return;
    const tipos = _cacheVariantes.filter(v => v.activo);
    if (!tipos.length) {
        cont.innerHTML = '<span class="prd-v2-chip-empty">Todavía no cargaste tipos de variante.</span>';
        return;
    }
    cont.innerHTML = tipos.map(t => {
        const valores = opcionesDeVariante(t.pk);
        const chips = valores.length
            ? valores.map(o => `
                <span class="prd-v2-chip" onclick="_seleccionarChipCatalogo('${t.pk}','${o.pk}')">
                    ${o.nombre}
                    <span class="prd-v2-chip-del" title="Eliminar valor" onclick="event.stopPropagation(); _eliminarValorCatalogo('${o.pk}','${o.nombre.replace(/'/g, "\\'")}')">
                        <svg width="9" height="9" viewBox="0 0 9 9" fill="none"><path d="M1 1L8 8M8 1L1 8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
                    </span>
                </span>`).join('')
            : '<span class="prd-v2-chip-empty">Sin valores todavía</span>';
        return `
            <div class="prd-v2-resumen-tipo">
                <div class="prd-v2-resumen-tipo-nombre">${t.nombre}</div>
                <div class="prd-v2-chips">${chips}</div>
            </div>`;
    }).join('');
}

function _seleccionarChipCatalogo(tipoPk, opcionPk) {
    const selTipo = document.getElementById('f_variante_tipo');
    selTipo.value = tipoPk;
    actualizarSelectValoresCatalogo();
    document.getElementById('f_variante_valor').value = opcionPk;
}

async function _eliminarValorCatalogo(pk, nombre) {
    if (!confirm(`¿Eliminar el valor "${nombre}"?`)) return;
    const res  = await fetch(URLS.opcionEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Valor "${nombre}" eliminado.`);
        await cargarCatalogoVariantes();
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

async function crearVariante() {
    const input  = document.getElementById('nuevaVarianteNombre');
    const nombre = input.value.trim();
    if (!nombre) return;
    const res  = await fetch(URLS.varianteAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ nombre }),
    });
    const data = await res.json();
    if (data.ok) {
        input.value = '';
        document.getElementById('varianteTipoManager').style.display = 'none';
        showToast(`Tipo de variante "${data.nombre}" creado.`);
        await cargarCatalogoVariantes();
        document.getElementById('f_variante_tipo').value = data.pk;
        actualizarSelectValoresCatalogo();
        document.querySelectorAll('.prd-combinacion-opcion-row select[data-rol="tipo"]').forEach(sel => poblarSelectVariantes(sel));
    } else {
        showToast(data.errors?.nombre?.[0] || data.error || 'Error', 'error');
    }
}

async function eliminarVarianteSeleccionada() {
    const sel = document.getElementById('f_variante_tipo');
    const pk  = sel.value;
    const nombre = sel.options[sel.selectedIndex]?.text;
    if (!pk) { showToast('Seleccioná un tipo de variante para eliminar.', 'error'); return; }
    if (!confirm(`¿Eliminar el tipo "${nombre}"? Solo se puede si no tiene valores asociados.`)) return;
    const res  = await fetch(URLS.varianteEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Tipo "${nombre}" eliminado.`);
        await cargarCatalogoVariantes();
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

async function crearOpcionVariante() {
    const variantePk = document.getElementById('f_variante_tipo').value;
    if (!variantePk) {
        showToast('Seleccioná primero un tipo de variante.', 'error');
        return;
    }
    const input  = document.getElementById('nuevaOpcionNombre');
    const nombre = input.value.trim();
    if (!nombre) return;
    const res  = await fetch(URLS.opcionAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ variante_pk: variantePk, nombre }),
    });
    const data = await res.json();
    if (data.ok) {
        input.value = '';
        document.getElementById('varianteValorManager').style.display = 'none';
        showToast(`Valor "${data.nombre}" creado.`);
        await cargarCatalogoVariantes();
        document.getElementById('f_variante_tipo').value = variantePk;
        actualizarSelectValoresCatalogo();
        document.getElementById('f_variante_valor').value = data.pk;
    } else {
        showToast(data.errors?.nombre?.[0] || data.error || 'Error', 'error');
    }
}

async function eliminarOpcionSeleccionada() {
    const sel = document.getElementById('f_variante_valor');
    const pk  = sel.value;
    const nombre = sel.options[sel.selectedIndex]?.text;
    if (!pk) { showToast('Seleccioná un valor para eliminar.', 'error'); return; }
    if (!confirm(`¿Eliminar el valor "${nombre}"?`)) return;
    const res  = await fetch(URLS.opcionEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Valor "${nombre}" eliminado.`);
        await cargarCatalogoVariantes();
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

document.getElementById('nuevaVarianteNombre')?.addEventListener('keydown', e => { if (e.key === 'Enter') crearVariante(); });
document.getElementById('nuevaOpcionNombre')?.addEventListener('keydown', e => { if (e.key === 'Enter') crearOpcionVariante(); });

// ════════════════════════════════════════════════════════════════════
//  VARIANTES — PANEL Y TOGGLE
// ════════════════════════════════════════════════════════════════════
function _actualizarCampoCodigoBarras(tieneVariantes) {
    const wrap = document.getElementById('wrap_codigo_barras');
    const input = document.getElementById('f_codigo_barras');
    const hint  = document.getElementById('hint_codigo_barras');
    if (!wrap || !input) return;
    if (tieneVariantes) {
        wrap.style.opacity = '0.45';
        input.disabled = true;
        input.value = '';
        input.placeholder = 'Se define por combinación';
        if (hint) hint.style.display = '';
    } else {
        wrap.style.opacity = '';
        input.disabled = false;
        input.placeholder = 'EAN-13, UPC...';
        if (hint) hint.style.display = 'none';
    }
}

function _actualizarPanelVariantes(tieneVariantes) {
    document.getElementById('panelSinVariantes').style.display = tieneVariantes ? 'none' : '';
    document.getElementById('panelConVariantes').style.display = tieneVariantes ? '' : 'none';
    const badge = document.getElementById('tabCombinacionCount');
    if (!tieneVariantes) { badge.style.display = 'none'; badge.textContent = '0'; }
}

document.getElementById('f_gestiona_variantes').addEventListener('change', async function () {
    _actualizarPanelVariantes(this.checked);
    _actualizarCampoCodigoBarras(this.checked);
    const pk = document.getElementById('prdPk').value;
    if (this.checked) {
        await cargarCatalogoVariantes();
        cancelarFormCombinacion();
        if (pk) {
            document.getElementById('combinacionNuevoAviso').style.display = 'none';
            cargarCombinaciones(pk);
        } else {
            document.getElementById('combinacionNuevoAviso').style.display = '';
        }
    }
});

// ════════════════════════════════════════════════════════════════════
//  VARIANTES — GENERADOR MASIVO DE COMBINACIONES (alta)
// ════════════════════════════════════════════════════════════════════
let _bulkDimId = 0;
let _bulkDimensiones = [];   // [{ id, tipoPk, valores: Set<string pk> }]
let _bulkExcluidos = new Set(); // keys de combos que el usuario destildó
let _bulkDatosFila = {};        // key -> { codigo_barras, sku }

function _cartesianBulk(arrs) {
    return arrs.reduce((acc, arr) => acc.flatMap(a => arr.map(v => [...a, v])), [[]]);
}

function agregarDimensionBulk() {
    _bulkDimensiones.push({ id: ++_bulkDimId, tipoPk: '', valores: new Set() });
    renderBulkDimensiones();
    renderBulkPreview();
}

function eliminarDimensionBulk(id) {
    _bulkDimensiones = _bulkDimensiones.filter(d => d.id !== id);
    renderBulkDimensiones();
    renderBulkPreview();
}

function cambiarTipoBulkDimension(id, tipoPk) {
    const dim = _bulkDimensiones.find(d => d.id === id);
    if (!dim) return;
    dim.tipoPk = tipoPk;
    dim.valores = new Set();
    renderBulkDimensiones();
    renderBulkPreview();
}

function toggleBulkValor(id, valorPk) {
    const dim = _bulkDimensiones.find(d => d.id === id);
    if (!dim) return;
    const key = String(valorPk);
    if (dim.valores.has(key)) dim.valores.delete(key); else dim.valores.add(key);
    renderBulkDimensiones();
    renderBulkPreview();
}

function renderBulkDimensiones() {
    const cont = document.getElementById('bulkDimensionesContainer');
    if (!cont) return;
    if (!_bulkDimensiones.length) {
        cont.innerHTML = '<p class="prd-v2-bulk-empty-hint">Todavía no agregaste ninguna dimensión.</p>';
        return;
    }
    cont.innerHTML = _bulkDimensiones.map(dim => {
        const tiposUsados = new Set(_bulkDimensiones.filter(d => d.id !== dim.id && d.tipoPk).map(d => String(d.tipoPk)));
        const opcionesTipo = _cacheVariantes.filter(v => v.activo && (!tiposUsados.has(String(v.pk)) || String(v.pk) === String(dim.tipoPk)));
        const selectHtml = '<option value="">— Seleccionar tipo —</option>' +
            opcionesTipo.map(v => `<option value="${v.pk}" ${String(v.pk) === String(dim.tipoPk) ? 'selected' : ''}>${v.nombre}</option>`).join('');
        const valoresDisponibles = dim.tipoPk ? opcionesDeVariante(dim.tipoPk) : [];
        const chipsHtml = !dim.tipoPk
            ? '<span class="prd-v2-bulk-empty-hint">Elegí un tipo primero</span>'
            : (valoresDisponibles.length
                ? valoresDisponibles.map(o => `<span class="prd-v2-chip-toggle ${dim.valores.has(String(o.pk)) ? 'prd-v2-chip-toggle--on' : ''}" onclick="toggleBulkValor(${dim.id}, '${o.pk}')">${o.nombre}</span>`).join('')
                : '<span class="prd-v2-bulk-empty-hint">Este tipo todavía no tiene valores cargados en el catálogo (paso 1)</span>');
        return `
            <div class="prd-v2-bulk-dim">
                <div class="prd-v2-bulk-dim-head">
                    <select class="prd-input prd-select" style="max-width:220px" onchange="cambiarTipoBulkDimension(${dim.id}, this.value)">${selectHtml}</select>
                    <button type="button" class="prd-btn-inline-manager prd-btn-inline-manager--del" style="margin-left:auto" onclick="eliminarDimensionBulk(${dim.id})" title="Quitar dimensión">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 4H12M5 4V3H9V4M5.5 6.5V10.5M8.5 6.5V10.5M3 4L3.8 12H10.2L11 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </button>
                </div>
                <div class="prd-v2-chips">${chipsHtml}</div>
            </div>`;
    }).join('');
}

function _bulkDimsActivas() {
    return _bulkDimensiones
        .filter(d => d.tipoPk && d.valores.size)
        .map(d => {
            const tipo = _cacheVariantes.find(v => String(v.pk) === String(d.tipoPk));
            const valores = [...d.valores]
                .map(pk => opcionesDeVariante(d.tipoPk).find(o => String(o.pk) === String(pk)))
                .filter(Boolean);
            return { tipoNombre: tipo ? tipo.nombre : '', valores };
        });
}

function _bulkComboKey(combo) {
    return combo.map(v => String(v.pk)).sort().join('|');
}

function _bulkYaExiste(combo) {
    const pks = combo.map(v => String(v.pk));
    return Object.values(_combinacionesCache).some(c => {
        const set = new Set((c.opciones || []).map(o => String(o.pk)));
        return set.size === pks.length && pks.every(pk => set.has(pk));
    });
}

function renderBulkPreview() {
    const wrap = document.getElementById('bulkPreviewWrap');
    if (!wrap) return;
    const dimsInfo = _bulkDimsActivas();
    if (!dimsInfo.length) {
        wrap.innerHTML = '';
        return;
    }
    const combos = _cartesianBulk(dimsInfo.map(d => d.valores));
    const rows = combos.map(combo => ({
        combo,
        key: _bulkComboKey(combo),
        yaExiste: _bulkYaExiste(combo),
    }));
    const incluidas = rows.filter(r => !r.yaExiste && !_bulkExcluidos.has(r.key));
    const grande = incluidas.length > 20;

    let html = '';
    if (grande) {
        html += `<div class="prd-v2-warning">
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M7.5 1L14 13H1L7.5 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7.5 6V9M7.5 10.5V11" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            Esto va a crear ${incluidas.length} combinaciones. Revisá si realmente necesitás todas antes de guardar.
        </div>`;
    }
    html += `<div class="prd-v2-preview-count">${rows.length} combinaciones posibles${rows.length !== incluidas.length ? ` (${incluidas.length} nuevas a crear)` : ''} — desmarcá las que no querés crear</div>`;
    html += `<div class="prd-v2-preview-tablewrap"><table class="prd-v2-preview-table"><thead><tr>
        <th style="width:30px"></th>
        ${dimsInfo.map(d => `<th>${d.tipoNombre}</th>`).join('')}
        <th>Código de barras</th><th>SKU</th>
    </tr></thead><tbody>`;
    html += rows.map(r => {
        const checked = !r.yaExiste && !_bulkExcluidos.has(r.key);
        const datos = _bulkDatosFila[r.key] || {};
        return `<tr style="opacity:${r.yaExiste ? 0.5 : 1}">
            <td><input type="checkbox" ${checked ? 'checked' : ''} ${r.yaExiste ? 'disabled' : ''} onchange="toggleBulkExcluir('${r.key}', this.checked)"></td>
            ${r.combo.map(v => `<td><span class="prd-v2-preview-chip">${v.nombre}</span></td>`).join('')}
            <td>${r.yaExiste ? '<span class="prd-v2-preview-existe">ya existe</span>' : `<input type="text" class="prd-v2-preview-input" value="${datos.codigo_barras || ''}" oninput="_bulkActualizarDato('${r.key}','codigo_barras',this.value)" placeholder="EAN-13...">`}</td>
            <td>${r.yaExiste ? '' : `<input type="text" class="prd-v2-preview-input" value="${datos.sku || ''}" oninput="_bulkActualizarDato('${r.key}','sku',this.value)" placeholder="opcional">`}</td>
        </tr>`;
    }).join('');
    html += '</tbody></table></div>';
    html += `<div class="prd-combinacion-form-actions" style="margin-top:12px">
        <button type="button" class="prd-btn prd-btn-primary prd-btn--sm" onclick="guardarCombinacionesBulk()">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1.5V11.5M1.5 6.5H11.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            Guardar ${incluidas.length} combinaciones
        </button>
    </div>`;

    wrap.innerHTML = html;
}

function _bulkActualizarDato(key, campo, valor) {
    if (!_bulkDatosFila[key]) _bulkDatosFila[key] = {};
    _bulkDatosFila[key][campo] = valor;
}

function toggleBulkExcluir(key, checked) {
    if (checked) _bulkExcluidos.delete(key); else _bulkExcluidos.add(key);
    renderBulkPreview();
}

async function guardarCombinacionesBulk() {
    const productoPk = document.getElementById('prdPk').value;
    if (!productoPk) {
        showToast('Guardá el producto primero antes de agregar combinaciones.', 'error');
        return;
    }
    const dimsInfo = _bulkDimsActivas();
    if (!dimsInfo.length) {
        showToast('Elegí al menos una dimensión con valores.', 'error');
        return;
    }
    const combos = _cartesianBulk(dimsInfo.map(d => d.valores));
    const aGuardar = combos.filter(combo => {
        const key = _bulkComboKey(combo);
        return !_bulkYaExiste(combo) && !_bulkExcluidos.has(key);
    });
    if (!aGuardar.length) {
        showToast('No hay combinaciones nuevas para guardar.', 'error');
        return;
    }

    let ok = 0, fallidas = 0;
    for (const combo of aGuardar) {
        const key = _bulkComboKey(combo);
        const datos = _bulkDatosFila[key] || {};
        const payload = {
            producto_pk: productoPk,
            opciones: combo.map(v => parseInt(v.pk, 10)),
            codigo_barras: (datos.codigo_barras || '').trim(),
            sku_variante: (datos.sku || '').trim(),
            stock_actual: 0,
        };
        try {
            const res  = await fetch(URLS.combinacionAcciones, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (data.ok) ok++; else fallidas++;
        } catch {
            fallidas++;
        }
    }

    showToast(fallidas
        ? `${ok} combinaciones agregadas, ${fallidas} con error.`
        : `${ok} combinaciones agregadas.`, fallidas ? 'error' : 'ok');

    _bulkDimensiones = [];
    _bulkExcluidos = new Set();
    _bulkDatosFila = {};
    renderBulkDimensiones();
    cargarCombinaciones(productoPk);
}

// ════════════════════════════════════════════════════════════════════
//  VARIANTES — CARGA Y RENDER DE LISTA
// ════════════════════════════════════════════════════════════════════
async function cargarCombinaciones(productoPk) {
    const lista = document.getElementById('combinacionLista');
    lista.innerHTML = '<div class="prd-manager-loading">Cargando combinaciones...</div>';

    const res  = await fetch(`${URLS.combinacionLista}?producto_pk=${productoPk}`);
    const data = await res.json();

    document.getElementById('combinacionStockTotal').textContent = parseFloat(data.stock_total || 0).toFixed(0);

    _combinacionesCache = {};
    (data.combinaciones || []).forEach(c => { _combinacionesCache[c.pk] = c; });

    const activos = (data.combinaciones || []).filter(c => c.activo).length;
    const badge   = document.getElementById('tabCombinacionCount');
    badge.textContent   = activos;
    badge.style.display = activos > 0 ? '' : 'none';

    if (!data.combinaciones || !data.combinaciones.length) {
        lista.innerHTML = '<div class="prd-manager-empty">Sin combinaciones definidas. Agregá la primera abajo.</div>';
        renderBulkPreview();
        return;
    }
    lista.innerHTML = data.combinaciones.map(_renderCombinacionItem).join('');
    renderBulkPreview();
}

function _renderCombinacionItem(c) {
    const inactivoClass = !c.activo ? 'prd-combinacion-item--inactivo' : '';
    const opciones = c.opciones || [];
    const chipsHtml = opciones.length
        ? opciones.map(o => `<span class="prd-combinacion-item2-chip">${o.variante_nombre}: ${o.nombre}</span>`).join('')
        : `<span class="prd-combinacion-item2-chip">${c.descripcion_combinacion || c.descripcion || 'Sin descripción'}</span>`;
    const metaBits = [];
    if (c.codigo_barras) metaBits.push(`CB ${c.codigo_barras}`);
    if (c.sku_variante) metaBits.push(`SKU ${c.sku_variante}`);
    return `
    <div class="prd-combinacion-item ${inactivoClass}" id="combinacion-${c.pk}">
        <div class="prd-combinacion-item-info prd-combinacion-item2">
            <div class="prd-combinacion-item2-chips">
                ${chipsHtml}
                ${!c.activo ? '<span class="prd-combinacion-item-inactivo-badge">Inactivo</span>' : ''}
            </div>
            ${metaBits.length ? `<span class="prd-combinacion-item2-meta">${metaBits.map(m => `<span>${m}</span>`).join('')}</span>` : ''}
        </div>
        <div class="prd-combinacion-item-stock">
            <span class="prd-combinacion-stock-num">${c.stock_actual}</span>
        </div>
        <div class="prd-combinacion-item-actions">
            <button class="prd-img-btn" title="Editar combinación" onclick="editarCombinacion(${c.pk})">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                    <path d="M9 2L11 4L4.5 10.5H2.5V8.5L9 2Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
                </svg>
            </button>
            <button class="prd-img-btn ${!c.activo ? 'prd-img-btn--activar' : ''}" title="${c.activo ? 'Desactivar' : 'Activar'}"
                onclick="toggleCombinacion(${c.pk})">
                ${c.activo
                    ? `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 2L11 11M11 2L2 11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`
                    : `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 7L5 10L11 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`
                }
            </button>
        </div>
    </div>`;
}

function resetFormCombinacionOpciones(opciones = null) {
    const container = document.getElementById('combinacionOpcionesContainer');
    if (!container) return;
    container.innerHTML = '';
    if (opciones && opciones.length) {
        opciones.forEach(op => agregarFilaOpcionCombinacion(op.variante_pk, op.pk));
    } else {
        agregarFilaOpcionCombinacion();
    }
}

function agregarFilaOpcionCombinacion(variantePk = '', opcionPk = '') {
    const container = document.getElementById('combinacionOpcionesContainer');
    const row = document.createElement('div');
    row.className = 'prd-combinacion-opcion-row';
    row.innerHTML = `
        <div class="prd-field">
            <label>Tipo</label>
            <select class="prd-input prd-select" data-rol="tipo"></select>
        </div>
        <div class="prd-field">
            <label>Valor</label>
            <select class="prd-input prd-select" data-rol="valor" disabled>
                <option value="">— Primero elegí un tipo —</option>
            </select>
        </div>
        <button type="button" class="prd-btn-inline-manager prd-btn-inline-manager--del" title="Quitar fila"
            onclick="this.closest('.prd-combinacion-opcion-row').remove()">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 4H12M5 4V3H9V4M5.5 6.5V10.5M8.5 6.5V10.5M3 4L3.8 12H10.2L11 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </button>`;

    const selTipo  = row.querySelector('[data-rol="tipo"]');
    const selValor = row.querySelector('[data-rol="valor"]');
    poblarSelectVariantes(selTipo, variantePk);
    poblarSelectOpciones(selValor, variantePk || selTipo.value, opcionPk);

    selTipo.addEventListener('change', () => {
        poblarSelectOpciones(selValor, selTipo.value);
    });

    container.appendChild(row);
}

function _obtenerOpcionesFormCombinacion() {
    const rows = document.querySelectorAll('#combinacionOpcionesContainer .prd-combinacion-opcion-row');
    const opciones = [];
    const tiposUsados = new Set();

    for (const row of rows) {
        const tipoPk  = row.querySelector('[data-rol="tipo"]').value;
        const valorPk = row.querySelector('[data-rol="valor"]').value;
        if (!tipoPk && !valorPk) continue;
        if (!tipoPk || !valorPk) {
            return { error: 'Completá tipo y valor en cada fila de la combinación.' };
        }
        if (tiposUsados.has(tipoPk)) {
            return { error: 'No podés repetir el mismo tipo de variante en una combinación.' };
        }
        tiposUsados.add(tipoPk);
        opciones.push(parseInt(valorPk, 10));
    }

    if (!opciones.length) {
        return { error: 'Seleccioná al menos una opción de variante.' };
    }
    return { opciones };
}

// ════════════════════════════════════════════════════════════════════
//  VARIANTES — GUARDAR (CREAR O EDITAR)
// ════════════════════════════════════════════════════════════════════
async function guardarCombinacion() {
    const pk = document.getElementById('f_combinacion_pk').value;
    const productoPk = document.getElementById('prdPk').value;
    if (!productoPk) {
        showToast('Guardá el producto primero antes de agregar combinaciones.', 'error');
        return;
    }

    const opcionesResult = _obtenerOpcionesFormCombinacion();
    if (opcionesResult.error) {
        showToast(opcionesResult.error, 'error');
        return;
    }

    const payload = {
        opciones: opcionesResult.opciones,
        codigo_barras: document.getElementById('f_combinacion_codigo_barras').value.trim(),
        sku_variante: document.getElementById('f_combinacion_sku').value.trim(),
        stock_actual: parseInt(document.getElementById('f_combinacion_stock').value, 10) || 0,
    };

    if (pk) {
        payload.pk = pk;
    } else {
        payload.producto_pk = productoPk;
    }

    const res  = await fetch(URLS.combinacionAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.ok) {
        const desc = data.combinacion?.descripcion_combinacion || data.combinacion?.descripcion || 'Combinación';
        showToast(data.creado ? `Combinación "${desc}" agregada.` : `Combinación "${desc}" actualizada.`);
        cancelarFormCombinacion();
        cargarCombinaciones(productoPk);
    } else {
        const msg = Object.values(data.errors || {}).flat().join(', ') || data.error || 'Error al guardar.';
        showToast(msg, 'error');
    }
}

async function editarCombinacion(pk) {
    const c = _combinacionesCache[pk];
    if (!c) return;

    if (!_cacheVariantes.length) await cargarCatalogoVariantes();

    document.getElementById('f_combinacion_pk').value = pk;
    document.getElementById('f_combinacion_codigo_barras').value = c.codigo_barras || '';
    document.getElementById('f_combinacion_sku').value = c.sku_variante || '';
    document.getElementById('f_combinacion_stock').value = c.stock_actual || 0;

    const desc = c.descripcion_combinacion || c.descripcion || '';
    document.getElementById('combinacionFormTitulo').textContent = `Editar combinación: ${desc}`;
    document.getElementById('btnCombinacionTxt').textContent = 'Guardar cambios';

    resetFormCombinacionOpciones(c.opciones || []);
    document.getElementById('combinacionBulkForm').style.display = 'none';
    document.getElementById('combinacionForm').style.display = '';
    document.getElementById('combinacionForm').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function cancelarFormCombinacion() {
    document.getElementById('f_combinacion_pk').value = '';
    document.getElementById('f_combinacion_codigo_barras').value = '';
    document.getElementById('f_combinacion_sku').value = '';
    document.getElementById('f_combinacion_stock').value = '0';
    document.getElementById('combinacionFormTitulo').textContent = 'Editar combinación';
    document.getElementById('btnCombinacionTxt').textContent = 'Guardar cambios';
    resetFormCombinacionOpciones();
    document.getElementById('combinacionForm').style.display = 'none';
    document.getElementById('combinacionBulkForm').style.display = '';
    _bulkDimensiones = [];
    _bulkExcluidos = new Set();
    _bulkDatosFila = {};
    renderBulkDimensiones();
    renderBulkPreview();
}

async function toggleCombinacion(pk) {
    const res  = await fetch(URLS.combinacionToggle, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Combinación ${data.activo ? 'activada' : 'desactivada'}.`);
        cargarCombinaciones(document.getElementById('prdPk').value);
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

// ════════════════════════════════════════════════════════════════════
//  VARIANTES — AJUSTE DE STOCK
// ════════════════════════════════════════════════════════════════════
function abrirAjusteStock(pk, descripcion, stockActual) {
    const nuevoStock = prompt(
        `Ajustar stock de "${descripcion}"\nStock actual: ${parseFloat(stockActual).toFixed(0)}\n\nIngresá el nuevo stock total:`
    );
    if (nuevoStock === null) return;
    const val = parseFloat(nuevoStock);
    if (isNaN(val)) { showToast('Valor inválido.', 'error'); return; }
    _ejecutarAjusteStock(pk, val);
}

async function _ejecutarAjusteStock(pk, nuevoStock) {
    const res  = await fetch(URLS.combinacionStock, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk, stock_actual: nuevoStock }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Stock actualizado: ${parseFloat(data.stock_posterior).toFixed(0)} unidades.`);
        cargarCombinaciones(document.getElementById('prdPk').value);
    } else {
        showToast(data.error || 'Error al ajustar stock.', 'error');
    }
}



// ════════════════════════════════════════════════════════════════════
//  DOM — AGREGAR / ACTUALIZAR FILAS DE TABLA SIN RECARGAR
// ════════════════════════════════════════════════════════════════════

function _buildRowHtml(d) {
    // Imagen/thumb
    const thumbHtml = d.imagen_url
        ? `<img src="${d.imagen_url}" alt="${d.nombre}" class="prd-thumb">`
        : `<div class="prd-thumb-empty"><svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <rect x="2" y="2" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.2"/>
                <circle cx="6.5" cy="6.5" r="1.5" fill="currentColor" fill-opacity=".4"/>
                <path d="M2 12L5 9L8 11L12 7L16 12" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
           </svg></div>`;

    // Código + SKU
    const codigoHtml = `<span class="prd-codigo">${d.codigo || ''}</span>${d.sku ? `<span class="prd-sku">${d.sku}</span>` : ''}`;

    // Nombre + marca + variantes
    let nombreHtml = `<span class="prd-nombre">${d.nombre}</span>`;
    if (d.marca) nombreHtml += `<span class="prd-marca">${d.marca}${d.modelo ? ' · ' + d.modelo : ''}</span>`;
    if (d.gestiona_variantes) {
        nombreHtml += `<span class="prd-badge prd-badge--variantes">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style="vertical-align:middle">
                <rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/>
                <circle cx="3" cy="3" r="1" fill="currentColor"/>
                <circle cx="7" cy="7" r="1" fill="currentColor"/>
            </svg> Variantes</span>`;
    }

    // Categoría
    const categHtml = d.categoria_nombre
        ? `<span class="prd-badge prd-badge--categ">${d.categoria_nombre}</span>`
        : '<span class="prd-muted">—</span>';

    // Tipo
    const tipoHtml = d.tipo_nombre
        ? `<span class="prd-badge prd-badge--tipo">${d.tipo_nombre}</span>`
        : '<span class="prd-muted">—</span>';

    // Precio
    const precioHtml = d.precio_venta
        ? `<span class="prd-precio">$${parseFloat(d.precio_venta).toFixed(2)}</span>`
        : '<span class="prd-muted">—</span>';

    // Stock
    let stockHtml;
    if (d.gestiona_stock) {
        const stockBajo = d.stock_bajo ? 'prd-stock--bajo' : '';
        const alerta    = d.stock_bajo ? `<span class="prd-stock-alerta" title="Stock mínimo: ${d.stock_minimo}">⚠</span>` : '';
        stockHtml = `<span class="prd-stock ${stockBajo}">${parseFloat(d.stock_actual || 0).toFixed(0)}
            <span class="prd-stock-um">${d.unidad_medida_display || ''}</span></span>${alerta}`;
    } else {
        stockHtml = '<span class="prd-muted">Sin stock</span>';
    }

    // Estado
    const estadoMap = {
        activo:       'prd-estado--activo',
        inactivo:     'prd-estado--inactivo',
        discontinuado:'prd-estado--disc',
        agotado:      'prd-estado--agotado',
    };
    const estadoLabel = { activo:'Activo', inactivo:'Inactivo', discontinuado:'Discontinuado', agotado:'Agotado' };
    const estadoHtml = `<span class="prd-estado ${estadoMap[d.estado] || ''}">${estadoLabel[d.estado] || d.estado}</span>`;

    // Acciones
    const publicadoClass = d.publicado ? 'prd-action-btn--publicado' : '';
    const publicadoTitle = d.publicado ? 'Despublicar del catálogo' : 'Publicar en catálogo';
    const accionesHtml = `
        <button class="prd-action-btn ${publicadoClass}" title="${publicadoTitle}"
                onclick="togglePublicar(${d.pk}, ${d.publicado}, this)">
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                <path d="M7.5 1C4 1 1 3.7 1 7c0 1.5.6 2.9 1.6 4L1 14l3.2-1.5C5.4 13.5 6.4 14 7.5 14c3.5 0 6.5-2.7 6.5-7S11 1 7.5 1z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
                <path d="M5 7.5h5M7.5 5v5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
        </button>
        <button class="prd-action-btn" title="Editar" onclick="abrirEditar(${d.pk})">
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                <path d="M10.5 2.5L12.5 4.5L5 12H3V10L10.5 2.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
            </svg>
        </button>
        <button class="prd-action-btn prd-action-btn--danger" title="Eliminar"
                onclick="confirmarEliminar(${d.pk}, '${(d.nombre || '').replace(/'/g, "\\'")}')">
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                <path d="M3 4H12M5 4V3H10V4M6 7V11M9 7V11M4 4L5 13H10L11 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </button>`;

    return { thumbHtml, codigoHtml, nombreHtml, categHtml, tipoHtml, precioHtml, stockHtml, estadoHtml, accionesHtml };
}

function agregarFilaTabla(d) {
    const tbody = document.getElementById('tablaProductosBody');
    if (!tbody) return;

    // Quitar fila de "no hay productos" si existe
    tbody.querySelector('td[colspan]')?.closest('tr')?.remove();

    const h = _buildRowHtml(d);
    const tr = document.createElement('tr');
    tr.className  = `prd-row${d.stock_bajo ? ' prd-row--stock-bajo' : ''}`;
    tr.dataset.pk = d.pk;
    tr.innerHTML  = `
        <td class="prd-td-img">${h.thumbHtml}</td>
        <td>${h.codigoHtml}</td>
        <td>${h.nombreHtml}</td>
        <td>${h.categHtml}</td>
        <td>${h.tipoHtml}</td>
        <td>${h.precioHtml}</td>
        <td>${h.stockHtml}</td>
        <td>${h.estadoHtml}</td>
        <td class="prd-td-actions">${h.accionesHtml}</td>`;

    // Animación de entrada
    tr.style.opacity   = '0';
    tr.style.transform = 'translateY(4px)';
    tr.style.transition = 'opacity .2s ease, transform .2s ease';
    tbody.prepend(tr);
    requestAnimationFrame(() => { tr.style.opacity = '1'; tr.style.transform = ''; });

    // Actualizar contador de resultados
    const countEl = document.querySelector('.prd-table-count');
    if (countEl) {
        const actual = parseInt(countEl.textContent) || 0;
        countEl.textContent = `${actual + 1} resultado${actual + 1 !== 1 ? 's' : ''}`;
    }
}

function actualizarFilaTabla(d) {
    const tr = document.querySelector(`#tablaProductosBody tr[data-pk="${d.pk}"]`);
    if (!tr) return;

    const h = _buildRowHtml(d);
    tr.className = `prd-row${d.stock_bajo ? ' prd-row--stock-bajo' : ''}`;
    tr.cells[0].innerHTML = `<td class="prd-td-img">${h.thumbHtml}</td>`.replace(/<td[^>]*>|<\/td>/g,'');
    tr.cells[1].innerHTML = h.codigoHtml;
    tr.cells[2].innerHTML = h.nombreHtml;
    tr.cells[3].innerHTML = h.categHtml;
    tr.cells[4].innerHTML = h.tipoHtml;
    tr.cells[5].innerHTML = h.precioHtml;
    tr.cells[6].innerHTML = h.stockHtml;
    tr.cells[7].innerHTML = h.estadoHtml;
    tr.cells[8].innerHTML = h.accionesHtml;

    // Destello visual para indicar que se actualizó
    tr.style.transition = 'background .15s';
    tr.style.background = 'rgba(242,106,27,0.07)';
    setTimeout(() => { tr.style.background = ''; }, 700);
}

// Actualiza los contadores de stats del header (Total, Activos, Publicados)
function actualizarContadoresStats(deltTotal, deltActivo, deltPublicado) {
    const elTotal     = document.getElementById('statTotal');
    const elActivos   = document.getElementById('statActivos');
    const elPublicados= document.getElementById('statPublicados');
    if (elTotal      && deltTotal      !== 0) elTotal.textContent      = (parseInt(elTotal.textContent)      || 0) + deltTotal;
    if (elActivos    && deltActivo     !== 0) elActivos.textContent    = (parseInt(elActivos.textContent)    || 0) + deltActivo;
    if (elPublicados && deltPublicado  !== 0) elPublicados.textContent = (parseInt(elPublicados.textContent) || 0) + deltPublicado;
}
// ════════════════════════════════════════════════════════════════════
//  UX GENERAL
// ════════════════════════════════════════════════════════════════════

// Auto-mayúsculas en código
document.getElementById('f_codigo')?.addEventListener('input', function () {
    const pos = this.selectionStart;
    this.value = this.value.toUpperCase();
    this.setSelectionRange(pos, pos);
});

// EAN-13: solo dígitos (producto y combinaciones)
document.getElementById('f_codigo_barras')?.addEventListener('input', function () {
    this.value = this.value.replace(/[^\d]/g, '').slice(0, 13);
});
document.getElementById('f_combinacion_codigo_barras')?.addEventListener('input', function () {
    this.value = this.value.replace(/[^\d]/g, '').slice(0, 13);
});

// Contador nombre corto
const nombreCorto = document.getElementById('f_nombre_corto');
if (nombreCorto) {
    const counter = document.createElement('span');
    counter.style.cssText = 'font-size:.7rem;color:var(--text-muted);text-align:right;display:block;margin-top:.2rem;';
    nombreCorto.parentElement.appendChild(counter);
    const update = () => {
        const len = nombreCorto.value.length;
        counter.textContent = `${len}/80`;
        counter.style.color = len > 70 ? 'var(--warning)' : 'var(--text-muted)';
        if (len >= 80) counter.style.color = 'var(--danger)';
    };
    nombreCorto.addEventListener('input', update);
    update();
}

// Tags: chips preview
const tagsInput = document.getElementById('f_tags');
if (tagsInput) {
    const preview = document.createElement('div');
    preview.style.cssText = 'display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.4rem;min-height:24px;';
    tagsInput.parentElement.appendChild(preview);
    const renderTags = () => {
        const tags = tagsInput.value.split(',').map(t => t.trim()).filter(Boolean);
        preview.innerHTML = tags.map(t =>
            `<span style="display:inline-block;padding:.15rem .5rem;background:var(--accent-light);color:var(--accent-primary);border-radius:.375rem;font-size:.7rem;font-weight:500;">${t.replace(/</g,'&lt;')}</span>`
        ).join('');
    };
    tagsInput.addEventListener('input', renderTags);
    renderTags();
}

// Animación de filas al cargar
document.querySelectorAll('.prd-row').forEach((row, i) => {
    row.style.opacity    = '0';
    row.style.transform  = 'translateY(4px)';
    row.style.transition = 'opacity .2s ease, transform .2s ease';
    setTimeout(() => { row.style.opacity = '1'; row.style.transform = ''; }, 40 + i * 18);
});

// Búsqueda con Enter
document.querySelector('.prd-search-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('filtrosForm').submit();
});

// ════════════════════════════════════════════════════════════════════
//  LISTAS DE DESCUENTO
// ════════════════════════════════════════════════════════════════════
let _cacheListasDescuento = [];

document.getElementById('btnListasDescuento')?.addEventListener('click', () => {
    _resetFormListaDescuento();
    abrirModal('modalListasDescuento');
    cargarListasDescuento();
});

async function cargarListasDescuento() {
    const res  = await fetch(URLS.listaDescuentoLista);
    const data = await res.json();
    _cacheListasDescuento = data.results || [];
    _renderListasDescuento();
}

function _renderListasDescuento() {
    const cont = document.getElementById('listaDescuentoLista');
    const empty = document.getElementById('ldEmptyMsg');
    if (!cont) return;

    if (!_cacheListasDescuento.length) {
        cont.innerHTML = '';
        empty.style.display = '';
        return;
    }
    empty.style.display = 'none';

    cont.innerHTML = _cacheListasDescuento.map(l => `
        <div class="prd-ld-row ${l.activa ? '' : 'prd-ld-row--inactiva'}">
            <div class="prd-ld-row-pct">${l.porcentaje}%</div>
            <div class="prd-ld-row-info">
                <span class="prd-ld-row-nombre">${l.nombre}</span>
                <span class="prd-badge ${l.activa ? 'prd-badge--tipo' : ''}">${l.activa ? 'Activa' : 'Inactiva'}</span>
            </div>
            <div class="prd-ld-row-actions">
                <button type="button" class="prd-ld-icon-btn" title="Editar" onclick="_editarListaDescuento(${l.pk})">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M10.5 2L13 4.5L5 12.5H2.5V10L10.5 2Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <button type="button" class="prd-ld-icon-btn" title="${l.activa ? 'Desactivar' : 'Activar'}" onclick="_toggleActivaListaDescuento(${l.pk})">
                    ${l.activa
                        ? `<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M4.5 4.5L10.5 10.5M10.5 4.5L4.5 10.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`
                        : `<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M4 2.5L11.5 7.5L4 12.5V2.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`}
                </button>
                <button type="button" class="prd-ld-icon-btn prd-ld-icon-btn--danger" title="Eliminar" onclick="_eliminarListaDescuento(${l.pk}, '${l.nombre.replace(/'/g, "\\'")}')">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M2.5 4H12.5M5.5 4V3H9.5V4M6 6.5V10.5M9 6.5V10.5M3.5 4L4.3 12H10.7L11.5 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');
}

function _resetFormListaDescuento() {
    document.getElementById('ldPk').value = '';
    document.getElementById('ldNombre').value = '';
    document.getElementById('ldPorcentaje').value = '';
    document.getElementById('btnGuardarListaTxt').textContent = 'Agregar';
    document.getElementById('ldFormError').style.display = 'none';
}

function _editarListaDescuento(pk) {
    const l = _cacheListasDescuento.find(x => x.pk === pk);
    if (!l) return;
    document.getElementById('ldPk').value = l.pk;
    document.getElementById('ldNombre').value = l.nombre;
    document.getElementById('ldPorcentaje').value = l.porcentaje;
    document.getElementById('btnGuardarListaTxt').textContent = 'Guardar cambios';
    document.getElementById('ldFormError').style.display = 'none';
    document.getElementById('ldNombre').focus();
}

async function guardarListaDescuento() {
    const pk         = document.getElementById('ldPk').value;
    const nombre     = document.getElementById('ldNombre').value.trim();
    const porcentaje = document.getElementById('ldPorcentaje').value;
    const errBox     = document.getElementById('ldFormError');
    errBox.style.display = 'none';

    if (!nombre || porcentaje === '') {
        errBox.textContent   = 'Completá el nombre y el porcentaje.';
        errBox.style.display = '';
        return;
    }

    const body = { nombre, porcentaje };
    if (pk) body.pk = pk;

    const res  = await fetch(URLS.listaDescuentoAcciones, {
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

    showToast(`Lista "${data.nombre}" ${data.creado ? 'creada' : 'actualizada'}.`);
    _resetFormListaDescuento();
    await cargarListasDescuento();
}

async function _toggleActivaListaDescuento(pk) {
    const l = _cacheListasDescuento.find(x => x.pk === pk);
    if (!l) return;
    const res  = await fetch(URLS.listaDescuentoAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk: l.pk, nombre: l.nombre, porcentaje: l.porcentaje, activa: !l.activa }),
    });
    const data = await res.json();
    if (data.ok) {
        await cargarListasDescuento();
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

async function _eliminarListaDescuento(pk, nombre) {
    if (!confirm(`¿Eliminar la lista "${nombre}"? Esta acción no se puede deshacer.`)) return;
    const res  = await fetch(URLS.listaDescuentoEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Lista "${data.nombre}" eliminada.`);
        _resetFormListaDescuento();
        await cargarListasDescuento();
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

// ESC cierra modales
document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.prd-modal-overlay--open').forEach(overlay => cerrarModal(overlay.id));
});