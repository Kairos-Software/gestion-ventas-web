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

    /* ---------------- Barra de anuncios (ticker) ---------------- */
    var tickerMsgs = document.querySelectorAll('#kcTickerMsgs .ticker-msg');
    if (tickerMsgs.length > 1) {
        var tIdx = 0;
        var tTimer;
        function mostrarMsg(n) {
            tIdx = (n + tickerMsgs.length) % tickerMsgs.length;
            tickerMsgs.forEach(function (m, i) { m.classList.toggle('active', i === tIdx); });
        }
        function reiniciarTicker() {
            clearInterval(tTimer);
            tTimer = setInterval(function () { mostrarMsg(tIdx + 1); }, 3800);
        }
        var tPrev = document.getElementById('kcTickerPrev');
        var tNext = document.getElementById('kcTickerNext');
        if (tPrev) tPrev.addEventListener('click', function () { mostrarMsg(tIdx - 1); reiniciarTicker(); });
        if (tNext) tNext.addEventListener('click', function () { mostrarMsg(tIdx + 1); reiniciarTicker(); });
        reiniciarTicker();
    }

    /* ---------------- Arrastrar con mouse los carruseles horizontales ----------------
       Los rails (categorías, novedades, ofertas, destacados) ya se pueden recorrer con
       touch/trackpad porque son overflow-x:auto — esto suma que también se puedan
       arrastrar con el mouse en desktop, como en un sitio real. */
    document.querySelectorAll('.hide-scrollbar').forEach(function (rail) {
        var down = false, startX = 0, startScroll = 0, moved = false;
        rail.addEventListener('mousedown', function (e) {
            down = true; moved = false;
            rail.classList.add('dragging');
            startX = e.pageX; startScroll = rail.scrollLeft;
        });
        window.addEventListener('mouseup', function () { down = false; rail.classList.remove('dragging'); });
        rail.addEventListener('mouseleave', function () { down = false; rail.classList.remove('dragging'); });
        rail.addEventListener('mousemove', function (e) {
            if (!down) return;
            e.preventDefault();
            if (Math.abs(e.pageX - startX) > 4) moved = true;
            rail.scrollLeft = startScroll - (e.pageX - startX);
        });
        // Evita que soltar el mouse después de arrastrar dispare el click del
        // link/producto que quedó debajo del cursor.
        rail.addEventListener('click', function (e) { if (moved) { e.preventDefault(); e.stopPropagation(); } }, true);
    });

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
    /* Publica la altura REAL del topbar como variable CSS (--topbar-h) en vez
       de que el CSS adivine un valor fijo — el topbar cambia de alto al
       "achicarse" (.shrink), así que un valor fijo queda mal en algún punto
       del scroll. La usa el sub-nav sticky de "La tienda" (ver .inst-subnav
       en bento.css). Mismo problema (y misma solución) que ya se encontró en
       la plantilla "almacen" con su sub-nav sticky. */
    var topbar = document.getElementById('kcTopbar');
    if (topbar) {
        var actualizarAlturaTopbar = function () {
            document.documentElement.style.setProperty('--topbar-h', topbar.offsetHeight + 'px');
        };
        window.addEventListener('scroll', function () {
            topbar.classList.toggle('shrink', window.scrollY > 10);
            actualizarAlturaTopbar();
        });
        window.addEventListener('resize', actualizarAlturaTopbar);
        actualizarAlturaTopbar();
    }

    /* ---------------- Buscador mobile (icono que expande el form) ---------------- */
    var searchToggle = document.getElementById('kcSearchToggle');
    var searchInput = document.querySelector('#kcSearchForm .search-input');
    if (searchToggle && topbar) {
        searchToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            var abierto = topbar.classList.toggle('search-open');
            if (abierto && searchInput) searchInput.focus();
        });
        document.addEventListener('click', function (e) {
            if (topbar.classList.contains('search-open') && !topbar.contains(e.target)) {
                topbar.classList.remove('search-open');
            }
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') topbar.classList.remove('search-open');
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

    /* ---------------- Zoom de la imagen principal (lightbox simple) ---------------- */
    var lightbox = document.getElementById('kcLightbox');
    var lightboxImg = document.getElementById('kcLightboxImg');
    var btnExpandir = document.getElementById('kcGaleriaExpandir');
    var btnCerrarLightbox = document.getElementById('kcLightboxCerrar');
    function abrirLightbox() {
        if (!lightbox || !imgActual) return;
        lightboxImg.src = imgActual.src;
        lightbox.classList.add('open');
    }
    function cerrarLightbox() {
        if (lightbox) lightbox.classList.remove('open');
    }
    if (btnExpandir) btnExpandir.addEventListener('click', abrirLightbox);
    if (imgActual) imgActual.addEventListener('click', abrirLightbox);
    if (btnCerrarLightbox) btnCerrarLightbox.addEventListener('click', cerrarLightbox);
    if (lightbox) lightbox.addEventListener('click', function (e) { if (e.target === lightbox) cerrarLightbox(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrarLightbox(); });

    /* ---------------- Desplegable de sugerencias en vivo del buscador ---------------- */
    /* Mismo comportamiento que initBuscadorSugerencias en catalogo.js (plantilla
       "almacen"): a medida que se escribe pide sugerencias al servidor (debounce
       250ms) y las muestra abajo del input. Clickear cualquier sugerencia (o
       apretar Enter, que sigue andando solo porque no se toca el submit nativo
       del form) lleva siempre a la misma pantalla de resultados — las
       sugerencias son una vista previa, no un atajo a la ficha del producto. */
    (function () {
        var form = document.getElementById('kcSearchForm');
        var input = form ? form.querySelector('.search-input') : null;
        var dropdown = document.getElementById('kcSearchDropdown');
        if (!form || !input || !dropdown || !window.KC_URLS || !window.KC_URLS.buscarSugerencias) return;

        var timer = null;

        function urlResultados() {
            var base = form.action.split('#')[0].split('?')[0];
            return base + '?q=' + encodeURIComponent(input.value.trim()) + '#kcCatalogo';
        }

        function ocultar() {
            dropdown.classList.remove('search-dropdown--abierto');
            dropdown.innerHTML = '';
        }

        function escapeHtml(s) {
            var div = document.createElement('div');
            div.textContent = s;
            return div.innerHTML;
        }

        function render(resultados) {
            if (!resultados.length) { ocultar(); return; }
            var destino = urlResultados();
            var html = resultados.map(function (r) {
                return '<a class="search-dropdown-item" href="' + destino + '">' +
                    '<span class="search-dropdown-img">' + (r.imagen ? '<img src="' + r.imagen + '" alt="">' : '') + '</span>' +
                    '<span class="search-dropdown-info">' +
                        '<span class="search-dropdown-nombre">' + escapeHtml(r.nombre) + '</span>' +
                        '<span class="search-dropdown-precio">' + escapeHtml(r.precio) + '</span>' +
                    '</span>' +
                '</a>';
            }).join('');
            html += '<a class="search-dropdown-vertodos" href="' + destino + '">Ver todos los resultados →</a>';
            dropdown.innerHTML = html;
            dropdown.classList.add('search-dropdown--abierto');
        }

        input.addEventListener('input', function () {
            clearTimeout(timer);
            var q = input.value.trim();
            if (q.length < 2) { ocultar(); return; }
            timer = setTimeout(function () {
                fetch(window.KC_URLS.buscarSugerencias + '?q=' + encodeURIComponent(q))
                    .then(function (r) { return r.json(); })
                    .then(function (data) { render(data.resultados || []); })
                    .catch(function () { ocultar(); });
            }, 250);
        });

        document.addEventListener('click', function (e) {
            if (!form.contains(e.target)) ocultar();
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') ocultar();
        });
    })();

    /* ---------------- Filtro Categoría/Tipo del drawer — cascada ---------------- */
    /* Elegir categorías/tipos no aplica al toque: se tildan checkboxes y recién
       se filtra al apretar "Aplicar filtros". "Tipo" arranca oculto (u oculto
       por completo si ningún tipo pertenece a las categorías tildadas) y solo
       muestra los tipos de las categorías tildadas — mismo patrón que el
       filtro de "almacen" (ver catalogo.js). */
    (function () {
        var form = document.getElementById('formFiltrosBento');
        if (!form) return;
        var categoriaBoxes = Array.prototype.slice.call(form.querySelectorAll('input[name="categoria"]'));
        var grupoTipo = document.getElementById('kcGrupoTipo');
        var tipoLabels = grupoTipo ? Array.prototype.slice.call(grupoTipo.querySelectorAll('.d-check')) : [];

        function categoriasElegidas() {
            return categoriaBoxes.filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
        }

        function actualizarTipos() {
            if (!grupoTipo) return;
            var elegidas = categoriasElegidas();
            grupoTipo.hidden = elegidas.length === 0;
            tipoLabels.forEach(function (label) {
                var coincide = elegidas.indexOf(label.dataset.categoria) !== -1;
                label.hidden = !coincide;
                if (!coincide) {
                    var box = label.querySelector('input[type="checkbox"]');
                    if (box) box.checked = false;
                }
            });
        }

        categoriaBoxes.forEach(function (c) { c.addEventListener('change', actualizarTipos); });
    })();

    /* ---------------- Sub-nav ancorado de "La tienda" ---------------- */
    /* Scroll suave al click + resalta la sección visible mientras se scrollea.
       No hace nada si la página no tiene esta barra (solo institucional.html
       la tiene). Mismo mecanismo que la plantilla "almacen" (initInstSubnav en
       catalogo.js), adaptado a .inst-subnav. */
    (function () {
        var subnav = document.querySelector('.inst-subnav');
        if (!subnav) return;
        var links = Array.prototype.slice.call(subnav.querySelectorAll('a'));
        var secciones = links
            .map(function (a) { return document.querySelector(a.getAttribute('href')); })
            .filter(Boolean);

        links.forEach(function (a) {
            a.addEventListener('click', function (e) {
                var destino = document.querySelector(a.getAttribute('href'));
                if (!destino) return;
                e.preventDefault();
                destino.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });

        if (!('IntersectionObserver' in window) || !secciones.length) return;
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                links.forEach(function (a) {
                    a.classList.toggle('inst-subnav-activo', a.getAttribute('href') === '#' + entry.target.id);
                });
            });
        }, { rootMargin: '-45% 0px -50% 0px' });
        secciones.forEach(function (sec) { observer.observe(sec); });
    })();
});
