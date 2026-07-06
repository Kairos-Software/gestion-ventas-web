// fullscreen-persist.js — Kai-Cart
//
// LIMITACIÓN DEL NAVEGADOR (no es un bug nuestro):
// requestFullscreen() exige una "activación transitoria" del usuario
// (un click/tecla muy reciente). Esa activación se pierde al navegar a
// un documento nuevo, incluso si la navegación ocurrió justo después de
// un click real. Por spec, ningún sitio puede reactivar fullscreen en
// silencio tras un full page load — la única forma 100% fiable es no
// recargar el documento (SPA), que es un cambio de arquitectura grande.
//
// Mitigación: si veníamos en fullscreen antes de navegar, mostramos un
// aviso con un botón "Reanudar" apenas carga la página nueva. Un click
// del usuario SÍ cuenta como activación válida, así que esto funciona
// siempre, en cualquier navegador.

(function () {
    const FS_FLAG = 'fsPersist';

    function isFullscreenActive() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement ||
                   document.mozFullScreenElement || document.msFullscreenElement);
    }

    function enterFullscreen() {
        const el = document.documentElement;
        const req = el.requestFullscreen || el.webkitRequestFullscreen ||
                    el.mozRequestFullScreen || el.msRequestFullscreen;
        if (!req) return Promise.reject(new Error('Fullscreen no soportado'));
        return req.call(el);
    }

    function mostrarBannerReanudar() {
        const banner = document.createElement('div');
        banner.className = 'fs-resume-banner';
        banner.innerHTML =
            '<span>Estabas en pantalla completa</span>' +
            '<button type="button">Reanudar</button>';
        document.body.appendChild(banner);

        function ocultar() {
            clearTimeout(autoOcultar);
            banner.classList.remove('visible');
            setTimeout(function () { banner.remove(); }, 300);
        }

        banner.querySelector('button').addEventListener('click', function () {
            enterFullscreen().catch(function () { /* el usuario canceló el permiso */ });
            ocultar();
        });

        requestAnimationFrame(function () { banner.classList.add('visible'); });
        const autoOcultar = setTimeout(ocultar, 7000);
    }

    document.addEventListener('DOMContentLoaded', function () {
        // Marcar antes de cualquier navegación interna (sidebar) si estamos
        // actualmente en fullscreen.
        document.querySelectorAll('.sidebar-nav a').forEach(function (link) {
            link.addEventListener('click', function () {
                if (isFullscreenActive()) sessionStorage.setItem(FS_FLAG, '1');
            });
        });

        // Si venimos de una navegación interna con fullscreen activo,
        // ofrecer reanudarlo con un click.
        if (sessionStorage.getItem(FS_FLAG) === '1') {
            sessionStorage.removeItem(FS_FLAG);
            mostrarBannerReanudar();
        }
    });
})();