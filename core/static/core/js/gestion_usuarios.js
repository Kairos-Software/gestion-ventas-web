document.addEventListener('DOMContentLoaded', function () {

    const modalEl  = document.getElementById('usuarioModal');
    const modal    = modalEl ? new bootstrap.Modal(modalEl) : null;
    const confirmEl= document.getElementById('confirmarEliminarModal');
    const confirmModal = confirmEl ? new bootstrap.Modal(confirmEl) : null;
    const form     = document.getElementById('formUsuario');
    const tablaBody= document.querySelector('#tablaUsuarios tbody');
    const btnNuevo = document.getElementById('btnNuevoUsuario');
    const btnConfirmar = document.getElementById('confirmarEliminarBtn');

    let usuarioAEliminar = null;

    // ── Elementos dinámicos de sub‑recursos ──────────────────────
    const estudiosContainer = document.getElementById('estudiosContainer');
    const estudioTemplate = document.getElementById('estudioTemplate');
    const btnAgregarEstudio = document.getElementById('btnAgregarEstudio');

    const experienciasContainer = document.getElementById('experienciasContainer');
    const experienciaTemplate = document.getElementById('experienciaTemplate');
    const btnAgregarExperiencia = document.getElementById('btnAgregarExperiencia');

    const capacitacionesContainer = document.getElementById('capacitacionesContainer');
    const capacitacionTemplate = document.getElementById('capacitacionTemplate');
    const btnAgregarCapacitacion = document.getElementById('btnAgregarCapacitacion');

    const documentosContainer = document.getElementById('documentosContainer');
    const documentoTemplate = document.getElementById('documentoTemplate');
    const btnAgregarDocumento = document.getElementById('btnAgregarDocumento');

    const cuentasContainer = document.getElementById('cuentasContainer');
    const cuentaTemplate   = document.getElementById('cuentaTemplate');
    const btnAgregarCuenta = document.getElementById('btnAgregarCuenta');

    // ── Foto de perfil ───────────────────────────────────────────
    const fotoInput = document.getElementById('id_foto_perfil');
    const fotoPreviewContainer = document.getElementById('fotoPreviewContainer');
    const btnSeleccionarFoto = document.getElementById('btnSeleccionarFoto');
    const btnEliminarFoto = document.getElementById('btnEliminarFoto');
    const fotoEliminarHidden = document.getElementById('id_foto_perfil_eliminar');

    function mostrarPlaceholder(letra) {
        if (!fotoPreviewContainer) return;
        fotoPreviewContainer.innerHTML = `<div class="foto-placeholder">${letra}</div>`;
    }

    function mostrarPreview(url) {
        if (!fotoPreviewContainer) return;
        fotoPreviewContainer.innerHTML = `<img src="${url}" class="foto-preview-img" alt="Vista previa">`;
    }

    function actualizarEstadoFoto(tieneFoto, url = null, letra = '?') {
        if (tieneFoto && url) {
            mostrarPreview(url);
            if (btnEliminarFoto) btnEliminarFoto.style.display = 'inline-block';
            if (fotoEliminarHidden) fotoEliminarHidden.value = '0';
        } else {
            mostrarPlaceholder(letra);
            if (btnEliminarFoto) btnEliminarFoto.style.display = 'none';
            if (fotoEliminarHidden) fotoEliminarHidden.value = '1';
        }
    }

    function obtenerInicial() {
        const nombreInput = document.getElementById('id_first_name');
        const apellidoInput = document.getElementById('id_last_name');
        if (nombreInput && nombreInput.value) return nombreInput.value[0].toUpperCase();
        if (apellidoInput && apellidoInput.value) return apellidoInput.value[0].toUpperCase();
        const usernameInput = document.getElementById('id_username');
        if (usernameInput && usernameInput.value) return usernameInput.value[0].toUpperCase();
        return '?';
    }

    if (btnSeleccionarFoto) btnSeleccionarFoto.addEventListener('click', () => fotoInput.click());
    if (fotoInput) {
        fotoInput.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                const reader = new FileReader();
                reader.onload = e => { actualizarEstadoFoto(true, e.target.result, ''); if (fotoEliminarHidden) fotoEliminarHidden.value = '0'; };
                reader.readAsDataURL(this.files[0]);
            }
        });
    }
    if (btnEliminarFoto) {
        btnEliminarFoto.addEventListener('click', () => {
            fotoInput.value = '';
            actualizarEstadoFoto(false, null, obtenerInicial());
        });
    }

    // ── Funciones para sub‑recursos ───────────────────────────────
    function agregarFilaEstudio(datos = {}) {
        if (!estudiosContainer || !estudioTemplate) return;
        const clone = estudioTemplate.content.cloneNode(true);
        const row = clone.querySelector('.estudio-row');
        Object.keys(datos).forEach(key => {
            const input = row.querySelector(`[name="estudio_${key}[]"]`);
            if (input) input.value = datos[key];
        });
        row.querySelector('.btn-del-tel').addEventListener('click', () => row.remove());
        estudiosContainer.appendChild(clone);
    }

    function agregarFilaExperiencia(datos = {}) {
        if (!experienciasContainer || !experienciaTemplate) return;
        const clone = experienciaTemplate.content.cloneNode(true);
        const row = clone.querySelector('.exp-row');
        Object.keys(datos).forEach(key => {
            const input = row.querySelector(`[name="exp_${key}[]"]`);
            if (input) {
                if (key === 'trabajo_actual' && datos[key] === true) input.checked = true;
                else input.value = datos[key];
            }
        });
        row.querySelector('.btn-del-tel').addEventListener('click', () => row.remove());
        experienciasContainer.appendChild(clone);
    }

    function agregarFilaCapacitacion(datos = {}) {
        if (!capacitacionesContainer || !capacitacionTemplate) return;
        const clone = capacitacionTemplate.content.cloneNode(true);
        const row = clone.querySelector('.cap-row');
        Object.keys(datos).forEach(key => {
            const input = row.querySelector(`[name="cap_${key}[]"]`);
            if (input) {
                if (key === 'es_obligatoria' && datos[key] === true) input.checked = true;
                else if (key === 'certificado_emitido' && datos[key] === true) input.checked = true;
                else input.value = datos[key];
            }
        });
        row.querySelector('.btn-del-tel').addEventListener('click', () => row.remove());
        capacitacionesContainer.appendChild(clone);
    }

    /**
     * Agrega una fila de documento.
     * En modo edición (datos.pk existe), muestra el archivo actual como link descargable
     * en lugar del input file vacío, y agrega un campo oculto doc_pk[] para que el backend
     * sepa que ese documento ya existe y no lo trate como nuevo.
     */
    function agregarFilaDocumento(datos = {}) {
        if (!documentosContainer || !documentoTemplate) return;
        const clone = documentoTemplate.content.cloneNode(true);
        const row = clone.querySelector('.doc-row');

        // Poblar campos de texto/select
        const campos = ['tipo', 'nombre', 'fecha_doc', 'vencimiento', 'observaciones'];
        campos.forEach(key => {
            const input = row.querySelector(`[name="doc_${key}[]"]`);
            if (input && datos[key] !== undefined) input.value = datos[key] || '';
        });

        // Si el documento es existente (tiene pk), manejar el campo archivo
        if (datos.pk) {
            // Agregar campo oculto con el pk del documento existente
            const pkInput = document.createElement('input');
            pkInput.type = 'hidden';
            pkInput.name = 'doc_pk[]';
            pkInput.value = datos.pk;
            row.querySelector('.subrecurso-fields').appendChild(pkInput);

            // Reemplazar el input file por un indicador visual del archivo existente
            const fileInput = row.querySelector('[name="doc_archivo[]"]');
            if (fileInput && datos.archivo_url) {
                const wrap = fileInput.closest('.field-group') || fileInput.parentElement;
                wrap.innerHTML = `
                    <label class="field-label">Archivo actual</label>
                    <div class="doc-archivo-actual">
                        <a href="${datos.archivo_url}" target="_blank" class="doc-link-actual" title="Ver / descargar">
                            📄 ${datos.archivo_nombre || 'Ver archivo'}
                        </a>
                        <label class="doc-cambiar-label">
                            <input type="file" name="doc_archivo[]" class="doc-archivo-input" accept=".pdf,.jpg,.png,.jpeg" style="display:none;">
                            <span class="doc-cambiar-btn">Cambiar</span>
                        </label>
                    </div>
                `;
                // Mostrar el nombre del nuevo archivo cuando se seleccione
                const newFile = wrap.querySelector('[name="doc_archivo[]"]');
                const cambiarBtn = wrap.querySelector('.doc-cambiar-btn');
                if (newFile && cambiarBtn) {
                    newFile.addEventListener('change', () => {
                        if (newFile.files[0]) {
                            cambiarBtn.textContent = newFile.files[0].name;
                            cambiarBtn.style.color = 'var(--brand-orange)';
                        }
                    });
                }
            } else if (fileInput) {
                // Tiene pk pero no url — dejar el input file pero agregar nota
                const wrap = fileInput.closest('.field-group') || fileInput.parentElement;
                const nota = document.createElement('small');
                nota.style.cssText = 'display:block;font-size:0.65rem;color:var(--text-muted);margin-top:2px;';
                nota.textContent = 'Dejá vacío para mantener el archivo actual';
                wrap.appendChild(nota);
            }
        } else {
            // Documento nuevo: agregar campo oculto vacío para mantener alineación de arrays
            const pkInput = document.createElement('input');
            pkInput.type = 'hidden';
            pkInput.name = 'doc_pk[]';
            pkInput.value = '';
            row.querySelector('.subrecurso-fields').appendChild(pkInput);
        }

        row.querySelector('.btn-del-tel').addEventListener('click', () => row.remove());
        documentosContainer.appendChild(clone);
    }

    function agregarFilaCuenta(datos = {}) {
        if (!cuentasContainer || !cuentaTemplate) return;
        const clone = cuentaTemplate.content.cloneNode(true);
        const row   = clone.querySelector('.cuenta-row');
        const set   = (name, val) => {
            const el = row.querySelector(`[name="${name}"]`);
            if (!el || val === undefined || val === null) return;
            if (el.type === 'checkbox') el.checked = val === true || val === '1';
            else el.value = val;
        };
        set('cb_tipo[]',          datos.tipo);
        set('cb_nombre[]',        datos.nombre);
        set('cb_titular[]',       datos.titular);
        set('cb_cbu_cvu[]',       datos.cbu_cvu);
        set('cb_alias[]',         datos.alias);
        set('cb_nro_cuenta[]',    datos.nro_cuenta);
        set('cb_es_principal[]',  datos.es_principal);
        set('cb_observaciones[]', datos.observaciones);
        row.querySelector('.btn-del-tel').addEventListener('click', () => row.remove());
        cuentasContainer.appendChild(clone);
    }

    function limpiarSubRecursos() {
        if (estudiosContainer) estudiosContainer.innerHTML = '';
        if (experienciasContainer) experienciasContainer.innerHTML = '';
        if (capacitacionesContainer) capacitacionesContainer.innerHTML = '';
        if (documentosContainer) documentosContainer.innerHTML = '';
        if (cuentasContainer) cuentasContainer.innerHTML = '';
    }

    function poblarSubRecursos(datos) {
        limpiarSubRecursos();
        if (datos.estudios) datos.estudios.forEach(e => agregarFilaEstudio(e));
        if (datos.experiencias) datos.experiencias.forEach(e => agregarFilaExperiencia(e));
        if (datos.capacitaciones) datos.capacitaciones.forEach(c => agregarFilaCapacitacion(c));
        if (datos.documentos) datos.documentos.forEach(d => agregarFilaDocumento(d));
        if (datos.cuentas_bancarias) datos.cuentas_bancarias.forEach(cb => agregarFilaCuenta(cb));
    }

    // ── Reset para CREACIÓN ───────────────────────────────────────
    function resetForm() {
        form.reset();
        document.getElementById('usuarioPk').value  = '';
        document.getElementById('usuarioModalLabel').innerText = 'Nuevo usuario';

        const defNac = document.getElementById('id_nacionalidad');
        if (defNac) defNac.value = 'Argentina';
        const defPais = document.getElementById('id_pais');
        if (defPais) defPais.value = 'Argentina';
        const defEst = document.getElementById('id_estado_laboral');
        if (defEst) defEst.value = 'activo';

        // Mostrar y habilitar contraseñas
        document.querySelectorAll('.campo-password').forEach(el => el.style.display = '');
        document.getElementById('id_password1').required = true;
        document.getElementById('id_password2').required = true;
        document.getElementById('id_password1').disabled = false;
        document.getElementById('id_password2').disabled = false;
        document.querySelectorAll('.req-pwd').forEach(el => el.style.display = '');

        // Limpiar foto
        fotoInput.value = '';
        actualizarEstadoFoto(false, null, obtenerInicial());

        limpiarSubRecursos();

        const primerTab = document.querySelector('#usuarioTabs .nav-link');
        if (primerTab) bootstrap.Tab.getOrCreateInstance(primerTab).show();

        ocultarError();
    }

    // ── Cargar datos del usuario para EDICIÓN ────────────────────
    async function cargarDatosEnForm(id) {
        try {
            const resp = await fetch(`${window.usuarioAccionesUrl}?get_pk=${id}`);
            const data = await resp.json();
            if (!data.usuario) throw new Error('No se encontraron datos');
            const u = data.usuario;

            document.getElementById('usuarioPk').value = id;
            document.getElementById('usuarioModalLabel').innerText = 'Editar usuario';

            // Campos de texto / selects
            const camposTexto = [
                'username','email','rol_nombre','first_name','last_name','dni','cuil',
                'fecha_nacimiento','genero','estado_civil','nacionalidad','cantidad_hijos',
                'telefono_personal','telefono_alternativo','email_personal','calle','numero',
                'piso_depto','barrio','localidad','partido','provincia','pais','codigo_postal',
                'puesto','area','sucursal','legajo','fecha_ingreso','fecha_egreso','estado_laboral',
                'tipo_contrato','modalidad_trabajo','emergencia_nombre',
                'emergencia_vinculo','emergencia_telefono','grupo_sanguineo','obra_social','nro_afiliado',
                'fecha_apto','observaciones_salud','notas_internas'
            ];
            camposTexto.forEach(campo => {
                const el = document.getElementById('id_' + campo);
                if (el) el.value = u[campo] || '';
            });

            // Checkboxes
            const chkHijos = document.getElementById('id_tiene_hijos');
            if (chkHijos) chkHijos.checked = !!u.tiene_hijos;
            const chkApto = document.getElementById('id_apto_psicofisico');
            if (chkApto) chkApto.checked = !!u.apto_psicofisico;

            // Foto
            if (u.foto_url) {
                actualizarEstadoFoto(true, u.foto_url, '');
            } else {
                const letra = (u.first_name && u.first_name[0]) || (u.username && u.username[0]) || '?';
                actualizarEstadoFoto(false, null, letra.toUpperCase());
            }

            // Ocultar contraseñas en edición
            document.querySelectorAll('.campo-password').forEach(el => el.style.display = 'none');
            document.getElementById('id_password1').required = false;
            document.getElementById('id_password2').required = false;
            document.getElementById('id_password1').disabled = true;
            document.getElementById('id_password2').disabled = true;
            document.querySelectorAll('.req-pwd').forEach(el => el.style.display = 'none');

            // Sub‑recursos (incluye documentos con pk y archivo_url)
            poblarSubRecursos(u);

            const primerTab = document.querySelector('#usuarioTabs .nav-link');
            if (primerTab) bootstrap.Tab.getOrCreateInstance(primerTab).show();

            ocultarError();
        } catch (err) {
            console.error(err);
            mostrarError('Error al cargar los datos del usuario.');
        }
    }

    // ── Abrir modal ───────────────────────────────────────────────
    if (btnNuevo) btnNuevo.addEventListener('click', () => { resetForm(); modal?.show(); });

    // ── Submit ────────────────────────────────────────────────────
    if (form) {
        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            const btn = document.getElementById('btnGuardarUsuario');
            btn.disabled = true; btn.textContent = 'Guardando…';
            const fd = new FormData(form);

            try {
                const resp = await fetch(window.usuarioAccionesUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': fd.get('csrfmiddlewaretoken') },
                    body: fd,
                });
                const data = await resp.json();

                if (data.success) {
                    if (fd.get('pk')) {
                        actualizarFila(data.usuario);
                    } else {
                        agregarFila(data.usuario);
                    }
                    modal?.hide();
                    resetForm();
                } else {
                    const errores = Object.entries(data.errors)
                        .map(([campo, msgs]) => `${campo}: ${msgs.join(', ')}`)
                        .join(' | ');
                    mostrarError(errores);
                }
            } catch {
                mostrarError('Error de conexión. Intentá de nuevo.');
            } finally {
                btn.disabled = false; btn.textContent = 'Guardar';
            }
        });
    }

    // ── Helpers de alerta ─────────────────────────────────────────
    function mostrarError(texto) {
        const el = document.getElementById('formErrores');
        if (!el) return;
        el.textContent = texto;
        el.style.display = 'block';
    }
    function ocultarError() {
        const el = document.getElementById('formErrores');
        if (el) el.style.display = 'none';
    }

    // ── DOM: agregar / actualizar filas de tabla ──────────────────
    function estadoBadge(est) {
        const map = {
            activo: ['Activo', 'estado-activo'],
            licencia: ['En licencia', 'estado-licencia'],
            suspendido: ['Suspendido', 'estado-suspendido'],
            egresado: ['Egresado', 'estado-egresado'],
            periodo_prueba: ['En prueba', 'estado-periodo_prueba'],
        };
        const [label, cls] = map[est] || ['Activo', 'estado-activo'];
        return `<span class="estado-badge ${cls}">${label}</span>`;
    }

    function avatarHtml(u) {
        if (u.foto_url) return `<img src="${u.foto_url}" class="tabla-avatar" alt="">`;
        const letra = (u.first_name || u.username || '?')[0].toUpperCase();
        return `<div class="tabla-avatar tabla-avatar-placeholder">${letra}</div>`;
    }

    function puestoHtml(u) {
        if (!u.puesto) return '<span class="text-muted small">—</span>';
        return `<span class="puesto-text">${u.puesto}</span>${u.area ? `<span class="area-text">${u.area}</span>` : ''}`;
    }

    function rolHtml(u) {
        if (!u.rol_nombre) return '<span class="rol-badge empty">Sin rol</span>';
        return `<span class="rol-badge">${u.rol_nombre}</span>`;
    }

    function accionesHtml(u) {
        const btnPermisos = window.puedeGestionarPermisos
            ? `<a href="${window.permisosBaseUrl.replace('/0/', '/' + u.id + '/')}" class="btn-accion btn-permisos">Permisos</a>`
            : '';
        return `<div class="acciones-cell">
            <a href="/usuarios/${u.id}/" class="btn-accion btn-ver">Ver</a>
            <button class="btn-accion btn-editar" data-id="${u.id}">Editar</button>
            ${btnPermisos}
            <button class="btn-accion btn-eliminar" data-id="${u.id}">Eliminar</button>
        </div>`;
    }

    function setRowData(tr, u) {
        tr.dataset.username = u.username;
        tr.dataset.first_name = u.first_name || '';
        tr.dataset.last_name = u.last_name || '';
        tr.dataset.email = u.email || '';
        tr.dataset.dni = u.dni || '';
        tr.dataset.puesto = u.puesto || '';
        tr.dataset.area = u.area || '';
        tr.dataset.estado_laboral = u.estado_laboral || '';
        tr.dataset.rol_nombre = u.rol_nombre || '';
        tr.dataset.id = u.id;
    }

    function agregarFila(u) {
        const empty = tablaBody.querySelector('td[colspan]');
        if (empty) empty.closest('tr').remove();
        const tr = document.createElement('tr');
        setRowData(tr, u);
        tr.innerHTML = `
             <td>${avatarHtml(u)}</td>
            <td class="col-username">${u.username}</td>
            <td>${u.first_name || ''} ${u.last_name || ''}</td>
            <td>${puestoHtml(u)}</td>
            <td>${u.dni || '—'}</td>
            <td>${rolHtml(u)}</td>
            <td>${estadoBadge(u.estado_laboral)}</td>
            <td>${accionesHtml(u)}</td>`;
        tablaBody.appendChild(tr);
        attachEvents();
    }

    function actualizarFila(u) {
        const tr = document.querySelector(`#tablaUsuarios tbody tr[data-id="${u.id}"]`);
        if (!tr) return;
        setRowData(tr, u);
        tr.cells[0].innerHTML = avatarHtml(u);
        tr.cells[1].innerText = u.username;
        tr.cells[2].innerText = `${u.first_name || ''} ${u.last_name || ''}`.trim();
        tr.cells[3].innerHTML = puestoHtml(u);
        tr.cells[4].innerText = u.dni || '—';
        tr.cells[5].innerHTML = rolHtml(u);
        tr.cells[6].innerHTML = estadoBadge(u.estado_laboral);
    }

    // ── Eliminar ──────────────────────────────────────────────────
    async function eliminarUsuario(id) {
        const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        const resp = await fetch(`${window.usuarioEliminarUrl}?pk=${id}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrf },
        });
        const data = await resp.json();
        if (data.success) {
            document.querySelector(`#tablaUsuarios tbody tr[data-id="${id}"]`)?.remove();
            confirmModal?.hide();
        } else {
            alert('Error al eliminar.');
        }
    }

    if (btnConfirmar) {
        btnConfirmar.addEventListener('click', () => {
            if (usuarioAEliminar) { eliminarUsuario(usuarioAEliminar); usuarioAEliminar = null; }
        });
    }

    // ── Eventos de tabla ─────────────────────────────────────────
    function attachEvents() {
        document.querySelectorAll('.btn-editar').forEach(btn => {
            btn.onclick = (e) => {
                cargarDatosEnForm(e.currentTarget.dataset.id);
                modal?.show();
            };
        });
        document.querySelectorAll('.btn-eliminar').forEach(btn => {
            btn.onclick = (e) => {
                const id   = e.currentTarget.dataset.id;
                const row  = document.querySelector(`#tablaUsuarios tbody tr[data-id="${id}"]`);
                const nombre = row ? row.cells[2].innerText.trim() : id;
                document.getElementById('nombreUsuarioEliminar').innerText = nombre || id;
                usuarioAEliminar = id;
                confirmModal?.show();
            };
        });
    }

    attachEvents();

    // ── Botones para agregar sub‑recursos ─────────────────────────
    if (btnAgregarEstudio) btnAgregarEstudio.addEventListener('click', () => agregarFilaEstudio());
    if (btnAgregarExperiencia) btnAgregarExperiencia.addEventListener('click', () => agregarFilaExperiencia());
    if (btnAgregarCapacitacion) btnAgregarCapacitacion.addEventListener('click', () => agregarFilaCapacitacion());
    if (btnAgregarDocumento) btnAgregarDocumento.addEventListener('click', () => agregarFilaDocumento());
    if (btnAgregarCuenta) btnAgregarCuenta.addEventListener('click', () => agregarFilaCuenta());
});