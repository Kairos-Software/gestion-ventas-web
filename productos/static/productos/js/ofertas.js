/**
 * ofertas.js
 * Página propia de Ofertas (fuera de Productos).
 * CSRF y URLS se inyectan desde el template (const CSRF, const URLS).
 */
'use strict';

let _cacheOfertas = [];
let _ofProductosSeleccionados = []; // [{pk, nombre, codigo}, ...] del formulario en edición

cargarOfertas();

function abrirModal(id) {
    document.getElementById(id).classList.add('prd-modal-overlay--open');
    document.body.style.overflow = 'hidden';
}

function cerrarModal(id) {
    document.getElementById(id).classList.remove('prd-modal-overlay--open');
    document.body.style.overflow = '';
}

document.getElementById('btnNuevaOferta')?.addEventListener('click', () => {
    _resetFormOferta();
    abrirModal('modalOferta');
});

function setTipoOferta(tipo) {
    document.getElementById('ofTipo').value = tipo;
    document.querySelectorAll('.prd-precio-toggle-btn').forEach(btn => {
        btn.classList.toggle('prd-precio-toggle-btn--active', btn.dataset.tipo === tipo);
    });
    document.getElementById('campoOfPorcentaje').hidden = tipo === 'nxm';
    document.getElementById('campoOfNxm').hidden = tipo !== 'nxm';
    document.getElementById('campoOfUmbral').hidden = tipo !== 'umbral';
    // El alcance por producto/categoría no tiene sentido para "gastá $X" —
    // esa oferta se mide sobre el total de la venta, no sobre un producto.
    document.getElementById('campoOfAlcance').hidden = tipo === 'umbral';
}

function _fmtFechaOf(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y}`;
}

function _alcanceTextoOferta(o) {
    if (o.tipo === 'umbral') return `Total de la venta ≥ $${o.monto_minimo}`;
    const nProd = o.productos.length;
    const nCat  = o.categorias.length;
    if (!nProd && !nCat) return 'Todo el catálogo';
    const partes = [];
    if (nProd) partes.push(`${nProd} producto${nProd !== 1 ? 's' : ''}`);
    if (nCat)  partes.push(`${nCat} categoría${nCat !== 1 ? 's' : ''}`);
    return partes.join(' + ');
}

function _tituloOferta(o) {
    if (o.tipo === 'nxm') return `${o.cantidad_lleva}x${o.cantidad_paga}`;
    return `${o.porcentaje}%`;
}

async function cargarOfertas() {
    const res  = await fetch(URLS.ofertaLista);
    const data = await res.json();
    _cacheOfertas = data.results || [];
    _renderOfertas();
}

function _renderOfertas() {
    const cont  = document.getElementById('ofertaLista');
    const empty = document.getElementById('ofEmptyMsg');
    if (!cont) return;

    if (!_cacheOfertas.length) {
        cont.innerHTML = '';
        empty.style.display = '';
        return;
    }
    empty.style.display = 'none';

    cont.innerHTML = _cacheOfertas.map(o => `
        <div class="prd-ld-row ${o.activa ? '' : 'prd-ld-row--inactiva'}">
            <div class="prd-ld-row-pct">${_tituloOferta(o)}</div>
            <div class="prd-ld-row-info">
                <span class="prd-ld-row-nombre">${o.nombre}</span>
                <span class="prd-badge ${o.activa ? 'prd-badge--tipo' : ''}">${o.activa ? 'Activa' : 'Inactiva'}</span>
                <span class="prd-badge">${o.aplicacion === 'automatica' ? 'Automática' : 'Manual'}</span>
                ${o.vigente_hoy ? '<span class="prd-badge prd-badge--tipo">Vigente hoy</span>' : ''}
                <span class="prd-of-row-meta">${_fmtFechaOf(o.fecha_inicio)} → ${_fmtFechaOf(o.fecha_fin)} · ${_alcanceTextoOferta(o)}</span>
            </div>
            <div class="prd-ld-row-actions">
                <button type="button" class="prd-ld-icon-btn" title="Editar" onclick="_editarOferta(${o.pk})">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M10.5 2L13 4.5L5 12.5H2.5V10L10.5 2Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <button type="button" class="prd-ld-icon-btn" title="${o.activa ? 'Desactivar' : 'Activar'}" onclick="_toggleActivaOferta(${o.pk})">
                    ${o.activa
                        ? `<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M4.5 4.5L10.5 10.5M10.5 4.5L4.5 10.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`
                        : `<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M4 2.5L11.5 7.5L4 12.5V2.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`}
                </button>
                <button type="button" class="prd-ld-icon-btn prd-ld-icon-btn--danger" title="Eliminar" onclick="_eliminarOferta(${o.pk}, '${o.nombre.replace(/'/g, "\\'")}')">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                        <path d="M2.5 4H12.5M5.5 4V3H9.5V4M6 6.5V10.5M9 6.5V10.5M3.5 4L4.3 12H10.7L11.5 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');
}

function _resetFormOferta() {
    document.getElementById('ofPk').value = '';
    setTipoOferta('porcentaje');
    document.getElementById('ofNombre').value = '';
    document.getElementById('ofPorcentaje').value = '';
    document.getElementById('ofCantidadLleva').value = '';
    document.getElementById('ofCantidadPaga').value = '';
    document.getElementById('ofMontoMinimo').value = '';
    document.getElementById('ofBaseCalculo').value = 'neto';
    document.getElementById('ofFechaInicio').value = '';
    document.getElementById('ofFechaFin').value = '';
    document.getElementById('ofAplicacion').value = 'automatica';
    document.getElementById('ofActiva').checked = true;
    document.querySelectorAll('.ofDia').forEach(el => el.checked = false);
    document.querySelectorAll('.ofCategoria').forEach(el => el.checked = false);
    _ofProductosSeleccionados = [];
    _renderOfertaChips();
    document.getElementById('ofProductoBuscar').value = '';
    document.getElementById('ofProductoDropdown').innerHTML = '';
    document.getElementById('btnGuardarOfertaTxt').textContent = 'Agregar';
    document.getElementById('modalOfertaTitulo').textContent = 'Nueva oferta';
    document.getElementById('ofFormError').style.display = 'none';
}

function _editarOferta(pk) {
    const o = _cacheOfertas.find(x => x.pk === pk);
    if (!o) return;
    document.getElementById('ofPk').value = o.pk;
    setTipoOferta(o.tipo);
    document.getElementById('ofNombre').value = o.nombre;
    document.getElementById('ofPorcentaje').value = o.porcentaje;
    document.getElementById('ofCantidadLleva').value = o.cantidad_lleva ?? '';
    document.getElementById('ofCantidadPaga').value = o.cantidad_paga ?? '';
    document.getElementById('ofMontoMinimo').value = o.monto_minimo ?? '';
    document.getElementById('ofBaseCalculo').value = o.base_calculo || 'neto';
    document.getElementById('ofFechaInicio').value = o.fecha_inicio;
    document.getElementById('ofFechaFin').value = o.fecha_fin;
    document.getElementById('ofAplicacion').value = o.aplicacion;
    document.getElementById('ofActiva').checked = o.activa;
    document.querySelectorAll('.ofDia').forEach(el => {
        el.checked = o.dias_semana.includes(parseInt(el.value, 10));
    });
    document.querySelectorAll('.ofCategoria').forEach(el => {
        el.checked = o.categorias.includes(parseInt(el.value, 10));
    });
    _ofProductosSeleccionados = o.productos.map(p => ({ ...p }));
    _renderOfertaChips();
    document.getElementById('btnGuardarOfertaTxt').textContent = 'Guardar cambios';
    document.getElementById('modalOfertaTitulo').textContent = 'Editar oferta';
    document.getElementById('ofFormError').style.display = 'none';
    abrirModal('modalOferta');
}

function _renderOfertaChips() {
    const cont = document.getElementById('ofProductoChips');
    cont.innerHTML = _ofProductosSeleccionados.map(p => `
        <span class="prd-of-chip">
            ${p.codigo ? `[${p.codigo}] ` : ''}${p.nombre}
            <button type="button" onclick="_quitarProductoOferta(${p.pk})" title="Quitar">✕</button>
        </span>
    `).join('');
}

function _quitarProductoOferta(pk) {
    _ofProductosSeleccionados = _ofProductosSeleccionados.filter(p => p.pk !== pk);
    _renderOfertaChips();
}

let _ofBuscarTimer;
document.getElementById('ofProductoBuscar')?.addEventListener('input', (e) => {
    clearTimeout(_ofBuscarTimer);
    const q = e.target.value.trim();
    const dropdown = document.getElementById('ofProductoDropdown');
    if (!q) {
        dropdown.innerHTML = '';
        return;
    }
    _ofBuscarTimer = setTimeout(async () => {
        const res  = await fetch(`${URLS.productoBuscar}?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        const results = (data.results || []).filter(
            p => !_ofProductosSeleccionados.some(sel => sel.pk === p.pk)
        );
        dropdown.innerHTML = results.length
            ? results.map(p => `
                <div class="prd-of-dropdown-option" data-pk="${p.pk}" data-nombre="${p.nombre.replace(/"/g, '&quot;')}" data-codigo="${p.codigo}">
                    [${p.codigo}] ${p.nombre}
                </div>`).join('')
            : '<div class="prd-of-dropdown-option">Sin resultados</div>';
        dropdown.querySelectorAll('.prd-of-dropdown-option[data-pk]').forEach(el => {
            el.addEventListener('click', () => {
                _ofProductosSeleccionados.push({
                    pk: parseInt(el.dataset.pk, 10),
                    nombre: el.dataset.nombre,
                    codigo: el.dataset.codigo,
                });
                _renderOfertaChips();
                dropdown.innerHTML = '';
                document.getElementById('ofProductoBuscar').value = '';
            });
        });
    }, 260);
});

function _payloadOferta() {
    const dias = Array.from(document.querySelectorAll('.ofDia:checked')).map(el => parseInt(el.value, 10));
    const categorias = Array.from(document.querySelectorAll('.ofCategoria:checked')).map(el => parseInt(el.value, 10));
    return {
        nombre:          document.getElementById('ofNombre').value.trim(),
        tipo:            document.getElementById('ofTipo').value,
        porcentaje:      document.getElementById('ofPorcentaje').value,
        cantidad_lleva:  document.getElementById('ofCantidadLleva').value,
        cantidad_paga:   document.getElementById('ofCantidadPaga').value,
        monto_minimo:    document.getElementById('ofMontoMinimo').value,
        base_calculo:    document.getElementById('ofBaseCalculo').value,
        fecha_inicio:    document.getElementById('ofFechaInicio').value,
        fecha_fin:       document.getElementById('ofFechaFin').value,
        dias_semana:     dias,
        aplicacion:      document.getElementById('ofAplicacion').value,
        activa:          document.getElementById('ofActiva').checked,
        categorias:      categorias,
        productos:       _ofProductosSeleccionados.map(p => p.pk),
    };
}

async function guardarOferta() {
    const pk     = document.getElementById('ofPk').value;
    const errBox = document.getElementById('ofFormError');
    errBox.style.display = 'none';

    const body = _payloadOferta();
    if (!body.nombre || !body.fecha_inicio || !body.fecha_fin) {
        errBox.textContent   = 'Completá el nombre y las fechas de vigencia.';
        errBox.style.display = '';
        return;
    }
    if ((body.tipo === 'porcentaje' || body.tipo === 'umbral') && body.porcentaje === '') {
        errBox.textContent   = 'Completá el porcentaje.';
        errBox.style.display = '';
        return;
    }
    if (body.tipo === 'nxm' && (body.cantidad_lleva === '' || body.cantidad_paga === '')) {
        errBox.textContent   = 'Completá "Llevá" y "Pagá".';
        errBox.style.display = '';
        return;
    }
    if (body.tipo === 'umbral' && body.monto_minimo === '') {
        errBox.textContent   = 'Completá el monto mínimo de compra.';
        errBox.style.display = '';
        return;
    }
    if (pk) body.pk = pk;

    const res  = await fetch(URLS.ofertaAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!data.ok) {
        errBox.textContent = Object.values(data.errors || {}).flat().join(' ') || 'Error al guardar.';
        errBox.style.display = '';
        return;
    }

    KaiToast.show(`Oferta "${data.nombre}" ${data.creado ? 'creada' : 'actualizada'}.`, 'success');
    cerrarModal('modalOferta');
    _resetFormOferta();
    await cargarOfertas();
}

async function _toggleActivaOferta(pk) {
    const o = _cacheOfertas.find(x => x.pk === pk);
    if (!o) return;
    const res  = await fetch(URLS.ofertaAcciones, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({
            pk: o.pk, nombre: o.nombre, tipo: o.tipo, porcentaje: o.porcentaje,
            cantidad_lleva: o.cantidad_lleva, cantidad_paga: o.cantidad_paga,
            monto_minimo: o.monto_minimo, base_calculo: o.base_calculo,
            fecha_inicio: o.fecha_inicio, fecha_fin: o.fecha_fin,
            dias_semana: o.dias_semana, aplicacion: o.aplicacion,
            categorias: o.categorias, productos: o.productos.map(p => p.pk),
            activa: !o.activa,
        }),
    });
    const data = await res.json();
    if (data.ok) {
        await cargarOfertas();
    } else {
        KaiToast.show(data.error || 'Error', 'danger');
    }
}

async function _eliminarOferta(pk, nombre) {
    if (!await KaiConfirm(`¿Eliminar la oferta "${nombre}"? Esta acción no se puede deshacer.`, { danger: true })) return;
    const res  = await fetch(URLS.ofertaEliminar, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ pk }),
    });
    const data = await res.json();
    if (data.ok) {
        KaiToast.show(`Oferta "${data.nombre}" eliminada.`, 'success');
        _resetFormOferta();
        await cargarOfertas();
    } else {
        KaiToast.show(data.error || 'Error', 'danger');
    }
}

// ESC cierra modales
document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.prd-modal-overlay--open').forEach(overlay => cerrarModal(overlay.id));
});
