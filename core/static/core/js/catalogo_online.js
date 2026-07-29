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
        const color = document.getElementById('idCatalogoColorMarca').value || defaults.colorMarca || '#ff9343';
        const colorSecundario = document.getElementById('idCatalogoColorMarcaSecundario')?.value || defaults.colorMarcaSecundario || '#111e2f';
        if (doc.documentElement) {
            doc.documentElement.style.setProperty('--primary', color);
            doc.documentElement.style.setProperty('--primary-dark', `color-mix(in srgb, ${color} 80%, black)`);
            doc.documentElement.style.setProperty('--primary-soft', `color-mix(in srgb, ${color} 12%, white)`);
            doc.documentElement.style.setProperty('--navy', colorSecundario);
            doc.documentElement.style.setProperty('--navy-2', `color-mix(in srgb, ${colorSecundario} 82%, black)`);
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
        'idCatalogoColorMarca', 'idCatalogoColorMarcaSecundario', 'idCatalogoNavCatalogo', 'idCatalogoNavOfertas', 'idCatalogoNavCombos', 'idCatalogoNavTienda',
        'idCatalogoInstTitulo', 'idCatalogoInstBajada',
        'idCatalogoDestacado1Titulo', 'idCatalogoDestacado1Texto',
        'idCatalogoDestacado2Titulo', 'idCatalogoDestacado2Texto',
        'idCatalogoDestacado3Titulo', 'idCatalogoDestacado3Texto',
    ].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', aplicarValoresAlPreview);
    });

    document.getElementById('btnResetColorMarca')?.addEventListener('click', function () {
        document.getElementById('idCatalogoColorMarca').value = defaults.colorMarca || '#ff9343';
        aplicarValoresAlPreview();
    });

    document.getElementById('btnResetColorMarcaSecundario')?.addEventListener('click', function () {
        document.getElementById('idCatalogoColorMarcaSecundario').value = defaults.colorMarcaSecundario || '#111e2f';
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
    let tabActiva = 'plantillas';
    // Qué página muestra el preview grande ahora mismo — "La tienda" y
    // "Contacto" vive en /la-tienda/, el resto en la home del catálogo.
    let previewPagina = 'home';

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
                previewFrame.src = paginaDestino === 'institucional'
                    ? catalogoInstitucionalUrl
                    : catalogoHomeUrl + '?preview_plantilla=' + encodeURIComponent(inputPlantilla.value);
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
    }
    aplicarToggleDataPlantilla();

    // ── Elegir plantilla desde las tarjetas ──
    document.querySelectorAll('.co-card-plantilla').forEach(function (card) {
        card.addEventListener('click', function () {
            const valor = card.dataset.plantillaValor;
            if (!inputPlantilla || inputPlantilla.value === valor) return;
            inputPlantilla.value = valor;

            document.querySelectorAll('.co-card-plantilla').forEach(function (c) {
                c.classList.toggle('co-card-plantilla--activa', c === card);
            });
            aplicarToggleDataPlantilla();

            // El preview grande cambia al instante (sin guardar) gracias a
            // ?preview_plantilla= en CatalogoHomeView.get_template_names().
            if (previewFrame) {
                previewFrame.src = catalogoHomeUrl + '?preview_plantilla=' + encodeURIComponent(valor);
            }
        });
    });

    formCatalogo.addEventListener('submit', function (e) {
        e.preventDefault();
        const msg = document.getElementById('catalogoMsg');
        fetch(urls.guardar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
                plantilla:          document.getElementById('idCatalogoPlantilla').value,
                hero_titulo:        document.getElementById('idCatalogoHeroTitulo').value,
                hero_subtitulo:     document.getElementById('idCatalogoHeroSubtitulo').value,
                hero_producto:      document.getElementById('idCatalogoHeroProducto')?.value || '',
                sobre_nosotros:     document.getElementById('idCatalogoSobreNosotros').value,
                contacto_texto:     document.getElementById('idCatalogoContactoTexto').value,
                color_marca:        document.getElementById('idCatalogoColorMarca').value,
                color_marca_secundario: document.getElementById('idCatalogoColorMarcaSecundario').value,
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
        })
        .then(r => r.json())
        .then(data => {
            msg.style.color = data.error ? '#e11d48' : 'var(--success)';
            msg.textContent = data.error || 'Guardado.';
            // Recargar el iframe solo tiene sentido DESPUÉS de guardar (recién
            // ahí el servidor persiste hero_titulo/hero_subtitulo/textos nuevos
            // para esa plantilla) — el cambio de plantilla en sí ya se ve al
            // instante desde el click en la card, sin esperar este guardado.
            if (!data.error && previewFrame && previewFrame.contentWindow) {
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
            window.location.reload();
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
                window.location.reload();
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
                    window.location.reload();
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
                    window.location.reload();
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
                    window.location.reload();
                });
            });
        });
    }
});
