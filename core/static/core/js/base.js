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