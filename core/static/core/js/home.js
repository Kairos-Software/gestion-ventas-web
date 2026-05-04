// home.js — Kai-Cart
document.addEventListener('DOMContentLoaded', function () {

    // ── Activity Tabs ────────────────────────────────────────────────
    const tabBtns = document.querySelectorAll('.tab-btn');
    const clientesList = document.getElementById('activityClientes');
    const usuariosList = document.getElementById('activityUsuarios');

    if (tabBtns.length) {
        tabBtns.forEach(btn => {
            btn.addEventListener('click', function () {
                const tab = this.dataset.tab;
                tabBtns.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                if (clientesList && usuariosList) {
                    if (tab === 'clientes') {
                        clientesList.style.display = 'block';
                        usuariosList.style.display = 'none';
                    } else {
                        clientesList.style.display = 'none';
                        usuariosList.style.display = 'block';
                    }
                }
            });
        });
    }

    // ── Stat Cards staggered reveal ──────────────────────────────────
    const statCards = document.querySelectorAll('.stat-card');
    statCards.forEach((card, index) => {
        setTimeout(() => {
            card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            card.classList.add('animated');
        }, index * 90);
    });

    // ── Module Cards staggered reveal ───────────────────────────────
    const moduleCards = document.querySelectorAll('.module-card');
    moduleCards.forEach((card, index) => {
        setTimeout(() => {
            card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            card.classList.add('animated');
        }, 280 + index * 70);
    });
});