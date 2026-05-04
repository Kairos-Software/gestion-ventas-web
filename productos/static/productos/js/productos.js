/**
 * productos.js
 * Lógica auxiliar estática de la app productos.
 * La mayor parte del JS vive inline en el template para acceder
 * a las URLs de Django vía {% url %}. Este archivo contiene
 * utilidades reutilizables y mejoras UX que no dependen del contexto
 * del template.
 */

'use strict';

/* ════════════════════════════════════════════════════════════════════
   SIDEBAR TOGGLE (heredado de base.js — por si se necesita en esta
   página específicamente)
   ════════════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {

    // ── Cerrar modales con ESC ────────────────────────────────────────
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        document.querySelectorAll('.prd-modal-overlay--open').forEach(overlay => {
            // No cerrar el modal de producto si hay cambios sin guardar
            if (overlay.id === 'modalProducto' && _hayDatosSinGuardar()) return;
            if (typeof cerrarModal === 'function') cerrarModal(overlay.id);
        });
    });

    // ── Auto-formatear código de barras (EAN-13: solo dígitos) ───────
    const inputBarras = document.getElementById('f_codigo_barras');
    if (inputBarras) {
        inputBarras.addEventListener('input', () => {
            inputBarras.value = inputBarras.value.replace(/[^\d]/g, '').slice(0, 13);
        });
    }

    // ── Formatear CUIT-like en código ────────────────────────────────
    const inputCodigo = document.getElementById('f_codigo');
    if (inputCodigo) {
        inputCodigo.addEventListener('input', () => {
            // Convertir a mayúsculas automáticamente
            const pos = inputCodigo.selectionStart;
            inputCodigo.value = inputCodigo.value.toUpperCase();
            inputCodigo.setSelectionRange(pos, pos);
        });
    }

    // ── Validación inline: precio oferta < precio venta ─────────────
    const precioOferta = document.getElementById('f_precio_oferta');
    const precioVenta  = document.getElementById('f_precio_venta');
    if (precioOferta && precioVenta) {
        precioOferta.addEventListener('blur', () => {
            const oferta = parseFloat(precioOferta.value);
            const venta  = parseFloat(precioVenta.value);
            if (oferta && venta && oferta >= venta) {
                precioOferta.style.borderColor = 'var(--danger)';
                _mostrarTipOferta('El precio de oferta debe ser menor al precio de venta.');
            } else {
                precioOferta.style.borderColor = '';
                _ocultarTipOferta();
            }
        });
        precioOferta.addEventListener('focus', () => {
            precioOferta.style.borderColor = '';
            _ocultarTipOferta();
        });
    }

    // ── Contador de caracteres en nombre_corto ───────────────────────
    const nombreCorto = document.getElementById('f_nombre_corto');
    if (nombreCorto) {
        const counter = document.createElement('span');
        counter.className = 'prd-char-counter';
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

    // ── Tags: mostrar chips mientras escribe ─────────────────────────
    const tagsInput = document.getElementById('f_tags');
    if (tagsInput) {
        const preview = document.createElement('div');
        preview.className = 'prd-tags-preview';
        preview.style.cssText = 'display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.4rem;min-height:24px;';
        tagsInput.parentElement.appendChild(preview);

        const renderTags = () => {
            const tags = tagsInput.value.split(',').map(t => t.trim()).filter(Boolean);
            preview.innerHTML = tags.map(t =>
                `<span style="display:inline-block;padding:.15rem .5rem;background:var(--accent-light);
                 color:var(--accent-primary);border-radius:.375rem;font-size:.7rem;font-weight:500;">${_escapeHtml(t)}</span>`
            ).join('');
        };
        tagsInput.addEventListener('input', renderTags);
        renderTags();
    }

    // ── Animación de filas al cargar ─────────────────────────────────
    const rows = document.querySelectorAll('.prd-row');
    rows.forEach((row, i) => {
        row.style.opacity = '0';
        row.style.transform = 'translateY(4px)';
        row.style.transition = 'opacity .2s ease, transform .2s ease';
        setTimeout(() => {
            row.style.opacity = '1';
            row.style.transform = '';
        }, 40 + i * 18);
    });

    // ── Highlight fila recién guardada (si viene ?saved=pk en URL) ───
    const params = new URLSearchParams(window.location.search);
    const savedPk = params.get('saved');
    if (savedPk) {
        const row = document.querySelector(`tr[data-pk="${savedPk}"]`);
        if (row) {
            row.style.background = 'var(--accent-light)';
            setTimeout(() => { row.style.transition = 'background 1s'; row.style.background = ''; }, 1200);
        }
        // Limpiar el param de la URL sin recargar
        const cleanUrl = window.location.pathname + window.location.search.replace(/[?&]saved=[^&]+/, '');
        window.history.replaceState(null, '', cleanUrl);
    }

});


/* ════════════════════════════════════════════════════════════════════
   HELPERS PRIVADOS
   ════════════════════════════════════════════════════════════════════ */

function _hayDatosSinGuardar() {
    const nombre = document.getElementById('f_nombre');
    return nombre && nombre.value.trim().length > 0 &&
           document.getElementById('modalProducto')?.classList.contains('prd-modal-overlay--open');
}

function _mostrarTipOferta(msg) {
    let tip = document.getElementById('_tipOferta');
    if (!tip) {
        tip = document.createElement('small');
        tip.id = '_tipOferta';
        tip.style.cssText = 'color:var(--danger);font-size:.72rem;margin-top:.2rem;display:block;';
        document.getElementById('f_precio_oferta')?.parentElement?.appendChild(tip);
    }
    tip.textContent = msg;
}

function _ocultarTipOferta() {
    document.getElementById('_tipOferta')?.remove();
}

function _escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}