// home.js — Kai-Cart
document.addEventListener('DOMContentLoaded', function () {

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