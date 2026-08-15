/* Pantalla "Catálogo online" — mudado desde configuracion.js (bloques
   formCatalogo/formSlide) cuando esta sección se sacó de Configuración
   a su propio ítem del menú. KaiConfirm/KaiToast/window.bootstrap ya
   están disponibles globalmente vía core/base.html. */
document.addEventListener('DOMContentLoaded', function () {
    const formCatalogo = document.getElementById('formCatalogo');
    if (!formCatalogo) return;

    const csrf = () => formCatalogo.querySelector('[name=csrfmiddlewaretoken]').value;
    const urls = window.CONFIG_CATALOGO_URLS || {};
    const defaults = window.CONFIG_CATALOGO_DEFAULTS || {};
    const catalogoHomeUrl = window.CATALOGO_HOME_URL || '/';
    const catalogoInstitucionalUrl = window.CATALOGO_INSTITUCIONAL_URL || '/la-tienda/';

    // ── Default de color por plantilla — cada plantilla tiene su propia
    //    identidad (naranja/navy en "almacen", verde lima/índigo en "bento",
    //    rosa/verde neón en "kinetic" —fija, no editable—, salvia/terracota
    //    en "lumina"). ──
    function colorDefaultPara(plantilla, campo) {
        if (plantilla === 'bento') {
            return campo === 'marca' ? (defaults.colorMarcaBento || '#6fa525') : (defaults.colorMarcaSecundarioBento || '#262b52');
        }
        if (plantilla === 'kinetic') {
            return campo === 'marca' ? (defaults.colorMarcaKinetic || '#ff3366') : (defaults.colorMarcaSecundarioKinetic || '#00e699');
        }
        if (plantilla === 'lumina') {
            return campo === 'marca' ? (defaults.colorMarcaLumina || '#4a6b5d') : (defaults.colorMarcaSecundarioLumina || '#e76f51');
        }
        return campo === 'marca' ? (defaults.colorMarca || '#ff9343') : (defaults.colorMarcaSecundario || '#111e2f');
    }
    function colorDefaultActual(campo) {
        return colorDefaultPara(document.getElementById('idCatalogoPlantilla')?.value || 'almacen', campo);
    }

    // ── Colores por plantilla — las 4 tienen cada una su propio campo en
    //    el modelo (Kinetic solo el principal, el secundario sigue fijo)
    //    pero el panel solo muestra un par de inputs a la vez; acá se
    //    guarda en memoria el color de cada plantilla para no perderlo ni
    //    mezclarlo con el de otra al cambiar de plantilla sin haber
    //    guardado todavía. ──
    const coloresGuardados = window.CONFIG_CATALOGO_COLORES || {};
    function coloresIniciales(plantilla) {
        const guardado = coloresGuardados[plantilla] || {};
        return {
            marca: guardado.marca || colorDefaultPara(plantilla, 'marca'),
            secundario: guardado.secundario || colorDefaultPara(plantilla, 'secundario'),
            marcaTocada: !!guardado.marca,
            secundarioTocada: !!guardado.secundario,
        };
    }
    const coloresPorPlantilla = {
        almacen: coloresIniciales('almacen'),
        bento: coloresIniciales('bento'),
        lumina: coloresIniciales('lumina'),
        kinetic: coloresIniciales('kinetic'),
    };

    function guardarColoresVisiblesEn(plantilla) {
        if (!coloresPorPlantilla[plantilla]) return;
        coloresPorPlantilla[plantilla] = {
            marca: document.getElementById('idCatalogoColorMarca').value,
            secundario: document.getElementById('idCatalogoColorMarcaSecundario')?.value || '',
            marcaTocada: colorMarcaTocado,
            secundarioTocada: colorMarcaSecundarioTocado,
        };
    }

    function cargarColoresVisiblesDe(plantilla) {
        const c = coloresPorPlantilla[plantilla] || coloresIniciales(plantilla);
        document.getElementById('idCatalogoColorMarca').value = c.marca;
        const secundario = document.getElementById('idCatalogoColorMarcaSecundario');
        if (secundario) secundario.value = c.secundario;
        colorMarcaTocado = c.marcaTocada;
        colorMarcaSecundarioTocado = c.secundarioTocada;
    }

    const plantillaInicial = document.getElementById('idCatalogoPlantilla')?.value || 'almacen';
    let colorMarcaTocado = (coloresPorPlantilla[plantillaInicial] || {}).marcaTocada || false;
    let colorMarcaSecundarioTocado = (coloresPorPlantilla[plantillaInicial] || {}).secundarioTocada || false;
    // Fondo de Bento — a diferencia de marca/secundario, estos 2 inputs
    // NO se comparten/relabelean entre plantillas (están ocultos para las
    // otras 3 con data-plantilla-oculta), así que su valor en el DOM
    // siempre representa a Bento — no hace falta el vaivén de
    // guardar/cargar al cambiar de tab, solo el tracking de "tocado".
    let colorFondoTocado = !!(coloresGuardados.bento && coloresGuardados.bento.fondo);
    let colorFondoOscuroTocado = !!(coloresGuardados.bento && coloresGuardados.bento.fondoOscuro);
    // Fondo de Kinetic — mismo criterio que el de Bento arriba, pero un
    // solo valor (Kinetic no tiene modo claro/oscuro).
    let colorFondoKineticTocado = !!(coloresGuardados.kinetic && coloresGuardados.kinetic.fondo);

    // ── Escalado de iframes de vista previa (mismo truco "device preview" para
    //    el preview grande y las mini-cards de plantilla — una sola implementación) ──
    // opts.alturaFija: si viene, la card se recorta a esa altura sin medir el
    // contenido real (mini-cards, no necesitan estar sincronizadas en vivo).
    // Si no viene, mide scrollHeight real + ResizeObserver (preview grande) —
    // el WRAP tiene un alto fijo por CSS (.co-preview-viewport) y scrollea
    // internamente si el contenido escalado no entra; acá solo se dimensiona
    // el iframe para que el escalado sea fiel al ancho real de producción.
    function crearPreviewEscalado(frame, wrap, opts) {
        opts = opts || {};
        const anchoBase = opts.anchoBase || 1280;
        let resizeObserver = null;

        function recalcular() {
            if (!wrap || !frame) return;
            const factor = wrap.clientWidth / anchoBase;
            frame.style.width = anchoBase + 'px';
            frame.style.transform = `scale(${factor})`;
            if (opts.alturaFija) {
                frame.style.height = (opts.alturaFija / factor) + 'px';
                return;
            }
            // Resetear a una altura chica ANTES de medir: el carrito (#kcDrawer,
            // ver catalogo.css/bento.css) es position:fixed con top:0;bottom:0,
            // así que su alto real se ata al viewport INTERNO del iframe — que es
            // justo lo que esta misma función fija más abajo. Si midiéramos
            // scrollHeight sin resetear antes, cada pasada infla el drawer (y con
            // él, lo medido) un poco más que la anterior — un loop de
            // realimentación que termina con un hueco en blanco enorme al final
            // de la vista previa, mucho más alto que el contenido real.
            frame.style.height = '100px';
            const doc = frame.contentDocument;
            const alturaReal = (doc && doc.documentElement) ? doc.documentElement.scrollHeight : 600;
            frame.style.height = alturaReal + 'px';
            // El wrap NO se agranda a la altura completa (a diferencia de antes):
            // queda con el alto fijo de .co-preview-viewport y scrollea si hace falta.
        }

        frame.addEventListener('load', function () {
            recalcular();
            if (!opts.alturaFija && 'ResizeObserver' in window) {
                if (resizeObserver) resizeObserver.disconnect();
                const doc = frame.contentDocument;
                if (doc && doc.body) {
                    resizeObserver = new ResizeObserver(recalcular);
                    resizeObserver.observe(doc.body);
                }
            }
            if (opts.onLoad) opts.onLoad();
        });

        return recalcular;
    }

    // ── Preview grande ──
    const previewFrame = document.getElementById('catalogoPreviewFrame');
    const previewWrap = document.getElementById('catalogoPreviewWrap');
    let heroObjectUrl = null;
    let instImagenObjectUrl = null;
    let kineticFondoObjectUrl = null;

    function aplicarValoresAlPreview() {
        const doc = previewFrame && previewFrame.contentDocument;
        if (!doc) return;
        const titulo = doc.getElementById('kcHeroTitulo');
        if (titulo) titulo.textContent = document.getElementById('idCatalogoHeroTitulo').value || defaults.heroTitulo || '';
        const subtitulo = doc.getElementById('kcHeroSubtitulo');
        if (subtitulo) subtitulo.textContent = document.getElementById('idCatalogoHeroSubtitulo').value || defaults.heroSubtitulo || '';
        const sobreNosotros = doc.getElementById('kcHistoriaTexto');
        if (sobreNosotros) sobreNosotros.textContent = document.getElementById('idCatalogoSobreNosotros').value || defaults.sobreNosotros || '';
        const contacto = doc.getElementById('kcContactoTexto');
        if (contacto) contacto.textContent = document.getElementById('idCatalogoContactoTexto').value || '';
        if (heroObjectUrl) {
            const visual = doc.getElementById('kcHeroVisual');
            if (visual) visual.innerHTML = `<img src="${heroObjectUrl}" alt="">`;
        }
        if (instImagenObjectUrl) {
            const portada = doc.querySelector('.kc-inst-portada');
            if (portada) {
                let img = portada.querySelector('.kc-inst-portada-img');
                if (!img) {
                    img = document.createElement('img');
                    img.className = 'kc-inst-portada-img';
                    portada.prepend(img);
                    if (!portada.querySelector('.kc-inst-portada-overlay')) {
                        const overlay = document.createElement('div');
                        overlay.className = 'kc-inst-portada-overlay';
                        img.after(overlay);
                    }
                }
                img.src = instImagenObjectUrl;
            }
        }
        if (kineticFondoObjectUrl) {
            const hero = doc.getElementById('kcHero');
            if (hero) {
                hero.classList.add('k-hero--con-fondo');
                hero.style.setProperty('--k-hero-fondo-url', `url("${kineticFondoObjectUrl}")`);
            }
        }
        const navCatalogo = doc.getElementById('kcNavCatalogo');
        if (navCatalogo) navCatalogo.textContent = document.getElementById('idCatalogoNavCatalogo').value || defaults.navCatalogo || '';
        const navOfertas = doc.getElementById('kcNavOfertas');
        if (navOfertas) navOfertas.textContent = document.getElementById('idCatalogoNavOfertas').value || defaults.navOfertas || '';
        const navCombos = doc.getElementById('kcNavCombos');
        if (navCombos) navCombos.textContent = document.getElementById('idCatalogoNavCombos').value || defaults.navCombos || '';
        const navTienda = doc.getElementById('kcNavTienda');
        if (navTienda) navTienda.textContent = document.getElementById('idCatalogoNavTienda').value || defaults.navTienda || '';
        const instTitulo = doc.getElementById('kcInstTitulo');
        if (instTitulo) instTitulo.textContent = document.getElementById('idCatalogoInstTitulo').value || defaults.instTitulo || '';
        const instBajada = doc.getElementById('kcInstBajada');
        if (instBajada) instBajada.textContent = document.getElementById('idCatalogoInstBajada').value || defaults.instBajada || '';
        [1, 2, 3].forEach(function (n) {
            const tituloEl = doc.getElementById('kcDestacado' + n + 'Titulo');
            const inputTitulo = document.getElementById('idCatalogoDestacado' + n + 'Titulo');
            if (tituloEl && inputTitulo) tituloEl.textContent = inputTitulo.value || defaults['destacado' + n + 'Titulo'] || '';
            const textoEl = doc.getElementById('kcDestacado' + n + 'Texto');
            const inputTexto = document.getElementById('idCatalogoDestacado' + n + 'Texto');
            if (textoEl && inputTexto) textoEl.textContent = inputTexto.value || defaults['destacado' + n + 'Texto'] || '';
        });
        const color = document.getElementById('idCatalogoColorMarca').value || colorDefaultActual('marca');
        const colorSecundario = document.getElementById('idCatalogoColorMarcaSecundario')?.value || colorDefaultActual('secundario');
        if (doc.documentElement) {
            doc.documentElement.style.setProperty('--primary', color);
            doc.documentElement.style.setProperty('--primary-dark', `color-mix(in srgb, ${color} 80%, black)`);
            doc.documentElement.style.setProperty('--primary-soft', `color-mix(in srgb, ${color} 12%, white)`);
            doc.documentElement.style.setProperty('--navy', colorSecundario);
            doc.documentElement.style.setProperty('--navy-2', `color-mix(in srgb, ${colorSecundario} 82%, black)`);
            // Mismos 2 colores, variables de Bento — si el iframe cargado es
            // Almacén estas simplemente no se usan en ningún selector, no hacen nada.
            doc.documentElement.style.setProperty('--lime', color);
            doc.documentElement.style.setProperty('--lime-dark', `color-mix(in srgb, ${color} 80%, black)`);
            doc.documentElement.style.setProperty('--lime-soft', `color-mix(in srgb, ${color} 12%, white)`);
            doc.documentElement.style.setProperty('--indigo', colorSecundario);
            doc.documentElement.style.setProperty('--indigo-2', `color-mix(in srgb, ${colorSecundario} 82%, black)`);
            // Variable de Kinetic — --k-primary-glow/--k-primary-dark se
            // recalculan solas porque están definidas con color-mix(var(--k-primary))
            // en kinetic.css; no hace falta pisarlas acá también. Kinetic no
            // tiene un color secundario propio editable (ver base.html).
            doc.documentElement.style.setProperty('--k-primary', color);
            // Fondo de Kinetic — un solo setProperty alcanza (a diferencia del
            // de Bento más abajo): --k-surface/--k-surface-card/--k-border
            // quedan fijos, solo cambia el color de fondo de la página en sí
            // (mismo criterio que --paper en Bento, ver kinetic.css).
            const colorFondoKinetic = document.getElementById('idCatalogoColorFondoKinetic')?.value || defaults.colorFondoKinetic || '#0d0d0f';
            doc.documentElement.style.setProperty('--k-bg', colorFondoKinetic);
            // Variables de Lumina — --l-primary-dark/--l-primary-soft/
            // --l-secondary-soft se recalculan solas vía color-mix(var(--l-primary)/
            // var(--l-secondary)) en lumina.css.
            doc.documentElement.style.setProperty('--l-primary', color);
            doc.documentElement.style.setProperty('--l-secondary', colorSecundario);

            // Fondo de Bento — 2 valores (claro/oscuro) que un solo setProperty
            // no puede expresar (el oscuro solo vale bajo html[data-theme="dark"]),
            // así que se inyecta un <style> chiquito en el <head> del iframe —
            // mismo mecanismo que ya usa bento/base.html en la página real.
            const colorFondo = document.getElementById('idCatalogoColorFondo')?.value || defaults.colorFondoBento || '#faf9f6';
            const colorFondoOscuro = document.getElementById('idCatalogoColorFondoOscuro')?.value || defaults.colorFondoOscuroBento || '#121320';
            let estiloFondoPreview = doc.getElementById('kcPreviewColorFondo');
            if (!estiloFondoPreview && doc.head) {
                estiloFondoPreview = doc.createElement('style');
                estiloFondoPreview.id = 'kcPreviewColorFondo';
                doc.head.appendChild(estiloFondoPreview);
            }
            if (estiloFondoPreview) {
                estiloFondoPreview.textContent = `:root{--paper:${colorFondo};} html[data-theme="dark"]{--paper:${colorFondoOscuro};}`;
            }
        }
    }

    const recalcularPreviewGrande = crearPreviewEscalado(previewFrame, previewWrap, { onLoad: aplicarValoresAlPreview });

    let previewResizeTimeout;
    window.addEventListener('resize', function () {
        clearTimeout(previewResizeTimeout);
        previewResizeTimeout = setTimeout(recalcularPreviewGrande, 150);
    });

    [
        'idCatalogoHeroTitulo', 'idCatalogoHeroSubtitulo', 'idCatalogoSobreNosotros', 'idCatalogoContactoTexto',
        'idCatalogoColorMarca', 'idCatalogoColorMarcaSecundario', 'idCatalogoColorFondo', 'idCatalogoColorFondoOscuro', 'idCatalogoColorFondoKinetic', 'idCatalogoNavCatalogo', 'idCatalogoNavOfertas', 'idCatalogoNavCombos', 'idCatalogoNavTienda',
        'idCatalogoInstTitulo', 'idCatalogoInstBajada',
        'idCatalogoDestacado1Titulo', 'idCatalogoDestacado1Texto',
        'idCatalogoDestacado2Titulo', 'idCatalogoDestacado2Texto',
        'idCatalogoDestacado3Titulo', 'idCatalogoDestacado3Texto',
    ].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', aplicarValoresAlPreview);
    });

    document.getElementById('idCatalogoColorMarca')?.addEventListener('input', function () { colorMarcaTocado = true; });
    document.getElementById('idCatalogoColorMarcaSecundario')?.addEventListener('input', function () { colorMarcaSecundarioTocado = true; });
    document.getElementById('idCatalogoColorFondo')?.addEventListener('input', function () { colorFondoTocado = true; });
    document.getElementById('idCatalogoColorFondoOscuro')?.addEventListener('input', function () { colorFondoOscuroTocado = true; });
    document.getElementById('idCatalogoColorFondoKinetic')?.addEventListener('input', function () { colorFondoKineticTocado = true; });

    document.getElementById('btnResetColorMarca')?.addEventListener('click', function () {
        document.getElementById('idCatalogoColorMarca').value = colorDefaultActual('marca');
        colorMarcaTocado = false;
        guardarColoresVisiblesEn(inputPlantilla.value);
        aplicarValoresAlPreview();
    });

    document.getElementById('btnResetColorMarcaSecundario')?.addEventListener('click', function () {
        document.getElementById('idCatalogoColorMarcaSecundario').value = colorDefaultActual('secundario');
        colorMarcaSecundarioTocado = false;
        guardarColoresVisiblesEn(inputPlantilla.value);
        aplicarValoresAlPreview();
    });

    document.getElementById('btnResetColorFondo')?.addEventListener('click', function () {
        document.getElementById('idCatalogoColorFondo').value = defaults.colorFondoBento || '#faf9f6';
        colorFondoTocado = false;
        aplicarValoresAlPreview();
    });

    document.getElementById('btnResetColorFondoOscuro')?.addEventListener('click', function () {
        document.getElementById('idCatalogoColorFondoOscuro').value = defaults.colorFondoOscuroBento || '#121320';
        colorFondoOscuroTocado = false;
        aplicarValoresAlPreview();
    });

    document.getElementById('btnResetColorFondoKinetic')?.addEventListener('click', function () {
        document.getElementById('idCatalogoColorFondoKinetic').value = defaults.colorFondoKinetic || '#0d0d0f';
        colorFondoKineticTocado = false;
        aplicarValoresAlPreview();
    });

    // ── Mini-previews de las tarjetas de plantilla ──
    document.querySelectorAll('.co-card-plantilla').forEach(function (card) {
        const frame = card.querySelector('.co-card-preview-frame');
        const wrap = card.querySelector('.co-card-preview-wrap');
        if (frame && wrap) crearPreviewEscalado(frame, wrap, { alturaFija: 130 });
    });

    // ── Tabs: la columna izquierda muestra un solo panel a la vez; los
    //    botones viven arriba de la vista previa (columna derecha) a
    //    pedido del usuario, pero controlan qué panel se ve a la izquierda ──
    const tabs = document.querySelectorAll('.co-tab');
    const panels = document.querySelectorAll('.co-panel');
    // Restaura la pestaña donde estaba el usuario cuando algo (galería,
    // slides) necesita recargar la página entera — ver recargarPreservandoTab()
    // más abajo. Sin esto, cualquier recarga completa perdía el lugar donde
    // se estaba trabajando y volvía siempre a "Plantillas".
    let tabActiva = sessionStorage.getItem('coTabActiva') || 'plantillas';
    // Qué página muestra el preview grande ahora mismo — "La tienda" y
    // "Contacto" vive en /la-tienda/, el resto en la home del catálogo.
    let previewPagina = sessionStorage.getItem('coPreviewPagina') || 'home';
    sessionStorage.removeItem('coTabActiva');
    sessionStorage.removeItem('coPreviewPagina');

    // Único punto de recarga completa de la página — guarda dónde estaba
    // parado el usuario (pestaña + qué página previsualizaba) para
    // restaurarlo apenas la página vuelve a cargar, en vez de arrancar
    // siempre de cero en "Plantillas".
    function recargarPreservandoTab() {
        sessionStorage.setItem('coTabActiva', tabActiva);
        sessionStorage.setItem('coPreviewPagina', previewPagina);
        window.location.reload();
    }

    function mostrarPanel(tabId) {
        tabActiva = tabId;
        panels.forEach(function (panel) {
            const coincideTab = panel.dataset.panel === tabId;
            const coincidePlantilla = !panel.dataset.plantilla || panel.dataset.plantilla === inputPlantilla.value;
            panel.style.display = (coincideTab && coincidePlantilla) ? '' : 'none';
        });
        tabs.forEach(function (btn) {
            btn.classList.toggle('co-tab--activa', btn.dataset.tab === tabId);
        });
    }

    tabs.forEach(function (btn) {
        btn.addEventListener('click', function () {
            mostrarPanel(btn.dataset.tab);
            const paginaDestino = btn.dataset.preview || 'home';
            if (paginaDestino !== previewPagina && previewFrame) {
                previewPagina = paginaDestino;
                const base = paginaDestino === 'institucional' ? catalogoInstitucionalUrl : catalogoHomeUrl;
                // ?preview_plantilla= también aplica acá — antes solo la home
                // lo llevaba, así que cambiar de plantilla estando en "La
                // tienda" no actualizaba ese preview.
                previewFrame.src = base + '?preview_plantilla=' + encodeURIComponent(inputPlantilla.value);
            }
        });
    });

    // ── Toggle de tabs/campos por plantilla — corre al cargar y al elegir una
    //    card (ej: la tab "Hero" solo tiene sentido con la plantilla Almacén) ──
    const inputPlantilla = document.getElementById('idCatalogoPlantilla');
    function aplicarToggleDataPlantilla() {
        if (!inputPlantilla) return;
        let tabActivaOculta = false;
        tabs.forEach(function (btn) {
            const restringida = btn.dataset.plantillaTab;
            const visible = !restringida || restringida === inputPlantilla.value;
            btn.hidden = !visible;
            if (!visible && btn.dataset.tab === tabActiva) tabActivaOculta = true;
        });
        mostrarPanel(tabActivaOculta ? 'plantillas' : tabActiva);

        // ── Campos sueltos dentro de un panel compartido (ej. "Apariencia")
        //    que no aplican a alguna plantilla puntual — a diferencia de
        //    data-plantilla arriba (que es "mostrar SOLO para esta"), acá es
        //    al revés: "ocultar PARA esta/estas" (soporta lista separada por
        //    comas), porque el campo sí vale para el resto. ──
        document.querySelectorAll('[data-plantilla-oculta]').forEach(function (el) {
            const ocultarEn = el.dataset.plantillaOculta.split(',').map(function (s) { return s.trim(); });
            el.style.display = ocultarEn.indexOf(inputPlantilla.value) !== -1 ? 'none' : '';
        });
    }
    aplicarToggleDataPlantilla();

    // El iframe grande arranca siempre apuntando a la home (ver el src fijo
    // en el template) — si se restauró una pestaña que previsualiza "La
    // tienda" (ver recargarPreservandoTab), hay que corregirlo acá.
    if (previewPagina === 'institucional' && previewFrame) {
        previewFrame.src = catalogoInstitucionalUrl + '?preview_plantilla=' + encodeURIComponent(inputPlantilla.value);
    }

    // ── Elegir plantilla desde las tarjetas ──
    document.querySelectorAll('.co-card-plantilla').forEach(function (card) {
        card.addEventListener('click', function () {
            const valor = card.dataset.plantillaValor;
            if (!inputPlantilla || inputPlantilla.value === valor) return;

            // Guardar en memoria el color de la plantilla que se deja atrás
            // antes de cambiar — así no se pierde ni se mezcla con el de la
            // plantilla nueva (cada una tiene su propio campo, ver arriba).
            guardarColoresVisiblesEn(inputPlantilla.value);
            inputPlantilla.value = valor;
            cargarColoresVisiblesDe(valor);

            document.querySelectorAll('.co-card-plantilla').forEach(function (c) {
                c.classList.toggle('co-card-plantilla--activa', c === card);
            });
            aplicarToggleDataPlantilla();

            // El preview grande cambia al instante (sin guardar) gracias a
            // ?preview_plantilla= en get_template_names() — respeta la página
            // que se esté previsualizando (home o "La tienda"), no siempre home.
            if (previewFrame) {
                const base = previewPagina === 'institucional' ? catalogoInstitucionalUrl : catalogoHomeUrl;
                previewFrame.src = base + '?preview_plantilla=' + encodeURIComponent(valor);
            }
        });
    });

    // El valor a guardar de un color: '' si nunca se tocó para esa plantilla
    // (mantiene el "usa el default" del modelo), el hex elegido si sí.
    function valorColorGuardado(plantilla, campo) {
        const c = coloresPorPlantilla[plantilla];
        const tocada = campo === 'marca' ? c.marcaTocada : c.secundarioTocada;
        if (!tocada) return '';
        return campo === 'marca' ? c.marca : c.secundario;
    }

    formCatalogo.addEventListener('submit', function (e) {
        e.preventDefault();
        // Snapshot de lo que se esté viendo ahora mismo (la plantilla activa
        // puede no haber pasado por un "cambio de card" todavía) antes de
        // armar el payload con los colores de las 3 plantillas juntas.
        guardarColoresVisiblesEn(inputPlantilla.value);
        const msg = document.getElementById('catalogoMsg');
        const guardarCatalogo = fetch(urls.guardar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
                plantilla:          document.getElementById('idCatalogoPlantilla').value,
                hero_titulo:        document.getElementById('idCatalogoHeroTitulo').value,
                hero_subtitulo:     document.getElementById('idCatalogoHeroSubtitulo').value,
                hero_producto:      document.getElementById('idCatalogoHeroProducto')?.value || '',
                hero_imagen_sin_fondo: document.getElementById('idCatalogoHeroSinFondo')?.checked || false,
                tiles_destacados_titulo: document.getElementById('idCatalogoTilesTitulo')?.value || '',
                mostrar_historia_en_home: document.getElementById('idCatalogoMostrarHistoriaHome') ? document.getElementById('idCatalogoMostrarHistoriaHome').checked : true,
                cta_final_titulo:     document.getElementById('idCatalogoCtaFinalTitulo')?.value || '',
                cta_final_texto:      document.getElementById('idCatalogoCtaFinalTexto')?.value || '',
                cta_final_boton_texto: document.getElementById('idCatalogoCtaFinalBotonTexto')?.value || '',
                cta_final_boton_url:  document.getElementById('idCatalogoCtaFinalBotonUrl')?.value || '',
                hero_spot2_producto: document.getElementById('idCatalogoHeroSpot2Producto')?.value || '',
                sobre_nosotros:     document.getElementById('idCatalogoSobreNosotros').value,
                contacto_texto:     document.getElementById('idCatalogoContactoTexto').value,
                color_marca:        valorColorGuardado('almacen', 'marca'),
                color_marca_secundario: valorColorGuardado('almacen', 'secundario'),
                color_marca_bento:      valorColorGuardado('bento', 'marca'),
                color_marca_secundario_bento: valorColorGuardado('bento', 'secundario'),
                color_marca_lumina:     valorColorGuardado('lumina', 'marca'),
                color_marca_secundario_lumina: valorColorGuardado('lumina', 'secundario'),
                color_marca_kinetic:    valorColorGuardado('kinetic', 'marca'),
                color_fondo_bento:        colorFondoTocado ? document.getElementById('idCatalogoColorFondo').value : '',
                color_fondo_bento_oscuro: colorFondoOscuroTocado ? document.getElementById('idCatalogoColorFondoOscuro').value : '',
                color_fondo_kinetic:      colorFondoKineticTocado ? document.getElementById('idCatalogoColorFondoKinetic').value : '',
                kinetic_hero_stat1_titulo: document.getElementById('idCatalogoKineticStat1Titulo')?.value || '',
                kinetic_hero_stat1_valor:  document.getElementById('idCatalogoKineticStat1Valor')?.value || '',
                kinetic_hero_stat2_titulo: document.getElementById('idCatalogoKineticStat2Titulo')?.value || '',
                kinetic_hero_stat2_valor:  document.getElementById('idCatalogoKineticStat2Valor')?.value || '',
                kinetic_hero_stat3_titulo: document.getElementById('idCatalogoKineticStat3Titulo')?.value || '',
                kinetic_hero_stat3_valor:  document.getElementById('idCatalogoKineticStat3Valor')?.value || '',
                nav_catalogo_label: document.getElementById('idCatalogoNavCatalogo').value,
                nav_ofertas_label:  document.getElementById('idCatalogoNavOfertas').value,
                nav_combos_label:   document.getElementById('idCatalogoNavCombos').value,
                nav_tienda_label:   document.getElementById('idCatalogoNavTienda').value,
                institucional_titulo: document.getElementById('idCatalogoInstTitulo').value,
                institucional_bajada: document.getElementById('idCatalogoInstBajada').value,
                destacado1_titulo: document.getElementById('idCatalogoDestacado1Titulo').value,
                destacado1_texto:  document.getElementById('idCatalogoDestacado1Texto').value,
                destacado2_titulo: document.getElementById('idCatalogoDestacado2Titulo').value,
                destacado2_texto:  document.getElementById('idCatalogoDestacado2Texto').value,
                destacado3_titulo: document.getElementById('idCatalogoDestacado3Titulo').value,
                destacado3_texto:  document.getElementById('idCatalogoDestacado3Texto').value,
                horarios_texto:    document.getElementById('idCatalogoHorarios').value,
                instagram_url:     document.getElementById('idCatalogoInstagram').value,
                facebook_url:      document.getElementById('idCatalogoFacebook').value,
                tiktok_url:        document.getElementById('idCatalogoTiktok').value,
            }),
        });

        // Datos de la empresa (pestaña "Contacto") — misma tabla que
        // Configuración → Empresa, mismo endpoint, un solo click en este
        // formulario guarda las dos cosas. Los campos fiscales que no se
        // muestran acá (razón social/CUIT/condición IVA) viajan igual desde
        // los inputs ocultos para no perderlos (ver nota en el template).
        const guardarEmpresa = fetch(empresaUrls.guardar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
                nombre_comercial: document.getElementById('idCatalogoEmpresaNombre').value,
                eslogan:          document.getElementById('idCatalogoEmpresaEslogan').value,
                domicilio:        document.getElementById('idCatalogoEmpresaDomicilio').value,
                telefono:         document.getElementById('idCatalogoEmpresaTelefono').value,
                email:            document.getElementById('idCatalogoEmpresaEmail').value,
                razon_social:     document.getElementById('idCatalogoEmpresaRazonSocial').value,
                cuit:             document.getElementById('idCatalogoEmpresaCuit').value,
                condicion_iva:    document.getElementById('idCatalogoEmpresaCondicionIva').value,
            }),
        });

        Promise.all([guardarCatalogo, guardarEmpresa])
            .then(respuestas => Promise.all(respuestas.map(r => r.json())))
            .then(([dataCatalogo, dataEmpresa]) => {
                const error = dataCatalogo.error || dataEmpresa.error;
                msg.style.color = error ? '#e11d48' : 'var(--success)';
                msg.textContent = error || 'Guardado.';
                // Recargar el iframe solo tiene sentido DESPUÉS de guardar (recién
                // ahí el servidor persiste hero_titulo/hero_subtitulo/textos nuevos
                // para esa plantilla) — el cambio de plantilla en sí ya se ve al
                // instante desde el click en la card, sin esperar este guardado.
                if (!error && previewFrame && previewFrame.contentWindow) {
                    previewFrame.contentWindow.location.reload();
                }
            });
    });

    document.getElementById('inputCatalogoHero')?.addEventListener('change', function () {
        if (!this.files[0]) return;

        if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl);
        heroObjectUrl = URL.createObjectURL(this.files[0]);
        aplicarValoresAlPreview();

        const fd = new FormData();
        fd.append('imagen', this.files[0]);
        fetch(urls.heroImagen, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf() },
            body: fd,
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoHeroPreviewBox').innerHTML =
                    `<img src="${data.imagen_url}" alt="Hero">`;
                document.getElementById('btnEliminarCatalogoHero').style.display = 'inline-block';
            }
        });
    });

    // Tarjetas del hero de Bento — mismo patrón que el hero de Almacén de
    // arriba (subir/eliminar por AJAX, actualiza solo la miniatura del
    // panel), pero sin intentar inyectar nada en el iframe de preview: el
    // producto destacado tampoco se refleja ahí en vivo (solo tras
    // guardar), así que estas 2 imágenes siguen el mismo criterio.
    function initSubidaImagenSpot(inputId, btnEliminarId, boxId, url) {
        document.getElementById(inputId)?.addEventListener('change', function () {
            if (!this.files[0]) return;
            const fd = new FormData();
            fd.append('imagen', this.files[0]);
            fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrf() },
                body: fd,
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    document.getElementById(boxId).innerHTML = `<img src="${data.imagen_url}" alt="">`;
                    const btn = document.getElementById(btnEliminarId);
                    if (btn) btn.style.display = 'inline-block';
                }
            });
        });

        document.getElementById(btnEliminarId)?.addEventListener('click', function () {
            fetch(url, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': csrf() },
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    document.getElementById(boxId).innerHTML =
                        '<span style="font-size:0.7rem; color:var(--text-muted);">Sin imagen</span>';
                    this.style.display = 'none';
                }
            });
        });
    }
    initSubidaImagenSpot('inputCatalogoHeroSpot1', 'btnEliminarCatalogoHeroSpot1', 'catalogoHeroSpot1PreviewBox', urls.heroSpot1Imagen);
    initSubidaImagenSpot('inputCatalogoHeroSpot2', 'btnEliminarCatalogoHeroSpot2', 'catalogoHeroSpot2PreviewBox', urls.heroSpot2Imagen);
    initSubidaImagenSpot('inputCatalogoCtaFinalImagen', 'btnEliminarCatalogoCtaFinalImagen', 'catalogoCtaFinalImagenPreviewBox', urls.ctaFinalImagen);

    document.getElementById('btnEliminarCatalogoHero')?.addEventListener('click', function () {
        fetch(urls.heroImagen, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrf() },
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoHeroPreviewBox').innerHTML =
                    '<span style="font-size:0.7rem; color:var(--text-muted);">Sin imagen</span>';
                this.style.display = 'none';
                if (heroObjectUrl) {
                    URL.revokeObjectURL(heroObjectUrl);
                    heroObjectUrl = null;
                }
                // Más simple y robusto que reconstruir a mano el SVG de
                // fallback del hero — el listener 'load' de arriba se
                // encarga de reaplicar los textos vigentes tras recargar.
                if (previewFrame && previewFrame.contentWindow) {
                    previewFrame.contentWindow.location.reload();
                }
            }
        });
    });

    // ── Fondo del hero de "Kinetic" (mismo patrón que la imagen del hero) ──
    document.getElementById('inputCatalogoKineticFondo')?.addEventListener('change', function () {
        if (!this.files[0]) return;

        if (kineticFondoObjectUrl) URL.revokeObjectURL(kineticFondoObjectUrl);
        kineticFondoObjectUrl = URL.createObjectURL(this.files[0]);
        aplicarValoresAlPreview();

        const fd = new FormData();
        fd.append('imagen', this.files[0]);
        fetch(urls.kineticHeroFondo, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf() },
            body: fd,
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoKineticFondoPreviewBox').innerHTML =
                    `<img src="${data.imagen_url}" alt="Fondo del hero">`;
                document.getElementById('btnEliminarCatalogoKineticFondo').style.display = 'inline-block';
            }
        });
    });

    document.getElementById('btnEliminarCatalogoKineticFondo')?.addEventListener('click', function () {
        fetch(urls.kineticHeroFondo, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrf() },
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoKineticFondoPreviewBox').innerHTML =
                    '<span style="font-size:0.7rem; color:var(--text-muted);">Sin imagen</span>';
                this.style.display = 'none';
                if (kineticFondoObjectUrl) {
                    URL.revokeObjectURL(kineticFondoObjectUrl);
                    kineticFondoObjectUrl = null;
                }
                if (previewFrame && previewFrame.contentWindow) {
                    previewFrame.contentWindow.location.reload();
                }
            }
        });
    });

    // ── Imagen de portada de "La tienda" (mismo patrón que la del hero) ──
    document.getElementById('inputCatalogoInstImagen')?.addEventListener('change', function () {
        if (!this.files[0]) return;

        if (instImagenObjectUrl) URL.revokeObjectURL(instImagenObjectUrl);
        instImagenObjectUrl = URL.createObjectURL(this.files[0]);
        aplicarValoresAlPreview();

        const fd = new FormData();
        fd.append('imagen', this.files[0]);
        fetch(urls.institucionalImagen, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf() },
            body: fd,
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoInstImagenPreviewBox').innerHTML =
                    `<img src="${data.imagen_url}" alt="Portada">`;
                document.getElementById('btnEliminarCatalogoInstImagen').style.display = 'inline-block';
            }
        });
    });

    document.getElementById('btnEliminarCatalogoInstImagen')?.addEventListener('click', function () {
        fetch(urls.institucionalImagen, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrf() },
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoInstImagenPreviewBox').innerHTML =
                    '<span style="font-size:0.7rem; color:var(--text-muted);">Sin imagen</span>';
                this.style.display = 'none';
                if (instImagenObjectUrl) {
                    URL.revokeObjectURL(instImagenObjectUrl);
                    instImagenObjectUrl = null;
                }
                if (previewFrame && previewFrame.contentWindow) {
                    previewFrame.contentWindow.location.reload();
                }
            }
        });
    });

    // ── Logo de la empresa — mismo endpoint que usa Configuración → Empresa
    //    (core:empresa_logo), subida instantánea igual que el resto de las
    //    imágenes de este panel. Los datos de texto de la empresa viajan
    //    junto con el resto del formulario (ver el submit de más abajo). ──
    const empresaUrls = window.CONFIG_EMPRESA_URLS || {};

    document.getElementById('inputCatalogoEmpresaLogo')?.addEventListener('change', function () {
        if (!this.files[0]) return;
        const fd = new FormData();
        fd.append('logo', this.files[0]);
        fetch(empresaUrls.logo, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf() },
            body: fd,
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoEmpresaLogoPreviewBox').innerHTML =
                    `<img src="${data.logo_url}" alt="Logo">`;
                document.getElementById('btnEliminarCatalogoEmpresaLogo').style.display = 'inline-block';
                if (previewFrame && previewFrame.contentWindow) previewFrame.contentWindow.location.reload();
            }
        });
    });

    document.getElementById('btnEliminarCatalogoEmpresaLogo')?.addEventListener('click', function () {
        fetch(empresaUrls.logo, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrf() },
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('catalogoEmpresaLogoPreviewBox').innerHTML =
                    '<span style="font-size:0.6rem; color:var(--text-muted);">Sin logo</span>';
                this.style.display = 'none';
                if (previewFrame && previewFrame.contentWindow) previewFrame.contentWindow.location.reload();
            }
        });
    });

    // ── Galería de fotos de "La tienda" — a diferencia de los slides, la
    //    foto se sube en un solo paso (no hay ningún campo de texto
    //    obligatorio que la bloquee) — ver CatalogoGaleriaImagenAjax. ──
    const urlsGaleria = window.CONFIG_GALERIA_URLS || {};
    document.getElementById('inputGaleriaImagen')?.addEventListener('change', function () {
        if (!this.files[0]) return;
        const msg = document.getElementById('galeriaMsg');
        const fd = new FormData();
        fd.append('imagen', this.files[0]);
        fetch(urlsGaleria.imagen, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf() },
            body: fd,
        })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                msg.style.color = '#e11d48';
                msg.textContent = data.error;
                return;
            }
            recargarPreservandoTab();
        });
        this.value = '';
    });

    document.querySelectorAll('.btn-eliminar-galeria').forEach(function (btn) {
        btn.addEventListener('click', async function () {
            const item = btn.closest('.galeria-item-admin');
            const ok = await KaiConfirm('¿Seguro que querés eliminar esta foto?');
            if (!ok) return;
            fetch(urlsGaleria.eliminar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                body: JSON.stringify({ pk: item.dataset.pk }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                recargarPreservandoTab();
            });
        });
    });

    // ── Slides del carrusel (plantilla "Bento") ──
    const formSlide = document.getElementById('formSlide');
    if (formSlide) {
        const csrfSlide = () => formSlide.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsSlide = window.CONFIG_SLIDES_URLS || {};
        const modalEl = document.getElementById('slideModal');
        const modal = window.bootstrap ? new bootstrap.Modal(modalEl) : null;
        let slideImagenFile = null;

        function limpiarFormSlide() {
            document.getElementById('slidePk').value = '';
            document.getElementById('slideEyebrow').value = '';
            document.getElementById('slideTitulo').value = '';
            document.getElementById('slideDescripcion').value = '';
            document.getElementById('slideCtaTexto').value = '';
            document.getElementById('slideImagenPreviewBox').innerHTML =
                '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
            document.getElementById('slideMsg').textContent = '';
            slideImagenFile = null;
        }

        document.getElementById('btnNuevoSlide')?.addEventListener('click', function () {
            limpiarFormSlide();
            document.getElementById('slideModalLabel').textContent = 'Nuevo slide';
        });

        document.querySelectorAll('.btn-editar-slide').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.slide-row');
                limpiarFormSlide();
                document.getElementById('slideModalLabel').textContent = 'Editar slide';
                document.getElementById('slidePk').value = row.dataset.pk;
                document.getElementById('slideEyebrow').value = row.dataset.eyebrow;
                document.getElementById('slideTitulo').value = row.dataset.titulo;
                document.getElementById('slideDescripcion').value = row.dataset.descripcion;
                document.getElementById('slideCtaTexto').value = row.dataset.ctaTexto;
                const imgActual = row.querySelector('.config-logo-box img');
                if (imgActual) {
                    document.getElementById('slideImagenPreviewBox').innerHTML = `<img src="${imgActual.src}" alt="">`;
                }
                if (modal) modal.show();
            });
        });

        document.getElementById('inputSlideImagen').addEventListener('change', function () {
            if (!this.files[0]) return;
            slideImagenFile = this.files[0];
            document.getElementById('slideImagenPreviewBox').innerHTML =
                `<img src="${URL.createObjectURL(slideImagenFile)}" alt="">`;
        });

        document.querySelectorAll('.btn-eliminar-slide').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.slide-row');
                const ok = await KaiConfirm(`¿Seguro que querés eliminar el slide "${row.dataset.titulo}"?`);
                if (!ok) return;
                fetch(urlsSlide.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfSlide() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formSlide.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('slideMsg');
            const pk = document.getElementById('slidePk').value || null;
            fetch(urlsSlide.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfSlide() },
                body: JSON.stringify({
                    pk: pk,
                    eyebrow: document.getElementById('slideEyebrow').value,
                    titulo: document.getElementById('slideTitulo').value,
                    descripcion: document.getElementById('slideDescripcion').value,
                    cta_texto: document.getElementById('slideCtaTexto').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                if (!slideImagenFile) {
                    recargarPreservandoTab();
                    return;
                }
                const fd = new FormData();
                fd.append('pk', data.pk);
                fd.append('imagen', slideImagenFile);
                fetch(urlsSlide.imagen, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfSlide() },
                    body: fd,
                })
                .then(r => r.json())
                .then(function (dataImg) {
                    if (dataImg.error) {
                        msg.style.color = '#e11d48';
                        msg.textContent = dataImg.error;
                        return;
                    }
                    recargarPreservandoTab();
                });
            });
        });
    }

    // ── Carteles promocionales de Almacén (hasta 6 en total). En el panel
    //    aparecen agrupados por ubicación, aunque conservan un solo formato. ──
    const formBanner = document.getElementById('formBanner');
    if (formBanner) {
        const csrfBanner = () => formBanner.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsBanner = window.CONFIG_BANNERS_URLS || {};
        const modalBannerEl = document.getElementById('bannerModal');
        const modalBanner = window.bootstrap ? new bootstrap.Modal(modalBannerEl) : null;
        const colorFondoDefault = document.getElementById('bannerColorFondo').value;
        let bannerImagenFile = null;
        let bannerTieneImagenGuardada = false;

        function limpiarFormBanner() {
            document.getElementById('bannerPk').value = '';
            document.getElementById('bannerPosicion').value = 'debajo_hero';
            document.getElementById('bannerTitulo').value = '';
            document.getElementById('bannerTexto').value = '';
            document.getElementById('bannerColorFondo').value = colorFondoDefault;
            document.getElementById('bannerCtaTexto').value = '';
            document.getElementById('bannerCtaUrl').value = '';
            document.getElementById('bannerImagenPreviewBox').innerHTML =
                '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
            document.getElementById('btnQuitarBannerImagen').style.display = 'none';
            document.getElementById('bannerMsg').textContent = '';
            bannerImagenFile = null;
            bannerTieneImagenGuardada = false;
        }

        document.querySelectorAll('.btn-nuevo-banner-almacen').forEach(function (btn) {
            btn.addEventListener('click', function () {
                limpiarFormBanner();
                document.getElementById('bannerPosicion').value = btn.dataset.bannerPosicion;
                document.getElementById('bannerModalLabel').textContent = `Nuevo cartel · ${btn.dataset.bannerEtiqueta}`;
                document.getElementById('bannerModalSubtitle').textContent = `Ubicación fija: ${btn.dataset.bannerEtiqueta}`;
            });
        });

        document.querySelectorAll('.btn-editar-banner').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.banner-row');
                const ubicacion = row.closest('.co-almacen-grupo')
                    .querySelector('.co-almacen-grupo-head .config-row-label').textContent.trim();
                limpiarFormBanner();
                document.getElementById('bannerModalLabel').textContent = `Editar cartel · ${ubicacion}`;
                document.getElementById('bannerModalSubtitle').textContent = `Ubicación fija: ${ubicacion}`;
                document.getElementById('bannerPk').value = row.dataset.pk;
                document.getElementById('bannerPosicion').value = row.dataset.posicion;
                document.getElementById('bannerTitulo').value = row.dataset.titulo;
                document.getElementById('bannerTexto').value = row.dataset.texto;
                document.getElementById('bannerColorFondo').value = row.dataset.colorFondo || colorFondoDefault;
                document.getElementById('bannerCtaTexto').value = row.dataset.ctaTexto;
                document.getElementById('bannerCtaUrl').value = row.dataset.ctaUrl;
                const imgActual = row.querySelector('.config-logo-box img');
                if (imgActual) {
                    document.getElementById('bannerImagenPreviewBox').innerHTML = `<img src="${imgActual.src}" alt="">`;
                    document.getElementById('btnQuitarBannerImagen').style.display = 'inline-block';
                    bannerTieneImagenGuardada = true;
                }
                if (modalBanner) modalBanner.show();
            });
        });

        document.getElementById('inputBannerImagen').addEventListener('change', function () {
            if (!this.files[0]) return;
            bannerImagenFile = this.files[0];
            document.getElementById('bannerImagenPreviewBox').innerHTML =
                `<img src="${URL.createObjectURL(bannerImagenFile)}" alt="">`;
            document.getElementById('btnQuitarBannerImagen').style.display = 'inline-block';
        });

        document.getElementById('btnQuitarBannerImagen').addEventListener('click', function () {
            const pk = document.getElementById('bannerPk').value;
            function quitarLocal() {
                bannerImagenFile = null;
                bannerTieneImagenGuardada = false;
                document.getElementById('bannerImagenPreviewBox').innerHTML =
                    '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
                document.getElementById('btnQuitarBannerImagen').style.display = 'none';
            }
            if (!bannerTieneImagenGuardada || !pk) { quitarLocal(); return; }
            fetch(urlsBanner.imagen, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBanner() },
                body: JSON.stringify({ pk: pk }),
            })
            .then(r => r.json())
            .then(function (data) {
                if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                quitarLocal();
            });
        });

        document.getElementById('btnResetBannerColor')?.addEventListener('click', function () {
            document.getElementById('bannerColorFondo').value = colorFondoDefault;
        });

        document.querySelectorAll('.btn-eliminar-banner').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.banner-row');
                const ok = await KaiConfirm(`¿Seguro que querés eliminar el banner "${row.dataset.titulo}"?`);
                if (!ok) return;
                fetch(urlsBanner.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBanner() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formBanner.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('bannerMsg');
            const pk = document.getElementById('bannerPk').value || null;
            fetch(urlsBanner.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBanner() },
                body: JSON.stringify({
                    pk: pk,
                    posicion: document.getElementById('bannerPosicion').value,
                    titulo: document.getElementById('bannerTitulo').value,
                    texto: document.getElementById('bannerTexto').value,
                    color_fondo: document.getElementById('bannerColorFondo').value,
                    cta_texto: document.getElementById('bannerCtaTexto').value,
                    cta_url: document.getElementById('bannerCtaUrl').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                if (!bannerImagenFile) {
                    recargarPreservandoTab();
                    return;
                }
                const fd = new FormData();
                fd.append('pk', data.pk);
                fd.append('imagen', bannerImagenFile);
                fetch(urlsBanner.imagen, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfBanner() },
                    body: fd,
                })
                .then(r => r.json())
                .then(function (dataImg) {
                    if (dataImg.error) {
                        msg.style.color = '#e11d48';
                        msg.textContent = dataImg.error;
                        return;
                    }
                    recargarPreservandoTab();
                });
            });
        });
    }

    // ── Categorías/marcas destacadas (opcional, hasta 16) ──
    const formTile = document.getElementById('formTile');
    if (formTile) {
        const csrfTile = () => formTile.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsTile = window.CONFIG_TILES_URLS || {};
        const modalTileEl = document.getElementById('tileModal');
        const modalTile = window.bootstrap ? new bootstrap.Modal(modalTileEl) : null;
        let tileImagenFile = null;

        function mostrarFilaTipo() {
            const esCategoria = document.getElementById('tileTipo').value === 'categoria';
            document.getElementById('tileFilaCategoria').style.display = esCategoria ? '' : 'none';
            document.getElementById('tileFilaMarca').style.display = esCategoria ? 'none' : '';
        }

        function limpiarFormTile() {
            document.getElementById('tilePk').value = '';
            document.getElementById('tileTipo').value = 'categoria';
            document.getElementById('tileCategoria').value = '';
            document.getElementById('tileMarca').value = '';
            document.getElementById('tileEtiqueta').value = '';
            document.getElementById('tileImagenPreviewBox').innerHTML =
                '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
            document.getElementById('tileMsg').textContent = '';
            tileImagenFile = null;
            mostrarFilaTipo();
        }

        document.querySelectorAll('.btn-nuevo-tile-almacen').forEach(function (btn) {
            btn.addEventListener('click', function () {
                limpiarFormTile();
                document.getElementById('tileTipo').value = btn.dataset.tileTipo;
                mostrarFilaTipo();
                document.getElementById('tileModalLabel').textContent =
                    btn.dataset.tileTipo === 'categoria' ? 'Nueva categoría' : 'Nueva marca';
            });
        });

        document.querySelectorAll('.btn-editar-tile').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.tile-row');
                limpiarFormTile();
                document.getElementById('tileModalLabel').textContent =
                    row.dataset.tipo === 'categoria' ? 'Editar categoría' : 'Editar marca';
                document.getElementById('tilePk').value = row.dataset.pk;
                document.getElementById('tileTipo').value = row.dataset.tipo;
                document.getElementById('tileCategoria').value = row.dataset.categoria;
                document.getElementById('tileMarca').value = row.dataset.marca;
                document.getElementById('tileEtiqueta').value = row.dataset.etiqueta;
                mostrarFilaTipo();
                const imgActual = row.querySelector('.config-logo-box img');
                if (imgActual) {
                    document.getElementById('tileImagenPreviewBox').innerHTML = `<img src="${imgActual.src}" alt="">`;
                }
                if (modalTile) modalTile.show();
            });
        });

        document.getElementById('inputTileImagen').addEventListener('change', function () {
            if (!this.files[0]) return;
            tileImagenFile = this.files[0];
            document.getElementById('tileImagenPreviewBox').innerHTML =
                `<img src="${URL.createObjectURL(tileImagenFile)}" alt="">`;
        });

        document.querySelectorAll('.btn-eliminar-tile').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.tile-row');
                const nombre = row.dataset.etiqueta || row.querySelector('.config-row-label').textContent;
                const ok = await KaiConfirm(`¿Seguro que querés eliminar "${nombre}"?`);
                if (!ok) return;
                fetch(urlsTile.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfTile() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formTile.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('tileMsg');
            const pk = document.getElementById('tilePk').value || null;
            fetch(urlsTile.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfTile() },
                body: JSON.stringify({
                    pk: pk,
                    tipo: document.getElementById('tileTipo').value,
                    categoria: document.getElementById('tileCategoria').value,
                    marca: document.getElementById('tileMarca').value,
                    etiqueta: document.getElementById('tileEtiqueta').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                if (!tileImagenFile) {
                    recargarPreservandoTab();
                    return;
                }
                const fd = new FormData();
                fd.append('pk', data.pk);
                fd.append('imagen', tileImagenFile);
                fetch(urlsTile.imagen, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfTile() },
                    body: fd,
                })
                .then(r => r.json())
                .then(function (dataImg) {
                    if (dataImg.error) {
                        msg.style.color = '#e11d48';
                        msg.textContent = dataImg.error;
                        return;
                    }
                    recargarPreservandoTab();
                });
            });
        });
    }

    // ── Filas de productos de Almacén — hasta tres categorías cuyo contenido
    //    se alimenta automáticamente en la home. ──
    const formGondolaAlmacen = document.getElementById('formGondolaAlmacen');
    if (formGondolaAlmacen) {
        const csrfGondola = () => formGondolaAlmacen.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsGondola = window.CONFIG_GONDOLAS_ALMACEN_URLS || {};
        const modalGondolaEl = document.getElementById('gondolaAlmacenModal');
        const modalGondola = window.bootstrap ? new bootstrap.Modal(modalGondolaEl) : null;

        function limpiarFormGondolaAlmacen() {
            document.getElementById('gondolaAlmacenPk').value = '';
            document.getElementById('gondolaAlmacenCategoria').value = '';
            document.getElementById('gondolaAlmacenTitulo').value = '';
            document.getElementById('gondolaAlmacenSubtitulo').value = '';
            document.getElementById('gondolaAlmacenMsg').textContent = '';
        }

        document.getElementById('btnNuevaGondolaAlmacen')?.addEventListener('click', function () {
            limpiarFormGondolaAlmacen();
            document.getElementById('gondolaAlmacenModalLabel').textContent = 'Nueva fila de productos';
        });

        document.querySelectorAll('.btn-editar-gondola-almacen').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.gondola-almacen-row');
                limpiarFormGondolaAlmacen();
                document.getElementById('gondolaAlmacenModalLabel').textContent = 'Editar fila de productos';
                document.getElementById('gondolaAlmacenPk').value = row.dataset.pk;
                document.getElementById('gondolaAlmacenCategoria').value = row.dataset.categoria;
                document.getElementById('gondolaAlmacenTitulo').value = row.dataset.titulo;
                document.getElementById('gondolaAlmacenSubtitulo').value = row.dataset.subtitulo;
                if (modalGondola) modalGondola.show();
            });
        });

        document.querySelectorAll('.btn-eliminar-gondola-almacen').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.gondola-almacen-row');
                const nombre = row.querySelector('.config-row-label').textContent.trim();
                const ok = await KaiConfirm(`¿Seguro que querés eliminar la fila "${nombre}"?`);
                if (!ok) return;
                fetch(urlsGondola.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfGondola() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formGondolaAlmacen.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('gondolaAlmacenMsg');
            fetch(urlsGondola.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfGondola() },
                body: JSON.stringify({
                    pk: document.getElementById('gondolaAlmacenPk').value || null,
                    categoria: document.getElementById('gondolaAlmacenCategoria').value,
                    titulo: document.getElementById('gondolaAlmacenTitulo').value,
                    subtitulo: document.getElementById('gondolaAlmacenSubtitulo').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                recargarPreservandoTab();
            });
        });
    }

    // ── Banners/anuncios de Bento — tres formatos visuales con cupos
    //    independientes. Comparten tabla, pero el editor no los mezcla. ──
    const formBannerBento = document.getElementById('formBannerBento');
    if (formBannerBento) {
        const csrfBannerBento = () => formBannerBento.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsBannerBento = window.CONFIG_BANNERS_BENTO_URLS || {};
        const modalBannerBentoEl = document.getElementById('bannerBentoModal');
        const modalBannerBento = window.bootstrap ? new bootstrap.Modal(modalBannerBentoEl) : null;
        const colorFondoBentoDefault = document.getElementById('bannerBentoColorFondo').value;
        let bannerBentoImagenFile = null;
        let bannerBentoTieneImagenGuardada = false;
        const posicionesPorFormatoBannerBento = {
            novedades: ['novedades'],
            promos: ['promos_mes'],
            franjas: ['antes_destacados', 'antes_combos'],
        };
        const nombresFormatoBannerBento = {
            novedades: 'Novedades',
            promos: 'Promos del mes',
            franjas: 'Franjas anchas',
        };

        function configurarFormatoBannerBento(formato, posicion) {
            const permitidas = posicionesPorFormatoBannerBento[formato] || posicionesPorFormatoBannerBento.novedades;
            const select = document.getElementById('bannerBentoPosicion');
            Array.from(select.options).forEach(function (option) {
                const visible = permitidas.includes(option.value);
                option.disabled = !visible;
                option.hidden = !visible;
            });
            select.value = permitidas.includes(posicion) ? posicion : permitidas[0];
            document.getElementById('bannerBentoModalSubtitle').textContent =
                `${nombresFormatoBannerBento[formato] || 'Banner'} · imagen o color sólido`;
        }

        function limpiarFormBannerBento() {
            document.getElementById('bannerBentoPk').value = '';
            document.getElementById('bannerBentoPosicion').value = 'novedades';
            document.getElementById('bannerBentoTitulo').value = '';
            document.getElementById('bannerBentoTexto').value = '';
            document.getElementById('bannerBentoColorFondo').value = colorFondoBentoDefault;
            document.getElementById('bannerBentoCtaTexto').value = '';
            document.getElementById('bannerBentoCtaUrl').value = '';
            document.getElementById('bannerBentoImagenPreviewBox').innerHTML =
                '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
            document.getElementById('btnQuitarBannerBentoImagen').style.display = 'none';
            document.getElementById('bannerBentoMsg').textContent = '';
            bannerBentoImagenFile = null;
            bannerBentoTieneImagenGuardada = false;
        }

        document.querySelectorAll('.btn-nuevo-banner-bento').forEach(function (btn) {
            btn.addEventListener('click', function () {
                limpiarFormBannerBento();
                configurarFormatoBannerBento(btn.dataset.bannerFormato, btn.dataset.bannerPosicion);
                document.getElementById('bannerBentoModalLabel').textContent =
                    `Nuevo banner · ${nombresFormatoBannerBento[btn.dataset.bannerFormato]}`;
            });
        });

        document.querySelectorAll('.btn-editar-banner-bento').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.banner-bento-row');
                limpiarFormBannerBento();
                configurarFormatoBannerBento(row.dataset.formato, row.dataset.posicion);
                document.getElementById('bannerBentoModalLabel').textContent =
                    `Editar banner · ${nombresFormatoBannerBento[row.dataset.formato]}`;
                document.getElementById('bannerBentoPk').value = row.dataset.pk;
                document.getElementById('bannerBentoTitulo').value = row.dataset.titulo;
                document.getElementById('bannerBentoTexto').value = row.dataset.texto;
                document.getElementById('bannerBentoColorFondo').value = row.dataset.colorFondo || colorFondoBentoDefault;
                document.getElementById('bannerBentoCtaTexto').value = row.dataset.ctaTexto;
                document.getElementById('bannerBentoCtaUrl').value = row.dataset.ctaUrl;
                const imgActual = row.querySelector('.config-logo-box img');
                if (imgActual) {
                    document.getElementById('bannerBentoImagenPreviewBox').innerHTML = `<img src="${imgActual.src}" alt="">`;
                    document.getElementById('btnQuitarBannerBentoImagen').style.display = 'inline-block';
                    bannerBentoTieneImagenGuardada = true;
                }
                if (modalBannerBento) modalBannerBento.show();
            });
        });

        document.getElementById('inputBannerBentoImagen').addEventListener('change', function () {
            if (!this.files[0]) return;
            bannerBentoImagenFile = this.files[0];
            document.getElementById('bannerBentoImagenPreviewBox').innerHTML =
                `<img src="${URL.createObjectURL(bannerBentoImagenFile)}" alt="">`;
            document.getElementById('btnQuitarBannerBentoImagen').style.display = 'inline-block';
        });

        document.getElementById('btnQuitarBannerBentoImagen').addEventListener('click', function () {
            const pk = document.getElementById('bannerBentoPk').value;
            function quitarLocal() {
                bannerBentoImagenFile = null;
                bannerBentoTieneImagenGuardada = false;
                document.getElementById('bannerBentoImagenPreviewBox').innerHTML =
                    '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
                document.getElementById('btnQuitarBannerBentoImagen').style.display = 'none';
            }
            if (!bannerBentoTieneImagenGuardada || !pk) { quitarLocal(); return; }
            fetch(urlsBannerBento.imagen, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBannerBento() },
                body: JSON.stringify({ pk: pk }),
            })
            .then(r => r.json())
            .then(function (data) {
                if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                quitarLocal();
            });
        });

        document.getElementById('btnResetBannerBentoColor')?.addEventListener('click', function () {
            document.getElementById('bannerBentoColorFondo').value = colorFondoBentoDefault;
        });

        document.querySelectorAll('.btn-eliminar-banner-bento').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.banner-bento-row');
                const ok = await KaiConfirm(`¿Seguro que querés eliminar el banner "${row.dataset.titulo}"?`);
                if (!ok) return;
                fetch(urlsBannerBento.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBannerBento() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formBannerBento.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('bannerBentoMsg');
            const pk = document.getElementById('bannerBentoPk').value || null;
            fetch(urlsBannerBento.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBannerBento() },
                body: JSON.stringify({
                    pk: pk,
                    posicion: document.getElementById('bannerBentoPosicion').value,
                    titulo: document.getElementById('bannerBentoTitulo').value,
                    texto: document.getElementById('bannerBentoTexto').value,
                    color_fondo: document.getElementById('bannerBentoColorFondo').value,
                    cta_texto: document.getElementById('bannerBentoCtaTexto').value,
                    cta_url: document.getElementById('bannerBentoCtaUrl').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                if (!bannerBentoImagenFile) {
                    recargarPreservandoTab();
                    return;
                }
                const fd = new FormData();
                fd.append('pk', data.pk);
                fd.append('imagen', bannerBentoImagenFile);
                fetch(urlsBannerBento.imagen, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfBannerBento() },
                    body: fd,
                })
                .then(r => r.json())
                .then(function (dataImg) {
                    if (dataImg.error) {
                        msg.style.color = '#e11d48';
                        msg.textContent = dataImg.error;
                        return;
                    }
                    recargarPreservandoTab();
                });
            });
        });
    }

    // ── Mensajes de la barra de anuncios (opcional, hasta 5, plantilla "Bento") ──
    const formTicker = document.getElementById('formTicker');
    if (formTicker) {
        const csrfTicker = () => formTicker.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsTicker = window.CONFIG_TICKER_URLS || {};
        const modalTickerEl = document.getElementById('tickerModal');
        const modalTicker = window.bootstrap ? new bootstrap.Modal(modalTickerEl) : null;

        function limpiarFormTicker() {
            document.getElementById('tickerPk').value = '';
            document.getElementById('tickerTexto').value = '';
            document.getElementById('tickerMsg').textContent = '';
        }

        document.getElementById('btnNuevoTicker')?.addEventListener('click', function () {
            limpiarFormTicker();
            document.getElementById('tickerModalLabel').textContent = 'Nuevo mensaje';
        });

        document.querySelectorAll('.btn-editar-ticker').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.ticker-row');
                limpiarFormTicker();
                document.getElementById('tickerModalLabel').textContent = 'Editar mensaje';
                document.getElementById('tickerPk').value = row.dataset.pk;
                document.getElementById('tickerTexto').value = row.dataset.texto;
                if (modalTicker) modalTicker.show();
            });
        });

        document.querySelectorAll('.btn-eliminar-ticker').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.ticker-row');
                const ok = await KaiConfirm(`¿Seguro que querés eliminar el mensaje "${row.dataset.texto}"?`);
                if (!ok) return;
                fetch(urlsTicker.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfTicker() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formTicker.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('tickerMsg');
            const pk = document.getElementById('tickerPk').value || null;
            fetch(urlsTicker.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfTicker() },
                body: JSON.stringify({ pk: pk, texto: document.getElementById('tickerTexto').value }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                recargarPreservandoTab();
            });
        });
    }

    // ── Mensajes de la barra de estado (opcional, hasta 4, plantilla "Kinetic") ──
    const formTickerKinetic = document.getElementById('formTickerKinetic');
    if (formTickerKinetic) {
        const csrfTickerKinetic = () => formTickerKinetic.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsTickerKinetic = window.CONFIG_TICKER_KINETIC_URLS || {};
        const modalTickerKineticEl = document.getElementById('tickerKineticModal');
        const modalTickerKinetic = window.bootstrap ? new bootstrap.Modal(modalTickerKineticEl) : null;

        function limpiarFormTickerKinetic() {
            document.getElementById('tickerKineticPk').value = '';
            document.getElementById('tickerKineticTexto').value = '';
            document.getElementById('tickerKineticMsg').textContent = '';
        }

        document.getElementById('btnNuevoTickerKinetic')?.addEventListener('click', function () {
            limpiarFormTickerKinetic();
            document.getElementById('tickerKineticModalLabel').textContent = 'Nuevo mensaje';
        });

        document.querySelectorAll('.btn-editar-ticker-kinetic').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.ticker-kinetic-row');
                limpiarFormTickerKinetic();
                document.getElementById('tickerKineticModalLabel').textContent = 'Editar mensaje';
                document.getElementById('tickerKineticPk').value = row.dataset.pk;
                document.getElementById('tickerKineticTexto').value = row.dataset.texto;
                if (modalTickerKinetic) modalTickerKinetic.show();
            });
        });

        document.querySelectorAll('.btn-eliminar-ticker-kinetic').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.ticker-kinetic-row');
                const ok = await KaiConfirm(`¿Seguro que querés eliminar el mensaje "${row.dataset.texto}"?`);
                if (!ok) return;
                fetch(urlsTickerKinetic.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfTickerKinetic() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formTickerKinetic.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('tickerKineticMsg');
            const pk = document.getElementById('tickerKineticPk').value || null;
            fetch(urlsTickerKinetic.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfTickerKinetic() },
                body: JSON.stringify({ pk: pk, texto: document.getElementById('tickerKineticTexto').value }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                recargarPreservandoTab();
            });
        });
    }

    // ── Banners de Kinetic (opcional, hasta 3) — tabla propia, rail único
    //    (sin 'posicion', a diferencia de Bento) — mismo patrón que formBannerBento. ──
    const formBannerKinetic = document.getElementById('formBannerKinetic');
    if (formBannerKinetic) {
        const csrfBannerKinetic = () => formBannerKinetic.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsBannerKinetic = window.CONFIG_BANNERS_KINETIC_URLS || {};
        const modalBannerKineticEl = document.getElementById('bannerKineticModal');
        const modalBannerKinetic = window.bootstrap ? new bootstrap.Modal(modalBannerKineticEl) : null;
        const colorFondoKineticBannerDefault = document.getElementById('bannerKineticColorFondo').value;
        let bannerKineticImagenFile = null;
        let bannerKineticTieneImagenGuardada = false;

        function limpiarFormBannerKinetic() {
            document.getElementById('bannerKineticPk').value = '';
            document.getElementById('bannerKineticTitulo').value = '';
            document.getElementById('bannerKineticTexto').value = '';
            document.getElementById('bannerKineticColorFondo').value = colorFondoKineticBannerDefault;
            document.getElementById('bannerKineticCtaTexto').value = '';
            document.getElementById('bannerKineticCtaUrl').value = '';
            document.getElementById('bannerKineticImagenPreviewBox').innerHTML =
                '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
            document.getElementById('btnQuitarBannerKineticImagen').style.display = 'none';
            document.getElementById('bannerKineticMsg').textContent = '';
            bannerKineticImagenFile = null;
            bannerKineticTieneImagenGuardada = false;
        }

        document.getElementById('btnNuevoBannerKinetic')?.addEventListener('click', function () {
            limpiarFormBannerKinetic();
            document.getElementById('bannerKineticModalLabel').textContent = 'Nuevo banner';
        });

        document.querySelectorAll('.btn-editar-banner-kinetic').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.banner-kinetic-row');
                limpiarFormBannerKinetic();
                document.getElementById('bannerKineticModalLabel').textContent = 'Editar banner';
                document.getElementById('bannerKineticPk').value = row.dataset.pk;
                document.getElementById('bannerKineticTitulo').value = row.dataset.titulo;
                document.getElementById('bannerKineticTexto').value = row.dataset.texto;
                document.getElementById('bannerKineticColorFondo').value = row.dataset.colorFondo || colorFondoKineticBannerDefault;
                document.getElementById('bannerKineticCtaTexto').value = row.dataset.ctaTexto;
                document.getElementById('bannerKineticCtaUrl').value = row.dataset.ctaUrl;
                const imgActual = row.querySelector('.config-logo-box img');
                if (imgActual) {
                    document.getElementById('bannerKineticImagenPreviewBox').innerHTML = `<img src="${imgActual.src}" alt="">`;
                    document.getElementById('btnQuitarBannerKineticImagen').style.display = 'inline-block';
                    bannerKineticTieneImagenGuardada = true;
                }
                if (modalBannerKinetic) modalBannerKinetic.show();
            });
        });

        document.getElementById('inputBannerKineticImagen').addEventListener('change', function () {
            if (!this.files[0]) return;
            bannerKineticImagenFile = this.files[0];
            document.getElementById('bannerKineticImagenPreviewBox').innerHTML =
                `<img src="${URL.createObjectURL(bannerKineticImagenFile)}" alt="">`;
            document.getElementById('btnQuitarBannerKineticImagen').style.display = 'inline-block';
        });

        document.getElementById('btnQuitarBannerKineticImagen').addEventListener('click', function () {
            const pk = document.getElementById('bannerKineticPk').value;
            function quitarLocal() {
                bannerKineticImagenFile = null;
                bannerKineticTieneImagenGuardada = false;
                document.getElementById('bannerKineticImagenPreviewBox').innerHTML =
                    '<span style="font-size:0.6rem; color:var(--text-muted);">Sin imagen</span>';
                document.getElementById('btnQuitarBannerKineticImagen').style.display = 'none';
            }
            if (!bannerKineticTieneImagenGuardada || !pk) { quitarLocal(); return; }
            fetch(urlsBannerKinetic.imagen, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBannerKinetic() },
                body: JSON.stringify({ pk: pk }),
            })
            .then(r => r.json())
            .then(function (data) {
                if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                quitarLocal();
            });
        });

        document.getElementById('btnResetBannerKineticColor')?.addEventListener('click', function () {
            document.getElementById('bannerKineticColorFondo').value = colorFondoKineticBannerDefault;
        });

        document.querySelectorAll('.btn-eliminar-banner-kinetic').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.banner-kinetic-row');
                const ok = await KaiConfirm(`¿Seguro que querés eliminar el banner "${row.dataset.titulo || 'sin título'}"?`);
                if (!ok) return;
                fetch(urlsBannerKinetic.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBannerKinetic() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formBannerKinetic.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('bannerKineticMsg');
            const pk = document.getElementById('bannerKineticPk').value || null;
            fetch(urlsBannerKinetic.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfBannerKinetic() },
                body: JSON.stringify({
                    pk: pk,
                    titulo: document.getElementById('bannerKineticTitulo').value,
                    texto: document.getElementById('bannerKineticTexto').value,
                    color_fondo: document.getElementById('bannerKineticColorFondo').value,
                    cta_texto: document.getElementById('bannerKineticCtaTexto').value,
                    cta_url: document.getElementById('bannerKineticCtaUrl').value,
                }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                if (!bannerKineticImagenFile) {
                    recargarPreservandoTab();
                    return;
                }
                const fd = new FormData();
                fd.append('pk', data.pk);
                fd.append('imagen', bannerKineticImagenFile);
                fetch(urlsBannerKinetic.imagen, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfBannerKinetic() },
                    body: fd,
                })
                .then(r => r.json())
                .then(function (dataImg) {
                    if (dataImg.error) {
                        msg.style.color = '#e11d48';
                        msg.textContent = dataImg.error;
                        return;
                    }
                    recargarPreservandoTab();
                });
            });
        });
    }

    // ── Marcas — logos (opcional, hasta 20, plantilla "Bento") ──
    const formMarca = document.getElementById('formMarca');
    if (formMarca) {
        const csrfMarca = () => formMarca.querySelector('[name=csrfmiddlewaretoken]').value;
        const urlsMarca = window.CONFIG_MARCAS_URLS || {};
        const modalMarcaEl = document.getElementById('marcaModal');
        const modalMarca = window.bootstrap ? new bootstrap.Modal(modalMarcaEl) : null;
        let marcaLogoFile = null;

        function limpiarFormMarca() {
            document.getElementById('marcaPk').value = '';
            document.getElementById('marcaNombre').value = '';
            document.getElementById('marcaLogoPreviewBox').innerHTML =
                '<span style="font-size:0.6rem; color:var(--text-muted);">Sin logo</span>';
            document.getElementById('marcaMsg').textContent = '';
            marcaLogoFile = null;
        }

        document.getElementById('btnNuevaMarca')?.addEventListener('click', function () {
            limpiarFormMarca();
            document.getElementById('marcaModalLabel').textContent = 'Nueva marca';
        });

        document.querySelectorAll('.btn-editar-marca').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = btn.closest('.marca-row');
                limpiarFormMarca();
                document.getElementById('marcaModalLabel').textContent = 'Editar marca';
                document.getElementById('marcaPk').value = row.dataset.pk;
                document.getElementById('marcaNombre').value = row.dataset.nombre;
                const imgActual = row.querySelector('.config-logo-box img');
                if (imgActual) {
                    document.getElementById('marcaLogoPreviewBox').innerHTML = `<img src="${imgActual.src}" alt="">`;
                }
                if (modalMarca) modalMarca.show();
            });
        });

        document.getElementById('inputMarcaLogo').addEventListener('change', function () {
            if (!this.files[0]) return;
            marcaLogoFile = this.files[0];
            document.getElementById('marcaLogoPreviewBox').innerHTML =
                `<img src="${URL.createObjectURL(marcaLogoFile)}" alt="">`;
        });

        document.querySelectorAll('.btn-eliminar-marca').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const row = btn.closest('.marca-row');
                const ok = await KaiConfirm(`¿Seguro que querés eliminar "${row.dataset.nombre}"?`);
                if (!ok) return;
                fetch(urlsMarca.eliminar, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfMarca() },
                    body: JSON.stringify({ pk: row.dataset.pk }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { KaiToast.show(data.error, 'danger'); return; }
                    recargarPreservandoTab();
                });
            });
        });

        formMarca.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = document.getElementById('marcaMsg');
            const pk = document.getElementById('marcaPk').value || null;
            fetch(urlsMarca.guardar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfMarca() },
                body: JSON.stringify({ pk: pk, nombre: document.getElementById('marcaNombre').value }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    msg.style.color = '#e11d48';
                    msg.textContent = data.error;
                    return;
                }
                if (!marcaLogoFile) {
                    recargarPreservandoTab();
                    return;
                }
                const fd = new FormData();
                fd.append('pk', data.pk);
                fd.append('imagen', marcaLogoFile);
                fetch(urlsMarca.imagen, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfMarca() },
                    body: fd,
                })
                .then(r => r.json())
                .then(function (dataImg) {
                    if (dataImg.error) {
                        msg.style.color = '#e11d48';
                        msg.textContent = dataImg.error;
                        return;
                    }
                    recargarPreservandoTab();
                });
            });
        });
    }
});
