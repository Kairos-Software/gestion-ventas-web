/**
 * historial_docs.js
 * Gestión de documentos adjuntos en el historial de ventas.
 *
 * Los documentos solo se pueden adjuntar / eliminar mientras
 * la fila está en modo edición (panel abierto).
 *
 * Depende de: historial_utils.js (iconDoc, _esc, mostrarToastExito/Error)
 * Usa:        HISTORIAL_URLS.documentoSubir / documentoEliminar
 *             CSRF_TOKEN
 */
'use strict';

/* ════════════════════════════════════════════════════════════════
   HTML — vista de solo lectura (sin controles de edición)
════════════════════════════════════════════════════════════════ */
function buildDocumentosReadOnly(venta) {
    const docs = venta.documentos || [];

    const listaHTML = docs.length
        ? docs.map(doc => `
            <div class="doc-item">
                <a href="${_esc(doc.url)}" target="_blank" rel="noopener" class="doc-link">
                    <span class="doc-icono">${_iconDoc(doc)}</span>
                    <span class="doc-nombre">${_esc(doc.nombre)}</span>
                    <span class="doc-tipo-badge">${_esc(doc.tipo_label)}</span>
                    ${doc.descripcion ? `<span class="doc-descripcion">${_esc(doc.descripcion)}</span>` : ''}
                </a>
                <span class="doc-fecha">${_esc(doc.subido_el)}</span>
            </div>`).join('')
        : `<p class="doc-vacio">Sin documentos adjuntos.</p>`;

    return `
    <div class="docs-seccion docs-seccion--readonly">
        <div class="docs-header">
            ${iconDoc()}
            <span>Documentos adjuntos</span>
            <span class="docs-count-badge">${docs.length}</span>
        </div>
        <div class="docs-lista">${listaHTML}</div>
    </div>`;
}

/* ════════════════════════════════════════════════════════════════
   HTML — modo edición (con botones eliminar + subir)
════════════════════════════════════════════════════════════════ */
function buildDocumentosEditor(venta) {
    const docs = venta.documentos || [];
    const pk   = venta.pk;

    const listaHTML = docs.length
        ? docs.map(doc => _buildDocItem(doc, pk)).join('')
        : `<p class="doc-vacio">Sin documentos adjuntos.</p>`;

    return `
    <div class="docs-seccion docs-seccion--edit" data-venta-pk="${pk}">
        <div class="docs-header">
            ${iconDoc()}
            <span>Documentos adjuntos</span>
            <span class="docs-count-badge" id="docsCount_${pk}">${docs.length}</span>
        </div>
        <div class="docs-lista" id="docsLista_${pk}">${listaHTML}</div>
        <div class="doc-subir-wrap">
            <label class="doc-subir-label">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M8 2V11M4 5.5L8 2L12 5.5" stroke="currentColor" stroke-width="1.5"
                          stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M2 14H14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                Adjuntar archivo
                <input type="file" class="doc-file-input" id="docFile_${pk}"
                       accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" style="display:none;">
            </label>
            <select class="doc-tipo-select" id="docTipo_${pk}">
                <option value="factura">Factura</option>
                <option value="remito">Remito</option>
                <option value="recibo">Recibo</option>
                <option value="otro">Otro</option>
            </select>
            <input type="text" class="doc-desc-input" id="docDesc_${pk}"
                   placeholder="Descripción (opcional)" maxlength="200">
            <span class="doc-upload-status" id="docStatus_${pk}" style="display:none;">Subiendo…</span>
        </div>
    </div>`;
}

function _buildDocItem(doc, ventaPk) {
    return `
    <div class="doc-item" id="docItem_${doc.pk}">
        <a href="${_esc(doc.url)}" target="_blank" rel="noopener" class="doc-link">
            <span class="doc-icono">${_iconDoc(doc)}</span>
            <span class="doc-nombre">${_esc(doc.nombre)}</span>
            <span class="doc-tipo-badge">${_esc(doc.tipo_label)}</span>
            ${doc.descripcion ? `<span class="doc-descripcion">${_esc(doc.descripcion)}</span>` : ''}
        </a>
        <span class="doc-fecha">${_esc(doc.subido_el)}</span>
        <button class="doc-btn-eliminar"
                data-doc-pk="${doc.pk}"
                data-venta-pk="${ventaPk}"
                title="Eliminar documento">
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
        </button>
    </div>`;
}

function _iconDoc(doc) {
    if (doc.es_imagen) return `<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <rect x="1.5" y="3" width="13" height="10" rx="2" stroke="currentColor" stroke-width="1.4"/>
        <circle cx="5.5" cy="6.5" r="1.5" stroke="currentColor" stroke-width="1.2"/>
        <path d="M1.5 11L5 7.5L8 10.5L10.5 8L14.5 13" stroke="currentColor" stroke-width="1.3"
              stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    if (doc.es_pdf)  return `<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M3 2H9.5L13 5.5V14H3V2Z" stroke="currentColor" stroke-width="1.4"
              stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M9.5 2V5.5H13" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
        <path d="M5.5 8.5H8C8.83 8.5 9.5 9.17 9.5 10C9.5 10.83 8.83 11.5 8 11.5H5.5V8.5Z"
              stroke="currentColor" stroke-width="1.2"/></svg>`;
    return iconDoc();
}

/* ════════════════════════════════════════════════════════════════
   BIND eventos en la sección de documentos del editor
════════════════════════════════════════════════════════════════ */
function bindDocumentosEditorEvents(editorEl, ventaPk) {
    // — Eliminar —
    editorEl.querySelectorAll('.doc-btn-eliminar').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            _doEliminarDoc(btn.dataset.docPk, ventaPk);
        });
    });

    // — Subir —
    const fileInput = document.getElementById(`docFile_${ventaPk}`);
    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files[0]) {
                _doSubirDoc(fileInput.files[0], ventaPk);
                fileInput.value = '';
            }
        });
    }
}

/* ════════════════════════════════════════════════════════════════
   ACCIONES
════════════════════════════════════════════════════════════════ */
function _doEliminarDoc(docPk, ventaPk) {
    fetch(HISTORIAL_URLS.documentoEliminar, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
        body:    JSON.stringify({ pk: docPk }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            document.getElementById(`docItem_${docPk}`)?.remove();
            _actualizarContadorDocs(ventaPk, -1);
            const lista = document.getElementById(`docsLista_${ventaPk}`);
            if (lista && !lista.querySelector('.doc-item')) {
                lista.innerHTML = '<p class="doc-vacio">Sin documentos adjuntos.</p>';
            }
            mostrarToastExito('Documento eliminado.');
        } else {
            mostrarToastError(data.error || 'No se pudo eliminar el documento.');
        }
    })
    .catch(() => mostrarToastError('Error de red. Intentá de nuevo.'));
}

function _doSubirDoc(file, ventaPk) {
    const tipoEl   = document.getElementById(`docTipo_${ventaPk}`);
    const descEl   = document.getElementById(`docDesc_${ventaPk}`);
    const statusEl = document.getElementById(`docStatus_${ventaPk}`);
    const labelEl  = document.querySelector(`#docFile_${ventaPk}`)?.closest('.doc-subir-label');

    if (statusEl) statusEl.style.display = 'inline';
    if (labelEl)  labelEl.style.pointerEvents = 'none';

    const formData = new FormData();
    formData.append('venta_pk',   ventaPk);
    formData.append('archivo',     file);
    formData.append('tipo',        tipoEl ? tipoEl.value : 'otro');
    formData.append('descripcion', descEl ? descEl.value.trim() : '');

    fetch(HISTORIAL_URLS.documentoSubir, {
        method:  'POST',
        headers: { 'X-CSRFToken': CSRF_TOKEN },
        body:    formData,
    })
    .then(r => r.json())
    .then(data => {
        if (statusEl) statusEl.style.display = 'none';
        if (labelEl)  labelEl.style.pointerEvents = '';
        if (descEl)   descEl.value = '';

        if (data.ok && data.documento) {
            const doc  = data.documento;
            const lista = document.getElementById(`docsLista_${ventaPk}`);
            if (lista) {
                // Quitar mensaje "Sin documentos" si existe
                lista.querySelector('.doc-vacio')?.remove();
                lista.insertAdjacentHTML('beforeend', _buildDocItem(doc, ventaPk));
                // Re-bind el botón nuevo
                const newBtn = document.getElementById(`docItem_${doc.pk}`)?.querySelector('.doc-btn-eliminar');
                if (newBtn) {
                    newBtn.addEventListener('click', e => {
                        e.stopPropagation();
                        _doEliminarDoc(newBtn.dataset.docPk, ventaPk);
                    });
                }
            }
            _actualizarContadorDocs(ventaPk, +1);
            mostrarToastExito('Documento adjuntado correctamente.');
        } else {
            mostrarToastError(data.error || 'No se pudo subir el archivo.');
        }
    })
    .catch(() => {
        if (statusEl) statusEl.style.display = 'none';
        if (labelEl)  labelEl.style.pointerEvents = '';
        mostrarToastError('Error de red. Intentá de nuevo.');
    });
}

function _actualizarContadorDocs(ventaPk, delta) {
    const badge = document.getElementById(`docsCount_${ventaPk}`);
    if (badge) badge.textContent = Math.max(0, parseInt(badge.textContent || '0') + delta);
}
