'use strict';

const CDT = window.CDT_CONFIG || {};

/* ════════════════════════════════════════════════════════════════
   REFS DOM
════════════════════════════════════════════════════════════════ */
const cdtDocZone  = document.getElementById('cdtDocZone');
const cdtDocInput = document.getElementById('cdtDocInput');
const cdtDocLista = document.getElementById('cdtDocLista');

/* ════════════════════════════════════════════════════════════════
   BORRADOR — Confirmar y Volver
════════════════════════════════════════════════════════════════ */
if (CDT.esBorrador) {
    const btnConfirmar = document.getElementById('cdtBtnConfirmar');
    const btnEditar    = document.getElementById('cdtBtnEditar');
    const btnVolver    = document.getElementById('cdtBtnVolver');
    const inputFecha   = document.getElementById('cdtFecha');
    const inputNotas   = document.getElementById('cdtNotas');

    /* ── Editar carrito (vuelve a Nueva Compra CON los productos cargados) ── */
    btnEditar.addEventListener('click', () => {
        window.location.href = CDT.urlEditarCarrito;
    });

    /* ── Confirmar compra ─────────────────────────────────────── */
    btnConfirmar.addEventListener('click', async () => {
        const fecha = inputFecha.value;
        if (!fecha) { cdtToast('Fecha requerida', 'Ingresá una fecha antes de confirmar.'); return; }

        btnConfirmar.disabled  = true;
        btnConfirmar.innerHTML = `<svg class="cmp-spin" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Confirmando…`;

        try {
            const res  = await fetch(CDT.urlConfirmar, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CDT.csrfToken },
                body:    JSON.stringify({
                    compra_pk: CDT.compraPk,
                    fecha:     fecha,
                    notas:     inputNotas ? inputNotas.value.trim() : '',
                }),
            });
            const data = await res.json();

            if (data.ok) {
                // Redirigir al historial con la compra ya confirmada
                window.location.href = CDT.urlHistorial;
            } else {
                cdtToast('Error al confirmar', data.error || 'No se pudo confirmar la compra.');
            }
        } catch {
            cdtToast('Error de conexión', 'Intentá de nuevo.');
        } finally {
            btnConfirmar.disabled  = false;
            btnConfirmar.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2.5 8L6.5 12L13.5 4" stroke="currentColor" stroke-width="1.6"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg> Confirmar compra`;
        }
    });

    /* ── Cancelar compra (descarta todo el borrador) ──────────── */
    btnVolver.addEventListener('click', async () => {
        const ok = confirm('¿Cancelar esta compra? El borrador y todos los productos cargados se van a perder.');
        if (!ok) return;

        btnVolver.disabled  = true;
        btnVolver.innerHTML = `<svg class="cmp-spin" width="14" height="14" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 15"/>
        </svg> Cancelando…`;

        try {
            const res  = await fetch(CDT.urlEliminarBorrador, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CDT.csrfToken },
                body:    JSON.stringify({ compra_pk: CDT.compraPk }),
            });
            const data = await res.json();

            if (data.ok) {
                window.location.href = CDT.urlNuevaCompra;
            } else {
                cdtToast('Error', data.error || 'No se pudo cancelar la compra.');
                btnVolver.disabled  = false;
                btnVolver.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                </svg> Cancelar compra`;
            }
        } catch {
            cdtToast('Error de conexión', 'Intentá de nuevo.');
            btnVolver.disabled = false;
        }
    });
}

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Selección por input
════════════════════════════════════════════════════════════════ */
cdtDocInput.addEventListener('change', () => {
    cdtSubirArchivos(Array.from(cdtDocInput.files));
    cdtDocInput.value = '';
});

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Drag & drop
════════════════════════════════════════════════════════════════ */
cdtDocZone.addEventListener('dragover', e => {
    e.preventDefault();
    cdtDocZone.classList.add('over');
});
cdtDocZone.addEventListener('dragleave', () => cdtDocZone.classList.remove('over'));
cdtDocZone.addEventListener('drop', e => {
    e.preventDefault();
    cdtDocZone.classList.remove('over');
    cdtSubirArchivos(Array.from(e.dataTransfer.files));
});

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Subir
════════════════════════════════════════════════════════════════ */
async function cdtSubirArchivos(files) {
    const PERMITIDOS = ['jpg','jpeg','png','webp','gif','pdf'];
    for (const file of files) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!PERMITIDOS.includes(ext)) {
            cdtToast('Tipo no permitido', `"${file.name}" debe ser JPG, PNG, WEBP, GIF o PDF.`);
            continue;
        }
        if (file.size > 10 * 1024 * 1024) {
            cdtToast('Archivo muy grande', `"${file.name}" supera los 10 MB.`);
            continue;
        }

        const tempId = `uploading-${Date.now()}`;
        cdtDocLista.insertAdjacentHTML('beforeend', `
            <div class="cmp-doc-item cmp-doc-item--uploading" id="${tempId}">
                <div class="cmp-doc-item-icon">
                    <svg class="cmp-spin" width="18" height="18" viewBox="0 0 18 18" fill="none">
                        <circle cx="9" cy="9" r="7" stroke="currentColor" stroke-width="1.5" stroke-dasharray="22 22" opacity=".3"/>
                        <path d="M9 2a7 7 0 0 1 7 7" stroke="var(--brand-orange)" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                </div>
                <div class="cmp-doc-item-info">
                    <span class="cmp-doc-item-nombre">${cdtEsc(file.name)}</span>
                    <span class="cmp-doc-item-tipo">Subiendo…</span>
                </div>
            </div>`);

        const fd = new FormData();
        fd.append('compra_pk', CDT.compraPk);
        fd.append('archivo',   file);
        fd.append('tipo',      document.getElementById('cdtDocTipo').value);

        try {
            const res  = await fetch(CDT.urlDocSubir, {
                method:  'POST',
                headers: { 'X-CSRFToken': CDT.csrfToken },
                body:    fd,
            });
            const data = await res.json();
            const tempEl = document.getElementById(tempId);

            if (data.ok) {
                if (tempEl) tempEl.outerHTML = cdtRenderDocItem(data);
                cdtActualizarBadge();
                cdtToast('Documento guardado', `"${data.nombre}" subido correctamente.`);
            } else {
                tempEl?.remove();
                cdtToast('Error al subir', data.error || 'No se pudo guardar el archivo.');
            }
        } catch {
            document.getElementById(tempId)?.remove();
            cdtToast('Error de conexión', 'No se pudo subir el archivo.');
        }
    }
}

/* ════════════════════════════════════════════════════════════════
   DOCUMENTOS — Eliminar
════════════════════════════════════════════════════════════════ */
async function cdtEliminarDoc(pk) {
    if (!confirm('¿Eliminar este documento? Esta acción no se puede deshacer.')) return;
    try {
        const res  = await fetch(CDT.urlDocEliminar, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CDT.csrfToken },
            body:    JSON.stringify({ pk }),
        });
        const data = await res.json();
        if (data.ok) {
            document.getElementById(`cdtdoc-${pk}`)?.remove();
            cdtActualizarBadge();
            cdtToast('Documento eliminado', '');
        } else {
            cdtToast('Error', data.error || 'No se pudo eliminar.');
        }
    } catch {
        cdtToast('Error de conexión', '');
    }
}

/* ════════════════════════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════════════════════════ */
function cdtRenderDocItem(doc) {
    const icono = doc.es_pdf
        ? `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
               <path d="M4 2H11L15 6V16H4V2Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
               <path d="M11 2V6H15" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
               <path d="M6 9H12M6 11.5H9" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
           </svg>`
        : `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
               <rect x="2" y="2" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.2"/>
               <circle cx="6.5" cy="6.5" r="1.3" fill="currentColor" fill-opacity=".4"/>
               <path d="M2 12L5.5 9L8 11L11.5 7.5L16 12" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
           </svg>`;

    return `
    <div class="cmp-doc-item" id="cdtdoc-${doc.pk}">
        <div class="cmp-doc-item-icon">${icono}</div>
        <div class="cmp-doc-item-info">
            <a href="${doc.url}" target="_blank" class="cmp-doc-item-nombre">${cdtEsc(doc.nombre)}</a>
            <span class="cmp-doc-item-tipo">${cdtEsc(doc.tipo_display)}</span>
        </div>
        <button class="cmp-doc-item-del" onclick="cdtEliminarDoc(${doc.pk})" title="Eliminar">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            </svg>
        </button>
    </div>`;
}

function cdtActualizarBadge() {
    const total = cdtDocLista
        ? cdtDocLista.querySelectorAll('.cmp-doc-item:not(.cmp-doc-item--uploading)').length
        : 0;
    const badge = document.getElementById('cdtDocBadge');
    if (!badge) return;
    badge.textContent   = total;
    badge.style.display = total > 0 ? 'inline-flex' : 'none';
}

function cdtToast(titulo, cuerpo) {
    const toast = document.getElementById('cdtToast');
    document.getElementById('cdtToastTitle').textContent = titulo;
    document.getElementById('cdtToastBody').textContent  = cuerpo || '';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4500);
}

function cdtEsc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}