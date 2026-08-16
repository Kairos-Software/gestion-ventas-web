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

/* Desplegable de sugerencias en vivo del buscador del header — mismo
   patrón/endpoint que catalogo.js (Almacén) y bento.js (Bento), cada
   plantilla con su propia copia porque los nombres de clase/ids del
   buscador son propios de cada una. */
(function () {
    var form = document.getElementById('kcSearchForm');
    var input = form ? form.querySelector('input[name="q"]') : null;
    var dropdown = document.getElementById('kcSearchDropdown');
    if (!form || !input || !dropdown || !window.KC_URLS || !window.KC_URLS.buscarSugerencias) return;

    var timer = null;

    function urlResultados() {
        var base = form.action.split('#')[0].split('?')[0];
        return base + '?q=' + encodeURIComponent(input.value.trim()) + '#kcCatalogo';
    }

    function ocultar() {
        dropdown.classList.remove('k-search-dropdown--abierto');
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
            return '<a class="k-search-dropdown-item" href="' + r.url + '">' +
                '<span class="k-search-dropdown-img">' + (r.imagen ? '<img src="' + r.imagen + '" alt="">' : '') + '</span>' +
                '<span class="k-search-dropdown-info">' +
                    '<span class="k-search-dropdown-nombre">' + escapeHtml(r.nombre) + '</span>' +
                    '<span class="k-search-dropdown-precio">' + escapeHtml(r.precio) + '</span>' +
                '</span>' +
            '</a>';
        }).join('');
        html += '<a class="k-search-dropdown-vertodos" href="' + destino + '">Ver todos los resultados →</a>';
        dropdown.innerHTML = html;
        dropdown.classList.add('k-search-dropdown--abierto');
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

/* Ticker de la barra de estado — crossfade entre los mensajes cargados
   (ver ConfiguracionCatalogo.ticker_mensajes_kinetic). Togglear una clase
   por JS en vez de animar por CSS puro evita huecos vacíos entre turnos
   cuando hay menos de 4 mensajes cargados. */
(function () {
    var ticker = document.getElementById('kcStatusTicker');
    if (!ticker) return;
    var msgs = ticker.querySelectorAll('.k-status-ticker-msg');
    if (msgs.length < 2) return;

    var indice = 0;
    setInterval(function () {
        msgs[indice].classList.remove('k-status-ticker-msg--activa');
        indice = (indice + 1) % msgs.length;
        msgs[indice].classList.add('k-status-ticker-msg--activa');
    }, 3500);
})();

/* El nav de escritorio conserva exactamente su comportamiento. En tablet y
   mobile, donde antes se ocultaba sin reemplazo, se abre este panel compacto. */
(function () {
    var toggle = document.getElementById('kcMenuToggle');
    var panel = document.getElementById('kcMobileNav');
    var overlay = document.getElementById('kcMobileNavOverlay');
    var cerrarBtn = document.getElementById('kcMobileNavCerrar');
    if (!toggle || !panel || !overlay) return;

    function abrir() {
        panel.classList.add('kc-abierto');
        overlay.classList.add('kc-abierto');
        toggle.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
    }
    function cerrar() {
        panel.classList.remove('kc-abierto');
        overlay.classList.remove('kc-abierto');
        toggle.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }

    toggle.addEventListener('click', abrir);
    overlay.addEventListener('click', cerrar);
    if (cerrarBtn) cerrarBtn.addEventListener('click', cerrar);
    panel.querySelectorAll('a').forEach(function (link) { link.addEventListener('click', cerrar); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrar(); });
})();

/* Base de consultas Kinetic: conserva una sola respuesta abierta para que la
   sección siga siendo compacta incluso cuando se cargan las ocho permitidas. */
(function () {
    var botones = document.querySelectorAll('.k-support-question');
    if (!botones.length) return;
    botones.forEach(function (boton) {
        boton.addEventListener('click', function () {
            var item = boton.closest('.k-support-item');
            var estabaAbierto = item.classList.contains('k-support-item--abierto');
            botones.forEach(function (otro) {
                otro.setAttribute('aria-expanded', 'false');
                otro.closest('.k-support-item').classList.remove('k-support-item--abierto');
            });
            if (!estabaAbierto) {
                item.classList.add('k-support-item--abierto');
                boton.setAttribute('aria-expanded', 'true');
            }
        });
    });
})();
