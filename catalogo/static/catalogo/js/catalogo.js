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

/* Partículas flotantes de fondo en el hero — puramente decorativo, sin
   datos ni dependencias externas (mismo recurso que el diseño de
   referencia, adaptado). */
(function () {
    var canvas = document.getElementById('kcHeroCanvas');
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext('2d');
    var particles = [];

    function resize() {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
    }
    window.addEventListener('resize', resize);
    resize();

    function Particle() {
        this.reset();
    }
    Particle.prototype.reset = function () {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.size = Math.random() * 2.5 + 1;
        this.speedX = (Math.random() - 0.5) * 0.6;
        this.speedY = (Math.random() - 0.5) * 0.6;
        this.opacity = Math.random() * 0.4 + 0.1;
    };
    Particle.prototype.update = function () {
        this.x += this.speedX;
        this.y += this.speedY;
        if (this.x < 0 || this.x > canvas.width) this.speedX *= -1;
        if (this.y < 0 || this.y > canvas.height) this.speedY *= -1;
    };
    Particle.prototype.draw = function () {
        ctx.fillStyle = 'rgba(255, 147, 67, ' + this.opacity + ')';
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
    };

    for (var i = 0; i < 40; i++) particles.push(new Particle());

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(function (p) { p.update(); p.draw(); });
        requestAnimationFrame(animate);
    }
    animate();
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
