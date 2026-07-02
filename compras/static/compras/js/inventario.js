document.addEventListener('DOMContentLoaded', function () {

    const tbody       = document.getElementById('inventarioTbody');
    const inputBuscar  = document.getElementById('inventarioBuscar');
    const filtrosWrap  = document.getElementById('inventarioFiltros');

    let filtroActual   = '';
    let debounceTimer   = null;

    // ── Carga inicial ──
    cargarLotes();
    cargarStats();

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
                    ${l.cantidad_actual} / ${l.cantidad_inicial}
                    <div class="inv-barra-restante">
                        <div class="inv-barra-restante-fill" style="width:${l.porcentaje_restante}%"></div>
                    </div>
                </td>
                <td>$${parseFloat(l.costo_unitario).toFixed(2)}</td>
                <td>${badgeVencimiento(l)}</td>
                <td>${l.fecha_compra}</td>
                <td>${escapeHtml(l.proveedor || '—')}</td>
                <td>
                    <button class="btn-ver-codigo" data-lote='${JSON.stringify(l).replace(/'/g, "&#39;")}'>
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
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.btn-ver-codigo').forEach(btn => {
            btn.addEventListener('click', () => {
                const lote = JSON.parse(btn.dataset.lote);
                abrirModalCodigo(lote);
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
        detalles.push(`Costo: $${parseFloat(lote.costo_unitario).toFixed(2)}`);
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
});