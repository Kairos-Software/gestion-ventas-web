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
 *
 * También cubre Notas de Crédito: si el selector se abrió apuntando a
 * una NC puntual (_ticketObjetivoNC, ver ticket_imprimir.js), usa los
 * generadores de ticket_nc.js (ncHtml{A4,Termica80,Termica58}) en vez
 * de los del ticket de venta — ver _pdfGuardarNC() más abajo.
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

// Mismo mapeo que _pdfGenerador(), pero para los generadores de Nota de
// Crédito (ticket_nc.js) — ver la rama NC al principio de ticketGuardarPdf().
function _pdfGeneradorNC(formato) {
    if (formato === 'a4')        return typeof ncHtmlA4 === 'function' ? ncHtmlA4 : null;
    if (formato === 'termica80') return typeof ncHtmlTermica80 === 'function' ? ncHtmlTermica80 : null;
    if (formato === 'termica58') return typeof ncHtmlTermica58 === 'function' ? ncHtmlTermica58 : null;
    return null;
}

// html2canvas con foreignObjectRendering (necesario para que el texto y los
// íconos SVG del encabezado no se desplacen — ver _pdfRasterizar) no logra
// dibujar imágenes que sean una URL externa: solo renderiza bien imágenes
// ya embebidas como data: URI. El QR ya viaja como data: URI (qrDataUrl),
// pero el logo de la empresa es una URL real del servidor — por eso al
// imprimir (motor normal del navegador) el logo se ve bien, pero al
// "Guardar PDF" (rasterizado con html2canvas) desaparecía. Se descarga acá
// y se reemplaza por su propio data: URI antes de armar el HTML a rasterizar.
async function _pdfImagenComoDataUri(url) {
    if (!url || url.startsWith('data:')) return url;
    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        return await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(blob);
        });
    } catch (err) {
        console.warn('ticket_pdf.js: no se pudo incrustar el logo en el PDF, se omite.', err);
        return null;
    }
}

async function _pdfConLogoEmbebido(data) {
    const logoUrl = data.empresa && data.empresa.logo_url;
    if (!logoUrl || logoUrl.startsWith('data:')) return data;
    const logoDataUri = await _pdfImagenComoDataUri(logoUrl);
    return { ...data, empresa: { ...data.empresa, logo_url: logoDataUri || '' } };
}

/**
 * @param {string} formato  'a4' | 'termica80' | 'termica58'
 * @param {boolean} soloTicket  igual que en ticketImprimir(): imprime
 *   como ticket simple (sin CAE/QR) aunque haya comprobante ARCA.
 *   Ignorado cuando el objetivo es una Nota de Crédito (ver _ticketObjetivoNC
 *   en ticket_imprimir.js) — una NC siempre es un comprobante fiscal.
 * @param {boolean} esDuplicado  igual que en ticketImprimir(): aclara
 *   "Duplicado" en vez de "Original" en el ticket A4 (ver ticket_a4.js).
 */
async function ticketGuardarPdf(formato, soloTicket, esDuplicado) {
    const objetivoNC = _ticketObjetivoNC;  // capturar ANTES de cerrar el selector (lo resetea a null)
    _ticketCerrarSelector();

    if (objetivoNC) {
        await _pdfGuardarNC(objetivoNC, formato, esDuplicado);
        return;
    }

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

        let data = soloTicket ? { ...window.TICKET_DATA, comprobante_arca: null } : window.TICKET_DATA;
        data = await _pdfConLogoEmbebido(data);
        const html = generador(data, { sinAutoImpresion: true, duplicado: !!esDuplicado });

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
   GUARDAR PDF — RAMA NOTA DE CRÉDITO
   ──────────────────────────────────────────────────────────────
   ncHtmlA4/Termica80/58 (ticket_nc.js) no usan logo de empresa (a
   diferencia de ticketHtmlA4) — solo texto —, así que no hace falta la
   incrustación de imagen que sí necesita _pdfConLogoEmbebido() más arriba.
════════════════════════════════════════════════════════════════ */
async function _pdfGuardarNC(objetivoNC, formato, esDuplicado) {
    if (objetivoNC.nc && objetivoNC.nc.qrReadyPromise) {
        await objetivoNC.nc.qrReadyPromise;
    }

    const generador = _pdfGeneradorNC(formato);
    if (!generador) {
        console.error(`ticket_pdf.js: generador de Nota de Crédito para "${formato}" no disponible. ¿Cargaste ticket_nc.js?`);
        return;
    }

    const aviso = (window.KaiToast && KaiToast.show)
        ? KaiToast.show('Generando PDF…', 'info', 0)
        : null;

    try {
        await _pdfAsegurarLibs();

        const html = generador(objetivoNC, { sinAutoImpresion: true, duplicado: !!esDuplicado });
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
        pdf.save(_pdfNombreArchivoNC(objetivoNC));
    } catch (err) {
        console.error('ticket_pdf.js:', err);
        if (window.KaiToast && KaiToast.show) {
            KaiToast.show('No se pudo generar el PDF. ' + (err.message || ''), 'danger', 6000);
        }
    } finally {
        if (aviso) aviso.querySelector('.kai-toast-close')?.click();
    }
}

function _pdfNombreArchivoNC(objetivoNC) {
    const nc = objetivoNC && objetivoNC.nc;
    let base = nc ? `${nc.tipo_display || 'Nota de Credito'} ${nc.numero_display || ''}` : 'Nota de Credito';
    base = base.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim();
    return (base || 'nota-de-credito') + '.pdf';
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
            // El renderer propio de html2canvas recalcula las métricas de
            // texto y SVG: en Chrome desplazaba la letra del comprobante y
            // los iconos de contacto aunque el HTML de impresión estuviera
            // bien. ForeignObject deja que el mismo motor del navegador
            // pinte el DOM, conservando el layout que se ve en Imprimir.
            foreignObjectRendering: true,
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

// Espera a que el iframe termine el layout, a que carguen sus imágenes
// (logo del comercio, QR del comprobante) y a que las fuentes estén
// listas. Nunca cuelga más de 4s.
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
            const fuentes = doc.fonts && doc.fonts.ready
                ? doc.fonts.ready.catch(() => undefined)
                : Promise.resolve();
            Promise.all([esperarImagenes(), fuentes]).then(() => {
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
