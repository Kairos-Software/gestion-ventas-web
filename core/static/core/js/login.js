// login.js
document.addEventListener('DOMContentLoaded', function() {
    // Nota: esta página es deliberadamente siempre animada — no respeta
    // prefers-reduced-motion. Decisión consciente del dueño del producto:
    // en la práctica, muchas máquinas Windows (sobre todo LTSC/corporativas)
    // traen las animaciones del SO desactivadas por defecto sin que el
    // usuario haya elegido "quiero menos movimiento" — con ese gate,
    // la mayoría de las visitas reales nunca hubiera visto el diseño.
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
    if (particlesEl) {
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
            loginPage.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        const username = document.getElementById('id_username');
        if (username) {
            setTimeout(() => username.focus({ preventScroll: true }), 550);
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
            if (showcase) showcase.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }

    // Riel de progreso — los puntos navegan a su sección al hacer click,
    // funciona igual con o sin animaciones (solo cambia el behavior).
    const railDots = Array.from(document.querySelectorAll('.scroll-rail-dot'));
    railDots.forEach(dot => {
        dot.addEventListener('click', function () {
            const target = document.getElementById(dot.dataset.target);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    // Se repite en los dos sentidos: cada bloque se revela al entrar en
    // viewport y vuelve a su estado inicial al salir, así que el mismo
    // "momento" (palabras subiendo, capturas enderezándose) se repite
    // scrolleando hacia abajo O volviendo hacia arriba — no es un
    // one-shot que se gasta la primera vez.
    const revealEls = document.querySelectorAll('.js-reveal');
    if (revealEls.length) {
        if (!('IntersectionObserver' in window)) {
            revealEls.forEach(el => el.classList.add('is-in'));
        } else {
            const io = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    entry.target.classList.toggle('is-in', entry.isIntersecting);
                });
            }, { threshold: 0.18, rootMargin: '0px 0px -8% 0px' });
            revealEls.forEach(el => io.observe(el));
        }
    }

    // ── Cursor a medida ──────────────────────────────────────────────────
    // Un punto que sigue al mouse 1:1 (precisión táctil) + un anillo con
    // lag propio que se agranda y tiñe de naranja sobre elementos
    // interactivos — solo con mouse real, nunca en touch. El panel del
    // formulario queda excluido por CSS (cursor nativo ahí, ver login.css).
    const cursorDot = document.getElementById('cursorDot');
    const cursorRing = document.getElementById('cursorRing');
    let ringHover = false;
    let ringX = window.innerWidth / 2, ringY = window.innerHeight / 2;

    if (hasFinePointer && cursorDot && cursorRing) {
        document.body.classList.add('custom-cursor-on');

        document.addEventListener('mousemove', function (e) {
            cursorDot.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0)`;
        });

        const formPanel = document.querySelector('.login-form-panel');
        if (formPanel) {
            formPanel.addEventListener('mouseenter', () => document.body.classList.add('cursor-over-form'));
            formPanel.addEventListener('mouseleave', () => document.body.classList.remove('cursor-over-form'));
        }

        const hoverables = document.querySelectorAll('a, button, input, .scroll-rail-dot');
        hoverables.forEach(el => {
            el.addEventListener('mouseenter', () => { ringHover = true; cursorRing.classList.add('is-active'); });
            el.addEventListener('mouseleave', () => { ringHover = false; cursorRing.classList.remove('is-active'); });
        });
    }

    // ── Shader de fondo (WebGL) ──────────────────────────────────────────
    // Ruido fluido tipo "aurora" con glow de mouse y acento de color que
    // se mezcla entre naranja/azul según la sección activa — reemplaza a
    // los orbes CSS estáticos con algo mucho más orgánico/continuo. Si el
    // navegador no soporta WebGL o falla la compilación, no se activa y
    // la capa de respaldo (orbes/partículas ya construida) sigue de fondo.
    function initBgShader() {
        const canvas = document.getElementById('bgShader');
        const backdrop = document.getElementById('pageBackdrop');
        if (!canvas || !backdrop || !window.WebGLRenderingContext) return null;
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (!gl) return null;

        const vsSource = `
            attribute vec2 a_position;
            varying vec2 v_texCoord;
            void main() {
                v_texCoord = a_position * 0.5 + 0.5;
                gl_Position = vec4(a_position, 0.0, 1.0);
            }
        `;
        const fsSource = `
            precision highp float;
            uniform float u_time;
            uniform vec2 u_resolution;
            uniform vec2 u_mouse;
            uniform float u_accent;
            varying vec2 v_texCoord;

            /* Simplex noise 2D (Ashima Arts / webgl-noise, forma canónica). La
               versión que trae la plantilla de referencia tenía un error de
               tipos en GLSL (vec3 * vec2) que compila en algunos drivers
               permisivos pero falla bajo ANGLE — el mismo validador que usa
               Chrome real, no solo este entorno de test — así que en la
               práctica nunca se activaba. Esta es la implementación correcta. */
            vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
            float snoise(vec2 v) {
                const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
                vec2 i  = floor(v + dot(v, C.yy));
                vec2 x0 = v - i + dot(i, C.xx);
                vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
                vec4 x12 = x0.xyxy + C.xxzz;
                x12.xy -= i1;
                i = mod(i, 289.0);
                vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
                vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
                m = m * m;
                m = m * m;
                vec3 x = 2.0 * fract(p * C.www) - 1.0;
                vec3 h = abs(x) - 0.5;
                vec3 ox = floor(x + 0.5);
                vec3 a0 = x - ox;
                m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
                vec3 g;
                g.x = a0.x * x0.x + h.x * x0.y;
                g.yz = a0.yz * x12.xz + h.yz * x12.yw;
                return 130.0 * dot(m, g);
            }

            void main() {
                vec2 uv = v_texCoord;
                vec2 mouse = u_mouse / u_resolution;
                float time = u_time * 0.045;
                float n = snoise(uv * 1.6 + time);
                n += 0.4 * snoise(uv * 3.2 - time * 0.5);
                float finalNoise = n * 0.5 + 0.5;

                vec3 colorBg  = vec3(0.020, 0.031, 0.059);
                vec3 colorMid = vec3(0.051, 0.106, 0.165);
                vec3 orange = vec3(0.949, 0.416, 0.106);
                vec3 blue   = vec3(0.373, 0.702, 0.910);
                vec3 accentColor = mix(orange, blue, u_accent);

                vec3 color = mix(colorBg, colorMid, finalNoise);
                color = mix(color, accentColor, pow(finalNoise, 6.0) * 0.16);

                float d = distance(uv, mouse);
                color += accentColor * exp(-d * 7.0) * 0.10;

                color *= 1.0 - length(uv - 0.5) * 0.7;
                gl_FragColor = vec4(color, 1.0);
            }
        `;

        function compile(type, source) {
            const shader = gl.createShader(type);
            gl.shaderSource(shader, source);
            gl.compileShader(shader);
            if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return null;
            return shader;
        }

        const vs = compile(gl.VERTEX_SHADER, vsSource);
        const fs = compile(gl.FRAGMENT_SHADER, fsSource);
        if (!vs || !fs) return null;

        const program = gl.createProgram();
        gl.attachShader(program, vs);
        gl.attachShader(program, fs);
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
        gl.useProgram(program);

        const positionBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
        const positionLoc = gl.getAttribLocation(program, 'a_position');
        gl.enableVertexAttribArray(positionLoc);
        gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

        const timeLoc = gl.getUniformLocation(program, 'u_time');
        const resLoc = gl.getUniformLocation(program, 'u_resolution');
        const mouseLoc = gl.getUniformLocation(program, 'u_mouse');
        const accentLoc = gl.getUniformLocation(program, 'u_accent');

        function resize() {
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.round(window.innerWidth * dpr);
            canvas.height = Math.round(window.innerHeight * dpr);
            gl.viewport(0, 0, canvas.width, canvas.height);
        }
        resize();
        window.addEventListener('resize', resize);

        backdrop.classList.add('shader-active');

        return {
            render: function (timeMs, mxNorm, myNorm, accent) {
                // ms → segundos. Sin esta conversión el ruido recorre su
                // patrón completo ~30 veces por segundo en vez de una vez
                // cada ~35s — el bug que hacía que el fondo pareciera un
                // estroboscopio en vez de una deriva lenta tipo aurora.
                gl.uniform1f(timeLoc, timeMs * 0.001);
                gl.uniform2f(resLoc, canvas.width, canvas.height);
                gl.uniform2f(mouseLoc, mxNorm * canvas.width, (1 - myNorm) * canvas.height);
                gl.uniform1f(accentLoc, accent);
                gl.drawArrays(gl.TRIANGLES, 0, 6);
            }
        };
    }
    const bgShader = initBgShader();

    // ── Loop único: cursor + scroll + velocidad ─────────────────────────
    // Todo el movimiento "vivo" del fondo y del contenido corre en un solo
    // requestAnimationFrame continuo (no atado a eventos de scroll, que
    // pueden llegar de forma irregular) — es lo que da la sensación
    // hipnótica: el fondo respira, sigue al cursor, se desplaza (más
    // lento que el contenido, efecto de profundidad) y "pulsa" un poco
    // según qué tan rápido se scrollea, y el color del shader (o el orbe
    // de acento, si WebGL no está disponible) viaja de sección en sección
    // tiñendo el fondo del color de lo que se está mostrando en pantalla.
    const orbs = document.getElementById('loginOrbs');
    const card = document.getElementById('loginCard');
    const orbAccent = document.getElementById('orbAccent');
    const mediaEls = Array.from(document.querySelectorAll('.showcase-media'));

    let targetX = 0.5, targetY = 0.4; // 0-1, posición normalizada del cursor
    let curX = targetX, curY = targetY;
    let lastScrollY = window.scrollY;
    let velocity = 0;
    let activeSectionIdx = -1;
    let accentSmooth = 0; // 0 = naranja, 1 = azul — el shader lo interpola

    const accentBySection = [null, 'orange', 'blue', 'orange', 'orange'];
    const accentTargetBySection = [0, 0, 1, 0, 0];
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
        if (idx === -1) return;
        // El target del shader se actualiza siempre (permite blend continuo
        // aunque la sección activa no haya cambiado de índice todavía).
        activeSectionIdx = idx;
        if (!orbAccent) return;

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

        if (hasFinePointer && cursorRing) {
            ringX += (curX * window.innerWidth - ringX) * 0.18;
            ringY += (curY * window.innerHeight - ringY) * 0.18;
            const ringScale = ringHover ? 1.7 : 1;
            cursorRing.style.transform = `translate3d(${ringX.toFixed(1)}px, ${ringY.toFixed(1)}px, 0) scale(${ringScale})`;
        }

        if (bgShader) {
            const accentTarget = accentTargetBySection[Math.max(activeSectionIdx, 0)];
            accentSmooth += (accentTarget - accentSmooth) * 0.03;
            bgShader.render(performance.now(), curX, curY, accentSmooth);
        }

        requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
});
