/** Selector común A4 / térmica 80 mm / térmica 58 mm. */
'use strict';

(function () {
    let alElegir = null;
    let focoAnterior = null;

    function obtenerOverlay() {
        return document.getElementById('kaiPrintSelector');
    }

    function cerrar(restaurarFoco = true) {
        const overlay = obtenerOverlay();
        if (!overlay || overlay.hidden) return;
        overlay.hidden = true;
        document.body.classList.remove('kps-open');
        alElegir = null;
        if (restaurarFoco && focoAnterior && typeof focoAnterior.focus === 'function') {
            focoAnterior.focus();
        }
        focoAnterior = null;
    }

    function abrir(opciones) {
        const overlay = obtenerOverlay();
        if (!overlay) {
            console.error('selector_impresion.js: falta #kaiPrintSelector en la página.');
            return false;
        }

        const config = opciones || {};
        if (typeof config.alElegir !== 'function') return false;

        focoAnterior = document.activeElement;
        alElegir = config.alElegir;
        const titulo = overlay.querySelector('#kaiPrintSelectorTitulo');
        const descripcion = overlay.querySelector('#kaiPrintSelectorDescripcion');
        if (titulo) titulo.textContent = config.titulo || 'Elegir formato de impresión';
        if (descripcion) {
            descripcion.textContent = config.descripcion || 'Seleccioná el tipo de papel o impresora que vas a usar.';
        }

        overlay.hidden = false;
        document.body.classList.add('kps-open');
        requestAnimationFrame(() => overlay.querySelector('[data-kps-formato]')?.focus());
        return true;
    }

    document.addEventListener('click', (e) => {
        const overlay = obtenerOverlay();
        if (!overlay || overlay.hidden) return;

        if (e.target === overlay || e.target.closest('[data-kps-cerrar]')) {
            cerrar();
            return;
        }

        const boton = e.target.closest('[data-kps-formato]');
        if (!boton || !overlay.contains(boton)) return;
        const callback = alElegir;
        const formato = boton.dataset.kpsFormato;
        cerrar(false);
        if (callback) callback(formato);
    });

    document.addEventListener('keydown', (e) => {
        const overlay = obtenerOverlay();
        if (e.key === 'Escape' && overlay && !overlay.hidden) {
            e.preventDefault();
            cerrar();
        }
    });

    window.KaiPrintSelector = { abrir, cerrar };
})();
