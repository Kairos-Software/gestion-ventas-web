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

/* Header que se "achica" al scrollear, y se oculta al bajar / reaparece
   rápido al subir — puramente visual, no depende de ningún dato. */
(function () {
    var header = document.getElementById('kcHeader');
    if (!header) return;
    var ultimoScroll = window.scrollY;

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
    }, { passive: true });
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
