/* Plantilla "Bento" — SOLO interactividad visual. El filtrado/orden/
   paginación reales los hace Django server-side (igual que la plantilla
   "almacen") vía recarga de página con querystring — acá no hay ningún
   array de productos en memoria ni carrito propio, eso lo maneja
   carrito.js (compartido, sin modificar) contra el markup con los
   mismos ids/atributos que espera (ver bento/base.html). */
document.addEventListener('DOMContentLoaded', function () {

    /* ---------------- Carrusel del hero ---------------- */
    var track = document.getElementById('kcCarouselTrack');
    if (track) {
        var slides = track.querySelectorAll('.c-slide');
        var dots = document.querySelectorAll('#kcCDots .c-dot');
        var idx = 0;
        var timer;

        function ir(i) {
            idx = (i + slides.length) % slides.length;
            track.style.transform = 'translateX(-' + (idx * 100) + '%)';
            dots.forEach(function (d, di) { d.classList.toggle('active', di === idx); });
            reiniciarAutoplay();
        }
        function reiniciarAutoplay() {
            clearInterval(timer);
            if (slides.length > 1) timer = setInterval(function () { ir(idx + 1); }, 5500);
        }
        dots.forEach(function (d) { d.addEventListener('click', function () { ir(Number(d.dataset.i)); }); });
        var btnPrev = document.getElementById('kcCPrev');
        var btnNext = document.getElementById('kcCNext');
        if (btnPrev) btnPrev.addEventListener('click', function () { ir(idx - 1); });
        if (btnNext) btnNext.addEventListener('click', function () { ir(idx + 1); });
        reiniciarAutoplay();
    }

    /* ---------------- Drawer de filtros ---------------- */
    var filtroDrawer = document.getElementById('kcFiltroDrawer');
    var filtroOverlay = document.getElementById('kcFiltroOverlay');
    var btnFiltros = document.getElementById('kcBtnFiltros');
    function abrirFiltros() {
        if (filtroDrawer) filtroDrawer.classList.add('open');
        if (filtroOverlay) filtroOverlay.classList.add('open');
    }
    function cerrarFiltros() {
        if (filtroDrawer) filtroDrawer.classList.remove('open');
        if (filtroOverlay) filtroOverlay.classList.remove('open');
    }
    if (btnFiltros) btnFiltros.addEventListener('click', abrirFiltros);
    var btnFiltroClose = document.getElementById('kcFiltroClose');
    if (btnFiltroClose) btnFiltroClose.addEventListener('click', cerrarFiltros);
    if (filtroOverlay) filtroOverlay.addEventListener('click', cerrarFiltros);

    /* ---------------- Modo oscuro ---------------- */
    var CLAVE_TEMA = 'kc_bento_tema';
    var themeSwitch = document.getElementById('kcThemeSwitch');
    try {
        if (localStorage.getItem(CLAVE_TEMA) === 'dark') {
            document.documentElement.dataset.theme = 'dark';
        }
    } catch (e) { /* modo privado, etc. */ }
    if (themeSwitch) {
        themeSwitch.addEventListener('click', function () {
            var html = document.documentElement;
            var nuevo = html.dataset.theme === 'dark' ? 'light' : 'dark';
            html.dataset.theme = nuevo;
            try { localStorage.setItem(CLAVE_TEMA, nuevo); } catch (e) { /* modo privado, etc. */ }
        });
    }

    /* ---------------- Topbar que se achica al hacer scroll ---------------- */
    var topbar = document.getElementById('kcTopbar');
    if (topbar) {
        window.addEventListener('scroll', function () {
            topbar.classList.toggle('shrink', window.scrollY > 10);
        });
    }

    /* ---------------- Galería de imágenes (detalle de producto) ---------------- */
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
});
