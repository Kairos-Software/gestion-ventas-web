/* Header — clase "scrolled" al bajar (header más compacto). */
(function () {
    var header = document.getElementById('lHeader');
    if (!header) return;

    function actualizar() {
        header.classList.toggle('l-scrolled', window.scrollY > 12);
    }
    window.addEventListener('scroll', actualizar, { passive: true });
    actualizar();
})();

/* Galería del detalle de producto — clic en una miniatura cambia la
   imagen principal. Mismo patrón que editorial.js/kinetic.js. */
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

/* Desplegable de sugerencias en vivo del buscador del header — mismo
   patrón/endpoint que catalogo.js (Almacén)/bento.js/kinetic.js, cada
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
        dropdown.classList.remove('l-search-dropdown--abierto');
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
            return '<a class="l-search-dropdown-item" href="' + r.url + '">' +
                '<span class="l-search-dropdown-img">' + (r.imagen ? '<img src="' + r.imagen + '" alt="">' : '') + '</span>' +
                '<span class="l-search-dropdown-info">' +
                    '<span class="l-search-dropdown-nombre">' + escapeHtml(r.nombre) + '</span>' +
                    '<span class="l-search-dropdown-precio">' + escapeHtml(r.precio) + '</span>' +
                '</span>' +
            '</a>';
        }).join('');
        html += '<a class="l-search-dropdown-vertodos" href="' + destino + '">Ver todos los resultados →</a>';
        dropdown.innerHTML = html;
        dropdown.classList.add('l-search-dropdown--abierto');
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

/* Scroll-reveal (fade-in al entrar en pantalla) + contadores animados de
   las cifras del hero — mismo patrón que catalogo.js (Almacén), única
   plantilla que ya lo tenía; acá con los selectores propios de Directo. */
(function () {
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var revealSelectors = [
        '.l-cat-item', '.l-offer-card', '.l-card', '.l-paq-card', '.l-paso',
        '.l-sec-head', '.l-nos-visual', '.l-nos-text', '.l-detalle-seccion',
    ];
    var revealItems = document.querySelectorAll(revealSelectors.join(','));

    revealItems.forEach(function (item, index) {
        item.classList.add('l-reveal');
        item.style.setProperty('--l-reveal-delay', ((index % 6) * 65) + 'ms');
    });

    if (!reduceMotion && 'IntersectionObserver' in window) {
        var revealObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add('l-reveal--in');
                revealObserver.unobserve(entry.target);
            });
        }, { threshold: 0.09, rootMargin: '0px 0px -5% 0px' });
        revealItems.forEach(function (item) { revealObserver.observe(item); });
    } else {
        revealItems.forEach(function (item) { item.classList.add('l-reveal--in'); });
    }

    function animateCounter(element) {
        var target = Number(element.getAttribute('data-kc-count')) || 0;
        var startedAt = performance.now();
        var duration = 1250;
        function tick(now) {
            var progress = Math.min((now - startedAt) / duration, 1);
            var eased = 1 - Math.pow(1 - progress, 3);
            element.textContent = Math.round(target * eased).toLocaleString('es-AR');
            if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    var counters = document.querySelectorAll('[data-kc-count]');
    if (!reduceMotion && 'IntersectionObserver' in window) {
        var counterObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                animateCounter(entry.target);
                counterObserver.unobserve(entry.target);
            });
        }, { threshold: 0.55 });
        counters.forEach(function (counter) { counterObserver.observe(counter); });
    } else {
        counters.forEach(function (counter) { counter.textContent = Number(counter.getAttribute('data-kc-count')) || 0; });
    }
})();
