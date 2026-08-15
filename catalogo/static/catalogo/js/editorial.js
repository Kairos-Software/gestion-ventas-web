/* Header — clase "scrolled" al bajar, mismo criterio visual que la
   referencia (header más compacto una vez que se deja de ver el masthead). */
(function () {
    var header = document.getElementById('edHeader');
    if (!header) return;

    function actualizar() {
        header.classList.toggle('ed-scrolled', window.scrollY > 12);
    }
    window.addEventListener('scroll', actualizar, { passive: true });
    actualizar();
})();

/* Galería del detalle de producto — clic en una miniatura cambia la
   imagen principal. Mismo patrón que lumina.js/kinetic.js. */
(function () {
    var imgActual = document.getElementById('kcGaleriaImgActual');
    var thumbs = document.querySelectorAll('.ed-thumb');
    if (!imgActual || !thumbs.length) return;

    thumbs.forEach(function (thumb) {
        thumb.addEventListener('click', function () {
            imgActual.src = thumb.dataset.src;
            thumbs.forEach(function (t) { t.classList.remove('ed-thumb--activo'); });
            thumb.classList.add('ed-thumb--activo');
        });
    });
})();
