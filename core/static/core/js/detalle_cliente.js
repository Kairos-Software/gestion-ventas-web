document.addEventListener('DOMContentLoaded', function () {

    // ══ LIGHTBOX ══
    let _lbImages = [], _lbIdx = 0;

    const lb       = document.getElementById('lightbox');
    const lbImg    = document.getElementById('lbImg');
    const lbCap    = document.getElementById('lbCaption');
    const lbCnt    = document.getElementById('lbCounter');
    const lbPrev   = document.getElementById('lbPrev');
    const lbNext   = document.getElementById('lbNext');
    const lbClose  = document.getElementById('lbClose');

    function recolectar() {
        _lbImages = Array.from(document.querySelectorAll('.galeria-item img')).map(img => ({
            url:     img.src,
            caption: img.closest('.galeria-item')
                        ?.querySelector('.galeria-tipo')
                        ?.textContent?.trim() || ''
        }));
    }

    function mostrar(idx) {
        if (!lb || !_lbImages.length) return;
        _lbIdx = idx;
        lb.classList.add('active');
        document.body.style.overflow = 'hidden';

        lbImg.style.opacity = '0';
        lbImg.src = _lbImages[idx].url;
        lbImg.onload = () => { lbImg.style.opacity = '1'; };
        if (lbImg.complete && lbImg.naturalWidth) lbImg.style.opacity = '1';

        if (lbCap) lbCap.textContent = _lbImages[idx].caption;
        if (lbCnt) lbCnt.textContent = _lbImages.length > 1 ? `${idx + 1} / ${_lbImages.length}` : '';
        if (lbPrev) lbPrev.style.visibility = _lbImages.length > 1 ? 'visible' : 'hidden';
        if (lbNext) lbNext.style.visibility = _lbImages.length > 1 ? 'visible' : 'hidden';
    }

    function cerrar() {
        if (lb) lb.classList.remove('active');
        document.body.style.overflow = '';
    }

    document.addEventListener('click', function (e) {
        const item = e.target.closest('.galeria-item');
        if (!item) return;

        const img = item.querySelector('img');
        if (!img) return;

        recolectar();
        const idx = _lbImages.findIndex(i => i.url === img.src);
        mostrar(idx >= 0 ? idx : 0);
    });

    if (lbClose) lbClose.addEventListener('click', cerrar);
    if (lb) lb.addEventListener('click', e => {
        if (e.target === lb) cerrar();
    });
    if (lbPrev) lbPrev.addEventListener('click', e => {
        e.stopPropagation();
        mostrar((_lbIdx - 1 + _lbImages.length) % _lbImages.length);
    });
    if (lbNext) lbNext.addEventListener('click', e => {
        e.stopPropagation();
        mostrar((_lbIdx + 1) % _lbImages.length);
    });
    document.addEventListener('keydown', e => {
        if (!lb?.classList.contains('active')) return;
        if (e.key === 'Escape')     cerrar();
        if (e.key === 'ArrowLeft')  mostrar((_lbIdx - 1 + _lbImages.length) % _lbImages.length);
        if (e.key === 'ArrowRight') mostrar((_lbIdx + 1) % _lbImages.length);
    });

    // ══ MAPA LEAFLET ══
    if (typeof window.clienteLatitud !== 'undefined' && document.getElementById('mapaDetalle')) {
        const mapa = L.map('mapaDetalle', { zoomControl: true, scrollWheelZoom: false })
            .setView([window.clienteLatitud, window.clienteLongitud], 16);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap', maxZoom: 19
        }).addTo(mapa);
        L.marker([window.clienteLatitud, window.clienteLongitud])
            .addTo(mapa).bindPopup('Ubicación del cliente').openPopup();
    }

    // ══ SCORING DE RIESGO DE PAGO ══
    (function initScoring() {
        const card = document.getElementById('scoCard');
        if (!card) return;
        const url = card.dataset.url;

        function getCookie(name) {
            let v = null;
            document.cookie.split(';').forEach(c => {
                const [k, val] = c.trim().split('=');
                if (k === name) v = decodeURIComponent(val);
            });
            return v;
        }

        const form  = document.getElementById('scoOverrideForm');
        const msgEl = document.getElementById('scoMsg');

        async function enviar(payload) {
            card.classList.add('sco-cargando');
            if (msgEl) msgEl.textContent = '';
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (!res.ok || !data.ok) {
                    if (msgEl) msgEl.textContent = data.error || 'No se pudo actualizar.';
                    return;
                }
                // Recargamos la ficha: es lo más simple y garantiza que el
                // aviso de override, los botones y el desglose queden coherentes.
                window.location.reload();
            } catch {
                if (msgEl) msgEl.textContent = 'Error de conexión. Intentá de nuevo.';
            } finally {
                card.classList.remove('sco-cargando');
            }
        }

        card.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-sco-accion]');
            if (!btn) return;
            const accion = btn.dataset.scoAccion;

            if (accion === 'recalcular') {
                enviar({ accion: 'recalcular' });
            } else if (accion === 'quitar') {
                enviar({ accion: 'quitar' });
            } else if (accion === 'override-abrir') {
                if (form) form.hidden = false;
            } else if (accion === 'override-cancelar') {
                if (form) form.hidden = true;
            } else if (accion === 'override-guardar') {
                const valor  = document.getElementById('scoOverrideValor')?.value;
                const motivo = document.getElementById('scoOverrideMotivo')?.value?.trim();
                if (!motivo) { if (msgEl) msgEl.textContent = 'Escribí el motivo del ajuste.'; return; }
                enviar({ accion: 'override', puntaje: valor, motivo });
            }
        });
    })();

    // ══ PAGARÉ EN BLANCO ══
    (function initPagare() {
        const card = document.getElementById('pagCard');
        if (!card) return;
        const urlGuardar = card.dataset.urlGuardar;
        const urlSubir = card.dataset.urlSubir;

        function getCookie(name) {
            let v = null;
            document.cookie.split(';').forEach(c => {
                const [k, val] = c.trim().split('=');
                if (k === name) v = decodeURIComponent(val);
            });
            return v;
        }

        const msgEl = document.getElementById('pagMsg');

        const btnGuardar = document.getElementById('btnGuardarPagare');
        if (btnGuardar) {
            btnGuardar.addEventListener('click', async () => {
                const numero = document.getElementById('pagNumero')?.value || '';
                btnGuardar.disabled = true;
                if (msgEl) msgEl.textContent = '';
                try {
                    const res = await fetch(urlGuardar, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                        body: JSON.stringify({ numero_pagare: numero }),
                    });
                    const data = await res.json();
                    if (!res.ok || !data.ok) {
                        if (msgEl) msgEl.textContent = data.error || 'No se pudo guardar.';
                        return;
                    }
                    if (window.KaiToast) KaiToast.show('N° de pagaré guardado.', 'success');
                } catch {
                    if (msgEl) msgEl.textContent = 'Error de conexión. Intentá de nuevo.';
                } finally {
                    btnGuardar.disabled = false;
                }
            });
        }

        const fileInput = document.getElementById('pagFile');
        if (fileInput) {
            fileInput.addEventListener('change', async () => {
                const file = fileInput.files && fileInput.files[0];
                if (!file) return;
                const statusEl = document.getElementById('pagStatus');
                const labelEl = fileInput.closest('.doc-subir-label');
                if (statusEl) statusEl.style.display = 'inline';
                if (labelEl) labelEl.style.pointerEvents = 'none';
                if (msgEl) msgEl.textContent = '';

                const formData = new FormData();
                formData.append('archivo', file);
                try {
                    const res = await fetch(urlSubir, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': getCookie('csrftoken') },
                        body: formData,
                    });
                    const data = await res.json();
                    if (!res.ok || !data.ok) {
                        if (msgEl) msgEl.textContent = data.error || 'No se pudo subir la foto.';
                        return;
                    }
                    // Recargamos la ficha: más simple y garantiza que la
                    // miniatura y el texto "Subir"/"Reemplazar" queden coherentes.
                    window.location.reload();
                } catch {
                    if (msgEl) msgEl.textContent = 'Error de conexión. Intentá de nuevo.';
                } finally {
                    if (statusEl) statusEl.style.display = 'none';
                    if (labelEl) labelEl.style.pointerEvents = '';
                    fileInput.value = '';
                }
            });
        }
    })();

});