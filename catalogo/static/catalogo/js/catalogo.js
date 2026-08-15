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

/* Lightbox simple para ver la imagen del producto en grande — solo
   presentación, reutiliza el src que ya está cargado en el visor. */
(function () {
    var btn = document.getElementById('kcGaleriaExpandir');
    var imgActual = document.getElementById('kcGaleriaImgActual');
    if (!btn || !imgActual) return;

    var overlay = document.createElement('div');
    overlay.className = 'kc-lightbox';
    overlay.innerHTML = '<button type="button" class="kc-lightbox-cerrar" aria-label="Cerrar">&times;</button><img class="kc-lightbox-img">';
    document.body.appendChild(overlay);
    var imgGrande = overlay.querySelector('.kc-lightbox-img');

    function abrir() {
        imgGrande.src = imgActual.src;
        overlay.classList.add('kc-lightbox--abierto');
        document.body.style.overflow = 'hidden';
    }
    function cerrar() {
        overlay.classList.remove('kc-lightbox--abierto');
        document.body.style.overflow = '';
    }

    btn.addEventListener('click', abrir);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) cerrar(); });
    overlay.querySelector('.kc-lightbox-cerrar').addEventListener('click', cerrar);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrar(); });
})();

function toggleFiltrosMobile(abrir) {
    var sidebar = document.getElementById('kcSidebar');
    if (!sidebar) return;
    sidebar.classList.toggle('kc-sidebar--abierto', abrir);
    document.body.style.overflow = abrir ? 'hidden' : '';
}

/* Flechas de las filas "vidriera" (Ofertas del momento / Destacados /
   Combos armados / Categorías y marcas, ver catalogo/home.html) —
   genérico, cablea todas las filas [data-carrusel] de la página sin
   necesitar ids únicos por fila. */
(function () {
    document.querySelectorAll('[data-carrusel]').forEach(function (carrusel) {
        var track = carrusel.querySelector('.kc-flash-row, .kc-feat-row, .kc-combo-row, .kc-tiles-row, .kc-gondola-rail');
        var btnPrev = carrusel.querySelector('[data-carrusel-prev]');
        var btnNext = carrusel.querySelector('[data-carrusel-next]');
        if (!track) return;
        function mover(signo) {
            track.scrollBy({ left: signo * track.clientWidth * 0.85, behavior: 'smooth' });
        }
        if (btnPrev) btnPrev.addEventListener('click', function () { mover(-1); });
        if (btnNext) btnNext.addEventListener('click', function () { mover(1); });
    });
})();

/* Header que se "achica" al scrollear, y se oculta al bajar / reaparece
   rápido al subir — puramente visual, no depende de ningún dato.
   También publica --kc-header-offset (0 cuando el header está oculto,
   su alto real cuando está visible) y --kc-scroll-offset (+ el alto de
   la sub-nav de "La tienda", si existe) como variables CSS — así
   cualquier barra sticky de más abajo (ver .kc-inst-subnav en
   catalogo.css) puede acomodarse contra la posición REAL del header en
   vez de asumir un alto fijo que se desincroniza apenas el header se
   oculta. */
(function () {
    var header = document.getElementById('kcHeader');
    if (!header) return;
    var subnav = document.querySelector('.kc-inst-subnav');
    var ultimoScroll = window.scrollY;

    function actualizarOffsets() {
        var headerOffset = header.classList.contains('kc-header--oculto') ? 0 : header.offsetHeight;
        document.documentElement.style.setProperty('--kc-header-offset', headerOffset + 'px');
        document.documentElement.style.setProperty(
            '--kc-scroll-offset', (headerOffset + (subnav ? subnav.offsetHeight : 0)) + 'px'
        );
    }

    window.addEventListener('scroll', function () {
        var actual = window.scrollY;
        header.classList.toggle('kc-header--scrolled', actual > 40);

        var delta = actual - ultimoScroll;
        if (actual <= header.offsetHeight) {
            header.classList.remove('kc-header--oculto');
        } else if (delta > 4) {
            header.classList.add('kc-header--oculto');
        } else if (delta < -4) {
            header.classList.remove('kc-header--oculto');
        }
        ultimoScroll = actual;
        actualizarOffsets();
    }, { passive: true });

    actualizarOffsets();
})();

/* Buscador mobile (icono que expande el form) — el input de búsqueda del
   header se oculta en mobile (catalogo.css) para no competir por espacio
   con el resto de los íconos; este botón lo despliega en una fila propia. */
(function () {
    var header = document.getElementById('kcHeader');
    var toggle = document.getElementById('kcSearchToggle');
    var input = document.querySelector('.kc-search input');
    if (!header || !toggle) return;

    toggle.addEventListener('click', function (e) {
        e.stopPropagation();
        var abierto = header.classList.toggle('kc-search-open');
        if (abierto && input) input.focus();
    });
    document.addEventListener('click', function (e) {
        if (header.classList.contains('kc-search-open') && !header.contains(e.target)) {
            header.classList.remove('kc-search-open');
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') header.classList.remove('kc-search-open');
    });
})();

/* Tilt 3D + glare sobre la tarjeta del hero al mover el mouse — puramente
   visual, no depende de ningún dato. */
(function () {
    var wrap = document.getElementById('kcHeroTiltWrap');
    var card = document.getElementById('kcHeroVisual');
    if (!wrap || !card) return;
    var glare = card.querySelector('.kc-hero-glare');
    wrap.addEventListener('mousemove', function (e) {
        var rect = card.getBoundingClientRect();
        var x = e.clientX - rect.left;
        var y = e.clientY - rect.top;
        var rotateX = ((y - rect.height / 2) / (rect.height / 2)) * -12;
        var rotateY = ((x - rect.width / 2) / (rect.width / 2)) * 12;
        card.style.transform = 'rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg)';
        if (glare) glare.style.opacity = '1';
    });
    wrap.addEventListener('mouseleave', function () {
        card.style.transform = 'rotateX(0deg) rotateY(0deg)';
        if (glare) glare.style.opacity = '0';
    });
})();

/* Red conectada del hero y de la historia. Replica el movimiento orgánico
   de la referencia, usa el color configurado por la tienda y se detiene
   cuando la pestaña no está visible. */
(function () {
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function cssColorToRgb(value, fallback) {
        var probe = document.createElement('span');
        probe.style.color = value;
        probe.style.display = 'none';
        document.body.appendChild(probe);
        var computed = getComputedStyle(probe).color.match(/\d+(?:\.\d+)?/g);
        probe.remove();
        return computed && computed.length >= 3
            ? computed.slice(0, 3).map(function (part) { return Math.round(Number(part)); }).join(',')
            : fallback;
    }

    function initNetworkCanvas(canvasId, options) {
        var canvas = document.getElementById(canvasId);
        if (!canvas || !canvas.getContext) return;

        var context = canvas.getContext('2d');
        var nodes = [];
        var width = 0;
        var height = 0;
        var pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        var color = options.color;
        var frameId = null;

        function resize() {
            width = canvas.parentElement.clientWidth;
            height = canvas.parentElement.clientHeight;
            canvas.width = Math.round(width * pixelRatio);
            canvas.height = Math.round(height * pixelRatio);
            canvas.style.width = width + 'px';
            canvas.style.height = height + 'px';
            context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
            nodes.forEach(function (node) {
                node.x = Math.min(node.x, width);
                node.y = Math.min(node.y, height);
            });
        }

        function NetworkNode() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.vx = (Math.random() - 0.5) * options.speed;
            this.vy = (Math.random() - 0.5) * options.speed;
            this.radius = Math.random() * 1.55 + 0.8;
        }

        NetworkNode.prototype.update = function () {
            this.x += this.vx;
            this.y += this.vy;
            if (this.x <= 0 || this.x >= width) this.vx *= -1;
            if (this.y <= 0 || this.y >= height) this.vy *= -1;
        };

        function draw() {
            context.clearRect(0, 0, width, height);
            nodes.forEach(function (node, index) {
                if (!reduceMotion) node.update();
                for (var next = index + 1; next < nodes.length; next++) {
                    var dx = node.x - nodes[next].x;
                    var dy = node.y - nodes[next].y;
                    var distance = Math.sqrt(dx * dx + dy * dy);
                    if (distance < options.linkDistance) {
                        context.strokeStyle = 'rgba(' + color + ',' + ((1 - distance / options.linkDistance) * options.linkAlpha) + ')';
                        context.lineWidth = 1;
                        context.beginPath();
                        context.moveTo(node.x, node.y);
                        context.lineTo(nodes[next].x, nodes[next].y);
                        context.stroke();
                    }
                }
            });
            nodes.forEach(function (node) {
                context.fillStyle = 'rgba(' + color + ',' + options.nodeAlpha + ')';
                context.beginPath();
                context.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
                context.fill();
            });
        }

        function animate() {
            draw();
            if (!reduceMotion && !document.hidden) frameId = requestAnimationFrame(animate);
        }

        resize();
        for (var i = 0; i < options.count; i++) nodes.push(new NetworkNode());
        animate();

        window.addEventListener('resize', resize);
        document.addEventListener('visibilitychange', function () {
            if (document.hidden && frameId) cancelAnimationFrame(frameId);
            if (!document.hidden && !reduceMotion) {
                if (frameId) cancelAnimationFrame(frameId);
                frameId = requestAnimationFrame(animate);
            }
        });
    }

    var configuredPrimary = getComputedStyle(document.documentElement).getPropertyValue('--primary').trim();
    var primaryRgb = cssColorToRgb(configuredPrimary, '255,147,67');
    initNetworkCanvas('kcHeroCanvas', { count: 54, linkDistance: 145, speed: 0.38, color: primaryRgb, linkAlpha: 0.34, nodeAlpha: 0.84 });
    initNetworkCanvas('kcStoryCanvas', { count: 26, linkDistance: 105, speed: 0.28, color: '148,163,184', linkAlpha: 0.25, nodeAlpha: 0.7 });
    initNetworkCanvas('kcInstCanvas', { count: 48, linkDistance: 135, speed: 0.34, color: primaryRgb, linkAlpha: 0.3, nodeAlpha: 0.78 });
    initNetworkCanvas('kcDetailCanvas', { count: 38, linkDistance: 125, speed: 0.3, color: primaryRgb, linkAlpha: 0.22, nodeAlpha: 0.66 });
})();

/* Apariciones escalonadas, contadores y una mínima profundidad al hacer
   scroll. Todo es progresivo: sin IntersectionObserver el contenido queda
   visible y la funcionalidad del catálogo no cambia. */
(function () {
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var revealSelectors = [
        '.kc-feature-item', '.kc-banner-promo', '.kc-home-story > *',
        '.kc-sec-head', '.kc-tile-destacado', '.kc-gondola',
        '.kc-flash-card', '.kc-card', '.kc-feat-card', '.kc-combo-card',
        '.kc-inst-portada-copy', '.kc-inst-portada-media',
        '.kc-inst-historia-inner > *', '.kc-destacado-card',
        '.kc-galeria-item', '.kc-inst-info-col', '.kc-inst-contacto-texto',
        '.kc-galeria', '.kc-detalle-info', '.kc-detalle-editorial-copy',
        '.kc-detalle-caracteristicas', '.kc-detalle-ficha-wrap', '.kc-rel-card'
    ];
    var revealItems = document.querySelectorAll(revealSelectors.join(','));

    revealItems.forEach(function (item, index) {
        item.classList.add('kc-reveal');
        item.style.setProperty('--kc-reveal-delay', ((index % 6) * 65) + 'ms');
    });

    if (!reduceMotion && 'IntersectionObserver' in window) {
        var revealObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add('kc-reveal--in');
                revealObserver.unobserve(entry.target);
            });
        }, { threshold: 0.09, rootMargin: '0px 0px -5% 0px' });
        revealItems.forEach(function (item) { revealObserver.observe(item); });
    } else {
        revealItems.forEach(function (item) { item.classList.add('kc-reveal--in'); });
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
    }

    var hero = document.querySelector('.kc-hero');
    var heroShape = document.querySelector('.kc-hero-bg-shape');
    if (!reduceMotion && hero && heroShape) {
        var ticking = false;
        window.addEventListener('scroll', function () {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(function () {
                var progress = Math.min(window.scrollY, hero.offsetHeight);
                heroShape.style.setProperty('--kc-hero-parallax', (progress * 0.075) + 'px');
                ticking = false;
            });
        }, { passive: true });
    }
})();

/* Toast de confirmación al agregar algo al carrito — aditivo: escucha los
   mismos botones que carrito.js (data-carrito-agregar) por delegación,
   sin tocar ni depender de su lógica interna (el chip "Ya en tu pedido"
   sigue siendo la fuente real de estado). */
(function () {
    var cont = document.createElement('div');
    cont.className = 'kc-toast-wrap';
    document.body.appendChild(cont);

    function mostrarToast(nombre) {
        var toast = document.createElement('div');
        toast.className = 'kc-toast';
        toast.innerHTML =
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
            '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>' +
            '<span>"' + nombre + '" agregado al pedido</span>';
        cont.appendChild(toast);
        setTimeout(function () { toast.classList.add('kc-toast--show'); }, 10);
        setTimeout(function () {
            toast.classList.remove('kc-toast--show');
            setTimeout(function () { toast.remove(); }, 400);
        }, 2600);
    }

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-carrito-agregar]');
        if (btn) mostrarToast(btn.dataset.nombre || 'Producto');
    });
})();

/* Desplegable de sugerencias en vivo del buscador del header — a medida
   que se escribe, pide sugerencias al servidor (debounce 250ms) y las
   muestra abajo del input. Clickear cualquier sugerencia (o apretar
   Enter, que sigue andando solo porque no se toca el submit nativo del
   form) lleva siempre a la misma pantalla de resultados — las
   sugerencias son una vista previa, no un atajo a la ficha del producto. */
(function () {
    var form = document.querySelector('.kc-search');
    var input = form ? form.querySelector('input[name="q"]') : null;
    var dropdown = document.getElementById('kcSearchDropdown');
    if (!form || !input || !dropdown || !window.KC_URLS || !window.KC_URLS.buscarSugerencias) return;

    var timer = null;

    function urlResultados() {
        var base = form.action.split('#')[0].split('?')[0];
        return base + '?q=' + encodeURIComponent(input.value.trim()) + '#kcCatalogo';
    }

    function ocultar() {
        dropdown.classList.remove('kc-search-dropdown--abierto');
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
            return '<a class="kc-search-dropdown-item" href="' + r.url + '">' +
                '<span class="kc-search-dropdown-img">' + (r.imagen ? '<img src="' + r.imagen + '" alt="">' : '') + '</span>' +
                '<span class="kc-search-dropdown-info">' +
                    '<span class="kc-search-dropdown-nombre">' + escapeHtml(r.nombre) + '</span>' +
                    '<span class="kc-search-dropdown-precio">' + escapeHtml(r.precio) + '</span>' +
                '</span>' +
            '</a>';
        }).join('');
        html += '<a class="kc-search-dropdown-vertodos" href="' + destino + '">Ver todos los resultados →</a>';
        dropdown.innerHTML = html;
        dropdown.classList.add('kc-search-dropdown--abierto');
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

/* Sub-nav ancorado de "La tienda" (exclusivo de Almacén, ver
   institucional.html) — scroll suave al click + resalta la sección
   visible mientras se scrollea. No hace nada si la página no tiene esta
   barra (las otras 3 plantillas no la tienen todavía). */
(function () {
    var subnav = document.querySelector('.kc-inst-subnav');
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
                a.classList.toggle('kc-inst-subnav-activo', a.getAttribute('href') === '#' + entry.target.id);
            });
        });
    }, { rootMargin: '-45% 0px -50% 0px' });
    secciones.forEach(function (sec) { observer.observe(sec); });
})();

/* Filtro de Categoría/Tipo del catálogo (sidebar) — a pedido del dueño,
   elegir categorías/tipos ya NO aplica al toque: se tildan checkboxes y
   recién se filtra al apretar "Aplicar filtros" (mismo botón/patrón que ya
   usa el filtro de Precio). "Tipo" además arranca oculto y solo aparece
   cuando hay alguna categoría tildada — mostrar todos los tipos de entrada
   no tiene sentido si ninguno tiene relación con la categoría que se busca
   (ej: "estampado" no aplica si se está buscando "zapatos"). */
(function () {
    var form = document.getElementById('formFiltroCatTipo');
    if (!form) return;
    var categoriaBoxes = Array.prototype.slice.call(form.querySelectorAll('input[name="categoria"]'));
    var grupoTipo = document.getElementById('kcGrupoTipo');
    var tipoLabels = grupoTipo ? Array.prototype.slice.call(grupoTipo.querySelectorAll('.kc-filtro-check')) : [];

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
    actualizarTipos();
})();
