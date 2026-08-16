(function () {
    'use strict';

    var header = document.getElementById('edHeader');
    var progress = document.getElementById('edReadingProgress');
    function updateScrollUI() {
        var y = window.scrollY || 0;
        if (header) header.classList.toggle('ed-scrolled', y > 12);
        if (progress) {
            var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
            progress.style.width = Math.min(100, y / max * 100) + '%';
        }
    }
    window.addEventListener('scroll', updateScrollUI, { passive: true });
    updateScrollUI();

    var menuButton = document.getElementById('edMenuToggle');
    var menu = document.getElementById('edMobileMenu');
    function setMenu(open) {
        if (!menuButton || !menu) return;
        menuButton.setAttribute('aria-expanded', open ? 'true' : 'false');
        menuButton.setAttribute('aria-label', open ? 'Cerrar menú' : 'Abrir menú');
        menu.hidden = !open;
    }
    if (menuButton && menu) {
        menuButton.addEventListener('click', function () {
            setMenu(menuButton.getAttribute('aria-expanded') !== 'true');
        });
        menu.querySelectorAll('a').forEach(function (link) {
            link.addEventListener('click', function () { setMenu(false); });
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') setMenu(false);
        });
    }

    var image = document.getElementById('kcGaleriaImgActual');
    var thumbs = document.querySelectorAll('.ed-thumb');
    if (image && thumbs.length) {
        thumbs.forEach(function (thumb) {
            thumb.addEventListener('click', function () {
                image.src = thumb.dataset.src;
                thumbs.forEach(function (item) { item.classList.toggle('ed-thumb--activo', item === thumb); });
            });
        });
    }

    var tocButton = document.getElementById('edTocMore');
    var tocList = document.getElementById('edTocList');
    if (tocButton && tocList) {
        tocButton.addEventListener('click', function () {
            var expanded = tocList.classList.toggle('ed-expanded');
            tocButton.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            tocButton.innerHTML = expanded ? 'MOSTRAR MENOS ↑' : 'VER ÍNDICE COMPLETO <span>+</span>';
        });
    }

    var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var revealItems = document.querySelectorAll('[data-ed-reveal]');
    if (!reducedMotion && 'IntersectionObserver' in window) {
        var revealObserver = new IntersectionObserver(function (entries, observer) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add('ed-in-view');
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.08, rootMargin: '0px 0px -50px' });
        revealItems.forEach(function (item) { revealObserver.observe(item); });
    } else {
        revealItems.forEach(function (item) { item.classList.add('ed-in-view'); });
    }

    function animateCount(element) {
        var target = Number(element.dataset.count || 0);
        if (!target || reducedMotion) { element.textContent = target; return; }
        var start = performance.now();
        var duration = 900;
        function tick(now) {
            var p = Math.min(1, (now - start) / duration);
            var eased = 1 - Math.pow(1 - p, 3);
            element.textContent = Math.round(target * eased);
            if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }
    var counts = document.querySelectorAll('.ed-count[data-count]');
    if ('IntersectionObserver' in window) {
        var countObserver = new IntersectionObserver(function (entries, observer) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                animateCount(entry.target);
                observer.unobserve(entry.target);
            });
        }, { threshold: .55 });
        counts.forEach(function (count) { countObserver.observe(count); });
    } else {
        counts.forEach(animateCount);
    }

    var rail = document.querySelector('[data-ed-rail]');
    if (rail) {
        var prev = document.querySelector('[data-ed-rail-prev]');
        var next = document.querySelector('[data-ed-rail-next]');
        function step(direction) {
            var card = rail.querySelector('.ed-set-card');
            var amount = card ? card.getBoundingClientRect().width : rail.clientWidth * .85;
            rail.scrollBy({ left: amount * direction, behavior: reducedMotion ? 'auto' : 'smooth' });
        }
        if (prev) prev.addEventListener('click', function () { step(-1); });
        if (next) next.addEventListener('click', function () { step(1); });
        if (!reducedMotion && rail.children.length > 3) {
            var timer = window.setInterval(function () {
                var atEnd = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 8;
                rail.scrollTo({ left: atEnd ? 0 : rail.scrollLeft + rail.clientWidth / 3, behavior: 'smooth' });
            }, 5200);
            rail.addEventListener('pointerenter', function () { window.clearInterval(timer); }, { once: true });
        }
    }

    document.addEventListener('click', function (event) {
        var button = event.target.closest('[data-carrito-agregar]');
        if (!button) return;
        button.classList.remove('ed-popped');
        void button.offsetWidth;
        button.classList.add('ed-popped');
    });
})();
