/* core/static/core/js/manual.js
   Manual de usuario:
   - Índice: arma el sub-índice de cada sección con sus <h3>, resalta la
     sección/subtema visible y muestra una barra de progreso de lectura.
   - Buscador: entiende la consulta como un problema ("cambiar contraseña",
     "devolver mercadería") y propone los temas que mejor responden (motor
     en manual_buscador.js). Abajo de la lista, "Buscar el texto exacto"
     hace la búsqueda literal de antes: filtra secciones y resalta.
   - Capturas: visor ampliado (<dialog>), recorte de capturas largas y
     globos de los marcadores numerados.
*/
document.addEventListener('DOMContentLoaded', function () {
    const nav = document.getElementById('manualToc');
    const contenido = document.getElementById('manualContenido');
    if (!nav || !contenido) return;

    const secciones = Array.from(contenido.querySelectorAll('.manual-section'));
    const linksToc = Array.from(nav.querySelectorAll(':scope > a'));
    const tocToggle = document.getElementById('manualTocToggle');
    const tocActual = document.getElementById('manualTocActual');
    const mediaMovil = window.matchMedia('(max-width: 900px)');
    const movimientoReducido = window.matchMedia('(prefers-reduced-motion: reduce)');

    function abrirIndice(abrir) {
        if (!tocToggle) return;
        nav.classList.toggle('is-open', abrir);
        tocToggle.classList.toggle('is-open', abrir);
        tocToggle.setAttribute('aria-expanded', abrir ? 'true' : 'false');
    }

    if (tocToggle) {
        tocToggle.addEventListener('click', () => abrirIndice(!nav.classList.contains('is-open')));
        linksToc.forEach(link => link.addEventListener('click', () => {
            if (mediaMovil.matches) abrirIndice(false);
        }));
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && nav.classList.contains('is-open')) {
                abrirIndice(false);
                tocToggle.focus();
            }
        });
        mediaMovil.addEventListener('change', e => {
            if (!e.matches) abrirIndice(false);
        });
    }

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
    const barras = [document.getElementById('manualProgreso'), document.getElementById('manualProgresoMovil')].filter(Boolean);
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
        if (activa && tocActual) {
            const linkActivo = nav.querySelector(`a[href="#${activa.id}"]`);
            tocActual.textContent = linkActivo ? linkActivo.textContent.trim() : 'Explorar temas';
        }
        nav.querySelectorAll('.manual-toc-sub').forEach(sub => {
            sub.hidden = !activa || sub.previousElementSibling.getAttribute('href') !== '#' + activa.id;
        });

        let tituloActivo = null;
        titulos.forEach(t => {
            if (t.seccion === activa && !t.objetivo.classList.contains('is-oculta') && t.h3.getBoundingClientRect().top <= corte) tituloActivo = t;
        });
        titulos.forEach(t => t.link.classList.toggle('is-active', t === tituloActivo));

        if (barras.length) {
            const r = contenido.getBoundingClientRect();
            const total = r.height - window.innerHeight + corte;
            const avance = Math.min(1, Math.max(0, (corte - r.top) / (total > 0 ? total : 1)));
            barras.forEach(barra => { barra.style.width = (avance * 100).toFixed(1) + '%'; });
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

    function buscarTexto(texto) {
        const termino = normalizar(texto.trim());
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
        el.scrollIntoView({ block: 'center', behavior: movimientoReducido.matches ? 'auto' : 'smooth' });
        estado.textContent = `Resultado ${indiceActual + 1} de ${rangos.length} · Enter para ir al siguiente`;
    }

    // ── Búsqueda por tema (ver manual_buscador.js) ──
    // Lo que escribe la persona se interpreta como un problema ("cambiar
    // contraseña", "devolver mercadería"): se muestra una lista de los
    // temas que mejor responden, y al elegir uno se va directo ahí.
    const panel = document.getElementById('manualResultadosPanel');
    const lista = document.getElementById('manualResultados');
    const btnTexto = document.getElementById('manualBuscarTexto');
    let indiceTemas = null;
    let opciones = [];        // resultados mostrados
    let activa = -1;
    let ultimaRaices = new Set();

    const esc = (t) => t.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    // Envuelve en <mark> las palabras del fragmento que coinciden.
    function marcar(texto, raicesBuscadas) {
        return esc(texto).replace(/[A-Za-zÀ-ÿñÑ0-9]+/g, w =>
            raicesBuscadas.has(ManualBuscador.raiz(ManualBuscador.normalizar(w))) ? `<mark>${w}</mark>` : w);
    }

    function abrirPanel(abrir) {
        panel.hidden = !abrir;
        input.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        if (!abrir) { activa = -1; input.removeAttribute('aria-activedescendant'); }
    }

    function marcarActiva(i) {
        const items = lista.querySelectorAll('[role="option"]');
        items.forEach((el, k) => el.setAttribute('aria-selected', k === i ? 'true' : 'false'));
        activa = i;
        if (i >= 0 && items[i]) {
            input.setAttribute('aria-activedescendant', items[i].id);
            items[i].scrollIntoView({ block: 'nearest' });
        } else {
            input.removeAttribute('aria-activedescendant');
        }
    }

    function sugerir() {
        const q = input.value.trim();
        limpiarBusqueda();
        if (q.length < 2) { abrirPanel(false); actualizarIndice(); return; }
        if (!indiceTemas) indiceTemas = ManualBuscador.crearIndice(contenido);

        const { resultados, raices } = ManualBuscador.buscar(indiceTemas, q, 7);
        opciones = resultados;
        ultimaRaices = raices;
        btnTexto.textContent = `Buscar el texto exacto «${q}» en todo el manual`;

        if (!resultados.length) {
            lista.innerHTML = `<li class="manual-resultado-vacio" role="presentation">
                No encontramos un tema parecido. Probá contarlo con otras palabras, por ejemplo
                <em>«anular una venta»</em>, <em>«cargar un producto»</em> o <em>«cerrar la caja»</em>.</li>`;
        } else {
            lista.innerHTML = resultados.map((r, i) => {
                const donde = r.tema.seccion ? `${esc(r.tema.seccion === 'Introducción' ? r.tema.titulo : r.tema.seccion)}` : '';
                return `<li role="option" id="manualRes${i}" class="manual-resultado" aria-selected="false" data-i="${i}">
                    <span class="manual-resultado-titulo">${marcar(r.tema.titulo, raices)}</span>
                    ${donde ? `<span class="manual-resultado-donde">${donde}${r.tema.seccion === 'Introducción' ? ' · introducción' : ''}</span>` : ''}
                    ${r.fragmento ? `<span class="manual-resultado-fragmento">${marcar(r.fragmento, raices)}</span>` : ''}
                </li>`;
            }).join('');
        }
        estado.textContent = resultados.length
            ? `${resultados.length} ${resultados.length === 1 ? 'tema encontrado' : 'temas encontrados'} · ↑↓ para elegir, Enter para abrir`
            : 'Sin temas parecidos';
        abrirPanel(true);
        marcarActiva(resultados.length ? 0 : -1);
    }

    function irATema(r) {
        abrirPanel(false);
        limpiarBusqueda();
        actualizarIndice();
        const destino = r.subtitulo || r.tema.destino;
        let d = destino.closest('details');
        while (d) { d.open = true; d = d.parentElement.closest('details'); }
        destino.scrollIntoView({ block: 'start', behavior: movimientoReducido.matches ? 'auto' : 'smooth' });

        // Resaltar el tema elegido y las palabras buscadas dentro de él.
        contenido.querySelectorAll('.is-encontrado').forEach(el => el.classList.remove('is-encontrado'));
        r.tema.el.classList.add('is-encontrado');
        setTimeout(() => r.tema.el.classList.remove('is-encontrado'), 2600);
        if (soportaHighlight) {
            const rs = ManualBuscador.rangosEn(r.tema.el, ultimaRaices);
            if (rs.length) CSS.highlights.set('manual-busqueda', new Highlight(...rs));
        }
        estado.textContent = `Mostrando: ${r.tema.titulo} · Esc para limpiar`;
    }

    if (input && panel) {
        let espera = null;
        input.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(sugerir, 140); });
        input.addEventListener('focus', () => { if (input.value.trim().length >= 2 && opciones.length) abrirPanel(true); });
        input.addEventListener('keydown', (e) => {
            const items = lista.querySelectorAll('[role="option"]');
            if (e.key === 'ArrowDown' && !panel.hidden) {
                e.preventDefault();
                marcarActiva(items.length ? (activa + 1) % items.length : -1);
            } else if (e.key === 'ArrowUp' && !panel.hidden) {
                e.preventDefault();
                marcarActiva(items.length ? (activa - 1 + items.length) % items.length : -1);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (!panel.hidden && opciones[activa]) irATema(opciones[activa]);
                else if (rangos.length) irAlSiguiente();
                else if (input.value.trim().length >= 2) sugerir();
            } else if (e.key === 'Escape') {
                if (!panel.hidden) { abrirPanel(false); return; }
                input.value = '';
                limpiarBusqueda();
                actualizarIndice();
            }
        });
        // mousedown (no click): que el input no pierda el foco antes de elegir.
        lista.addEventListener('mousedown', (e) => {
            const li = e.target.closest('[role="option"]');
            if (!li) return;
            e.preventDefault();
            irATema(opciones[Number(li.dataset.i)]);
        });
        lista.addEventListener('mousemove', (e) => {
            const li = e.target.closest('[role="option"]');
            if (li && Number(li.dataset.i) !== activa) marcarActiva(Number(li.dataset.i));
        });
        btnTexto.addEventListener('mousedown', (e) => e.preventDefault());
        btnTexto.addEventListener('click', () => {
            abrirPanel(false);
            buscarTexto(input.value);
            if (rangos.length) irAlSiguiente();
        });
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.manual-search')) abrirPanel(false);
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

    // El manual es largo: acceso discreto para volver al buscador y al inicio.
    const volverArriba = document.getElementById('manualVolverArriba');
    if (volverArriba) {
        const actualizarVolver = () => volverArriba.classList.toggle('is-visible', window.scrollY > 700);
        volverArriba.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: movimientoReducido.matches ? 'auto' : 'smooth' });
        });
        window.addEventListener('scroll', actualizarVolver, { passive: true });
        actualizarVolver();
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
