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

// 'imprimir' → window.print() (abre la impresora del navegador)
// 'pdf'      → ticket_pdf.js genera el archivo y lo descarga directo
let _ticketModo = 'imprimir';

/**
 * Muestra el modal selector de formato.
 * @param {string} [modo]  'imprimir' (default) | 'pdf'
 */
function ticketAbrirSelector(modo) {
    _ticketModo = modo === 'pdf' ? 'pdf' : 'imprimir';

    const overlay = document.getElementById('ticketSelectorOverlay');
    if (!overlay) {
        console.error('ticket_imprimir.js: no se encontró #ticketSelectorOverlay en el DOM.');
        return;
    }

    // El mismo modal sirve para imprimir y para guardar PDF — cambia
    // solo el texto según con qué botón se abrió.
    const titulo = document.getElementById('ticketSelectorTitulo');
    const sub    = document.getElementById('ticketSelectorSub');
    if (titulo) titulo.textContent = _ticketModo === 'pdf' ? 'Elegir formato del PDF' : 'Elegir formato de impresión';
    if (sub)    sub.textContent    = _ticketModo === 'pdf'
        ? 'Seleccioná el tamaño de página del archivo.'
        : 'Seleccioná el tipo de papel/impresora que vas a usar.';
    // El checkbox "imprimir como ticket simple" solo tiene sentido si la
    // venta tiene de verdad un comprobante ARCA — si no, ya imprime como
    // ticket simple por default, no hace falta ofrecer la opción.
    const wrapSoloTicket = document.getElementById('ticketSoloTicketWrap');
    if (wrapSoloTicket) {
        wrapSoloTicket.style.display = (window.TICKET_DATA && window.TICKET_DATA.comprobante_arca) ? 'flex' : 'none';
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
 * @param {boolean} soloTicket  Si es true, imprime como ticket simple
 *   (sin CAE/QR/desglose de IVA) aunque la venta tenga un comprobante
 *   ARCA real de verdad — la factura ya se emitió electrónicamente de
 *   todas formas, esto solo cambia qué se IMPRIME en papel. No toca
 *   window.TICKET_DATA (se arma una copia), para que la próxima
 *   impresión pueda volver a mostrar los datos fiscales sin recargar.
 */
async function ticketImprimir(formato, soloTicket) {
    _ticketCerrarSelector();

    if (!window.TICKET_DATA) {
        console.error('ticket_imprimir.js: window.TICKET_DATA no está definido.');
        return;
    }

    // Si hay comprobante ARCA, el QR se genera en la página (ver
    // detalle_venta.html) de forma asíncrona — hay que esperar a que
    // esté listo antes de armar el HTML del ticket, si no puede abrirse
    // sin QR por una carrera de tiempos (CDN todavía cargando). Si se
    // pidió "solo ticket", el QR no se va a mostrar — no hace falta
    // esperarlo.
    if (!soloTicket && window.TICKET_DATA.comprobante_arca && window.TICKET_DATA.comprobante_arca.qrReadyPromise) {
        await window.TICKET_DATA.comprobante_arca.qrReadyPromise;
    }

    const data = soloTicket ? { ...window.TICKET_DATA, comprobante_arca: null } : window.TICKET_DATA;

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
        KaiToast.show('El navegador bloqueó la ventana de impresión. Permití popups para este sitio e intentá de nuevo.', 'warning', 6000);
        return;
    }

    ventana.document.write(html);
    ventana.document.close();
}

/* ════════════════════════════════════════════════════════════════
   BIND DE EVENTOS — delegado en document
   ──────────────────────────────────────────────────────────────
   Delegado (no bind directo en DOMContentLoaded) porque en el panel
   flotante de cobro (/ventas/nueva/) el #ticketSelectorOverlay se
   inyecta por AJAX DESPUÉS de que carga la página — un bind directo
   se lo perdería. En la página completa /ventas/detalle/ el overlay
   ya está en el DOM y funciona igual.
════════════════════════════════════════════════════════════════ */
document.addEventListener('click', e => {
    // Cerrar al hacer click en el overlay (fuera del modal)
    const overlay = e.target.closest('#ticketSelectorOverlay');
    if (overlay && e.target === overlay) { _ticketCerrarSelector(); return; }

    // Botón cerrar (✕)
    if (e.target.closest('#ticketSelectorCerrar')) { _ticketCerrarSelector(); return; }

    // Botones de formato
    const btnFormato = e.target.closest('[data-ticket-formato]');
    if (btnFormato) {
        const chkSoloTicket = document.getElementById('ticketSoloTicket');
        const soloTicket = !!(chkSoloTicket && chkSoloTicket.checked);
        const formato = btnFormato.dataset.ticketFormato;
        if (_ticketModo === 'pdf' && typeof ticketGuardarPdf === 'function') {
            ticketGuardarPdf(formato, soloTicket);
        } else {
            ticketImprimir(formato, soloTicket);
        }
    }
});