/* core/static/core/js/manual.js
   Resalta en el índice (TOC) sticky la sección del manual que se está viendo.
*/
document.addEventListener('DOMContentLoaded', function () {
    const nav = document.getElementById('manualToc');
    if (!nav) return;

    const links = Array.from(nav.querySelectorAll('a'));
    const secciones = links
        .map(a => document.getElementById(a.getAttribute('href').slice(1)))
        .filter(Boolean);

    if (!secciones.length || !('IntersectionObserver' in window)) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            links.forEach(a => a.classList.remove('is-active'));
            const link = nav.querySelector(`a[href="#${entry.target.id}"]`);
            if (link) {
                link.classList.add('is-active');
                link.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            }
        });
    }, { rootMargin: '-15% 0px -70% 0px' });

    secciones.forEach(sec => observer.observe(sec));
});
