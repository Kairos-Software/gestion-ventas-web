document.addEventListener('DOMContentLoaded', function () {

    const tbody       = document.getElementById('inventarioTbody');
    const inputBuscar  = document.getElementById('inventarioBuscar');
    const filtrosWrap  = document.getElementById('inventarioFiltros');

    let filtroActual   = '';
    let debounceTimer   = null;

    // ── Carga inicial ──
    cargarLotes();
    cargarStats();
    cargarStatsPerdidas();

    // ── Búsqueda (con debounce, sirve tanto para tipear como escanear) ──
    inputBuscar.addEventListener('input', function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(cargarLotes, 300);
    });

    // La pistola manda un Enter al final del escaneo — disparamos al toque.
    inputBuscar.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            clearTimeout(debounceTimer);
            cargarLotes();
        }
    });

    // ── Filtros de vencimiento ──
    filtrosWrap.addEventListener('click', function (e) {
        const btn = e.target.closest('.filtro-btn');
        if (!btn) return;
        filtrosWrap.querySelectorAll('.filtro-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        filtroActual = btn.dataset.filtro || '';
        cargarLotes();
    });

    function cargarLotes() {
        const params = new URLSearchParams();
        if (inputBuscar.value.trim()) params.set('q', inputBuscar.value.trim());
        if (filtroActual) params.set('vencimiento', filtroActual);

        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">Cargando...</td></tr>`;

        fetch(`${window.INVENTARIO_URLS.listar}?${params.toString()}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">${data.error}</td></tr>`;
                    return;
                }
                renderTabla(data.results);
            })
            .catch(() => {
                tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">Error al cargar el inventario.</td></tr>`;
            });
    }

    // ── Stat cards (Vigentes / Por vencer / Vencidos) ──
    // Se calculan sobre el total del inventario, sin aplicar el buscador
    // ni los filtros de la tabla — igual que las tarjetas de "Mi Stock".
    function cargarStats() {
        const statOk        = document.getElementById('statOk');
        const statPorVencer  = document.getElementById('statPorVencer');
        const statVencidos   = document.getElementById('statVencidos');
        if (!statOk || !statPorVencer || !statVencidos) return;

        fetch(window.INVENTARIO_URLS.listar)
            .then(r => r.json())
            .then(data => {
                if (data.error || !Array.isArray(data.results)) return;

                let ok = 0, porVencer = 0, vencidos = 0;
                data.results.forEach(l => {
                    if (l.estado_vencimiento === 'ok') ok++;
                    else if (l.estado_vencimiento === 'por_vencer') porVencer++;
                    else if (l.estado_vencimiento === 'vencido') vencidos++;
                });

                statOk.textContent = ok;
                statPorVencer.textContent = porVencer;
                statVencidos.textContent = vencidos;
            })
            .catch(() => {
                statOk.textContent = '—';
                statPorVencer.textContent = '—';
                statVencidos.textContent = '—';
            });
    }

    // ── Stat card de Pérdidas (últimas 100, costo total) ──
    function cargarStatsPerdidas() {
        const statPerdidasCosto = document.getElementById('statPerdidasCosto');
        if (!statPerdidasCosto) return;

        fetch(window.INVENTARIO_URLS.listarPerdidas)
            .then(r => r.json())
            .then(data => {
                if (data.error) return;
                statPerdidasCosto.textContent = '$' + parseFloat(data.total_costo || 0).toLocaleString('es-AR', { minimumFractionDigits: 2 });
            })
            .catch(() => { statPerdidasCosto.textContent = '—'; });
    }

    function renderTabla(lotes) {
        if (!lotes.length) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">No se encontraron lotes.</td></tr>`;
            return;
        }

        tbody.innerHTML = lotes.map(l => `
            <tr>
                <td>
                    <div class="inv-producto-nombre">${escapeHtml(l.producto_nombre)}</div>
                    ${l.variante_desc ? `<div class="inv-variante-desc">${escapeHtml(l.variante_desc)}</div>` : ''}
                </td>
                <td><span class="inv-codigo-lote">${escapeHtml(l.codigo)}</span></td>
                <td>
                    ${KaiFormat.cantidad(l.cantidad_actual)} / ${KaiFormat.cantidad(l.cantidad_inicial)} <span class="inv-unidad-medida">${escapeHtml(l.unidad_medida || '')}</span>
                    ${l.unidades_por_presentacion ? `<div class="inv-contenido-neto">cada ${escapeHtml(l.unidad_medida || '')} trae ${l.unidades_por_presentacion} piezas${l.contenido_neto ? ` de ${KaiFormat.cantidad(l.contenido_neto)} c/u` : ''}</div>` : (l.contenido_neto ? `<div class="inv-contenido-neto">cada ${escapeHtml(l.unidad_medida || '')} trae ${KaiFormat.cantidad(l.contenido_neto)} → ${KaiFormat.cantidad(parseFloat(l.cantidad_actual) * parseFloat(l.contenido_neto))} en total</div>` : '')}
                    <div class="inv-barra-restante">
                        <div class="inv-barra-restante-fill" style="width:${l.porcentaje_restante}%"></div>
                    </div>
                </td>
                <td>$${KaiFormat.moneda(l.costo_unitario)}</td>
                <td>${badgeVencimiento(l)}</td>
                <td>${l.fecha_compra}</td>
                <td>${escapeHtml(l.proveedor || '—')}</td>
                <td>
                    <div class="inv-acciones-lote">
                        <button class="btn-ver-codigo" data-lote='${JSON.stringify(l).replace(/'/g, "&#39;")}' title="Ver / imprimir código">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <rect x="2" y="3" width="1.3" height="10" fill="currentColor"/>
                                <rect x="4.5" y="3" width="0.7" height="10" fill="currentColor"/>
                                <rect x="6.2" y="3" width="1.3" height="10" fill="currentColor"/>
                                <rect x="9" y="3" width="0.7" height="10" fill="currentColor"/>
                                <rect x="10.5" y="3" width="1.3" height="10" fill="currentColor"/>
                                <rect x="13" y="3" width="0.7" height="10" fill="currentColor"/>
                            </svg>
                            Código
                        </button>
                        <button class="btn-ver-codigo btn-perdida" data-pk="${l.pk}" data-nombre="${escapeHtml(l.producto_nombre)}"
                                data-codigo="${escapeHtml(l.codigo)}" data-disponible="${l.cantidad_actual}" data-unidad="${escapeHtml(l.unidad_medida || '')}"
                                title="Registrar pérdida de este lote">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M3 3L13 13M13 3L3 13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
                            </svg>
                            Pérdida
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.btn-ver-codigo[data-lote]').forEach(btn => {
            btn.addEventListener('click', () => {
                const lote = JSON.parse(btn.dataset.lote);
                abrirModalCodigo(lote);
            });
        });

        tbody.querySelectorAll('.btn-ver-codigo[data-pk]').forEach(btn => {
            btn.addEventListener('click', () => {
                abrirModalPerdida({
                    pk: btn.dataset.pk,
                    nombre: btn.dataset.nombre,
                    codigo: btn.dataset.codigo,
                    disponible: btn.dataset.disponible,
                    unidad: btn.dataset.unidad,
                });
            });
        });
    }

    function badgeVencimiento(l) {
        if (!l.fecha_vencimiento) {
            return `<span class="badge-vencimiento sin-fecha">Sin vencimiento</span>`;
        }
        const labels = { vencido: 'Vencido', por_vencer: 'Por vencer', ok: 'OK' };
        return `<span class="badge-vencimiento ${l.estado_vencimiento}">${labels[l.estado_vencimiento]} · ${l.fecha_vencimiento}</span>`;
    }

    // ══════════════════════════════════════════════════════════
    //  MODAL — Código de lote
    // ══════════════════════════════════════════════════════════

    const modalEl        = document.getElementById('modalCodigo');
    const modalCodigo     = new bootstrap.Modal(modalEl);
    const btnImprimir     = document.getElementById('btnImprimirEtiqueta');

    const impTipo      = document.getElementById('impTipo');
    const impCantidad  = document.getElementById('impCantidad');
    const impAncho     = document.getElementById('impAncho');
    const impAlto      = document.getElementById('impAlto');
    const impHoja      = document.getElementById('impHoja');
    const impMargen    = document.getElementById('impMargen');
    const impHojaOpciones = document.getElementById('impHojaOpciones');
    const impResumen   = document.getElementById('impResumen');
    const impPresets   = document.getElementById('impPresets');

    let loteActual = null;

    function abrirModalCodigo(lote) {
        loteActual = lote;

        document.getElementById('etiquetaProducto').textContent = lote.producto_nombre;
        document.getElementById('etiquetaVariante').textContent = lote.variante_desc || '';

        const detalles = [];
        detalles.push(`Costo: $${KaiFormat.moneda(lote.costo_unitario)}`);
        if (lote.fecha_vencimiento) detalles.push(`Vence: ${lote.fecha_vencimiento}`);
        detalles.push(`Ingreso: ${lote.fecha_compra}`);
        document.getElementById('etiquetaDetalle').textContent = detalles.join('  ·  ');

        JsBarcode('#etiquetaBarcode', lote.codigo, {
            format: 'CODE128',
            width: 2,
            height: 55,
            fontSize: 13,
            margin: 4,
        });

        actualizarResumenImpresion();
        modalCodigo.show();
    }

    // ── Config de impresión: tipo hoja/térmica ──
    impTipo.addEventListener('change', () => {
        const esTermica = impTipo.value === 'termica';
        impHojaOpciones.style.display = esTermica ? 'none' : 'flex';
        // Defaults razonables al cambiar de modo
        impAncho.value = esTermica ? 40 : 50;
        impAlto.value  = esTermica ? 30 : 30;
        actualizarResumenImpresion();
    });

    [impCantidad, impAncho, impAlto, impHoja, impMargen].forEach(el => {
        el.addEventListener('input', actualizarResumenImpresion);
    });

    impPresets.addEventListener('click', (e) => {
        const btn = e.target.closest('.inv-preset-btn');
        if (!btn) return;
        impAncho.value = btn.dataset.w;
        impAlto.value  = btn.dataset.h;
        actualizarResumenImpresion();
    });

    function calcularGrilla(ancho, alto, hoja, margen) {
        const tamHoja = hoja === 'A4' ? { w: 210, h: 297 } : { w: 216, h: 279 };
        const cols = Math.max(1, Math.floor((tamHoja.w - margen * 2 + 2) / (ancho + 2)));
        const rows = Math.max(1, Math.floor((tamHoja.h - margen * 2 + 2) / (alto + 2)));
        return { cols, rows, porHoja: cols * rows };
    }

    function actualizarResumenImpresion() {
        const ancho    = parseFloat(impAncho.value) || 0;
        const alto     = parseFloat(impAlto.value) || 0;
        const cantidad = Math.max(1, parseInt(impCantidad.value) || 1);

        if (!ancho || !alto) { impResumen.textContent = ''; return; }

        if (impTipo.value === 'termica') {
            impResumen.textContent = `Se imprimirán ${cantidad} etiqueta${cantidad > 1 ? 's' : ''} de ${ancho}×${alto} mm, una por página — pensado para impresora de etiquetas térmica (pistola).`;
            return;
        }

        const margen = parseFloat(impMargen.value) || 0;
        const { cols, rows, porHoja } = calcularGrilla(ancho, alto, impHoja.value, margen);
        const hojas = Math.ceil(cantidad / porHoja);
        impResumen.textContent = `Entran ${porHoja} etiquetas por hoja ${impHoja.value} (${cols} columnas × ${rows} filas) — se usarán ${hojas} hoja${hojas > 1 ? 's' : ''} para ${cantidad} etiqueta${cantidad > 1 ? 's' : ''}.`;
    }

    function crearEtiquetaNodo(lote, wMM, hMM) {
        const div = document.createElement('div');
        div.className = 'inv-print-label';
        div.style.width  = wMM + 'mm';
        div.style.height = hMM + 'mm';

        const svgId = 'bc' + Math.random().toString(36).slice(2, 9);
        div.innerHTML = `
            <div class="inv-print-label-prod">${escapeHtml(lote.producto_nombre)}</div>
            ${lote.variante_desc ? `<div class="inv-print-label-var">${escapeHtml(lote.variante_desc)}</div>` : ''}
            <svg id="${svgId}"></svg>
        `;

        const alturaBarra = Math.max(10, Math.min(hMM * 2.6, 60));
        JsBarcode(div.querySelector('svg'), lote.codigo, {
            format: 'CODE128',
            width: 1.1,
            height: alturaBarra,
            fontSize: 8,
            margin: 1,
            displayValue: true,
        });

        return div;
    }

    function limpiarAreaImpresion() {
        const area = document.getElementById('inv-print-area');
        if (area) area.remove();
        const style = document.getElementById('inv-print-page-style');
        if (style) style.remove();
        window.onafterprint = null;
    }

    function imprimirEtiquetas() {
        if (!loteActual) return;

        limpiarAreaImpresion();

        const tipo     = impTipo.value;
        const ancho    = parseFloat(impAncho.value) || 50;
        const alto     = parseFloat(impAlto.value) || 30;
        const cantidad = Math.max(1, parseInt(impCantidad.value) || 1);

        const pageStyle = document.createElement('style');
        pageStyle.id = 'inv-print-page-style';

        const area = document.createElement('div');
        area.id = 'inv-print-area';

        if (tipo === 'termica') {
            pageStyle.textContent = `@page { size: ${ancho}mm ${alto}mm; margin: 0; }`;
            for (let i = 0; i < cantidad; i++) {
                area.appendChild(crearEtiquetaNodo(loteActual, ancho, alto));
            }
        } else {
            const hoja    = impHoja.value;
            const margen  = parseFloat(impMargen.value) || 8;
            const tamHojaCss = hoja === 'A4' ? 'A4' : 'letter';
            pageStyle.textContent = `@page { size: ${tamHojaCss}; margin: ${margen}mm; }`;

            const { cols, porHoja } = calcularGrilla(ancho, alto, hoja, margen);

            let grid = null;
            for (let i = 0; i < cantidad; i++) {
                if (i % porHoja === 0) {
                    grid = document.createElement('div');
                    grid.className = 'inv-print-grid';
                    grid.style.gridTemplateColumns = `repeat(${cols}, ${ancho}mm)`;
                    grid.style.gridAutoRows = `${alto}mm`;
                    if (i > 0) grid.style.pageBreakBefore = 'always';
                    area.appendChild(grid);
                }
                grid.appendChild(crearEtiquetaNodo(loteActual, ancho, alto));
            }
        }

        document.head.appendChild(pageStyle);
        document.body.appendChild(area);

        window.onafterprint = limpiarAreaImpresion;
        setTimeout(() => window.print(), 50);
    }

    btnImprimir.addEventListener('click', imprimirEtiquetas);

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ══════════════════════════════════════════════════════════
    //  PÉRDIDAS
    // ══════════════════════════════════════════════════════════

    function getCookie(name) {
        let v = null;
        document.cookie.split(';').forEach(c => {
            const [k, val] = c.trim().split('=');
            if (k === name) v = decodeURIComponent(val);
        });
        return v;
    }

    // ── Registrar pérdida manual (rotura / otro) sobre un lote ──
    const modalPerdidaEl   = document.getElementById('modalPerdida');
    const modalPerdida      = new bootstrap.Modal(modalPerdidaEl);
    const perdidaLoteInfo   = document.getElementById('perdidaLoteInfo');
    const perdidaCantidad   = document.getElementById('perdidaCantidad');
    const perdidaMotivo     = document.getElementById('perdidaMotivo');
    const perdidaDetalle    = document.getElementById('perdidaDetalle');
    const perdidaMsg        = document.getElementById('perdidaMsg');
    const btnConfirmarPerdida = document.getElementById('btnConfirmarPerdida');

    let loteParaPerdida = null;

    function abrirModalPerdida(lote) {
        loteParaPerdida = lote;
        perdidaLoteInfo.textContent = `${lote.nombre} — lote ${lote.codigo} (disponible: ${KaiFormat.cantidad(lote.disponible)} ${lote.unidad || ''})`;
        perdidaCantidad.value = '';
        perdidaCantidad.max = lote.disponible;
        perdidaMotivo.value = 'rotura';
        perdidaDetalle.value = '';
        perdidaMsg.textContent = '';
        modalPerdida.show();
    }

    btnConfirmarPerdida.addEventListener('click', () => {
        if (!loteParaPerdida) return;
        const cantidad = parseFloat(perdidaCantidad.value);
        if (!cantidad || cantidad <= 0) {
            perdidaMsg.textContent = 'Ingresá una cantidad válida.';
            return;
        }
        if (cantidad > parseFloat(loteParaPerdida.disponible)) {
            perdidaMsg.textContent = `Ese lote solo tiene ${KaiFormat.cantidad(loteParaPerdida.disponible)} unidad(es) disponibles.`;
            return;
        }

        btnConfirmarPerdida.disabled = true;
        fetch(window.INVENTARIO_URLS.registrarPerdida, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({
                lote_pk: loteParaPerdida.pk,
                cantidad: cantidad,
                motivo: perdidaMotivo.value,
                motivo_detalle: perdidaDetalle.value.trim(),
            }),
        })
        .then(r => r.json())
        .then(data => {
            btnConfirmarPerdida.disabled = false;
            if (data.error) {
                perdidaMsg.textContent = data.error;
                return;
            }
            modalPerdida.hide();
            cargarLotes();
            cargarStats();
            cargarStatsPerdidas();
        })
        .catch(() => {
            btnConfirmarPerdida.disabled = false;
            perdidaMsg.textContent = 'Error de conexión.';
        });
    });

    // ── Historial de pérdidas ──
    const modalPerdidasEl = document.getElementById('modalPerdidas');
    const modalPerdidas = new bootstrap.Modal(modalPerdidasEl);
    const perdidasTbody = document.getElementById('perdidasTbody');
    const statPerdidasCard = document.getElementById('statPerdidasCard');

    if (statPerdidasCard) {
        statPerdidasCard.addEventListener('click', () => {
            modalPerdidas.show();
            cargarListadoPerdidas();
        });
    }

    function cargarListadoPerdidas() {
        perdidasTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">Cargando...</td></tr>`;
        fetch(window.INVENTARIO_URLS.listarPerdidas)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    perdidasTbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">${data.error}</td></tr>`;
                    return;
                }
                if (!data.results.length) {
                    perdidasTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No hay pérdidas registradas.</td></tr>`;
                    return;
                }
                perdidasTbody.innerHTML = data.results.map(p => `
                    <tr>
                        <td>${p.fecha}</td>
                        <td>
                            ${escapeHtml(p.producto_nombre)}
                            ${p.variante_desc ? `<div class="inv-variante-desc">${escapeHtml(p.variante_desc)}</div>` : ''}
                        </td>
                        <td><span class="inv-codigo-lote">${escapeHtml(p.lote_codigo)}</span></td>
                        <td>${KaiFormat.cantidad(p.cantidad)} <span class="inv-unidad-medida">${escapeHtml(p.unidad_medida || '')}</span></td>
                        <td>
                            ${p.motivo_label}${p.automatica ? ' <span class="badge-vencimiento sin-fecha">auto</span>' : ''}
                            ${p.motivo_detalle ? `<div class="inv-variante-desc">${escapeHtml(p.motivo_detalle)}</div>` : ''}
                        </td>
                        <td>$${KaiFormat.moneda(p.costo_total)}</td>
                        <td>${escapeHtml(p.registrado_por)}</td>
                    </tr>
                `).join('');
            })
            .catch(() => {
                perdidasTbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">Error al cargar pérdidas.</td></tr>`;
            });
    }

    // ══════════════════════════════════════════════════════════
    //  FRACCIONAMIENTO — armar un producto empaquetado desde otro
    //  a granel (ver fraccionar() en compras/models.py).
    // ══════════════════════════════════════════════════════════

    cargarStatsFraccionamientos();

    function cargarStatsFraccionamientos() {
        const statFrac = document.getElementById('statFraccionamientosCantidad');
        if (!statFrac || !window.INVENTARIO_URLS.listarFraccionamientos) return;

        fetch(window.INVENTARIO_URLS.listarFraccionamientos)
            .then(r => r.json())
            .then(data => {
                if (data.error) return;
                statFrac.textContent = data.results.length;
            })
            .catch(() => { statFrac.textContent = '—'; });
    }

    const modalFraccionarEl = document.getElementById('modalFraccionar');
    const modalFraccionar   = modalFraccionarEl ? new bootstrap.Modal(modalFraccionarEl) : null;
    const btnAbrirFraccionar = document.getElementById('btnAbrirFraccionar');

    const fracOrigenBuscar   = document.getElementById('fracOrigenBuscar');
    const fracOrigenPk       = document.getElementById('fracOrigenPk');
    const fracOrigenDropdown = document.getElementById('fracOrigenDropdown');
    const fracOrigenStock    = document.getElementById('fracOrigenStock');

    const fracDestinoBuscar   = document.getElementById('fracDestinoBuscar');
    const fracDestinoPk       = document.getElementById('fracDestinoPk');
    const fracDestinoDropdown = document.getElementById('fracDestinoDropdown');

    const fracCantidadOrigen     = document.getElementById('fracCantidadOrigen');
    const fracCantidadOrigenHint = document.getElementById('fracCantidadOrigenHint');
    const fracPaquetes           = document.getElementById('fracPaquetes');
    const fracPaquetesHint       = document.getElementById('fracPaquetesHint');
    const fracSugerencia         = document.getElementById('fracSugerencia');
    const fracNotas     = document.getElementById('fracNotas');
    const fracPreview   = document.getElementById('fracPreview');
    const fracMsg       = document.getElementById('fracMsg');
    const btnConfirmarFraccionar = document.getElementById('btnConfirmarFraccionar');

    // Datos del producto elegido (unidad, si permite fracción, contenido neto)
    // — se guardan al elegir de la lista, se usan para validar y sugerir.
    let fracOrigenDatos = null;
    let fracDestinoDatos = null;

    if (btnAbrirFraccionar && modalFraccionar) {
        btnAbrirFraccionar.addEventListener('click', () => {
            fracOrigenBuscar.value = '';
            fracOrigenPk.value = '';
            fracOrigenStock.textContent = '';
            fracOrigenDatos = null;
            fracDestinoBuscar.value = '';
            fracDestinoPk.value = '';
            fracDestinoDatos = null;
            fracCantidadOrigen.value = '';
            fracCantidadOrigenHint.textContent = '';
            fracPaquetes.value = '';
            fracPaquetesHint.textContent = '';
            fracSugerencia.style.display = 'none';
            fracNotas.value = '';
            fracMsg.textContent = '';
            fracPreview.style.display = 'none';
            modalFraccionar.show();
        });
    }

    function _buscarProductosFraccionar(query, excluirPk, dropdownEl, onElegir) {
        const params = new URLSearchParams();
        if (query) params.set('q', query);
        if (excluirPk) params.set('excluir', excluirPk);

        fetch(`${window.INVENTARIO_URLS.fraccionarBuscar}?${params.toString()}`)
            .then(r => r.json())
            .then(data => {
                if (data.error || !data.results.length) {
                    dropdownEl.innerHTML = `<div class="frac-dropdown-empty">Sin resultados.</div>`;
                    dropdownEl.classList.add('visible');
                    return;
                }
                dropdownEl.innerHTML = data.results.map(p => `
                    <div class="frac-dropdown-item" data-pk="${p.pk}" data-nombre="${escapeHtml(p.nombre)}"
                         data-stock="${p.stock_actual}" data-unidad="${escapeHtml(p.unidad_medida)}"
                         data-unidad-key="${escapeHtml(p.unidad_medida_key)}" data-permite-fraccion="${p.permite_fraccion}"
                         data-contenido-neto="${p.contenido_neto}"
                         data-unidades-por-presentacion="${p.unidades_por_presentacion}">
                        ${escapeHtml(p.nombre)}${p.marca ? ` <span class="frac-dropdown-marca">· ${escapeHtml(p.marca)}</span>` : ''}
                        <small>${escapeHtml(p.codigo)} · Stock: ${KaiFormat.cantidad(p.stock_actual)} ${escapeHtml(p.unidad_medida)}</small>
                    </div>
                `).join('');
                dropdownEl.classList.add('visible');
                dropdownEl.querySelectorAll('.frac-dropdown-item').forEach(item => {
                    item.addEventListener('click', () => {
                        onElegir(item.dataset);
                        dropdownEl.classList.remove('visible');
                    });
                });
            })
            .catch(() => {
                dropdownEl.innerHTML = `<div class="frac-dropdown-empty">Error al buscar.</div>`;
                dropdownEl.classList.add('visible');
            });
    }

    let fracOrigenDebounce = null;
    if (fracOrigenBuscar) {
        fracOrigenBuscar.addEventListener('input', () => {
            fracOrigenPk.value = '';
            fracOrigenDatos = null;
            fracOrigenStock.textContent = '';
            clearTimeout(fracOrigenDebounce);
            fracOrigenDebounce = setTimeout(() => {
                _buscarProductosFraccionar(fracOrigenBuscar.value.trim(), fracDestinoPk.value, fracOrigenDropdown, (ds) => {
                    fracOrigenBuscar.value = ds.nombre;
                    fracOrigenPk.value = ds.pk;
                    fracOrigenDatos = ds;
                    fracOrigenStock.textContent = `Stock disponible: ${KaiFormat.cantidad(ds.stock)} ${ds.unidad}`;
                    fracCantidadOrigenHint.textContent = ds.permiteFraccion === 'true'
                        ? `Se mide en ${ds.unidad} — admite decimales.`
                        : `Se cuenta en ${ds.unidad} — solo números enteros.`;
                    _sugerirCantidadOrigen();
                });
            }, 250);
        });
        fracOrigenBuscar.addEventListener('focus', () => {
            if (fracOrigenDropdown.innerHTML) fracOrigenDropdown.classList.add('visible');
        });
    }

    let fracDestinoDebounce = null;
    if (fracDestinoBuscar) {
        fracDestinoBuscar.addEventListener('input', () => {
            fracDestinoPk.value = '';
            fracDestinoDatos = null;
            clearTimeout(fracDestinoDebounce);
            fracDestinoDebounce = setTimeout(() => {
                _buscarProductosFraccionar(fracDestinoBuscar.value.trim(), fracOrigenPk.value, fracDestinoDropdown, (ds) => {
                    fracDestinoBuscar.value = ds.nombre;
                    fracDestinoPk.value = ds.pk;
                    fracDestinoDatos = ds;
                    fracPaquetesHint.textContent = ds.permiteFraccion === 'true'
                        ? `Se mide en ${ds.unidad} — admite decimales.`
                        : `Se cuenta en ${ds.unidad} — solo números enteros.`;
                    _sugerirCantidadOrigen();
                });
            }, 250);
        });
        fracDestinoBuscar.addEventListener('focus', () => {
            if (fracDestinoDropdown.innerHTML) fracDestinoDropdown.classList.add('visible');
        });
    }

    document.addEventListener('click', (e) => {
        if (fracOrigenDropdown && !fracOrigenDropdown.contains(e.target) && e.target !== fracOrigenBuscar) {
            fracOrigenDropdown.classList.remove('visible');
        }
        if (fracDestinoDropdown && !fracDestinoDropdown.contains(e.target) && e.target !== fracDestinoBuscar) {
            fracDestinoDropdown.classList.remove('visible');
        }
    });

    function _wireUsarSugerencia(inputEl, valor) {
        const link = document.getElementById('fracUsarSugerencia');
        if (link) {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                inputEl.value = valor;
                _actualizarPreviewFraccionar();
            });
        }
    }

    // Camino simple: si el producto de origen tiene cargado "¿trae piezas
    // sueltas adentro?", con ese solo dato alcanza para sugerir la otra
    // cantidad — no hace falta que el destino tenga nada cargado.
    // Si no está cargado, usamos el contenido neto de ambos como referencia
    // (menos directo, pero sirve de todos modos). El usuario puede pisar
    // cualquier sugerencia sin problema.
    function _sugerirCantidadOrigen() {
        fracSugerencia.style.display = 'none';
        if (!fracOrigenDatos) return;
        const porPresentacion = parseInt(fracOrigenDatos.unidadesPorPresentacion, 10);

        if (porPresentacion) {
            const origenActual = parseFloat(fracCantidadOrigen.value);
            const paquetesActual = parseFloat(fracPaquetes.value);

            if (origenActual > 0 && !paquetesActual) {
                const sugerido = Math.round(origenActual * porPresentacion * 1000) / 1000;
                fracSugerencia.style.display = 'block';
                fracSugerencia.innerHTML = `"${escapeHtml(fracOrigenDatos.nombre)}" trae ${porPresentacion} piezas por ${escapeHtml(fracOrigenDatos.unidad)} → con ${KaiFormat.cantidad(origenActual)} ${escapeHtml(fracOrigenDatos.unidad)} salen <strong>${KaiFormat.cantidad(sugerido)}</strong> piezas.
                    <a href="#" id="fracUsarSugerencia" style="text-decoration:underline;">Usar este valor</a>`;
                _wireUsarSugerencia(fracPaquetes, sugerido);
                return;
            }
            if (paquetesActual > 0 && !origenActual) {
                const sugerido = Math.round((paquetesActual / porPresentacion) * 1000) / 1000;
                fracSugerencia.style.display = 'block';
                fracSugerencia.innerHTML = `"${escapeHtml(fracOrigenDatos.nombre)}" trae ${porPresentacion} piezas por ${escapeHtml(fracOrigenDatos.unidad)} → para armar ${KaiFormat.cantidad(paquetesActual)} necesitás <strong>${KaiFormat.cantidad(sugerido)}</strong> ${escapeHtml(fracOrigenDatos.unidad)} de origen.
                    <a href="#" id="fracUsarSugerencia" style="text-decoration:underline;">Usar este valor</a>`;
                _wireUsarSugerencia(fracCantidadOrigen, sugerido);
                return;
            }
            return;
        }

        if (!fracDestinoDatos) return;
        const contenidoOrigen  = parseFloat(fracOrigenDatos.contenidoNeto);
        const contenidoDestino = parseFloat(fracDestinoDatos.contenidoNeto);
        const paquetes = parseFloat(fracPaquetes.value);
        if (!contenidoOrigen || !contenidoDestino || !paquetes) return;

        const sugerido = (contenidoDestino * paquetes) / contenidoOrigen;
        const sugeridoFmt = Math.round(sugerido * 1000) / 1000;
        fracSugerencia.style.display = 'block';
        fracSugerencia.innerHTML = `Según el contenido neto cargado, para armar ${KaiFormat.cantidad(paquetes)} necesitarías <strong>${KaiFormat.cantidad(sugeridoFmt)}</strong> ${escapeHtml(fracOrigenDatos.unidad)} de origen.
            <a href="#" id="fracUsarSugerencia" style="text-decoration:underline;">Usar este valor</a>`;
        _wireUsarSugerencia(fracCantidadOrigen, sugeridoFmt);
    }
    if (fracPaquetes) fracPaquetes.addEventListener('input', _sugerirCantidadOrigen);
    if (fracCantidadOrigen) fracCantidadOrigen.addEventListener('input', _sugerirCantidadOrigen);

    function _actualizarPreviewFraccionar() {
        const cantidadOrigen = parseFloat(fracCantidadOrigen.value);
        const paquetes = parseFloat(fracPaquetes.value);
        if (!cantidadOrigen || !paquetes || cantidadOrigen <= 0 || paquetes <= 0) {
            fracPreview.style.display = 'none';
            return;
        }
        fracPreview.style.display = 'block';
        fracPreview.innerHTML = `Vas a descontar <strong>${KaiFormat.cantidad(cantidadOrigen)}</strong> de "${escapeHtml(fracOrigenBuscar.value || '—')}" y vas a armar <strong>${KaiFormat.cantidad(paquetes)}</strong> unidad(es) de "${escapeHtml(fracDestinoBuscar.value || '—')}".`;
    }
    if (fracCantidadOrigen) fracCantidadOrigen.addEventListener('input', _actualizarPreviewFraccionar);
    if (fracPaquetes) fracPaquetes.addEventListener('input', _actualizarPreviewFraccionar);

    function _esEntero(valor) {
        return Math.abs(valor - Math.round(valor)) < 1e-9;
    }

    if (btnConfirmarFraccionar) {
        btnConfirmarFraccionar.addEventListener('click', () => {
            fracMsg.textContent = '';

            if (!fracOrigenPk.value) {
                fracMsg.textContent = 'Elegí el producto de origen de la lista.';
                return;
            }
            if (!fracDestinoPk.value) {
                fracMsg.textContent = 'Elegí el producto de destino de la lista.';
                return;
            }
            if (fracOrigenPk.value === fracDestinoPk.value) {
                fracMsg.textContent = 'El origen y el destino no pueden ser el mismo producto.';
                return;
            }
            const cantidadOrigen = parseFloat(fracCantidadOrigen.value);
            const paquetes = parseFloat(fracPaquetes.value);
            if (!cantidadOrigen || cantidadOrigen <= 0) {
                fracMsg.textContent = 'Ingresá cuánto vas a usar del origen.';
                return;
            }
            if (!paquetes || paquetes <= 0) {
                fracMsg.textContent = 'Ingresá cuántas unidades vas a armar.';
                return;
            }
            if (fracOrigenDatos && fracOrigenDatos.permiteFraccion === 'false' && !_esEntero(cantidadOrigen)) {
                fracMsg.textContent = `"${fracOrigenBuscar.value}" se cuenta en ${fracOrigenDatos.unidad} — ingresá un número entero.`;
                return;
            }
            if (fracDestinoDatos && fracDestinoDatos.permiteFraccion === 'false' && !_esEntero(paquetes)) {
                fracMsg.textContent = `"${fracDestinoBuscar.value}" se cuenta en ${fracDestinoDatos.unidad} — ingresá un número entero.`;
                return;
            }

            btnConfirmarFraccionar.disabled = true;
            fetch(window.INVENTARIO_URLS.fraccionar, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    producto_origen_pk: fracOrigenPk.value,
                    producto_destino_pk: fracDestinoPk.value,
                    cantidad_origen: cantidadOrigen,
                    cantidad_paquetes: paquetes,
                    notas: fracNotas.value.trim(),
                }),
            })
            .then(r => r.json())
            .then(data => {
                btnConfirmarFraccionar.disabled = false;
                if (data.error) {
                    fracMsg.textContent = data.error;
                    return;
                }
                modalFraccionar.hide();
                cargarLotes();
                cargarStats();
                cargarStatsFraccionamientos();
            })
            .catch(() => {
                btnConfirmarFraccionar.disabled = false;
                fracMsg.textContent = 'Error de conexión.';
            });
        });
    }

    // ── Historial de fraccionamientos ──
    const modalFraccionamientosEl = document.getElementById('modalFraccionamientos');
    const modalFraccionamientos   = modalFraccionamientosEl ? new bootstrap.Modal(modalFraccionamientosEl) : null;
    const fraccionamientosTbody   = document.getElementById('fraccionamientosTbody');
    const statFraccionamientosCard = document.getElementById('statFraccionamientosCard');

    if (statFraccionamientosCard && modalFraccionamientos) {
        statFraccionamientosCard.addEventListener('click', () => {
            modalFraccionamientos.show();
            cargarListadoFraccionamientos();
        });
    }

    function cargarListadoFraccionamientos() {
        fraccionamientosTbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">Cargando...</td></tr>`;
        fetch(window.INVENTARIO_URLS.listarFraccionamientos)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    fraccionamientosTbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger py-4">${data.error}</td></tr>`;
                    return;
                }
                if (!data.results.length) {
                    fraccionamientosTbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">Todavía no hiciste ningún fraccionamiento.</td></tr>`;
                    return;
                }
                fraccionamientosTbody.innerHTML = data.results.map(f => `
                    <tr>
                        <td>${f.fecha}</td>
                        <td>${escapeHtml(f.producto_origen)} <span class="inv-unidad-medida">(${KaiFormat.cantidad(f.cantidad_total_origen)} ${escapeHtml(f.unidad_origen)})</span></td>
                        <td>${escapeHtml(f.producto_destino)} <span class="inv-unidad-medida">(${KaiFormat.cantidad(f.cantidad_paquetes)} ${escapeHtml(f.unidad_destino)})</span></td>
                        <td>$${KaiFormat.moneda(f.costo_unitario_calculado)}</td>
                        <td>${escapeHtml(f.creado_por)}</td>
                    </tr>
                `).join('');
            })
            .catch(() => {
                fraccionamientosTbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger py-4">Error al cargar fraccionamientos.</td></tr>`;
            });
    }
});