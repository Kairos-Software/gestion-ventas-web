/* ventas/static/ventas/js/balanza.js — Etiquetas de peso/medida variable */
'use strict';

(function () {
    const CFG = window.BAL_CONFIG || {};

    function escapeHtml(s) {
        return (s == null ? '' : String(s)).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    /* ══════════════════════════════════════════════════════════
       GENERAR ETIQUETA
    ══════════════════════════════════════════════════════════ */
    const productoBuscar   = document.getElementById('balProductoBuscar');
    const productoPk       = document.getElementById('balProductoPk');
    const productoDropdown = document.getElementById('balProductoDropdown');
    const cantidadInput    = document.getElementById('balCantidad');
    const cantidadHint     = document.getElementById('balCantidadHint');
    const preview          = document.getElementById('balPreview');
    const msg              = document.getElementById('balMsg');
    const btnGenerar       = document.getElementById('btnGenerarEtiqueta');

    let productoElegido = null;

    if (productoBuscar && CFG.puedeCrear) {
        let debounce = null;
        productoBuscar.addEventListener('input', () => {
            productoPk.value = '';
            productoElegido = null;
            cantidadInput.value = '';
            cantidadInput.disabled = true;
            cantidadHint.textContent = 'Elegí un producto primero.';
            btnGenerar.disabled = true;
            preview.style.display = 'none';
            clearTimeout(debounce);
            const q = productoBuscar.value.trim();
            if (!q) { productoDropdown.classList.remove('visible'); return; }
            debounce = setTimeout(() => _buscarProducto(q), 250);
        });
        productoBuscar.addEventListener('focus', () => {
            if (productoDropdown.innerHTML) productoDropdown.classList.add('visible');
        });
        document.addEventListener('click', (e) => {
            if (!productoDropdown.contains(e.target) && e.target !== productoBuscar) {
                productoDropdown.classList.remove('visible');
            }
        });
    }

    function _buscarProducto(q) {
        fetch(`${CFG.urlBuscarProducto}?q=${encodeURIComponent(q)}`)
            .then(r => r.json())
            .then(data => {
                if (data.error || !data.results.length) {
                    productoDropdown.innerHTML = `<div class="bal-dropdown-empty">Sin resultados.</div>`;
                    productoDropdown.classList.add('visible');
                    return;
                }
                productoDropdown.innerHTML = data.results.map(p => `
                    <div class="bal-dropdown-item" data-pk="${p.pk}" data-nombre="${escapeHtml(p.nombre)}"
                         data-unidad="${escapeHtml(p.unidad_medida)}" data-permite-fraccion="${p.permite_fraccion}"
                         data-precio="${p.precio_venta || ''}" data-stock="${p.stock_actual}">
                        ${escapeHtml(p.nombre)}${p.marca ? ` <span class="bal-dropdown-marca">· ${escapeHtml(p.marca)}</span>` : ''}
                        <small>${escapeHtml(p.codigo)} · Se mide en ${escapeHtml(p.unidad_medida)} · Stock: ${KaiFormat.cantidad(p.stock_actual)}</small>
                    </div>
                `).join('');
                productoDropdown.classList.add('visible');
                productoDropdown.querySelectorAll('.bal-dropdown-item').forEach(item => {
                    item.addEventListener('click', () => _elegirProducto(item.dataset));
                });
            })
            .catch(() => {
                productoDropdown.innerHTML = `<div class="bal-dropdown-empty">Error al buscar.</div>`;
                productoDropdown.classList.add('visible');
            });
    }

    function _elegirProducto(ds) {
        productoBuscar.value = ds.nombre;
        productoPk.value = ds.pk;
        productoElegido = {
            pk: parseInt(ds.pk, 10), nombre: ds.nombre, unidad: ds.unidad,
            permiteFraccion: ds.permiteFraccion === 'true',
            precio: ds.precio ? parseFloat(ds.precio) : null,
            stock: parseFloat(ds.stock),
        };
        productoDropdown.classList.remove('visible');
        msg.style.display = 'none';

        if (!productoElegido.permiteFraccion) {
            cantidadInput.disabled = true;
            btnGenerar.disabled = true;
            cantidadHint.textContent = `"${ds.nombre}" se cuenta por ${ds.unidad} — la balanza es solo para productos que se pesan o miden.`;
            preview.style.display = 'none';
            return;
        }
        if (productoElegido.precio == null) {
            cantidadInput.disabled = true;
            btnGenerar.disabled = true;
            cantidadHint.textContent = `"${ds.nombre}" todavía no tiene un precio de venta cargado.`;
            preview.style.display = 'none';
            return;
        }

        cantidadInput.disabled = false;
        cantidadInput.value = '';
        cantidadInput.focus();
        cantidadHint.textContent = `Se mide en ${ds.unidad}. Precio actual: ${KaiFormat.moneda(productoElegido.precio)} por ${ds.unidad}.`;
        btnGenerar.disabled = true;
        preview.style.display = 'none';
    }

    if (cantidadInput) {
        cantidadInput.addEventListener('input', () => {
            const cantidad = parseFloat(cantidadInput.value);
            if (!productoElegido || !cantidad || cantidad <= 0) {
                preview.style.display = 'none';
                btnGenerar.disabled = true;
                return;
            }
            const total = cantidad * productoElegido.precio;
            preview.style.display = 'block';
            preview.innerHTML = `Total a cobrar: ${KaiFormat.moneda(total)}
                <small>${KaiFormat.cantidad(cantidad)} ${productoElegido.unidad} × ${KaiFormat.moneda(productoElegido.precio)}</small>`;
            btnGenerar.disabled = false;
        });
    }

    if (btnGenerar) {
        btnGenerar.addEventListener('click', () => {
            if (!productoElegido) return;
            const cantidad = parseFloat(cantidadInput.value);
            if (!cantidad || cantidad <= 0) {
                msg.textContent = 'Cargá la cantidad pesada.';
                msg.style.display = 'block';
                return;
            }
            btnGenerar.disabled = true;
            msg.style.display = 'none';
            fetch(CFG.urlGenerar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ producto_pk: productoElegido.pk, cantidad: cantidadInput.value }),
            })
                .then(r => r.json())
                .then(data => {
                    btnGenerar.disabled = false;
                    if (data.error) {
                        msg.textContent = data.error;
                        msg.style.display = 'block';
                        return;
                    }
                    if (data.aviso_stock) KaiToast.show(data.aviso_stock, 'warning', 7000);
                    KaiToast.show(`Etiqueta ${data.codigo} generada.`, 'success');
                    _mostrarResultado(data);
                    cargarHistorial();
                })
                .catch(() => {
                    btnGenerar.disabled = false;
                    msg.textContent = 'Error de conexión.';
                    msg.style.display = 'block';
                });
        });
    }

    let etiquetaActual = null;
    const resultadoCard = document.getElementById('balResultado');

    function _mostrarResultado(etiqueta) {
        etiquetaActual = etiqueta;
        document.getElementById('balResProducto').textContent = etiqueta.producto_nombre;
        document.getElementById('balResCantidad').textContent =
            `${KaiFormat.cantidad(etiqueta.cantidad)} ${etiqueta.unidad_medida} × ${KaiFormat.moneda(etiqueta.precio_unitario)}`;
        document.getElementById('balResPrecio').textContent = `${KaiFormat.moneda(etiqueta.precio_total)}`;
        JsBarcode('#balBarcodeSvg', etiqueta.codigo, {
            format: 'CODE128', width: 2, height: 55, fontSize: 13, margin: 4,
        });
        resultadoCard.style.display = 'block';
        resultadoCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    const btnGenerarOtra = document.getElementById('btnGenerarOtra');
    if (btnGenerarOtra) {
        btnGenerarOtra.addEventListener('click', () => {
            resultadoCard.style.display = 'none';
            productoBuscar.value = '';
            productoPk.value = '';
            productoElegido = null;
            cantidadInput.value = '';
            cantidadInput.disabled = true;
            cantidadHint.textContent = 'Elegí un producto primero.';
            btnGenerar.disabled = true;
            preview.style.display = 'none';
            productoBuscar.focus();
        });
    }

    const btnImprimir = document.getElementById('btnImprimirEtiqueta');
    if (btnImprimir) {
        btnImprimir.addEventListener('click', () => {
            if (!etiquetaActual) return;
            let area = document.getElementById('bal-print-area');
            if (area) area.remove();
            area = document.createElement('div');
            area.id = 'bal-print-area';
            const nodo = document.getElementById('balEtiquetaNodo').cloneNode(true);
            nodo.removeAttribute('id');
            area.appendChild(nodo);
            document.body.appendChild(area);
            // Recrear el barcode en el clon (el cloneNode ya trae el SVG
            // anterior tal cual, así que no hace falta — pero por las
            // dudas, si el navegador no clonó bien el contenido interno):
            const svgClon = nodo.querySelector('svg');
            if (svgClon && !svgClon.querySelector('rect, path')) {
                JsBarcode(svgClon, etiquetaActual.codigo, { format: 'CODE128', width: 2, height: 55, fontSize: 13, margin: 4 });
            }
            window.onafterprint = () => { area.remove(); window.onafterprint = null; };
            setTimeout(() => window.print(), 50);
        });
    }

    /* ══════════════════════════════════════════════════════════
       HISTORIAL
    ══════════════════════════════════════════════════════════ */
    const tbody         = document.getElementById('balHistorialTbody');
    const buscarHistorial = document.getElementById('balBuscarHistorial');
    const filtroEstado  = document.getElementById('balFiltroEstado');

    const ESTADO_LABEL_CLASE = { disponible: 'disponible', vendida: 'vendida', anulada: 'anulada' };

    function cargarHistorial() {
        const params = new URLSearchParams();
        if (buscarHistorial && buscarHistorial.value.trim()) params.set('q', buscarHistorial.value.trim());
        if (filtroEstado && filtroEstado.value) params.set('estado', filtroEstado.value);

        fetch(`${CFG.urlListar}?${params.toString()}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">${escapeHtml(data.error)}</td></tr>`;
                    return;
                }
                if (!data.results.length) {
                    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">Todavía no hay etiquetas generadas.</td></tr>`;
                    return;
                }
                tbody.innerHTML = data.results.map(e => `
                    <tr>
                        <td><code>${escapeHtml(e.codigo)}</code></td>
                        <td>${escapeHtml(e.producto_nombre)}</td>
                        <td>${KaiFormat.cantidad(e.cantidad)} ${escapeHtml(e.unidad_medida)}</td>
                        <td>${KaiFormat.moneda(e.precio_total)}</td>
                        <td><span class="bal-badge-estado bal-badge-estado--${ESTADO_LABEL_CLASE[e.estado] || ''}">${escapeHtml(e.estado_display)}</span></td>
                        <td>${escapeHtml(e.creado_por)}</td>
                        <td>${escapeHtml(e.fecha_alta)}</td>
                        <td>${e.puede_anular ? `<button type="button" class="bal-btn-anular" data-pk="${e.pk}" data-codigo="${escapeHtml(e.codigo)}">Anular</button>` : ''}</td>
                    </tr>
                `).join('');
                tbody.querySelectorAll('.bal-btn-anular').forEach(btn => {
                    btn.addEventListener('click', () => _anular(btn.dataset.pk, btn.dataset.codigo));
                });
            })
            .catch(() => {
                tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">Error al cargar el historial.</td></tr>`;
            });
    }

    async function _anular(pk, codigo) {
        const ok = await KaiConfirm(
            `¿Anular la etiqueta ${codigo}? Vas a tener que pesar el producto de nuevo si te equivocaste.`,
            { danger: true, confirmText: 'Anular' },
        );
        if (!ok) return;

        fetch(CFG.urlAnular, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ pk }),
        })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    KaiToast.show(data.error, 'danger');
                    return;
                }
                KaiToast.show(`Etiqueta ${codigo} anulada.`, 'success');
                cargarHistorial();
            })
            .catch(() => KaiToast.show('Error de conexión.', 'danger'));
    }

    let buscarDebounce = null;
    if (buscarHistorial) {
        buscarHistorial.addEventListener('input', () => {
            clearTimeout(buscarDebounce);
            buscarDebounce = setTimeout(cargarHistorial, 300);
        });
    }
    if (filtroEstado) filtroEstado.addEventListener('change', cargarHistorial);

    cargarHistorial();
})();
