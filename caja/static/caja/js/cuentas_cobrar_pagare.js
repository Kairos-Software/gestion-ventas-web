/**
 * cuentas_cobrar_pagare.js
 * ─────────────────────────────────────────────────────────────────
 * Foto + N° de pagaré de una CuentaPorCobrar, dentro del modal de
 * detalle. A diferencia de los documentos adjuntos (que se acumulan),
 * acá hay una sola foto — subir una nueva reemplaza la anterior.
 *
 * Expone: renderizarPagareCxc(cxc) — llamada desde cuentas_cobrar.js
 * cada vez que se abre/actualiza el modal de detalle.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function _cpGetCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

function renderizarPagareCxc(cxc) {
    const contenedor = document.getElementById('cxcPagare');
    if (!contenedor) return;

    const pk = cxc.pk;
    const fotoUrl = cxc.foto_pagare_url || '';

    const fotoHTML = fotoUrl
        ? `<a href="${fotoUrl}" target="_blank" rel="noopener" class="pagare-foto-link">
               <img src="${fotoUrl}" alt="Foto del pagaré" class="pagare-foto-thumb" id="cpFotoThumb_${pk}">
           </a>`
        : `<p class="pagare-foto-vacio" id="cpFotoThumb_${pk}">Sin foto del pagaré.</p>`;

    const uploaderHTML = window.cxcPuedeEditar ? `
        <label class="doc-subir-label">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M8 2V11M4 5.5L8 2L12 5.5" stroke="currentColor" stroke-width="1.5"
                      stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M2 14H14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            ${fotoUrl ? 'Reemplazar foto' : 'Subir foto'}
            <input type="file" class="doc-file-input" id="cpFile_${pk}" accept="image/*" style="display:none;">
        </label>
        <span class="doc-upload-status" id="cpStatus_${pk}" style="display:none;">Subiendo…</span>` : '';

    contenedor.innerHTML = `
        <div class="pagare-foto-wrap" id="cpFotoWrap_${pk}">${fotoHTML}</div>
        ${uploaderHTML}
    `;

    const fileInput = document.getElementById(`cpFile_${pk}`);
    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files[0]) {
                _cpSubir(fileInput.files[0], pk);
                fileInput.value = '';
            }
        });
    }
}

function _cpSubir(file, cuentaPk) {
    const statusEl = document.getElementById(`cpStatus_${cuentaPk}`);
    const labelEl = document.querySelector(`#cpFile_${cuentaPk}`)?.closest('.doc-subir-label');

    if (statusEl) statusEl.style.display = 'inline';
    if (labelEl) labelEl.style.pointerEvents = 'none';

    const formData = new FormData();
    formData.append('cuenta_pk', cuentaPk);
    formData.append('archivo', file);

    fetch(window.cxcUrls.pagareSubir, {
        method: 'POST',
        headers: { 'X-CSRFToken': _cpGetCookie('csrftoken') },
        body: formData,
    })
        .then(r => r.json())
        .then(data => {
            if (statusEl) statusEl.style.display = 'none';
            if (labelEl) labelEl.style.pointerEvents = '';

            if (data.ok && data.foto_pagare_url) {
                renderizarPagareCxc({ pk: cuentaPk, foto_pagare_url: data.foto_pagare_url });
                KaiToast.show('Foto del pagaré subida correctamente.', 'success');
            } else {
                KaiToast.show(data.error || 'No se pudo subir la foto.', 'danger');
            }
        })
        .catch(() => {
            if (statusEl) statusEl.style.display = 'none';
            if (labelEl) labelEl.style.pointerEvents = '';
            KaiToast.show('Error de red. Intentá de nuevo.', 'danger');
        });
}
