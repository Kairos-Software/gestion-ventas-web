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

    // ── Acciones primarias: reveal escalonado ────────────────────────
    const ctaCards = document.querySelectorAll('.home-cta');
    ctaCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(10px)';
        setTimeout(() => {
            card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 80);
    });
});