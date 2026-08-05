/* Dark mode — toggle + persistencia en localStorage. El atributo
   data-theme ya se setea de forma sincrónica al abrir <body> (ver
   base.html) para evitar el flash del tema equivocado; acá solo hace
   falta manejar el click y guardar la preferencia. */
(function () {
    var btn = document.getElementById('kcThemeToggle');
    if (!btn) return;

    btn.addEventListener('click', function () {
        var actual = document.body.dataset.theme === 'dark' ? 'dark' : 'light';
        var nuevo = actual === 'dark' ? 'light' : 'dark';
        document.body.dataset.theme = nuevo;
        try { localStorage.setItem('lumina-theme', nuevo); } catch (e) { /* Storage puede estar deshabilitado (modo privado) — no es crítico. */ }
    });
})();

/* Galería del detalle de producto — clic en una miniatura cambia la
   imagen principal. Mismo patrón base que kinetic.js/catalogo.js. */
(function () {
    var imgActual = document.getElementById('kcGaleriaImgActual');
    var thumbs = document.querySelectorAll('.l-thumb');
    if (!imgActual || !thumbs.length) return;

    thumbs.forEach(function (thumb) {
        thumb.addEventListener('click', function () {
            imgActual.src = thumb.dataset.src;
            thumbs.forEach(function (t) { t.classList.remove('l-thumb--activo'); });
            thumb.classList.add('l-thumb--activo');
        });
    });
})();

/* Sidebar de filtros — en desktop está siempre visible (columna fija);
   en mobile colapsa a un drawer, mismo mecanismo de abrir/cerrar que ya
   usan el carrito y el panel de Kinetic (clase "kc-abierto", click
   afuera, Escape). */
(function () {
    var panel = document.getElementById('kcSidebar');
    var overlay = document.getElementById('kcSidebarOverlay');
    var toggle = document.getElementById('kcFiltrosToggle');
    var cerrar = document.getElementById('kcSidebarCerrar');
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
