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

    // ── Escalado de iframes de vista previa (mismo truco "device preview" para
    //    el preview grande y las mini-cards de plantilla — una sola implementación) ──
    // opts.alturaFija: si viene, la card se recorta a esa altura sin medir el
    // contenido real (mini-cards, no necesitan estar sincronizadas en vivo).
    // Si no viene, mide scrollHeight real + ResizeObserver (preview grande).
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
            wrap.style.height = Math.round(alturaReal * factor) + 'px';
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

    function aplicarValoresAlPreview() {
        const doc = previewFrame && previewFrame.contentDocument;
        if (!doc) return;
        const titulo = doc.getElementById('kcHeroTitulo');
        if (titulo) titulo.textContent = document.getElementById('idCatalogoHeroTitulo').value || defaults.heroTitulo || '';
        const subtitulo = doc.getElementById('kcHeroSubtitulo');
        if (subtitulo) subtitulo.textContent = document.getElementById('idCatalogoHeroSubtitulo').value || defaults.heroSubtitulo || '';
        const sobreNosotros = doc.getElementById('kcFooterSobreNosotros');
        if (sobreNosotros) sobreNosotros.textContent = document.getElementById('idCatalogoSobreNosotros').value || defaults.sobreNosotros || '';
        const contacto = doc.getElementById('kcFooterContacto');
        if (contacto) contacto.textContent = document.getElementById('idCatalogoContactoTexto').value || '';
        if (heroObjectUrl) {
            const visual = doc.getElementById('kcHeroVisual');
            if (visual) visual.innerHTML = `<img src="${heroObjectUrl}" alt="">`;
        }
    }

    const recalcularPreviewGrande = crearPreviewEscalado(previewFrame, previewWrap, { onLoad: aplicarValoresAlPreview });

    let previewResizeTimeout;
    window.addEventListener('resize', function () {
        clearTimeout(previewResizeTimeout);
        previewResizeTimeout = setTimeout(recalcularPreviewGrande, 150);
    });

    ['idCatalogoHeroTitulo', 'idCatalogoHeroSubtitulo', 'idCatalogoSobreNosotros', 'idCatalogoContactoTexto'].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', aplicarValoresAlPreview);
    });

    // ── Mini-previews de las tarjetas de plantilla ──
    document.querySelectorAll('.co-card-plantilla').forEach(function (card) {
        const frame = card.querySelector('.co-card-preview-frame');
        const wrap = card.querySelector('.co-card-preview-wrap');
        if (frame && wrap) crearPreviewEscalado(frame, wrap, { alturaFija: 130 });
    });

    // ── Toggle de campos por plantilla — corre al cargar y al elegir una card ──
    const inputPlantilla = document.getElementById('idCatalogoPlantilla');
    function aplicarToggleDataPlantilla() {
        if (!inputPlantilla) return;
        document.querySelectorAll('[data-plantilla]').forEach(function (bloque) {
            bloque.style.display = (bloque.dataset.plantilla === inputPlantilla.value) ? '' : 'none';
        });
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
                plantilla:       document.getElementById('idCatalogoPlantilla').value,
                hero_titulo:     document.getElementById('idCatalogoHeroTitulo').value,
                hero_subtitulo:  document.getElementById('idCatalogoHeroSubtitulo').value,
                sobre_nosotros:  document.getElementById('idCatalogoSobreNosotros').value,
                contacto_texto:  document.getElementById('idCatalogoContactoTexto').value,
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
