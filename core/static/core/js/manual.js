/* core/static/core/js/manual.js
   Manual de usuario:
   - Índice: arma el sub-índice de cada sección con sus <h3>, resalta la
     sección/subtema visible y muestra una barra de progreso de lectura.
   - Buscador: filtra secciones y subtemas, resalta coincidencias (sin
     distinguir tildes ni mayúsculas) y Enter salta a la siguiente.
   - Capturas: visor ampliado (<dialog>), recorte de capturas largas y
     globos de los marcadores numerados.
*/
document.addEventListener('DOMContentLoaded', function () {
    const nav = document.getElementById('manualToc');
    const contenido = document.getElementById('manualContenido');
    if (!nav || !contenido) return;

    const secciones = Array.from(contenido.querySelectorAll('.manual-section'));
    const linksToc = Array.from(nav.querySelectorAll(':scope > a'));

    const slug = (txt) => txt.toLowerCase()
        .normalize('NFD').replace(/[̀-ͯ]/g, '')
        .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60);

    // ══════════ Sub-índice por sección ══════════
    const titulos = [];   // { h3, seccion, link }
    secciones.forEach(sec => {
        const linkSec = nav.querySelector(`a[href="#${sec.id}"]`);
        const h3s = Array.from(sec.querySelectorAll('.manual-body h3'))
            .filter(h => !h.closest('details'));
        if (!linkSec || !h3s.length) return;

        const sub = document.createElement('div');
        sub.className = 'manual-toc-sub';
        sub.hidden = true;
        h3s.forEach(h3 => {
            const cont = h3.parentElement.classList.contains('manual-sub') ? h3.parentElement : null;
            if (!h3.id && !(cont && cont.id)) h3.id = sec.id.replace('seccion-', '') + '-' + slug(h3.textContent);
            const destino = (cont && cont.id) ? cont.id : h3.id;

            const ancla = document.createElement('a');
            ancla.className = 'manual-anchor';
            ancla.href = '#' + destino;
            ancla.textContent = '#';
            ancla.setAttribute('aria-label', 'Link a esta parte');
            h3.appendChild(ancla);

            const a = document.createElement('a');
            a.href = '#' + destino;
            a.textContent = h3.firstChild.textContent.trim();
            sub.appendChild(a);
            titulos.push({ h3, seccion: sec, link: a, objetivo: cont || h3 });
        });
        linkSec.after(sub);
    });

    // ══════════ Referencias a partes que este usuario no ve ══════════
    // El servidor no manda las secciones de pantallas sin permiso (ver
    // _secciones_manual_visibles en core/views.py). Un "ver Caja" dentro de
    // otra sección quedaría como link roto: se deja solo el texto.
    contenido.querySelectorAll('a[href^="#"]').forEach(a => {
        const id = a.getAttribute('href').slice(1);
        if (id && !document.getElementById(id)) a.replaceWith(...a.childNodes);
    });

    // ══════════ Sección activa + progreso ══════════
    const barra = document.getElementById('manualProgreso');
    let pendiente = false;

    function actualizarIndice() {
        pendiente = false;
        const corte = (parseInt(getComputedStyle(document.documentElement).getPropertyValue('--header-height')) || 56) + 120;

        let activa = null;
        secciones.forEach(sec => {
            if (!sec.classList.contains('is-oculta') && sec.getBoundingClientRect().top <= corte) activa = sec;
        });
        if (!activa) activa = secciones.find(s => !s.classList.contains('is-oculta')) || null;

        linksToc.forEach(a => a.classList.toggle('is-active', !!activa && a.getAttribute('href') === '#' + activa.id));
        nav.querySelectorAll('.manual-toc-sub').forEach(sub => {
            sub.hidden = !activa || sub.previousElementSibling.getAttribute('href') !== '#' + activa.id;
        });

        let tituloActivo = null;
        titulos.forEach(t => {
            if (t.seccion === activa && !t.objetivo.classList.contains('is-oculta') && t.h3.getBoundingClientRect().top <= corte) tituloActivo = t;
        });
        titulos.forEach(t => t.link.classList.toggle('is-active', t === tituloActivo));

        if (barra) {
            const r = contenido.getBoundingClientRect();
            const total = r.height - window.innerHeight + corte;
            const avance = Math.min(1, Math.max(0, (corte - r.top) / (total > 0 ? total : 1)));
            barra.style.width = (avance * 100).toFixed(1) + '%';
        }
    }

    window.addEventListener('scroll', () => {
        if (!pendiente) { pendiente = true; requestAnimationFrame(actualizarIndice); }
    }, { passive: true });
    actualizarIndice();

    // Mantener visible en el índice el link activo (sin mover la página)
    const activoObs = new MutationObserver(() => {
        const act = nav.querySelector('a.is-active');
        if (!act) return;
        const nr = nav.getBoundingClientRect(), ar = act.getBoundingClientRect();
        if (ar.top < nr.top || ar.bottom > nr.bottom) nav.scrollTop += ar.top - nr.top - nr.height / 3;
        if (ar.left < nr.left || ar.right > nr.right) nav.scrollLeft += ar.left - nr.left - 16;
    });
    activoObs.observe(nav, { subtree: true, attributeFilter: ['class'] });

    // ══════════ Buscador ══════════
    const input = document.getElementById('manualBuscar');
    const estado = document.getElementById('manualBuscarEstado');
    const sinResultados = document.getElementById('manualSinResultados');
    const soportaHighlight = typeof Highlight !== 'undefined' && CSS.highlights;

    const normalizar = (txt) => txt.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

    // Cache de nodos de texto con su versión normalizada + mapa de índices
    let nodosTexto = null;
    function cargarNodos() {
        nodosTexto = [];
        const walker = document.createTreeWalker(contenido, NodeFilter.SHOW_TEXT, {
            acceptNode: n => (n.nodeValue.trim() && !n.parentElement.closest('.manual-anchor, script, style'))
                ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
        });
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            const original = n.nodeValue;
            let norm = '';
            const mapa = [];
            for (let i = 0; i < original.length; i++) {
                const c = normalizar(original[i]);
                for (let k = 0; k < c.length; k++) { norm += c[k]; mapa.push(i); }
            }
            mapa.push(original.length);
            nodosTexto.push({ nodo: n, norm, mapa });
        }
    }

    let rangos = [];
    let indiceActual = -1;

    function limpiarBusqueda() {
        secciones.forEach(s => s.classList.remove('is-oculta'));
        contenido.querySelectorAll('.manual-sub.is-oculta').forEach(s => s.classList.remove('is-oculta'));
        linksToc.forEach(a => a.classList.remove('is-sin-resultados'));
        if (soportaHighlight) CSS.highlights.delete('manual-busqueda');
        sinResultados.hidden = true;
        estado.textContent = '';
        rangos = [];
        indiceActual = -1;
    }

    function buscar() {
        const termino = normalizar(input.value.trim());
        limpiarBusqueda();
        if (termino.length < 2) { actualizarIndice(); return; }
        if (!nodosTexto) cargarNodos();

        nodosTexto.forEach(({ nodo, norm, mapa }) => {
            let pos = norm.indexOf(termino);
            while (pos !== -1) {
                const r = new Range();
                r.setStart(nodo, mapa[pos]);
                r.setEnd(nodo, mapa[pos + termino.length]);
                rangos.push(r);
                pos = norm.indexOf(termino, pos + termino.length);
            }
        });

        const conResultado = new Set();
        const subsConResultado = new Set();
        rangos.forEach(r => {
            const el = r.startContainer.parentElement;
            const sec = el.closest('.manual-section');
            if (sec) conResultado.add(sec);
            const sub = el.closest('.manual-sub');
            if (sub) subsConResultado.add(sub);
            const det = el.closest('details');
            if (det) det.open = true;
        });

        secciones.forEach(sec => {
            const tiene = conResultado.has(sec);
            sec.classList.toggle('is-oculta', !tiene);
            const link = nav.querySelector(`a[href="#${sec.id}"]`);
            if (link) link.classList.toggle('is-sin-resultados', !tiene);
            // Dentro de una sección con resultados, esconder los subtemas que no coinciden
            if (tiene) {
                sec.querySelectorAll('.manual-sub').forEach(sub => {
                    sub.classList.toggle('is-oculta', !subsConResultado.has(sub));
                });
            }
        });

        if (soportaHighlight && rangos.length) CSS.highlights.set('manual-busqueda', new Highlight(...rangos));

        sinResultados.hidden = rangos.length > 0;
        estado.textContent = rangos.length
            ? `${rangos.length} ${rangos.length === 1 ? 'resultado' : 'resultados'} en ${conResultado.size} ${conResultado.size === 1 ? 'sección' : 'secciones'} · Enter para ir al siguiente`
            : 'Sin resultados';
        actualizarIndice();
    }

    function irAlSiguiente() {
        if (!rangos.length) return;
        indiceActual = (indiceActual + 1) % rangos.length;
        const el = rangos[indiceActual].startContainer.parentElement;
        el.scrollIntoView({ block: 'center', behavior: 'smooth' });
        estado.textContent = `Resultado ${indiceActual + 1} de ${rangos.length} · Enter para ir al siguiente`;
    }

    if (input) {
        let espera = null;
        input.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(buscar, 160); });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); irAlSiguiente(); }
            if (e.key === 'Escape') { input.value = ''; buscar(); }
        });
        document.addEventListener('keydown', (e) => {
            const enCampo = e.target.closest('input, textarea, select, [contenteditable="true"]');
            if (e.key === '/' && !enCampo && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                input.focus();
                input.select();
            }
        });
    }

    // ══════════ Capturas ══════════
    // Capturas largas: recorte con degradé (se ven completas en el visor)
    contenido.querySelectorAll('.manual-shot--tall > img').forEach(img => {
        const crop = document.createElement('div');
        crop.className = 'manual-shot-crop';
        img.before(crop);
        crop.appendChild(img);
    });

    const visor = document.getElementById('manualLightbox');
    const visorImg = document.getElementById('manualLightboxImg');
    const visorTxt = document.getElementById('manualLightboxCaption');

    if (visor && typeof visor.showModal === 'function') {
        contenido.querySelectorAll('.manual-shot img').forEach(img => {
            img.tabIndex = 0;
            img.setAttribute('role', 'button');
            img.setAttribute('aria-label', 'Ampliar captura: ' + img.alt);
            const abrir = () => {
                const fig = img.closest('figure');
                const cap = fig && fig.querySelector('figcaption');
                visorImg.src = img.currentSrc || img.src;
                visorImg.alt = img.alt;
                visorTxt.textContent = cap ? cap.textContent.replace(/\s+/g, ' ').trim() : '';
                visor.showModal();
            };
            img.addEventListener('click', abrir);
            img.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); }
            });
        });

        // Cerrar tocando afuera en navegadores sin soporte de closedby (Safari)
        if (!('closedBy' in HTMLDialogElement.prototype)) {
            visor.addEventListener('click', (e) => {
                if (e.target !== visor) return;
                const r = visor.getBoundingClientRect();
                const adentro = r.top <= e.clientY && e.clientY <= r.bottom && r.left <= e.clientX && e.clientX <= r.right;
                if (!adentro) visor.close();
            });
        }
        visor.addEventListener('close', () => { visorImg.removeAttribute('src'); });
    }

    // Marcadores numerados: el globo toma el título de su ítem de la leyenda
    contenido.querySelectorAll('.manual-hotspot').forEach(hs => {
        const item = document.getElementById(hs.getAttribute('aria-describedby') || '');
        if (!item) return;
        const titulo = item.querySelector('strong');
        hs.dataset.tip = (titulo ? titulo.textContent : item.textContent).replace(/[.:]\s*$/, '').trim();
        hs.setAttribute('aria-label', 'Marcador ' + hs.textContent + ': ' + hs.dataset.tip);
        const marcar = (on) => item.classList.toggle('is-resaltado', on);
        hs.addEventListener('mouseenter', () => marcar(true));
        hs.addEventListener('mouseleave', () => marcar(false));
        hs.addEventListener('focus', () => marcar(true));
        hs.addEventListener('blur', () => { marcar(false); hs.classList.remove('is-abierto'); });
        hs.addEventListener('click', () => hs.classList.toggle('is-abierto'));
    });

    // Al imprimir: todo visible y desplegado
    window.addEventListener('beforeprint', () => {
        contenido.querySelectorAll('details').forEach(d => { d.dataset.estabaAbierto = d.open ? '1' : ''; d.open = true; });
    });
    window.addEventListener('afterprint', () => {
        contenido.querySelectorAll('details').forEach(d => { d.open = !!d.dataset.estabaAbierto; });
    });
});
