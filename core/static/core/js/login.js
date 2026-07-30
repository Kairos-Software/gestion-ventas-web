// login.js
document.addEventListener('DOMContentLoaded', function() {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const hasFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

    // Toggle password visibility
    const toggleBtns = document.querySelectorAll('.toggle-password');

    toggleBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.closest('.input-wrapper').querySelector('input');
            const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
            input.setAttribute('type', type);

            // Optional: change icon
            const svg = this.querySelector('svg');
            if (type === 'text') {
                svg.innerHTML = `<path d="M9 4C5 4 2.5 7 1 9C2.5 11 5 14 9 14C13 14 15.5 11 17 9C15.5 7 13 4 9 4Z" stroke="currentColor" stroke-width="1.5" fill="none"/>
                                 <path d="M13 5L5 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                                 <circle cx="9" cy="9" r="2.5" stroke="currentColor" stroke-width="1.5"/>`;
            } else {
                svg.innerHTML = `<path d="M9 4C5 4 2.5 7 1 9C2.5 11 5 14 9 14C13 14 15.5 11 17 9C15.5 7 13 4 9 4Z" stroke="currentColor" stroke-width="1.5"/>
                                 <circle cx="9" cy="9" r="2.5" stroke="currentColor" stroke-width="1.5"/>`;
            }
        });
    });

    // Brillo periódico sobre el logo — mismo mecanismo que usa el sidebar
    // real del sistema logueado (ver core/static/core/js/base.js), para que
    // se sienta el mismo producto ya desde el login.
    const logoEl = document.querySelector('.login-brand-panel .logo');
    if (logoEl) {
        const shine = document.createElement('span');
        shine.className = 'logo-shine';
        logoEl.appendChild(shine);

        function triggerShine() {
            shine.classList.remove('sweep');
            void shine.offsetWidth;
            shine.classList.add('sweep');
            shine.addEventListener('animationend', () => {
                shine.classList.remove('sweep');
            }, { once: true });
            scheduleShine();
        }

        function scheduleShine() {
            const delay = 6000 + Math.random() * 4000;
            setTimeout(triggerShine, delay);
        }

        setTimeout(triggerShine, 2500);
    }

    // ── Títulos grandes: reveal palabra por palabra ─────────────────────
    // Envuelve cada palabra en <span class="word"><span class="word-inner">
    // para animarlas por separado (ver login.css) — motion editorial en el
    // statement de apertura y en el h3 de cada fila, sin tocar el resto.
    function splitWords(el) {
        if (!el || el.dataset.split) return;
        el.dataset.split = '1';
        const words = el.textContent.trim().split(/\s+/);
        el.textContent = '';
        words.forEach((word, i) => {
            const wrap = document.createElement('span');
            wrap.className = 'word';
            wrap.style.setProperty('--i', i);
            const inner = document.createElement('span');
            inner.className = 'word-inner';
            inner.textContent = word;
            wrap.appendChild(inner);
            el.appendChild(wrap);
            if (i < words.length - 1) el.appendChild(document.createTextNode(' '));
        });
    }
    document.querySelectorAll('.showcase-heading, .showcase-text h3').forEach(splitWords);

    // ── Partículas de fondo ──────────────────────────────────────────────
    // Puntos finos que derivan hacia arriba muy lento (ver @keyframes
    // particleFloat en login.css) — dan profundidad al lienzo sin ser
    // protagonistas. Nada de esto corre con reduced-motion.
    const particlesEl = document.getElementById('loginParticles');
    if (particlesEl && !prefersReducedMotion) {
        const COUNT = 26;
        const colors = ['rgba(242,106,27,0.55)', 'rgba(95,179,232,0.5)', 'rgba(255,255,255,0.45)'];
        const frag = document.createDocumentFragment();
        for (let i = 0; i < COUNT; i++) {
            const p = document.createElement('span');
            p.className = 'particle';
            p.style.setProperty('--p-left', (Math.random() * 100).toFixed(1) + '%');
            p.style.setProperty('--p-size', (Math.random() * 2.2 + 1.4).toFixed(1) + 'px');
            p.style.setProperty('--p-duration', (16 + Math.random() * 18).toFixed(1) + 's');
            p.style.setProperty('--p-delay', (-Math.random() * 30).toFixed(1) + 's');
            p.style.setProperty('--p-drift', (Math.random() * 60 - 30).toFixed(0) + 'px');
            p.style.setProperty('--p-opacity', (0.2 + Math.random() * 0.3).toFixed(2));
            p.style.setProperty('--p-color', colors[i % colors.length]);
            frag.appendChild(p);
        }
        particlesEl.appendChild(frag);
    }

    // ── Volver al login (foco en usuario) ──────────────────────────────
    function goToLogin() {
        const loginPage = document.getElementById('loginPage');
        if (loginPage) {
            loginPage.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' });
        }
        const username = document.getElementById('id_username');
        if (username) {
            setTimeout(() => username.focus({ preventScroll: true }), prefersReducedMotion ? 0 : 550);
        }
    }

    const closeCta = document.getElementById('closeCta');
    if (closeCta) closeCta.addEventListener('click', goToLogin);

    const scrollFab = document.getElementById('scrollFab');
    if (scrollFab) scrollFab.addEventListener('click', goToLogin);

    const scrollCue = document.getElementById('scrollCue');
    if (scrollCue) {
        scrollCue.addEventListener('click', function () {
            const showcase = document.getElementById('showcase');
            if (showcase) showcase.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' });
        });
    }

    // Riel de progreso — los puntos navegan a su sección al hacer click,
    // funciona igual con o sin animaciones (solo cambia el behavior).
    const railDots = Array.from(document.querySelectorAll('.scroll-rail-dot'));
    railDots.forEach(dot => {
        dot.addEventListener('click', function () {
            const target = document.getElementById(dot.dataset.target);
            if (target) target.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' });
        });
    });
    const railFill = document.getElementById('scrollRailFill');
    const railSections = ['loginPage', 'row-0', 'row-1', 'row-2', 'showcaseClose']
        .map(id => document.getElementById(id))
        .filter(Boolean);

    function updateRail(scrollY, vh) {
        if (railFill) {
            const maxScroll = document.documentElement.scrollHeight - vh;
            const pct = maxScroll > 0 ? Math.min(100, Math.max(0, (scrollY / maxScroll) * 100)) : 0;
            railFill.style.height = pct.toFixed(1) + '%';
        }
        if (!railSections.length) return -1;
        let closestIdx = 0, closestDist = Infinity;
        railSections.forEach((sec, i) => {
            const r = sec.getBoundingClientRect();
            const dist = Math.abs((r.top + r.height / 2) - vh / 2);
            if (dist < closestDist) { closestDist = dist; closestIdx = i; }
        });
        railDots.forEach(dot => {
            dot.classList.toggle('is-active', dot.dataset.target === railSections[closestIdx].id);
        });
        return closestIdx;
    }

    // ── Revelado de secciones al hacer scroll ──────────────────────────
    // One-shot: cada bloque se revela la primera vez que entra en
    // viewport y deja de observarse (misma "coreografía" de entrada que
    // ya usa el hero, pero disparada por scroll en vez de por carga).
    const revealEls = document.querySelectorAll('.js-reveal');
    if (revealEls.length) {
        if (prefersReducedMotion || !('IntersectionObserver' in window)) {
            revealEls.forEach(el => el.classList.add('is-in'));
        } else {
            const io = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('is-in');
                        io.unobserve(entry.target);
                    }
                });
            }, { threshold: 0.18, rootMargin: '0px 0px -8% 0px' });
            revealEls.forEach(el => io.observe(el));
        }
    }

    if (prefersReducedMotion) {
        // Estado final estático: el riel y el CTA flotante siguen siendo
        // funcionales (responden al scroll real), pero sin ningún tipo de
        // parallax, flotado idle ni transición — solo la clase que los
        // muestra/oculta u marca como activos.
        const scrollFabEl = document.getElementById('scrollFab');
        function onScrollStatic() {
            const vh = window.innerHeight;
            const scrollY = window.scrollY;
            if (scrollFabEl) scrollFabEl.classList.toggle('is-visible', scrollY > vh * 0.6);
            updateRail(scrollY, vh);
        }
        window.addEventListener('scroll', onScrollStatic, { passive: true });
        onScrollStatic();
        return;
    }

    // ── Loop único: cursor + scroll + velocidad ─────────────────────────
    // Todo el movimiento "vivo" del fondo y del contenido corre en un solo
    // requestAnimationFrame continuo (no atado a eventos de scroll, que
    // pueden llegar de forma irregular) — es lo que da la sensación
    // hipnótica: el fondo respira, sigue al cursor, se desplaza (más
    // lento que el contenido, efecto de profundidad) y "pulsa" un poco
    // según qué tan rápido se scrollea, y el orbe de acento viaja de
    // sección en sección tiñendo el fondo del color de lo que se está
    // mostrando en pantalla.
    const orbs = document.getElementById('loginOrbs');
    const card = document.getElementById('loginCard');
    const orbAccent = document.getElementById('orbAccent');
    const mediaEls = Array.from(document.querySelectorAll('.showcase-media'));

    let targetX = 0.5, targetY = 0.4; // 0-1, posición normalizada del cursor
    let curX = targetX, curY = targetY;
    let lastScrollY = window.scrollY;
    let velocity = 0;
    let activeSectionIdx = -1;

    const accentBySection = [null, 'orange', 'blue', 'orange', 'orange'];
    const orbOffsets = [
        null,
        { x: '22vw', y: '-18vh' },
        { x: '-24vw', y: '14vh' },
        { x: '20vw', y: '10vh' },
        { x: '0vw', y: '-10vh' },
    ];

    if (hasFinePointer) {
        window.addEventListener('mousemove', function (e) {
            targetX = e.clientX / window.innerWidth;
            targetY = e.clientY / window.innerHeight;
        });
        document.documentElement.addEventListener('mouseleave', function () {
            targetX = 0.5;
            targetY = 0.4;
        });
    }

    function updateAccentOrb(vh) {
        const idx = updateRail(window.scrollY, vh);
        if (idx === -1 || idx === activeSectionIdx || !orbAccent) return;
        activeSectionIdx = idx;

        const accent = accentBySection[idx];
        const offset = orbOffsets[idx];
        if (!accent || !offset) {
            orbAccent.style.opacity = '0';
            return;
        }
        const color = accent === 'blue' ? 'rgba(95,179,232,0.4)' : 'rgba(242,106,27,0.42)';
        orbAccent.style.background = `radial-gradient(circle, ${color} 0%, transparent 70%)`;
        orbAccent.style.transform = `translate3d(${offset.x}, ${offset.y}, 0)`;
        orbAccent.style.opacity = '1';
    }

    function frame() {
        // Suavizado (easing) hacia la posición real del cursor, en vez
        // de saltar de golpe — es lo que da la sensación "hipnótica".
        curX += (targetX - curX) * 0.07;
        curY += (targetY - curY) * 0.07;

        document.body.style.setProperty('--mx', (curX * 100).toFixed(2) + '%');
        document.body.style.setProperty('--my', (curY * 100).toFixed(2) + '%');

        const scrollY = window.scrollY;
        const vh = window.innerHeight;
        const rawVelocity = scrollY - lastScrollY;
        lastScrollY = scrollY;
        velocity += (rawVelocity - velocity) * 0.15;
        const pulse = Math.min(Math.abs(velocity) / 60, 1) * 0.05;

        if (orbs) {
            const ox = (curX - 0.5) * -26;
            // El fondo se desplaza mucho más lento que el contenido real
            // (0.045x) — profundidad clásica de parallax, casi imperceptible
            // como movimiento propio pero se nota al comparar con el resto.
            const oy = (curY - 0.5) * -26 - scrollY * 0.045;
            orbs.style.transform = `translate3d(${ox.toFixed(1)}px, ${oy.toFixed(1)}px, 0) scale(${(1 + pulse).toFixed(3)})`;
        }
        if (card) {
            const rotY = (curX - 0.5) * 6;
            const rotX = (curY - 0.5) * -6;
            card.style.transform = `rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg)`;
        }

        const t = performance.now() / 1000;
        mediaEls.forEach((el, i) => {
            const rect = el.getBoundingClientRect();
            const center = rect.top + rect.height / 2;
            const progress = (center - vh / 2) / vh;
            const offset = Math.max(-30, Math.min(30, progress * 40));
            // Flotado idle continuo (seno), desfasado por elemento para que
            // las tres capturas no "respiren" en sincro.
            const bob = Math.sin(t * 0.6 + i * 1.7) * 5;
            el.style.transform = `translateY(${(offset + bob).toFixed(1)}px)`;
        });

        if (scrollFab) scrollFab.classList.toggle('is-visible', scrollY > vh * 0.6);
        if (scrollCue) scrollCue.classList.toggle('is-hidden', scrollY > 40);

        updateAccentOrb(vh);

        requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
});
