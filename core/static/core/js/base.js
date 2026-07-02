// base.js — Kai-Cart
document.addEventListener('DOMContentLoaded', function () {

    const sidebar = document.querySelector('.sidebar');

    // ── Sidebar collapse / expand (desktop) ───────────────────────────
    if (sidebar && localStorage.getItem('sidebarCollapsed') === 'true' && window.innerWidth >= 768) {
        sidebar.classList.add('collapsed');
    }

    // ── Mobile sidebar con overlay ─────────────────────────────────────
    const overlay      = document.getElementById('sidebarOverlay');
    const closeBtn     = document.getElementById('sidebarCloseBtn');
    const mobileToggle = document.getElementById('sidebarToggle');

    function openMobileSidebar() {
        sidebar.classList.add('mobile-open');
        if (overlay) overlay.classList.add('visible');
        document.body.style.overflow = 'hidden';
    }

    function closeMobileSidebar() {
        sidebar.classList.remove('mobile-open');
        if (overlay) overlay.classList.remove('visible');
        document.body.style.overflow = '';
    }

    function isMobile() { return window.innerWidth < 768; }

    // El sidebarToggle en móvil abre el drawer; en desktop colapsa
    if (mobileToggle && sidebar) {
        mobileToggle.addEventListener('click', function () {
            if (isMobile()) {
                sidebar.classList.contains('mobile-open')
                    ? closeMobileSidebar()
                    : openMobileSidebar();
            } else {
                sidebar.classList.toggle('collapsed');
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
            }
        });
    }

    if (closeBtn)  closeBtn.addEventListener('click', closeMobileSidebar);
    if (overlay)   overlay.addEventListener('click', closeMobileSidebar);

    // Cerrar con Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && isMobile()) closeMobileSidebar();
    });

    // Cerrar sidebar en móvil al navegar (click en un nav-item)
    if (sidebar) {
        sidebar.querySelectorAll('.nav-item, .nav-subitem').forEach(function(link) {
            link.addEventListener('click', function() {
                if (isMobile()) closeMobileSidebar();
            });
        });
    }

    // ── Nav groups: restaurar estado ───────────────────────────────────
    try {
        const state = JSON.parse(sessionStorage.getItem('navGroupState') || '{}');
        document.querySelectorAll('.nav-group').forEach(function (group) {
            const tieneActivo = group.querySelector('.nav-subitem.active');
            if (!tieneActivo && group.id in state) {
                group.classList.toggle('open', state[group.id]);
            }
        });
    } catch (e) { /* sessionStorage no disponible */ }

    // ── User Dropdown ──────────────────────────────────────────────────
    const dropdownBtn  = document.getElementById('userDropdownBtn');
    const dropdownMenu = document.getElementById('userDropdownMenu');

    if (dropdownBtn && dropdownMenu) {
        dropdownBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            const isOpen = dropdownMenu.classList.contains('open');
            dropdownMenu.classList.toggle('open', !isOpen);
            dropdownBtn.setAttribute('aria-expanded', String(!isOpen));
        });

        // Cerrar al hacer click fuera
        document.addEventListener('click', function (e) {
            if (!dropdownBtn.contains(e.target) && !dropdownMenu.contains(e.target)) {
                dropdownMenu.classList.remove('open');
                dropdownBtn.setAttribute('aria-expanded', 'false');
            }
        });

        // Cerrar con Escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                dropdownMenu.classList.remove('open');
                dropdownBtn.setAttribute('aria-expanded', 'false');
            }
        });
    }


    // Agrega un <span class="logo-shine"> dentro del .logo y lo anima
    // con un sweep periódico (cada 7s, con variación aleatoria de ±2s).
    const logoLink = document.querySelector('.sidebar-header .logo');

    if (logoLink) {
        // Crear el elemento shine
        const shine = document.createElement('span');
        shine.className = 'logo-shine';
        logoLink.appendChild(shine);

        function triggerShine() {
            // No animar si el sidebar está colapsado
            if (sidebar && sidebar.classList.contains('collapsed')) {
                scheduleShine();
                return;
            }

            // Quitar clase para poder re-añadirla (resetea la animación)
            shine.classList.remove('sweep');

            // Forzar reflow para que el browser procese el reset
            void shine.offsetWidth;

            shine.classList.add('sweep');

            // Limpiar clase al terminar para poder reusar
            shine.addEventListener('animationend', () => {
                shine.classList.remove('sweep');
            }, { once: true });

            scheduleShine();
        }

        function scheduleShine() {
            // Entre 6 y 10 segundos para que se sienta natural
            const delay = 6000 + Math.random() * 4000;
            setTimeout(triggerShine, delay);
        }

        // Primer disparo: 2.5s después de cargar la página
        setTimeout(triggerShine, 2500);
    }

    // ── Modo pantalla completa (Fullscreen API) ────────────────────────
    // Combinación elegida: Ctrl + Alt + F  (letra "F", no tecla de función)
    // Ningún navegador ni SO la reserva: Ctrl+Alt+F1..F7 en Linux usa las
    // TECLAS DE FUNCIÓN (F1, F2...) para cambiar de terminal virtual, no
    // la letra "F", así que no hay colisión. Tampoco choca con F11 (pantalla
    // completa nativa del navegador), F12/Ctrl+Shift+I (devtools) ni Win+I (SO).
    function isFullscreenActive() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement ||
                   document.mozFullScreenElement || document.msFullscreenElement);
    }

    function enterFullscreen() {
        const el = document.documentElement;
        const req = el.requestFullscreen || el.webkitRequestFullscreen ||
                    el.mozRequestFullScreen || el.msRequestFullscreen;
        if (req) req.call(el).catch(function () { /* el navegador denegó el pedido */ });
    }

    function exitFullscreen() {
        const exit = document.exitFullscreen || document.webkitExitFullscreen ||
                     document.mozCancelFullScreen || document.msExitFullscreen;
        if (exit) exit.call(document).catch(function () {});
    }

    function toggleFullscreen() {
        isFullscreenActive() ? exitFullscreen() : enterFullscreen();
    }

    function showFullscreenHint(text) {
        let hint = document.getElementById('fsHint');
        if (!hint) {
            hint = document.createElement('div');
            hint.id = 'fsHint';
            hint.style.cssText = [
                'position:fixed', 'bottom:20px', 'left:50%', 'transform:translateX(-50%)',
                'background:rgba(20,20,20,0.88)', 'color:#fff', 'padding:8px 16px',
                'border-radius:8px', 'font-size:13px', 'font-family:inherit',
                'z-index:99999', 'pointer-events:none', 'opacity:0',
                'transition:opacity .25s ease'
            ].join(';');
            document.body.appendChild(hint);
        }
        hint.textContent = text;
        requestAnimationFrame(function () { hint.style.opacity = '1'; });
        clearTimeout(hint._timeout);
        hint._timeout = setTimeout(function () { hint.style.opacity = '0'; }, 2200);
    }

    document.addEventListener('keydown', function (e) {
        const key = (e.key || '').toLowerCase();
        // Solo la letra "f" (code 'KeyF'), sin Shift, para no confundirla
        // con F1..F12 ni con combinaciones que agreguen Shift.
        if (e.ctrlKey && e.altKey && !e.shiftKey && (key === 'p' || e.code === 'KeyP')) {
            e.preventDefault();
            toggleFullscreen();
        }
    });

    document.addEventListener('fullscreenchange', function () {
        showFullscreenHint(isFullscreenActive()
            ? 'Pantalla completa activada — Esc o Ctrl+Alt+P para salir'
            : 'Pantalla completa desactivada');
    });
    ['webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(function (evt) {
        document.addEventListener(evt, function () {
            showFullscreenHint(isFullscreenActive()
                ? 'Pantalla completa activada — Esc o Ctrl+Alt+F para salir'
                : 'Pantalla completa desactivada');
        });
    });

});

// ── Nav groups toggle ──────────────────────────────────────────────────
function toggleNavGroup(id) {
    const group = document.getElementById(id);
    if (!group) return;
    group.classList.toggle('open');

    const state = {};
    document.querySelectorAll('.nav-group').forEach(function (g) {
        state[g.id] = g.classList.contains('open');
    });
    sessionStorage.setItem('navGroupState', JSON.stringify(state));
}