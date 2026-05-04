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

});