/**
 * factura_inicial_pdf.js
 * ─────────────────────────────────────────────────────────────────
 * Salida del comprobante de la herramienta Factura inicial:
 *
 *   facturaInicialDescargarPdf(html, data) → baja un .pdf (rasteriza el
 *       HTML A4 con jsPDF + html2canvas, sin diálogo de impresión).
 *   facturaInicialImprimir(html) → manda el HTML A4 directo al diálogo
 *       de impresión del navegador (impresora física o "Guardar como
 *       PDF"), vía un iframe oculto — no abre ventana nueva, así no lo
 *       frena el bloqueador de popups.
 *
 * jsPDF + html2canvas se cargan perezosamente desde window.FI_VENDOR
 * (los pone el template — son los mismos vendoreados de Ventas).
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

let _fiPdfLibs = null;

function _fiCargarScript(src) {
    return new Promise((resolve, reject) => {
        if (!src) { reject(new Error('ruta de librería no configurada (window.FI_VENDOR)')); return; }
        const s = document.createElement('script');
        s.src = src;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error('no se pudo cargar ' + src));
        document.head.appendChild(s);
    });
}

function _fiAsegurarLibs() {
    if (window.jspdf && window.html2canvas) return Promise.resolve();
    if (_fiPdfLibs) return _fiPdfLibs;
    const v = window.FI_VENDOR || {};
    _fiPdfLibs = _fiCargarScript(v.html2canvas)
        .then(() => _fiCargarScript(v.jspdf))
        .catch(err => { _fiPdfLibs = null; throw err; });
    return _fiPdfLibs;
}

// Ancho de render del A4 a 96 dpi: 210 mm ≈ 794 px.
const _FI_ANCHO_PX = 794;

async function _fiRasterizar(html) {
    const iframe = document.createElement('iframe');
    iframe.setAttribute('aria-hidden', 'true');
    iframe.style.cssText =
        `position:fixed; left:-10000px; top:0; border:0; width:${_FI_ANCHO_PX}px; height:100px; background:#fff;`;
    document.body.appendChild(iframe);
    try {
        const doc = iframe.contentDocument;
        doc.open(); doc.write(html); doc.close();
        await _fiEsperarIframe(iframe);
        const alto = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight, 1);
        const canvas = await window.html2canvas(doc.body, {
            scale: 2,
            backgroundColor: '#ffffff',
            useCORS: true,
            logging: false,
            windowWidth: _FI_ANCHO_PX,
            windowHeight: alto,
            width: _FI_ANCHO_PX,
            height: alto,
        });
        return canvas;
    } finally {
        iframe.remove();
    }
}

function _fiEsperarIframe(iframe) {
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
                win.requestAnimationFrame(() => win.requestAnimationFrame(terminar));
            });
        }
        if (doc.readyState === 'complete') cuandoCargue();
        else win.addEventListener('load', cuandoCargue, { once: true });
        setTimeout(terminar, 4000);
    });
}

function _fiPegarMultipagina(pdf, canvas, anchoPagMm, altoPagMm) {
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

function _fiNombreArchivo(data) {
    const c = (data && data.comprobante) || {};
    let base = `${c.titulo || 'Comprobante'} ${c.letra || ''} ${c.numero || ''}`;
    base = base.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim();
    return 'Factura inicial - ' + (base || 'comprobante') + '.pdf';
}

async function facturaInicialDescargarPdf(html, data) {
    await _fiAsegurarLibs();
    const canvas = await _fiRasterizar(html);
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF({ unit: 'mm', format: 'a4', compress: true });
    _fiPegarMultipagina(pdf, canvas, 210, 297);
    pdf.save(_fiNombreArchivo(data));
}

/**
 * Manda el HTML A4 directo al diálogo de impresión del navegador.
 * Usa un iframe oculto (no window.open) para que no lo bloquee el
 * navegador. Espera a que el documento y sus imágenes carguen, dispara
 * print() y limpia el iframe cuando termina.
 *
 * @param {string} html  HTML completo del comprobante (facturaInicialHtmlA4)
 * @returns {Promise<void>}
 */
function facturaInicialImprimir(html) {
    return new Promise(resolve => {
        const iframe = document.createElement('iframe');
        iframe.setAttribute('aria-hidden', 'true');
        iframe.style.cssText =
            'position:fixed; right:0; bottom:0; width:0; height:0; border:0; visibility:hidden;';
        document.body.appendChild(iframe);

        let terminado = false;
        const limpiar = () => {
            if (terminado) return;
            terminado = true;
            setTimeout(() => iframe.remove(), 800);
            resolve();
        };

        const doc = iframe.contentDocument;
        doc.open();
        // Sin el auto-print embebido: lo dispara este helper cuando el
        // contenido (incluidas imágenes) terminó de cargar.
        doc.write(html.replace(/<script[\s\S]*?<\/script>/gi, ''));
        doc.close();

        const disparar = () => {
            const win = iframe.contentWindow;
            const imgs = Array.from(doc.images || []);
            Promise.all(imgs.map(img => img.complete ? null : new Promise(r => {
                img.addEventListener('load', r, { once: true });
                img.addEventListener('error', r, { once: true });
            }))).then(() => {
                win.focus();
                win.addEventListener('afterprint', limpiar, { once: true });
                try { win.print(); } catch (e) { limpiar(); return; }
                // Fallback si 'afterprint' no dispara (algunos navegadores).
                setTimeout(limpiar, 60000);
            });
        };

        if (doc.readyState === 'complete') disparar();
        else iframe.contentWindow.addEventListener('load', disparar, { once: true });
    });
}
