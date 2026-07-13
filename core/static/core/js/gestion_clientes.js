document.addEventListener('DOMContentLoaded', function () {

    // ══ HELPERS ══
    function getCookie(name) {
        let v = null;
        document.cookie.split(';').forEach(c => { const [k, val] = c.trim().split('='); if (k === name) v = decodeURIComponent(val); });
        return v;
    }
    async function postForm(url, fd) {
        return fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') }, body: fd });
    }

    // ══ TIPO SELECTOR ══
    const radios = document.querySelectorAll('input[name="tipo"]');
    function aplicarTipo(tipo) {
        document.querySelectorAll('.seccion-persona').forEach(el => el.style.display = tipo === 'persona' ? '' : 'none');
        document.querySelectorAll('.seccion-empresa').forEach(el => el.style.display = tipo === 'empresa' ? '' : 'none');
        document.getElementById('clienteModalSubtitle').textContent = tipo === 'empresa' ? 'Datos de empresa' : 'Datos de persona física';
    }
    radios.forEach(r => r.addEventListener('change', () => aplicarTipo(r.value)));

    // ══ MAPA LEAFLET ══
    let mapaForm = null, markerForm = null;

    function iniciarMapa(lat, lng) {
        if (mapaForm) { mapaForm.setView([lat, lng], 15); markerForm.setLatLng([lat, lng]); return; }
        mapaForm = L.map('mapaFormulario').setView([lat, lng], 15);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap', maxZoom: 19 }).addTo(mapaForm);
        markerForm = L.marker([lat, lng], { draggable: true }).addTo(mapaForm);
        markerForm.on('dragend', e => guardarCoords(e.target.getLatLng().lat, e.target.getLatLng().lng));
        mapaForm.on('click', e => { markerForm.setLatLng(e.latlng); guardarCoords(e.latlng.lat, e.latlng.lng); });
    }

    function guardarCoords(lat, lng) {
        document.getElementById('id_latitud').value = lat.toFixed(7);
        document.getElementById('id_longitud').value = lng.toFixed(7);
        const osm = `https://www.openstreetmap.org/?mlat=${lat.toFixed(7)}&mlon=${lng.toFixed(7)}&zoom=17`;
        document.getElementById('id_maps_url').value = osm;
        const d = document.getElementById('coordsDisplay');
        document.getElementById('coordsText').textContent = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
        document.getElementById('btnVerEnMapa').href = osm;
        d.style.display = '';
    }

    document.querySelectorAll('[data-bs-target="#tabDir"]').forEach(btn => {
        btn.addEventListener('shown.bs.tab', () => {
            const lat = parseFloat(document.getElementById('id_latitud').value);
            const lng = parseFloat(document.getElementById('id_longitud').value);
            setTimeout(() => { iniciarMapa(isNaN(lat) ? -34.6037 : lat, isNaN(lng) ? -58.3816 : lng); mapaForm?.invalidateSize(); }, 150);
        });
    });

    // Buscador nominatim
    const searchInput = document.getElementById('mapaSearchInput');
    const suggestions = document.getElementById('mapaSearchSuggestions');
    let searchTimer = null;
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimer);
            const q = searchInput.value.trim();
            if (q.length < 3) { suggestions.style.display = 'none'; return; }
            searchTimer = setTimeout(async () => {
                const res = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&addressdetails=1&limit=6&countrycodes=ar`, { headers: { 'Accept-Language': 'es' } });
                const data = await res.json();
                suggestions.innerHTML = '';
                if (!data.length) { suggestions.innerHTML = '<div class="mapa-suggestion-item">Sin resultados</div>'; suggestions.style.display = ''; return; }
                data.forEach(r => {
                    const item = document.createElement('div');
                    item.className = 'mapa-suggestion-item';
                    item.textContent = r.display_name.substring(0, 70);
                    item.addEventListener('click', () => {
                        const lat = parseFloat(r.lat), lng = parseFloat(r.lon);
                        iniciarMapa(lat, lng); guardarCoords(lat, lng);
                        const a = r.address || {};
                        const set = (id, v) => { const el = document.getElementById(id); if (el && v) el.value = v; };
                        set('id_calle', a.road); set('id_numero', a.house_number); set('id_barrio', a.suburb || a.neighbourhood);
                        set('id_localidad', a.city || a.town || a.village); set('id_partido', a.county);
                        set('id_provincia', a.state); set('id_pais', a.country || 'Argentina'); set('id_codigo_postal', a.postcode);
                        searchInput.value = r.display_name.substring(0, 50);
                        suggestions.style.display = 'none';
                    });
                    suggestions.appendChild(item);
                });
                suggestions.style.display = '';
            }, 400);
        });
        document.addEventListener('click', e => { if (!e.target.closest('.mapa-search-wrapper')) suggestions.style.display = 'none'; });
    }

    // ══ TELÉFONOS EN FORMULARIO ══
    const telContainer = document.getElementById('telefonosContainer');
    const telTemplate  = document.getElementById('telTemplate');
    const btnAddTel    = document.getElementById('btnAgregarTel');

    function agregarFilaTelefono(datos = {}) {
        if (!telTemplate || !telContainer) return;
        const clone = telTemplate.content.cloneNode(true);
        const row   = clone.querySelector('.tel-row');
        if (datos.numero)  row.querySelector('[name="tel_numero[]"]').value  = datos.numero;
        if (datos.tipo)    row.querySelector('[name="tel_tipo[]"]').value     = datos.tipo;
        if (datos.descripcion) row.querySelector('[name="tel_desc[]"]').value = datos.descripcion;
        if (datos.es_titular)  row.querySelector('[name="tel_titular[]"]').checked  = true;
        if (datos.tiene_whatsapp) row.querySelector('[name="tel_whatsapp[]"]').checked = true;
        row.querySelector('.btn-del-tel').addEventListener('click', () => row.remove());
        telContainer.appendChild(clone);
    }

    if (btnAddTel) btnAddTel.addEventListener('click', () => agregarFilaTelefono());

    // ══ GRUPO FAMILIAR ══
    const grupoInput   = document.getElementById('grupoSearchInput');
    const grupoSugg    = document.getElementById('grupoSuggestions');
    const grupoHidden  = document.getElementById('id_grupo_familiar');
    const grupoSel     = document.getElementById('grupoSeleccionado');
    const grupoNomEl   = document.getElementById('grupoNombre');
    const btnQuitarGrupo = document.getElementById('btnQuitarGrupo');
    let   grupoTimer   = null;

    if (grupoInput) {
        grupoInput.addEventListener('input', () => {
            clearTimeout(grupoTimer);
            const q = grupoInput.value.trim();
            if (q.length < 1) { grupoSugg.style.display = 'none'; return; }
            grupoTimer = setTimeout(async () => {
                const res = await fetch(`${window.grupoFamiliarUrl}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                grupoSugg.innerHTML = '';
                data.grupos.forEach(g => {
                    const item = document.createElement('div');
                    item.className = 'mapa-suggestion-item';
                    item.textContent = g.label;
                    item.addEventListener('click', () => seleccionarGrupo(g));
                    grupoSugg.appendChild(item);
                });
                if (!data.grupos.length) grupoSugg.innerHTML = '<div class="mapa-suggestion-item">Sin resultados</div>';
                grupoSugg.style.display = '';
            }, 300);
        });
        document.addEventListener('click', e => { if (!e.target.closest('.grupo-search-wrapper')) grupoSugg.style.display = 'none'; });
    }

    function seleccionarGrupo(g) {
        if (!grupoHidden) return;
        grupoHidden.value = g.id;
        grupoNomEl.textContent = g.label;
        grupoSel.style.display = '';
        if (grupoInput) grupoInput.value = '';
        grupoSugg.style.display = 'none';
    }
    if (btnQuitarGrupo) btnQuitarGrupo.addEventListener('click', () => { grupoHidden.value = ''; grupoSel.style.display = 'none'; });

    // Crear nuevo grupo
    const btnToggleGrupo = document.getElementById('btnToggleNuevoGrupo');
    const nuevoGrupoForm = document.getElementById('nuevoGrupoForm');
    const btnCrearGrupo  = document.getElementById('btnCrearGrupo');
    if (btnToggleGrupo) btnToggleGrupo.addEventListener('click', () => { nuevoGrupoForm.style.display = nuevoGrupoForm.style.display === 'none' ? '' : 'none'; });
    if (btnCrearGrupo) {
        btnCrearGrupo.addEventListener('click', async () => {
            const apellido  = document.getElementById('ng_apellido').value.trim();
            const direccion = document.getElementById('ng_direccion').value.trim();
            if (!apellido) { KaiToast.show('Ingresá el apellido de referencia.', 'warning'); return; }
            const fd = new FormData();
            fd.append('apellido_referencia', apellido);
            fd.append('direccion_referencia', direccion);
            const resp = await postForm(window.grupoFamiliarUrl, fd);
            const data = await resp.json();
            if (data.success) {
                seleccionarGrupo(data.grupo);
                nuevoGrupoForm.style.display = 'none';
                document.getElementById('ng_apellido').value = '';
                document.getElementById('ng_direccion').value = '';
            } else KaiToast.show('Error al crear grupo: ' + JSON.stringify(data.errors), 'danger');
        });
    }

    // ══ REFERIDO POR ══
    const refInput  = document.getElementById('referidoSearchInput');
    const refSugg   = document.getElementById('referidoSuggestions');
    const refHidden = document.getElementById('id_referido_por');
    const refSel    = document.getElementById('referidoSeleccionado');
    const refNomEl  = document.getElementById('referidoNombre');
    let   refTimer  = null;

    if (refInput) {
        refInput.addEventListener('input', () => {
            clearTimeout(refTimer);
            const q = refInput.value.trim();
            if (q.length < 2) { refSugg.style.display = 'none'; return; }
            refTimer = setTimeout(async () => {
                const res = await fetch(`${window.clienteBuscarUrl}?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                refSugg.innerHTML = '';
                data.clientes.forEach(c => {
                    const item = document.createElement('div');
                    item.className = 'mapa-suggestion-item';
                    item.textContent = c.label;
                    item.addEventListener('click', () => {
                        refHidden.value = c.id;
                        refNomEl.textContent = c.label;
                        refSel.style.display = '';
                        refInput.value = '';
                        refSugg.style.display = 'none';
                    });
                    refSugg.appendChild(item);
                });
                if (!data.clientes.length) refSugg.innerHTML = '<div class="mapa-suggestion-item">Sin resultados</div>';
                refSugg.style.display = '';
            }, 300);
        });
        document.addEventListener('click', e => { if (!e.target.closest('[id="referidoSearchInput"]') && !e.target.closest('#referidoSuggestions')) refSugg.style.display = 'none'; });
        const btnQuitarRef = document.getElementById('btnQuitarReferido');
        if (btnQuitarRef) btnQuitarRef.addEventListener('click', () => { refHidden.value = ''; refSel.style.display = 'none'; });
    }

    // ══ IMÁGENES EN FORMULARIO ══
    let imagenesSeleccionadas = [];   // archivos nuevos pendientes de subir
    let imagenesAEliminar    = [];   // IDs de imágenes existentes marcadas para borrar

    const imgFilesInput  = document.getElementById('imgFilesInput');
    const imgUploadZone  = document.getElementById('imgUploadZone');
    const imgPreviewCont = document.getElementById('imgPreviewContainer');
    const imgPlaceholder = document.getElementById('imgUploadPlaceholder');
    const btnSelArch     = document.getElementById('btnSeleccionarArchivos');

    // Contenedor de imágenes existentes (se crea dinámicamente en el tab)
    let imgExistentesWrap = null;

    function obtenerOCrearExistentesWrap() {
        if (imgExistentesWrap) return imgExistentesWrap;
        const tabImagenes = document.getElementById('tabImagenes');
        if (!tabImagenes) return null;
        // Insertar antes del upload zone
        imgExistentesWrap = document.createElement('div');
        imgExistentesWrap.id = 'imgExistentesWrap';
        imgExistentesWrap.innerHTML = '<p class="form-section-title" style="margin-bottom:0.5rem;">Imágenes actuales</p><div id="imgExistentesGrid" class="img-existentes-grid"></div>';
        tabImagenes.insertBefore(imgExistentesWrap, tabImagenes.firstChild);
        return imgExistentesWrap;
    }

    function limpiarExistentes() {
        imagenesAEliminar = [];
        if (imgExistentesWrap) { imgExistentesWrap.remove(); imgExistentesWrap = null; }
    }

    function renderizarImagenesExistentes(imagenes) {
        limpiarExistentes();
        if (!imagenes || !imagenes.length) return;

        obtenerOCrearExistentesWrap();
        const grid = document.getElementById('imgExistentesGrid');
        if (!grid) return;

        imagenes.forEach(img => {
            const item = document.createElement('div');
            item.className = 'img-existente-item';
            item.dataset.id = img.id;
            item.innerHTML = `
                <img src="${img.url}" alt="${img.tipo || ''}">
                <div class="img-existente-overlay">
                    <span class="img-existente-tipo">${img.tipo || ''}</span>
                </div>
                <button type="button" class="img-existente-del" title="Eliminar esta imagen" data-id="${img.id}">×</button>
            `;
            item.querySelector('.img-existente-del').addEventListener('click', () => {
                imagenesAEliminar.push(img.id);
                item.classList.add('img-marcada-borrar');
                item.querySelector('.img-existente-del').disabled = true;
                item.querySelector('.img-existente-del').textContent = '✓';
                item.style.opacity = '0.4';
            });
            grid.appendChild(item);
        });
    }

    if (btnSelArch) btnSelArch.addEventListener('click', () => imgFilesInput?.click());
    if (imgFilesInput) imgFilesInput.addEventListener('change', e => agregarArchivos(e.target.files));
    if (imgUploadZone) {
        imgUploadZone.addEventListener('dragover', e => { e.preventDefault(); imgUploadZone.classList.add('dragover'); });
        imgUploadZone.addEventListener('dragleave', () => imgUploadZone.classList.remove('dragover'));
        imgUploadZone.addEventListener('drop', e => { e.preventDefault(); imgUploadZone.classList.remove('dragover'); agregarArchivos(e.dataTransfer.files); });
    }

    function agregarArchivos(files) {
        Array.from(files).forEach(f => {
            if (!f.type.startsWith('image/')) return;
            const idx = imagenesSeleccionadas.length;
            imagenesSeleccionadas.push(f);
            const reader = new FileReader();
            reader.onload = e => {
                if (!imgPreviewCont) return;
                const item = document.createElement('div'); item.className = 'img-preview-item'; item.dataset.index = idx;
                item.innerHTML = `<img src="${e.target.result}"><button type="button" class="img-preview-remove" data-index="${idx}">✕</button><span class="img-preview-name">${f.name}</span>`;
                item.querySelector('.img-preview-remove').addEventListener('click', ev => { imagenesSeleccionadas[parseInt(ev.currentTarget.dataset.index)] = null; item.remove(); actualizarPlaceholder(); });
                imgPreviewCont.appendChild(item);
                actualizarPlaceholder();
            };
            reader.readAsDataURL(f);
        });
    }

    function actualizarPlaceholder() { if (imgPlaceholder) imgPlaceholder.style.display = imagenesSeleccionadas.filter(f=>f).length > 0 ? 'none' : ''; }

    function limpiarImagenes() {
        imagenesSeleccionadas = [];
        if (imgPreviewCont) imgPreviewCont.innerHTML = '';
        actualizarPlaceholder();
        if (imgFilesInput) imgFilesInput.value = '';
        limpiarExistentes();
    }

    async function subirImagenesPendientes(clientePk) {
        const archivos = imagenesSeleccionadas.filter(f => f);
        const url = `/clientes/${clientePk}/imagenes/`;

        // Primero eliminar las marcadas
        for (const imgId of imagenesAEliminar) {
            await fetch(url, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ imagen_id: imgId })
            }).catch(() => {});
        }

        // Luego subir las nuevas
        for (const archivo of archivos) {
            const fd = new FormData();
            fd.append('imagen', archivo); fd.append('tipo', 'otro'); fd.append('descripcion', '');
            await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') }, body: fd }).catch(() => {});
        }
    }

    // ══ MODALES ══
    const modalEl    = document.getElementById('clienteModal');
    const eliminarEl = document.getElementById('eliminarModal');
    const modal      = modalEl    ? new bootstrap.Modal(modalEl)    : null;
    const elimModal  = eliminarEl ? new bootstrap.Modal(eliminarEl) : null;
    const form       = document.getElementById('formCliente');
    const btnNuevo   = document.getElementById('btnNuevoCliente');
    const btnGuardar = document.getElementById('btnGuardarCliente');
    const formError  = document.getElementById('formError');
    let   pkEliminar = null;

    if (modalEl) modalEl.addEventListener('hidden.bs.modal', () => { if (mapaForm) { mapaForm.remove(); mapaForm = null; markerForm = null; } });

    function resetForm() {
        if (!form) return;
        form.reset();
        document.getElementById('clientePk').value = '';
        document.getElementById('clienteModalLabel').textContent = 'Nuevo cliente';
        aplicarTipo('persona');
        document.querySelector('input[name="tipo"][value="persona"]').checked = true;
        if (formError) formError.style.display = 'none';
        const cD = document.getElementById('coordsDisplay'); if (cD) cD.style.display = 'none';
        if (telContainer) telContainer.innerHTML = '';
        limpiarImagenes();
        if (grupoHidden) grupoHidden.value = '';
        if (grupoSel) grupoSel.style.display = 'none';
        if (refHidden) refHidden.value = '';
        if (refSel) refSel.style.display = 'none';
        const editNota = document.getElementById('imgEditNota'); if (editNota) editNota.style.display = 'none';
        document.querySelector('#formTabs .nav-link')?.click();
    }

    function poblarFormulario(c) {
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
        document.getElementById('clientePk').value = c.id;
        const r = document.querySelector(`input[name="tipo"][value="${c.tipo}"]`);
        if (r) { r.checked = true; aplicarTipo(c.tipo); }
        set('id_estado', c.estado); set('id_nivel_riesgo', c.nivel_riesgo); set('id_canal_preferido', c.canal_preferido);
        set('id_nombre', c.nombre); set('id_apellido', c.apellido); set('id_ocupacion', c.ocupacion);
        set('id_dni', c.dni); set('id_cuil', c.cuil); set('id_fecha_nacimiento', c.fecha_nacimiento); set('id_genero', c.genero);
        set('id_razon_social', c.razon_social); set('id_nombre_comercial', c.nombre_comercial);
        set('id_cuit', c.cuit); set('id_cond_iva', c.cond_iva); set('id_rubro', c.rubro);
        set('id_sitio_web', c.sitio_web); set('id_fecha_fundacion', c.fecha_fundacion);
        set('id_email_principal', c.email_principal); set('id_email_secundario', c.email_secundario);
        set('id_instagram', c.instagram); set('id_facebook', c.facebook); set('id_linkedin', c.linkedin);
        set('id_calle', c.calle); set('id_numero', c.numero); set('id_piso_depto', c.piso_depto);
        set('id_barrio', c.barrio); set('id_localidad', c.localidad); set('id_partido', c.partido);
        set('id_provincia', c.provincia); set('id_pais', c.pais); set('id_codigo_postal', c.codigo_postal);
        set('id_latitud', c.latitud); set('id_longitud', c.longitud); set('id_maps_url', c.maps_url);
        set('id_notas', c.notas); set('id_como_nos_conocio', c.como_nos_conocio); set('id_tags', c.tags);
        set('id_fecha_desde_cliente', c.fecha_desde_cliente);
        set('id_fecha_ultimo_contacto', c.fecha_ultimo_contacto);
        set('id_fecha_proximo_contacto', c.fecha_proximo_contacto);

        // Teléfonos
        if (telContainer) { telContainer.innerHTML = ''; (c.telefonos || []).forEach(t => agregarFilaTelefono(t)); }

        // Grupo familiar
        if (c.grupo_familiar_id && grupoHidden) {
            grupoHidden.value = c.grupo_familiar_id;
            if (grupoNomEl) grupoNomEl.textContent = c.grupo_familiar_nombre;
            if (grupoSel) grupoSel.style.display = '';
        }
        set('id_unidad_habitacional', c.unidad_habitacional);

        // Referido
        if (c.referido_por_id && refHidden) {
            refHidden.value = c.referido_por_id;
            if (refNomEl) refNomEl.textContent = c.referido_por_nombre;
            if (refSel) refSel.style.display = '';
        }

        // Coords display
        if (c.latitud && c.longitud) {
            const d = document.getElementById('coordsDisplay');
            if (d) {
                document.getElementById('coordsText').textContent = `${c.latitud}, ${c.longitud}`;
                document.getElementById('btnVerEnMapa').href = `https://www.openstreetmap.org/?mlat=${c.latitud}&mlon=${c.longitud}&zoom=17`;
                d.style.display = '';
            }
        }

        // ── Imágenes existentes ──────────────────────────────────
        limpiarImagenes();

        // Mostrar nota de edición
        const editNota = document.getElementById('imgEditNota');
        if (editNota) {
            editNota.style.display = '';
            const link = document.getElementById('linkDetalleCliente');
            if (link) link.href = `/clientes/${c.id}/`;
        }

        // Cargar imágenes actuales del cliente vía API
        const imgUrl = `/clientes/${c.id}/imagenes/`;
        fetch(imgUrl)
            .then(r => r.json())
            .then(data => {
                const imagenes = data.imagenes || data.results || data || [];
                if (Array.isArray(imagenes) && imagenes.length) {
                    renderizarImagenesExistentes(imagenes);
                }
            })
            .catch(() => {}); // silencioso si el endpoint no existe aún
    }

    if (btnNuevo) btnNuevo.addEventListener('click', () => { resetForm(); modal?.show(); });

    document.querySelectorAll('.btn-editar').forEach(btn => {
        btn.addEventListener('click', () => {
            fetch(`${window.clienteAccionesUrl}?get_pk=${btn.dataset.id}`).then(r=>r.json()).then(data => {
                if (!data.cliente) return;
                resetForm();
                poblarFormulario(data.cliente);
                document.getElementById('clienteModalLabel').textContent = 'Editar cliente';
                modal?.show();
            });
        });
    });

    if (btnGuardar) {
        btnGuardar.addEventListener('click', async () => {
            if (!form) return;
            const fd = new FormData(form);
            // Teléfonos: recolectar de las filas
            const telFilas = telContainer?.querySelectorAll('.tel-row') || [];
            fd.delete('tel_numero[]'); fd.delete('tel_tipo[]'); fd.delete('tel_desc[]'); fd.delete('tel_titular[]'); fd.delete('tel_whatsapp[]');
            telFilas.forEach(fila => {
                fd.append('tel_numero[]',   fila.querySelector('[name="tel_numero[]"]').value);
                fd.append('tel_tipo[]',     fila.querySelector('[name="tel_tipo[]"]').value);
                fd.append('tel_desc[]',     fila.querySelector('[name="tel_desc[]"]').value);
                fd.append('tel_titular[]',  fila.querySelector('[name="tel_titular[]"]').checked ? '1' : '0');
                fd.append('tel_whatsapp[]', fila.querySelector('[name="tel_whatsapp[]"]').checked ? '1' : '0');
            });
            if (formError) formError.style.display = 'none';
            btnGuardar.disabled = true; btnGuardar.textContent = 'Guardando...';
            try {
                const resp = await postForm(window.clienteAccionesUrl, fd);
                const data = await resp.json();
                if (data.success) {
                    await subirImagenesPendientes(data.cliente.id);
                    modal?.hide(); location.reload();
                } else {
                    const err = Object.entries(data.errors||{}).map(([k,v])=>`${k}: ${v.join(', ')}`).join(' | ');
                    if (formError) { formError.textContent = err || 'Error al guardar.'; formError.style.display = 'block'; }
                }
            } catch (e) { if (formError) { formError.textContent = 'Error de conexión.'; formError.style.display = 'block'; } }
            finally { btnGuardar.disabled = false; btnGuardar.textContent = 'Guardar cliente'; }
        });
    }

    // ══ ELIMINAR ══
    document.querySelectorAll('.btn-eliminar').forEach(btn => {
        btn.addEventListener('click', () => {
            pkEliminar = btn.dataset.id;
            document.getElementById('nombreEliminar').textContent = btn.dataset.nombre;
            elimModal?.show();
        });
    });
    const confirmarElim = document.getElementById('confirmarEliminarBtn');
    if (confirmarElim) confirmarElim.addEventListener('click', async () => {
        if (!pkEliminar) return;
        const fd = new FormData(); fd.append('pk', pkEliminar);
        const resp = await postForm(window.clienteEliminarUrl, fd);
        const data = await resp.json();
        if (data.success) location.reload(); else KaiToast.show('Error al eliminar.', 'danger');
    });
});