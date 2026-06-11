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
//  NUEVO PRODUCTO
// ════════════════════════════════════════════════════════════════════
document.getElementById('btnNuevoProducto').addEventListener('click', () => {
    limpiarFormProducto();
    document.getElementById('modalProductoTitulo').textContent = 'Nuevo producto';
    document.getElementById('prdPk').value = '';
    document.querySelector('.prd-tab[data-tab="identificacion"]').click();
    document.getElementById('imgNuevoAviso').style.display = '';
    document.getElementById('imgPanel').style.display = 'none';
    _actualizarPanelColores(false);
    abrirModal('modalProducto');
});

function limpiarFormProducto() {
    [
        'f_codigo','f_sku','f_codigo_barras','f_nombre','f_nombre_corto',
        'f_marca','f_modelo','f_fabricante','f_pais_origen',
        'f_contenido_neto','f_descripcion','f_descripcion_publica',
        'f_precio_venta',
        'f_notas','f_tags',
        'f_peso_kg','f_alto_cm','f_ancho_cm','f_profundidad_cm',
        'f_color_unico', 'f_stock_minimo', 'f_posicion_deposito',
    ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });

    document.getElementById('f_unidad_medida').value    = 'unidad';
    document.getElementById('f_estado').value           = 'activo';
    document.getElementById('f_categoria').value        = '';
    document.getElementById('f_tipo').value             = '';

    ['f_destacado','f_requiere_refrigeracion','f_es_fragil',
     'f_es_peligroso','f_tiene_variantes_color',
     'f_gestiona_stock','f_permite_stock_negativo'].forEach(id => {
        document.getElementById(id).checked = false;
    });

    document.getElementById('f_precio_incluye_iva') && (document.getElementById('f_precio_incluye_iva').checked = true); // compatibilidad
    document.getElementById('f_gestiona_stock').checked       = true;  // default: siempre gestiona stock
    document.getElementById('prdFormError').style.display   = 'none';
    document.getElementById('categManager').style.display   = 'none';
    document.getElementById('tipoManager').style.display    = 'none';
    document.getElementById('colorWarningMovimientos').style.display = 'none';
    // Limpiar lista de colores para que no queden los del producto anterior
    const colorLista = document.getElementById('colorLista');
    if (colorLista) colorLista.innerHTML = '<div class="prd-manager-loading">Cargando colores...</div>';
    document.getElementById('colorStockTotal').textContent = '0';
    const badge = document.getElementById('tabColorCount');
    badge.textContent = '0'; badge.style.display = 'none';
    cancelarFormColor();
    _actualizarPanelColores(false);
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
    document.getElementById('f_notas').value                   = data.notas || '';
    document.getElementById('f_peso_kg').value                 = data.peso_kg || '';
    document.getElementById('f_alto_cm').value                 = data.alto_cm || '';
    document.getElementById('f_ancho_cm').value                = data.ancho_cm || '';
    document.getElementById('f_profundidad_cm').value          = data.profundidad_cm || '';
    document.getElementById('f_color_unico').value             = data.color_unico || '';
    document.getElementById('f_stock_minimo').value            = data.stock_minimo || '0';
    document.getElementById('f_posicion_deposito').value       = data.posicion_deposito || '';
    document.getElementById('f_destacado').checked             = data.destacado;
    document.getElementById('f_requiere_refrigeracion').checked = data.requiere_refrigeracion;
    document.getElementById('f_es_fragil').checked             = data.es_fragil;
    document.getElementById('f_es_peligroso').checked          = data.es_peligroso;
    document.getElementById('f_tiene_variantes_color').checked  = data.tiene_variantes_color;
    document.getElementById('f_gestiona_stock').checked          = data.gestiona_stock;
    document.getElementById('f_permite_stock_negativo').checked  = data.permite_stock_negativo;

    if (data.tiene_movimientos) {
        document.getElementById('colorWarningMovimientos').style.display = '';
    }

    _actualizarPanelColores(data.tiene_variantes_color);
    if (data.tiene_variantes_color) {
        document.getElementById('colorNuevoAviso').style.display = 'none';
        cargarColores(data.pk);
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

    const tieneVariantes = document.getElementById('f_tiene_variantes_color').checked;

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
        estado:                 document.getElementById('f_estado').value,
        destacado:              document.getElementById('f_destacado').checked,
        requiere_refrigeracion: document.getElementById('f_requiere_refrigeracion').checked,
        es_fragil:              document.getElementById('f_es_fragil').checked,
        es_peligroso:           document.getElementById('f_es_peligroso').checked,
        notas:                  document.getElementById('f_notas').value,
        tags:                   document.getElementById('f_tags').value,
        tiene_variantes_color:  tieneVariantes,
        color_unico:            tieneVariantes ? '' : document.getElementById('f_color_unico').value,
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

                // Habilitar colores si corresponde
                if (tieneVariantes) {
                    document.getElementById('colorNuevoAviso').style.display = 'none';
                    cargarColores(data.pk);
                }

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
            tiene_variantes_color: data.tiene_variantes_color,
            color_unico:          data.color_unico || '',
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
    // Cerrar ambos primero
    document.getElementById('categManager').style.display = 'none';
    document.getElementById('tipoManager').style.display  = 'none';
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
//  COLORES — PANEL Y TOGGLE
// ════════════════════════════════════════════════════════════════════
function _actualizarPanelColores(tieneVariantes) {
    document.getElementById('panelSinVariantes').style.display = tieneVariantes ? 'none' : '';
    document.getElementById('panelConVariantes').style.display = tieneVariantes ? '' : 'none';
    document.getElementById('campoColorUnico').style.display   = tieneVariantes ? 'none' : '';
    const badge = document.getElementById('tabColorCount');
    if (!tieneVariantes) { badge.style.display = 'none'; badge.textContent = '0'; }
}

document.getElementById('f_tiene_variantes_color').addEventListener('change', function () {
    _actualizarPanelColores(this.checked);
    const pk = document.getElementById('prdPk').value;
    if (this.checked) {
        if (pk) {
            document.getElementById('colorNuevoAviso').style.display = 'none';
            cargarColores(pk);
        } else {
            document.getElementById('colorNuevoAviso').style.display = '';
        }
    }
});

// Sincronizar color picker ↔ input hex
document.getElementById('f_color_hex_picker').addEventListener('input', function () {
    document.getElementById('f_color_hex').value = this.value.toUpperCase();
});
document.getElementById('f_color_hex').addEventListener('input', function () {
    if (/^#[0-9A-Fa-f]{6}$/.test(this.value.trim())) {
        document.getElementById('f_color_hex_picker').value = this.value.trim();
    }
});

// ════════════════════════════════════════════════════════════════════
//  COLORES — CARGA Y RENDER DE LISTA
// ════════════════════════════════════════════════════════════════════
async function cargarColores(productoPk) {
    const lista = document.getElementById('colorLista');
    lista.innerHTML = '<div class="prd-manager-loading">Cargando colores...</div>';

    const res  = await fetch(`${URLS.colorLista}?producto_pk=${productoPk}`);
    const data = await res.json();

    document.getElementById('colorStockTotal').textContent = parseFloat(data.stock_total || 0).toFixed(0);

    const activos = (data.colores || []).filter(c => c.activo).length;
    const badge   = document.getElementById('tabColorCount');
    badge.textContent   = activos;
    badge.style.display = activos > 0 ? '' : 'none';

    if (!data.colores || !data.colores.length) {
        lista.innerHTML = '<div class="prd-manager-empty">Sin colores definidos. Agregá el primero abajo.</div>';
        return;
    }
    lista.innerHTML = data.colores.map(_renderColorItem).join('');
}

function _renderColorItem(c) {
    const pastilla = c.codigo_hex
        ? `<span class="prd-color-pastilla" style="background:${c.codigo_hex}" title="${c.codigo_hex}"></span>`
        : `<span class="prd-color-pastilla prd-color-pastilla--vacia"></span>`;
    const inactivoClass  = !c.activo ? 'prd-color-item--inactivo' : '';
    return `
    <div class="prd-color-item ${inactivoClass}" id="color-${c.pk}">
        <div class="prd-color-item-info">
            ${pastilla}
            <div class="prd-color-item-datos">
                <span class="prd-color-item-nombre">${c.nombre}</span>
                ${c.sku_variante ? `<span class="prd-color-item-sku">${c.sku_variante}</span>` : ''}
                ${!c.activo ? '<span class="prd-color-item-inactivo-badge">Inactivo</span>' : ''}
            </div>
        </div>
        <div class="prd-color-item-stock">
            <span class="prd-color-stock-num">${c.stock_actual}</span>
        </div>
        <div class="prd-color-item-actions">
            <button class="prd-img-btn" title="Editar color"
                onclick="editarColor(${c.pk}, '${c.nombre.replace(/'/g,"\\'")}', '${c.codigo_hex}', '${c.sku_variante}')">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                    <path d="M9 2L11 4L4.5 10.5H2.5V8.5L9 2Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
                </svg>
            </button>
            <button class="prd-img-btn ${!c.activo ? 'prd-img-btn--activar' : ''}" title="${c.activo ? 'Desactivar' : 'Activar'}"
                onclick="toggleColor(${c.pk})">
                ${c.activo
                    ? `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 2L11 11M11 2L2 11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`
                    : `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 7L5 10L11 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`
                }
            </button>
        </div>
    </div>`;
}

// ════════════════════════════════════════════════════════════════════
//  COLORES — GUARDAR (CREAR O EDITAR)
//
//  FIX: se eliminó la validación "tiene_variantes_color" del backend.
//  El frontend controla el flujo — si el panel está visible y el usuario
//  guarda un color, el producto YA tiene tiene_variantes_color=true en la BD
//  (fue guardado antes). El backend solo verifica que el producto exista.
// ════════════════════════════════════════════════════════════════════
async function guardarColor() {
    const pk     = document.getElementById('f_color_pk').value;
    const nombre = document.getElementById('f_color_nombre').value.trim();
    if (!nombre) { showToast('El nombre del color es obligatorio.', 'error'); return; }

    const hex = document.getElementById('f_color_hex').value.trim();
    if (hex && !/^#[0-9A-Fa-f]{6}$/.test(hex)) {
        showToast('El color hex debe tener formato #RRGGBB.', 'error'); return;
    }

    const productoPk = document.getElementById('prdPk').value;
    if (!productoPk) {
        showToast('Guardá el producto primero antes de agregar colores.', 'error'); return;
    }

    const payload = {
        nombre,
        codigo_hex:   hex,
        sku_variante: document.getElementById('f_color_sku').value.trim(),
    };

    if (pk) {
        payload.pk = pk;
    } else {
        payload.producto_pk = productoPk;
    }

    const res  = await fetch(URLS.colorAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.ok) {
        showToast(data.creado ? `Color "${nombre}" agregado.` : `Color "${nombre}" actualizado.`);
        cancelarFormColor();
        cargarColores(productoPk);
    } else {
        const msg = Object.values(data.errors || {}).flat().join(', ') || data.error || 'Error al guardar.';
        showToast(msg, 'error');
    }
}

function editarColor(pk, nombre, hex, sku) {
    document.getElementById('f_color_pk').value          = pk;
    document.getElementById('f_color_nombre').value      = nombre;
    document.getElementById('f_color_hex').value         = hex || '';
    document.getElementById('f_color_hex_picker').value  = hex || '#000000';
    document.getElementById('f_color_sku').value         = sku || '';
    document.getElementById('colorFormTitulo').textContent = `Editar color: ${nombre}`;
    document.getElementById('btnColorTxt').textContent     = 'Guardar cambios';
    document.getElementById('btnCancelarColor').style.display = '';
    document.getElementById('colorForm').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function cancelarFormColor() {
    document.getElementById('f_color_pk').value          = '';
    document.getElementById('f_color_nombre').value      = '';
    document.getElementById('f_color_hex').value         = '';
    document.getElementById('f_color_hex_picker').value  = '#000000';
    document.getElementById('f_color_sku').value         = '';
    document.getElementById('colorFormTitulo').textContent = 'Agregar color';
    document.getElementById('btnColorTxt').textContent     = 'Agregar color';
    document.getElementById('btnCancelarColor').style.display = 'none';
}

async function toggleColor(pk) {
    const res  = await fetch(URLS.colorToggle, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Color ${data.activo ? 'activado' : 'desactivado'}.`);
        cargarColores(document.getElementById('prdPk').value);
    } else {
        showToast(data.error || 'Error', 'error');
    }
}

// ════════════════════════════════════════════════════════════════════
//  COLORES — AJUSTE DE STOCK
// ════════════════════════════════════════════════════════════════════
function abrirAjusteStock(pk, nombre, stockActual) {
    const nuevoStock = prompt(
        `Ajustar stock de "${nombre}"\nStock actual: ${parseFloat(stockActual).toFixed(0)}\n\nIngresá el nuevo stock total:`
    );
    if (nuevoStock === null) return;
    const val = parseFloat(nuevoStock);
    if (isNaN(val)) { showToast('Valor inválido.', 'error'); return; }
    _ejecutarAjusteStock(pk, val);
}

async function _ejecutarAjusteStock(pk, nuevoStock) {
    const res  = await fetch(URLS.colorStock, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk, stock_actual: nuevoStock }),
    });
    const data = await res.json();
    if (data.ok) {
        showToast(`Stock actualizado: ${parseFloat(data.stock_posterior).toFixed(0)} unidades.`);
        cargarColores(document.getElementById('prdPk').value);
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
    if (d.tiene_variantes_color) {
        nombreHtml += `<span class="prd-badge prd-badge--color">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style="vertical-align:middle">
                <circle cx="5" cy="5" r="4" stroke="currentColor" stroke-width="1.2"/>
                <circle cx="5" cy="5" r="2" fill="currentColor"/>
            </svg> Colores</span>`;
    } else if (d.color_unico) {
        nombreHtml += `<span class="prd-color-unico-badge">${d.color_unico}</span>`;
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

// EAN-13: solo dígitos
document.getElementById('f_codigo_barras')?.addEventListener('input', function () {
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

// ESC cierra modales
document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.prd-modal-overlay--open').forEach(overlay => cerrarModal(overlay.id));
});