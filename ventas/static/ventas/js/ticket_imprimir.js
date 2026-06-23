/**
 * ticket_imprimir.js
 * ─────────────────────────────────────────────────────────────────
 * Controlador central de impresión de tickets.
 *
 * Responsabilidades:
 *   - Mostrar el selector de formato (A4 / térmica 80mm / térmica 58mm)
 *   - Recibir los datos del ticket desde la página (window.TICKET_DATA)
 *   - Llamar al generador de HTML correspondiente (ticket_a4.js,
 *     ticket_termica_80.js, ticket_termica_58.js)
 *   - Abrir la ventana de impresión con ese HTML
 *
 * Dependencias (deben cargarse antes en el template):
 *   ticket_a4.js          → función ticketHtmlA4(data)
 *   ticket_termica_80.js  → función ticketHtmlTermica80(data)
 *   ticket_termica_58.js  → función ticketHtmlTermica58(data)
 *
 * Uso desde detalle_venta.js:
 *   vdtImprimirTicket()  →  llama a ticketAbrirSelector()
 *
 * window.TICKET_DATA debe estar definido antes de llamar a
 * ticketAbrirSelector(). Se construye en detalle_venta.html
 * con datos de Django (ver bloque #ticket-data-json).
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

/* ════════════════════════════════════════════════════════════════
   SELECTOR DE FORMATO
════════════════════════════════════════════════════════════════ */

/**
 * Muestra el modal selector de formato de impresión.
 * Es la función que debe llamar el botón "Imprimir" de la página.
 */
function ticketAbrirSelector() {
    const overlay = document.getElementById('ticketSelectorOverlay');
    if (!overlay) {
        console.error('ticket_imprimir.js: no se encontró #ticketSelectorOverlay en el DOM.');
        return;
    }
    overlay.style.display = 'flex';
}

function _ticketCerrarSelector() {
    const overlay = document.getElementById('ticketSelectorOverlay');
    if (overlay) overlay.style.display = 'none';
}

/* ════════════════════════════════════════════════════════════════
   IMPRIMIR
════════════════════════════════════════════════════════════════ */

/**
 * Obtiene el generador correspondiente al formato elegido,
 * genera el HTML del ticket y lo abre en una ventana nueva
 * que dispara automáticamente el diálogo de impresión.
 *
 * @param {string} formato  'a4' | 'termica80' | 'termica58'
 */
function ticketImprimir(formato) {
    _ticketCerrarSelector();

    const data = window.TICKET_DATA;
    if (!data) {
        console.error('ticket_imprimir.js: window.TICKET_DATA no está definido.');
        return;
    }

    // Seleccionar el generador según el formato
    let htmlGenerador;
    if (formato === 'a4') {
        if (typeof ticketHtmlA4 !== 'function') {
            console.error('ticket_imprimir.js: ticketHtmlA4 no está disponible. ¿Cargaste ticket_a4.js?');
            return;
        }
        htmlGenerador = ticketHtmlA4;
    } else if (formato === 'termica80') {
        if (typeof ticketHtmlTermica80 !== 'function') {
            console.error('ticket_imprimir.js: ticketHtmlTermica80 no está disponible. ¿Cargaste ticket_termica_80.js?');
            return;
        }
        htmlGenerador = ticketHtmlTermica80;
    } else if (formato === 'termica58') {
        if (typeof ticketHtmlTermica58 !== 'function') {
            console.error('ticket_imprimir.js: ticketHtmlTermica58 no está disponible. ¿Cargaste ticket_termica_58.js?');
            return;
        }
        htmlGenerador = ticketHtmlTermica58;
    } else {
        console.error(`ticket_imprimir.js: formato desconocido "${formato}".`);
        return;
    }

    const html = htmlGenerador(data);
    _abrirVentanaImpresion(html);
}

/**
 * Abre una ventana auxiliar con el HTML del ticket
 * y dispara el diálogo de impresión del navegador.
 * El usuario puede imprimir físicamente o elegir "Guardar como PDF".
 *
 * @param {string} html  HTML completo del ticket (generado por el módulo de formato)
 */
function _abrirVentanaImpresion(html) {
    const ventana = window.open('', '_blank', 'width=750,height=950');
    if (!ventana) {
        // Si el navegador bloquea el popup, notificar al usuario.
        // La función vdtToast puede no existir fuera del contexto de detalle_venta.js,
        // así que usamos alert como fallback.
        if (typeof vdtToast === 'function') {
            vdtToast('Popup bloqueado', 'Permitir popups para este sitio y volver a intentarlo.');
        } else {
            alert('El navegador bloqueó la ventana de impresión.\nPermitir popups para este sitio e intentar de nuevo.');
        }
        return;
    }

    ventana.document.write(html);
    ventana.document.close();
}

/* ════════════════════════════════════════════════════════════════
   BIND DE EVENTOS AL CARGAR EL DOM
════════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {

    // Cerrar al hacer click en el overlay (fuera del modal)
    const overlay = document.getElementById('ticketSelectorOverlay');
    if (overlay) {
        overlay.addEventListener('click', e => {
            if (e.target === overlay) _ticketCerrarSelector();
        });
    }

    // Botón cerrar (✕)
    const btnCerrar = document.getElementById('ticketSelectorCerrar');
    if (btnCerrar) btnCerrar.addEventListener('click', _ticketCerrarSelector);

    // Botones de formato
    document.querySelectorAll('[data-ticket-formato]').forEach(btn => {
        btn.addEventListener('click', () => {
            ticketImprimir(btn.dataset.ticketFormato);
        });
    });
});