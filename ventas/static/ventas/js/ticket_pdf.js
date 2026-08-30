/**
 * ticket_pdf.js
 * ─────────────────────────────────────────────────────────────────
 * "Guardar PDF" — arma el PDF del ticket/comprobante en el navegador y
 * lo descarga directo, SIN pasar por el diálogo de impresión.
 *
 * Por qué: el diálogo del navegador recuerda el último destino usado.
 * Si la última vez se imprimió en papel, al querer un PDF había que
 * cambiar el destino a mano (y al revés). Con un botón propio, "Guardar
 * PDF" siempre da un archivo y "Imprimir" siempre abre la impresora.
 *
 * Reusa los MISMOS generadores de HTML del ticket (ticket_a4.js,
 * ticket_termica_80/58.js) — una sola fuente de verdad para el diseño.
 * El HTML se rasteriza con html2canvas y se arma el PDF con jsPDF.
 *
 * Las dos librerías (~560 KB juntas) se cargan perezosamente: recién
 * la primera vez que se toca "Guardar PDF". Las rutas vienen en
 * window.TICKET_VENDOR (las pone el template que carga este script).
 *
 * Depende de: window.TICKET_DATA y ticketHtml{A4,Termica80,Termica58}.
 * Lo llama ticket_imprimir.js cuando el selector de formato se abrió
 * en modo "pdf" (ver ticketAbrirSelector).
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

/* ════════════════════════════════════════════════════════════════
   CARGA PEREZOSA DE LAS LIBRERÍAS
════════════════════════════════════════════════════════════════ */
let _pdfLibsPromise = null;

function _pdfCargarScript(src) {
    return new Promise((resolve, reject) => {
        if (!src) { reject(new Error('ruta de librería no configurada en window.TICKET_VENDOR')); return; }
        const s = document.createElement('script');
        s.src = src;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error('no se pudo cargar ' + src));
        document.head.appendChild(s);
    });
}

function _pdfAsegurarLibs() {
    if (window.jspdf && window.html2canvas) return Promise.resolve();
    if (_pdfLibsPromise) return _pdfLibsPromise;
    const v = window.TICKET_VENDOR || {};
    _pdfLibsPromise = _pdfCargarScript(v.html2canvas)
        .then(() => _pdfCargarScript(v.jspdf))
        .catch(err => { _pdfLibsPromise = null; throw err; });
    return _pdfLibsPromise;
}

/* ════════════════════════════════════════════════════════════════
   GENERAR Y DESCARGAR
════════════════════════════════════════════════════════════════ */

// px por mm a 96 dpi — para pasar el alto real del ticket térmico
// (medido en px de pantalla) a milímetros de página PDF.
const _PX_POR_MM = 96 / 25.4;

// Ancho de render en px, por formato — el ANCHO EXACTO con el que está
// diseñado cada ticket (a 96 dpi): A4 210mm, térmica 72mm / 48mm (ver
// `html,body { width }` en cada generador). El alto lo mide el contenido.
const _PDF_ANCHO_IFRAME = { a4: 794, termica80: 272, termica58: 182 };

function _pdfGenerador(formato) {
    if (formato === 'a4')        return typeof ticketHtmlA4 === 'function' ? ticketHtmlA4 : null;
    if (formato === 'termica80') return typeof ticketHtmlTermica80 === 'function' ? ticketHtmlTermica80 : null;
    if (formato === 'termica58') return typeof ticketHtmlTermica58 === 'function' ? ticketHtmlTermica58 : null;
    return null;
}

/**
 * @param {string} formato  'a4' | 'termica80' | 'termica58'
 * @param {boolean} soloTicket  igual que en ticketImprimir(): imprime
 *   como ticket simple (sin CAE/QR) aunque haya comprobante ARCA.
 */
async function ticketGuardarPdf(formato, soloTicket) {
    _ticketCerrarSelector();

    if (!window.TICKET_DATA) {
        console.error('ticket_pdf.js: window.TICKET_DATA no está definido.');
        return;
    }
    const generador = _pdfGenerador(formato);
    if (!generador) {
        console.error(`ticket_pdf.js: generador para "${formato}" no disponible.`);
        return;
    }

    const aviso = (window.KaiToast && KaiToast.show)
        ? KaiToast.show('Generando PDF…', 'info', 0)
        : null;

    try {
        await _pdfAsegurarLibs();

        if (!soloTicket && window.TICKET_DATA.comprobante_arca && window.TICKET_DATA.comprobante_arca.qrReadyPromise) {
            await window.TICKET_DATA.comprobante_arca.qrReadyPromise;
        }

        const data = soloTicket ? { ...window.TICKET_DATA, comprobante_arca: null } : window.TICKET_DATA;
        const html = generador(data, { sinAutoImpresion: true });

        const canvas = await _pdfRasterizar(html, _PDF_ANCHO_IFRAME[formato] || 794);

        const { jsPDF } = window.jspdf;
        let pdf;
        if (formato === 'a4') {
            pdf = new jsPDF({ unit: 'mm', format: 'a4', compress: true });
            _pdfPegarMultipagina(pdf, canvas, 210, 297);
        } else {
            const escala  = canvas._escala || 1;
            const anchoMm = canvas.width  / escala / _PX_POR_MM;
            const altoMm  = canvas.height / escala / _PX_POR_MM;
            pdf = new jsPDF({ unit: 'mm', format: [anchoMm, altoMm], compress: true });
            pdf.addImage(canvas, 'PNG', 0, 0, anchoMm, altoMm, undefined, 'FAST');
        }
        pdf.save(_pdfNombreArchivo(data));
    } catch (err) {
        console.error('ticket_pdf.js:', err);
        if (window.KaiToast && KaiToast.show) {
            KaiToast.show('No se pudo generar el PDF. ' + (err.message || ''), 'danger', 6000);
        }
    } finally {
        if (aviso) aviso.querySelector('.kai-toast-close')?.click();
    }
}

/* ════════════════════════════════════════════════════════════════
   RASTERIZADO — render del HTML del ticket en un iframe oculto
════════════════════════════════════════════════════════════════ */
async function _pdfRasterizar(html, anchoIframePx) {
    const iframe = document.createElement('iframe');
    iframe.setAttribute('aria-hidden', 'true');
    iframe.style.cssText =
        `position:fixed; left:-10000px; top:0; border:0; ` +
        `width:${anchoIframePx}px; height:100px; background:#fff;`;
    document.body.appendChild(iframe);

    try {
        const doc = iframe.contentDocument;
        doc.open();
        doc.write(html);
        doc.close();

        await _pdfEsperarIframe(iframe);

        const objetivo = doc.body;
        const alto = Math.max(objetivo.scrollHeight, doc.documentElement.scrollHeight, 1);

        const canvas = await window.html2canvas(objetivo, {
            scale: 2,
            backgroundColor: '#ffffff',
            useCORS: true,
            allowTaint: false,
            logging: false,
            windowWidth: anchoIframePx,
            windowHeight: alto,
            width: anchoIframePx,
            height: alto,
        });
        canvas._escala = 2;
        return canvas;
    } finally {
        iframe.remove();
    }
}

// Espera a que el iframe termine el layout y a que carguen sus
// imágenes (logo del comercio, QR del comprobante). Nunca cuelga más
// de 4s.
function _pdfEsperarIframe(iframe) {
    return new Promise(resolve => {
        const win = iframe.contentWindow;
        const doc = iframe.contentDocument;
        let listo = false;
        const terminar = () => { if (listo) return; listo = true; resolve(); };

        function esperarImagenes() {
            const imgs = Array.from(doc.images || []);
            return Promise.all(imgs.map(img => img.complete
                ? Promise.resolve()
                : new Promise(res => {
                    img.addEventListener('load', res, { once: true });
                    img.addEventListener('error', res, { once: true });
                })));
        }

        function cuandoCargue() {
            esperarImagenes().then(() => {
                // dos rAF: deja que el navegador aplique el layout final
                win.requestAnimationFrame(() => win.requestAnimationFrame(terminar));
            });
        }

        if (doc.readyState === 'complete') cuandoCargue();
        else win.addEventListener('load', cuandoCargue, { once: true });

        setTimeout(terminar, 4000);
    });
}

/* ════════════════════════════════════════════════════════════════
   ARMADO DEL PDF
════════════════════════════════════════════════════════════════ */

// A4: la imagen del ticket puede ser más alta que una hoja — se pega
// la misma imagen desplazada hacia arriba en cada página nueva.
function _pdfPegarMultipagina(pdf, canvas, anchoPagMm, altoPagMm) {
    const imgAltoMm = canvas.height * anchoPagMm / canvas.width;
    let posicion = 0;
    let restante = imgAltoMm;

    pdf.addImage(canvas, 'PNG', 0, posicion, anchoPagMm, imgAltoMm, undefined, 'FAST');
    restante -= altoPagMm;

    while (restante > 0.5) {
        posicion -= altoPagMm;
        pdf.addPage();
        pdf.addImage(canvas, 'PNG', 0, posicion, anchoPagMm, imgAltoMm, undefined, 'FAST');
        restante -= altoPagMm;
    }
}

function _pdfNombreArchivo(data) {
    const v = (data && data.venta) || {};
    const cbte = data && data.comprobante_arca;
    let base = cbte
        ? `${cbte.tipo_display || 'Comprobante'} ${cbte.numero_display || ''}`
        : `Ticket ${v.numero || ''}`;
    base = base.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim();
    return (base || 'ticket') + '.pdf';
}
