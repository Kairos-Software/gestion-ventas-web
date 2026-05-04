// base.js — Kai-Cart
document.addEventListener('DOMContentLoaded', function () {

    // ── Sidebar collapse / expand ──────────────────────────────────────
    const sidebar   = document.querySelector('.sidebar');
    const toggleBtn = document.getElementById('sidebarToggle');

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', function () {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        });
    }

    if (sidebar && localStorage.getItem('sidebarCollapsed') === 'true') {
        sidebar.classList.add('collapsed');
    }

    // ── Mobile sidebar ─────────────────────────────────────────────────
    if (sidebar && window.innerWidth <= 768) {
        const mobileToggle = document.createElement('button');
        mobileToggle.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M3 12H21M3 6H21M3 18H21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
        mobileToggle.className = 'mobile-menu-toggle';
        mobileToggle.style.cssText = `
            position:fixed; bottom:1.25rem; right:1.25rem;
            width:46px; height:46px; border-radius:50%;
            background:var(--brand-orange); border:none; color:white;
            cursor:pointer; display:flex; align-items:center; justify-content:center;
            z-index:1000; box-shadow:0 4px 14px rgba(242,106,27,0.4);
        `;
        document.body.appendChild(mobileToggle);

        mobileToggle.addEventListener('click', () => sidebar.classList.toggle('mobile-open'));

        document.addEventListener('click', (e) => {
            if (!sidebar.contains(e.target) && !mobileToggle.contains(e.target)) {
                sidebar.classList.remove('mobile-open');
            }
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

    // ── LOGO SHINE ─────────────────────────────────────────────────────
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