/**
 * deudas_documentos.js
 * ─────────────────────────────────────────────────────────────────
 * Documentos adjuntos (factura del proveedor, contrato, etc.) de una
 * Deuda, dentro del modal de detalle. Mismo patrón que
 * compras/static/compras/js/historial_docs.js, adaptado a deuda_pk
 * y a las URLs de caja:deuda_documento_subir/eliminar.
 *
 * Expone: renderizarDocumentosDeuda(deuda) — llamada desde deudas.js
 * cada vez que se abre/actualiza el modal de detalle.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _ddEsc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function _ddGetCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

function _ddIconDoc(doc) {
    if (doc.es_imagen) return `<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <rect x="1.5" y="3" width="13" height="10" rx="2" stroke="currentColor" stroke-width="1.4"/>
        <circle cx="5.5" cy="6.5" r="1.5" stroke="currentColor" stroke-width="1.2"/>
        <path d="M1.5 11L5 7.5L8 10.5L10.5 8L14.5 13" stroke="currentColor" stroke-width="1.3"
              stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    if (doc.es_pdf) return `<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M3 2H9.5L13 5.5V14H3V2Z" stroke="currentColor" stroke-width="1.4"
              stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M9.5 2V5.5H13" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
        <path d="M5.5 8.5H8C8.83 8.5 9.5 9.17 9.5 10C9.5 10.83 8.83 11.5 8 11.5H5.5V8.5Z"
              stroke="currentColor" stroke-width="1.2"/></svg>`;
    return `<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M3 2H9.5L13 5.5V14H3V2Z" stroke="currentColor" stroke-width="1.4"
              stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M9.5 2V5.5H13" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`;
}

function _ddBuildDocItem(doc, deudaPk) {
    return `
    <div class="doc-item" id="ddDocItem_${doc.pk}">
        <a href="${_ddEsc(doc.url)}" target="_blank" rel="noopener" class="doc-link">
            <span class="doc-icono">${_ddIconDoc(doc)}</span>
            <span class="doc-nombre">${_ddEsc(doc.nombre)}</span>
            <span class="doc-tipo-badge">${_ddEsc(doc.tipo_label)}</span>
            ${doc.descripcion ? `<span class="doc-descripcion">${_ddEsc(doc.descripcion)}</span>` : ''}
        </a>
        <span class="doc-fecha">${_ddEsc(doc.subido_el)}</span>
        ${window.deudasPuedeEditar ? `
        <button class="doc-btn-eliminar" data-doc-pk="${doc.pk}" title="Eliminar documento">
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
        </button>` : ''}
    </div>`;
}

function renderizarDocumentosDeuda(deuda) {
    const contenedor = document.getElementById('deudasDocumentos');
    if (!contenedor) return;

    const docs = deuda.documentos || [];
    const pk = deuda.pk;

    const listaHTML = docs.length
        ? docs.map(doc => _ddBuildDocItem(doc, pk)).join('')
        : `<p class="doc-vacio">Sin documentos adjuntos.</p>`;

    const uploaderHTML = window.deudasPuedeEditar ? `
        <div class="doc-subir-wrap">
            <label class="doc-subir-label">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M8 2V11M4 5.5L8 2L12 5.5" stroke="currentColor" stroke-width="1.5"
                          stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M2 14H14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                Adjuntar archivo
                <input type="file" class="doc-file-input" id="ddFile_${pk}"
                       accept="image/*,.pdf" style="display:none;">
            </label>
            <select class="doc-tipo-select" id="ddTipo_${pk}">
                <option value="factura">Factura</option>
                <option value="contrato">Contrato</option>
                <option value="recibo">Recibo</option>
                <option value="otro">Otro</option>
            </select>
            <input type="text" class="doc-desc-input" id="ddDesc_${pk}"
                   placeholder="Descripción (opcional)" maxlength="200">
            <span class="doc-upload-status" id="ddStatus_${pk}" style="display:none;">Subiendo…</span>
        </div>` : '';

    contenedor.innerHTML = `
        <div class="docs-lista" id="ddLista_${pk}">${listaHTML}</div>
        ${uploaderHTML}
    `;

    contenedor.querySelectorAll('.doc-btn-eliminar').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            _ddEliminar(btn.dataset.docPk, pk);
        });
    });

    const fileInput = document.getElementById(`ddFile_${pk}`);
    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files[0]) {
                _ddSubir(fileInput.files[0], pk);
                fileInput.value = '';
            }
        });
    }
}

function _ddSubir(file, deudaPk) {
    const tipoEl = document.getElementById(`ddTipo_${deudaPk}`);
    const descEl = document.getElementById(`ddDesc_${deudaPk}`);
    const statusEl = document.getElementById(`ddStatus_${deudaPk}`);
    const labelEl = document.querySelector(`#ddFile_${deudaPk}`)?.closest('.doc-subir-label');

    if (statusEl) statusEl.style.display = 'inline';
    if (labelEl) labelEl.style.pointerEvents = 'none';

    const formData = new FormData();
    formData.append('deuda_pk', deudaPk);
    formData.append('archivo', file);
    formData.append('tipo', tipoEl ? tipoEl.value : 'otro');
    formData.append('descripcion', descEl ? descEl.value.trim() : '');

    fetch(window.deudasUrls.documentoSubir, {
        method: 'POST',
        headers: { 'X-CSRFToken': _ddGetCookie('csrftoken') },
        body: formData,
    })
        .then(r => r.json())
        .then(data => {
            if (statusEl) statusEl.style.display = 'none';
            if (labelEl) labelEl.style.pointerEvents = '';
            if (descEl) descEl.value = '';

            if (data.ok && data.documento) {
                const lista = document.getElementById(`ddLista_${deudaPk}`);
                if (lista) {
                    lista.querySelector('.doc-vacio')?.remove();
                    lista.insertAdjacentHTML('beforeend', _ddBuildDocItem(data.documento, deudaPk));
                    const nuevoBtn = document.getElementById(`ddDocItem_${data.documento.pk}`)?.querySelector('.doc-btn-eliminar');
                    if (nuevoBtn) {
                        nuevoBtn.addEventListener('click', e => {
                            e.stopPropagation();
                            _ddEliminar(nuevoBtn.dataset.docPk, deudaPk);
                        });
                    }
                }
                KaiToast.show('Documento adjuntado correctamente.', 'success');
            } else {
                KaiToast.show(data.error || 'No se pudo subir el archivo.', 'danger');
            }
        })
        .catch(() => {
            if (statusEl) statusEl.style.display = 'none';
            if (labelEl) labelEl.style.pointerEvents = '';
            KaiToast.show('Error de red. Intentá de nuevo.', 'danger');
        });
}

function _ddEliminar(docPk, deudaPk) {
    fetch(window.deudasUrls.documentoEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _ddGetCookie('csrftoken') },
        body: JSON.stringify({ pk: docPk }),
    })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById(`ddDocItem_${docPk}`)?.remove();
                const lista = document.getElementById(`ddLista_${deudaPk}`);
                if (lista && !lista.querySelector('.doc-item')) {
                    lista.innerHTML = '<p class="doc-vacio">Sin documentos adjuntos.</p>';
                }
                KaiToast.show('Documento eliminado.', 'success');
            } else {
                KaiToast.show(data.error || 'No se pudo eliminar el documento.', 'danger');
            }
        })
        .catch(() => KaiToast.show('Error de red. Intentá de nuevo.', 'danger'));
}
