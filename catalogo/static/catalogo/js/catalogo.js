(function () {
    var imgActual = document.getElementById('kcGaleriaImgActual');
    var thumbs = document.querySelectorAll('.kc-thumb');

    thumbs.forEach(function (thumb) {
        thumb.addEventListener('click', function () {
            if (!imgActual) return;
            imgActual.src = thumb.dataset.src;
            thumbs.forEach(function (t) { t.classList.remove('kc-thumb--activo'); });
            thumb.classList.add('kc-thumb--activo');
        });
    });
})();

function toggleFiltrosMobile(abrir) {
    var sidebar = document.getElementById('kcSidebar');
    if (!sidebar) return;
    sidebar.classList.toggle('kc-sidebar--abierto', abrir);
    document.body.style.overflow = abrir ? 'hidden' : '';
}
