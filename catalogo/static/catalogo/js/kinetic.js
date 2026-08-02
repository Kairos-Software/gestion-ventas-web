/* Galería del detalle de producto — clic en una miniatura (o en las flechas
   prev/next sobre la imagen grande) cambia la imagen principal. Mismo
   patrón base que catalogo.js/bento.js (cada plantilla tiene su propia
   copia), con el agregado de las flechas — acá las miniaturas van al
   costado en vez de debajo, así que la navegación por flechas ayuda a no
   depender solo de apuntar a una miniatura chica. */
(function () {
    var imgActual = document.getElementById('kcGaleriaImgActual');
    var thumbs = document.querySelectorAll('.k-thumb');
    var btnPrev = document.getElementById('kcGaleriaPrev');
    var btnNext = document.getElementById('kcGaleriaNext');
    if (!imgActual || !thumbs.length) return;

    function activar(indice) {
        var thumb = thumbs[indice];
        if (!thumb) return;
        imgActual.src = thumb.dataset.src;
        thumbs.forEach(function (t) { t.classList.remove('k-thumb--activo'); });
        thumb.classList.add('k-thumb--activo');
    }

    function indiceActual() {
        var i = -1;
        thumbs.forEach(function (t, idx) { if (t.classList.contains('k-thumb--activo')) i = idx; });
        return i;
    }

    thumbs.forEach(function (thumb, indice) {
        thumb.addEventListener('click', function () { activar(indice); });
    });

    if (btnPrev) btnPrev.addEventListener('click', function () {
        activar((indiceActual() - 1 + thumbs.length) % thumbs.length);
    });
    if (btnNext) btnNext.addEventListener('click', function () {
        activar((indiceActual() + 1) % thumbs.length);
    });
})();

/* Panel de filtros (solo existe en home.html) — mismo mecanismo de
   abrir/cerrar que ya usan el carrito y el buscador mobile en esta
   plantilla (clase "kc-abierto", click afuera, Escape). */
(function () {
    var panel = document.getElementById('kcFiltrosPanel');
    var overlay = document.getElementById('kcFiltrosOverlay');
    var toggle = document.getElementById('kcFiltrosToggle');
    var cerrar = document.getElementById('kcFiltrosCerrar');
    if (!panel || !overlay || !toggle) return;

    function abrir() {
        panel.classList.add('kc-abierto');
        overlay.classList.add('kc-abierto');
        document.body.style.overflow = 'hidden';
    }
    function cerrarPanel() {
        panel.classList.remove('kc-abierto');
        overlay.classList.remove('kc-abierto');
        document.body.style.overflow = '';
    }

    toggle.addEventListener('click', abrir);
    if (cerrar) cerrar.addEventListener('click', cerrarPanel);
    overlay.addEventListener('click', cerrarPanel);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrarPanel(); });
})();
