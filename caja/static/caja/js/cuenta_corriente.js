/* Cuenta corriente — vista por cliente del saldo consolidado + cobro FIFO.
 * Server-rendered shell (cuenta_corriente.html); esto llena todo por AJAX.
 * Firma del diseño: el preview de imputación en vivo dentro del modal de
 * cobro — muestra en texto claro qué deudas cancela el pago y qué queda. */
document.addEventListener('DOMContentLoaded', function () {
    if (!window.CC) return;
    const { urls, today, puedeCobrar, puedeAnular, puedeEditar } = window.CC;

    const CUENTAS = JSON.parse(document.getElementById('cc-cuentas-data')?.textContent || '[]');

    // ── helpers ──────────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);
    const csrf = () => (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    const num = (v) => parseFloat(v || 0) || 0;

    function fmt(v, moneda) {
        const n = num(v).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return `$ ${n}${moneda && moneda !== 'ARS' ? ' ' + moneda : ''}`;
    }
    function fmtFecha(iso) {
        if (!iso) return '—';
        const [y, m, d] = iso.slice(0, 10).split('-');
        return `${d}/${m}/${y}`;
    }
    function diasDesde(iso) {
        if (!iso) return null;
        const ms = Date.now() - new Date(iso + 'T00:00:00').getTime();
        return Math.max(0, Math.floor(ms / 86400000));
    }
    function textoAntiguedad(iso) {
        const d = diasDesde(iso);
        if (d === null) return '';
        if (d === 0) return 'desde hoy';
        if (d < 31) return `hace ${d} día${d === 1 ? '' : 's'}`;
        const meses = Math.round(d / 30);
        return `hace ${meses} mes${meses === 1 ? '' : 'es'}`;
    }
    function esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }
    async function postJSON(url, body) {
        const r = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify(body || {}),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || 'No se pudo completar la operación.');
        return data;
    }
    const toast = (m, t) => (window.KaiToast ? KaiToast.show(m, t || 'info') : console.log(m));
    async function confirmar(msg, opts) {
        if (window.KaiConfirm) return KaiConfirm(msg, opts);
        return window.confirm(msg);
    }

    // ── estado ───────────────────────────────────────────────────────
    let filas = [];          // último listado (para orden/print sin refetch)
    let marcada = -1;        // índice del cliente marcado por teclado
    let clienteActual = null;
    let resumenActual = null;

    // ══════════════════════════════════════════════════════════════
    //  LISTA
    // ══════════════════════════════════════════════════════════════
    const lista = $('ccLista');
    const buscar = $('ccBuscar');
    const buscadorWrap = $('ccBuscadorWrap');
    const orden = $('ccOrden');

    function ordenar(arr) {
        const modo = orden.value;
        const copia = [...arr];
        if (modo === 'nombre') {
            copia.sort((a, b) => a.cliente_nombre.localeCompare(b.cliente_nombre, 'es'));
        } else if (modo === 'antiguedad') {
            copia.sort((a, b) => a.deuda_mas_vieja.localeCompare(b.deuda_mas_vieja));
        } else if (modo === 'mora') {
            copia.sort((a, b) => (b.en_mora - a.en_mora) || (num(b.saldo_total) - num(a.saldo_total)));
        } else {
            copia.sort((a, b) => num(b.saldo_total) - num(a.saldo_total));
        }
        return copia;
    }

    function skeleton() {
        lista.innerHTML = Array.from({ length: 5 }, () => '<div class="cc-skeleton"></div>').join('');
    }

    async function cargarLista(mantenerMarca) {
        const q = buscar.value.trim();
        buscadorWrap.classList.toggle('has-value', q.length > 0);
        if (!filas.length) skeleton();
        let data;
        try {
            data = await (await fetch(`${urls.listar}?q=${encodeURIComponent(q)}`)).json();
        } catch (e) {
            lista.innerHTML = `<div class="cc-lista-vacia"><strong>No se pudo cargar</strong>Revisá la conexión e intentá de nuevo.</div>`;
            return;
        }
        filas = data.results || [];
        $('ccSaldoTotal').textContent = fmt(data.saldo_total);
        $('ccClientesConDeuda').textContent = data.clientes_con_deuda;

        const enMora = filas.filter((f) => f.en_mora).length;
        $('ccMoraStat').hidden = enMora === 0;
        if (enMora) $('ccMoraCount').textContent = enMora;

        renderLista(mantenerMarca);
    }

    function renderLista(mantenerMarca) {
        if (!mantenerMarca) marcada = -1;
        if (!filas.length) {
            const q = buscar.value.trim();
            lista.innerHTML = q
                ? `<div class="cc-lista-vacia"><strong>Sin resultados</strong>Ningún cliente coincide con «${esc(q)}».</div>`
                : `<div class="cc-lista-vacia"><strong>Nadie debe nada</strong>Cuando hagas una venta a crédito o cargues una deuda, el cliente aparece acá.</div>`;
            return;
        }
        const arr = ordenar(filas);
        // reindexar marcada según el nuevo orden (por pk)
        lista.innerHTML = arr.map((c, i) => `
            <div class="cc-fila ${c.en_mora ? 'cc-fila--mora' : ''} ${i === marcada ? 'is-marcada' : ''}"
                 role="listitem" tabindex="0" data-cliente="${c.cliente_pk}" data-idx="${i}">
                <div class="cc-fila-main">
                    <div class="cc-fila-nombre">${esc(c.cliente_nombre)}</div>
                    <div class="cc-fila-sub">
                        ${c.en_mora ? '<span class="cc-fila-mora-tag">En mora</span>' : ''}
                        <span>${c.cant_deudas} deuda${c.cant_deudas === 1 ? '' : 's'}</span>
                        <span>debe ${textoAntiguedad(c.deuda_mas_vieja)}</span>
                        ${c.doc ? `<span>${esc(c.doc)}</span>` : ''}
                    </div>
                </div>
                <div class="cc-fila-right">
                    <span class="cc-fila-saldo">${fmt(c.saldo_total)}</span>
                    ${puedeCobrar ? `<button type="button" class="cc-fila-cobrar" data-cobrar="${c.cliente_pk}">Cobrar</button>` : ''}
                </div>
            </div>`).join('');
        ordenActual = arr;
    }
    let ordenActual = [];

    let debTimer;
    buscar.addEventListener('input', () => {
        clearTimeout(debTimer);
        debTimer = setTimeout(() => cargarLista(false), 220);
    });
    $('ccBuscarClear').addEventListener('click', () => {
        buscar.value = '';
        buscar.focus();
        cargarLista(false);
    });
    orden.addEventListener('change', () => renderLista(false));

    lista.addEventListener('click', (e) => {
        const cobrarBtn = e.target.closest('[data-cobrar]');
        if (cobrarBtn) { e.stopPropagation(); abrirCobrarDesdeLista(cobrarBtn.dataset.cobrar); return; }
        const fila = e.target.closest('.cc-fila');
        if (fila) abrirCliente(fila.dataset.cliente);
    });
    lista.addEventListener('keydown', (e) => {
        const fila = e.target.closest('.cc-fila');
        if (!fila) return;
        if (e.key === 'Enter') { abrirCliente(fila.dataset.cliente); }
        else if (e.key.toLowerCase() === 'c' && puedeCobrar) { e.preventDefault(); abrirCobrarDesdeLista(fila.dataset.cliente); }
    });

    // ══════════════════════════════════════════════════════════════
    //  MODAL DETALLE CLIENTE
    // ══════════════════════════════════════════════════════════════
    const modalCliente = $('ccModalCliente');

    async function abrirCliente(pk) {
        try {
            const data = await (await fetch(urls.detalleCliente.replace('/0/', `/${pk}/`))).json();
            resumenActual = data.resumen;
            clienteActual = { pk, nombre: resumenActual.cliente_nombre };
        } catch (e) {
            toast('No se pudo abrir el cliente. Probá de nuevo.', 'danger');
            return;
        }
        renderDetalle();
        activarTab('deudas');
        abrirModal(modalCliente);
        modalCliente.querySelector('.cc-det-tab').focus();
    }
    function cerrarCliente() {
        cerrarModal(modalCliente);
        clienteActual = null;
        resumenActual = null;
    }
    modalCliente.querySelectorAll('[data-cc-cerrar]').forEach((el) => el.addEventListener('click', cerrarCliente));

    function renderDetalle() {
        const r = resumenActual;
        const saldo = num(r.saldo_total);
        $('ccClienteTitulo').textContent = r.cliente_nombre;
        $('ccDetSaldo').textContent = fmt(r.saldo_total);
        $('ccSaldoGrande').classList.toggle('cc-saldo-grande-cero', saldo <= 0);
        $('ccLinkPerfil').href = urls.clientePerfilBase + r.cliente_pk + '/';
        const btnCobrar = $('ccBtnCobrar');
        if (btnCobrar) btnCobrar.disabled = saldo <= 0;

        // contadores en las tabs
        setTabCount('deudas', r.deudas.length);
        setTabCount('cobros', r.cobros.filter((c) => c.estado === 'activo').length);

        // ── Deudas (orden FIFO visible) ──
        $('ccPanelDeudas').innerHTML = r.deudas.length ? `
            <p class="cc-deudas-hint">De la más vieja a la más nueva — así se van cobrando.</p>
            ${r.deudas.map((d, i) => {
                const esFija = d.modo_cuotas === 'fijas';
                const puedeConv = esFija && puedeEditar && num(d.saldo_pendiente) > 0;
                return `
                <div class="cc-deuda">
                    <span class="cc-deuda-orden">${i + 1}</span>
                    <div class="cc-deuda-top">
                        <span class="cc-deuda-titulo">${esc(d.titulo)}</span>
                        <span class="cc-deuda-saldo">${fmt(d.saldo_pendiente, d.moneda)}</span>
                    </div>
                    <div class="cc-deuda-meta">
                        <span>${esFija
                            ? `<span class="cc-deuda-fija-tag">Cuotas fijas</span> · ${d.cuotas_cobradas}/${d.cantidad_cuotas || '—'} cobradas`
                            : 'Saldo libre'}</span>
                        <span>de ${fmt(d.monto_total, d.moneda)}</span>
                        <span>desde ${fmtFecha(d.fecha_inicio)}</span>
                    </div>
                    ${puedeConv ? `<button type="button" class="cc-deuda-conv" data-conv="${d.pk}">Pasar a saldo libre</button>` : ''}
                </div>`;
            }).join('')}` : '<div class="cc-vacio">Este cliente no tiene deudas activas.</div>';

        // ── Movimientos ──
        // El signo se deduce de cómo se movió el saldo corrido (no del
        // texto): así "Pago cuota…" hecho fuera de la cascada también
        // sale como resta.
        let saldoPrev = 0;
        const filasMov = r.historial.map((f) => {
            const saldoFila = num(f.saldo);
            const esPago = saldoFila - saldoPrev < -0.005;
            saldoPrev = saldoFila;
            return `<tr class="${esPago ? 'cc-mov-cobro' : 'cc-mov-cargo'}">
                <td>${fmtFecha(f.fecha)}</td><td>${esc(f.descripcion)}</td>
                <td class="cc-num">${esPago ? '−' : '+'} ${fmt(f.monto)}</td>
                <td class="cc-num">${fmt(f.saldo)}</td></tr>`;
        }).join('');
        $('ccPanelMovimientos').innerHTML = r.historial.length ? `
            <div class="cc-mov-head">
                <p class="cc-deudas-hint">Cada venta suma y cada pago resta. El saldo es lo que debía después de ese movimiento.</p>
                <button type="button" class="cc-mov-imprimir" id="ccBtnMovimientos">Imprimir</button>
            </div>
            <div class="cc-tabla-wrap">
            <table class="cc-tabla">
                <thead><tr><th>Fecha</th><th>Detalle</th>
                    <th class="cc-num">Monto</th><th class="cc-num">Saldo</th></tr></thead>
                <tbody>${filasMov}</tbody>
            </table></div>` : '<div class="cc-vacio">Todavía no hay movimientos.</div>';

        // ── Cobros ──
        $('ccPanelCobros').innerHTML = r.cobros.length ? r.cobros.map((c) => `
            <div class="cc-cobro ${c.estado === 'anulado' ? 'is-anulado' : ''}">
                <div class="cc-cobro-top">
                    <span>${fmtFecha(c.fecha)} · <span class="cc-cobro-monto">${fmt(c.monto, c.moneda)}</span>
                        ${c.cuenta_nombre ? '· ' + esc(c.cuenta_nombre) : ''}
                        ${c.estado === 'anulado' ? '<span class="cc-badge-anul">ANULADO</span>' : ''}</span>
                    <span class="cc-cobro-acciones">
                        <button type="button" class="cc-cobro-recibo" data-recibo="${c.pk}">Recibo</button>
                        ${(c.estado === 'activo' && puedeAnular)
                            ? `<button type="button" class="cc-cobro-anular" data-anular="${c.pk}">Anular</button>` : ''}
                    </span>
                </div>
                <ul class="cc-cobro-imp">${c.imputaciones.map((i) => `
                    <li><span>${esc(i.titulo)}</span>
                        <span>${fmt(i.monto)} ${i.cancelo ? '<span class="cc-imp-ok">saldada</span>' : ''}</span></li>`).join('')}
                </ul>
                ${c.numero_comprobante ? `<div class="cc-cobro-extra">Comprob.: ${esc(c.numero_comprobante)}</div>` : ''}
                ${c.notas ? `<div class="cc-cobro-extra">${esc(c.notas)}</div>` : ''}
            </div>`).join('') : '<div class="cc-vacio">Todavía no registraste cobros por acá.</div>';

        // ── Pagaré ──
        const p = r.pagare;
        $('ccPanelPagare').innerHTML = `
            <p class="cc-pagare-info">Pagaré en blanco que cubre <strong>el total</strong> de la cuenta del cliente.
                Se carga desde la ficha del cliente.</p>
            <div class="cc-pagare-datos">
                <div><span class="cc-pagare-label">N°</span> ${p.numero ? esc(p.numero) : '—'}</div>
                ${p.foto_url ? `<a href="${esc(p.foto_url)}" target="_blank" rel="noopener">
                    <img src="${esc(p.foto_url)}" alt="Pagaré firmado" class="cc-pagare-foto"></a>`
                    : '<div class="cc-pagare-label">Sin foto cargada</div>'}
            </div>`;
    }

    function setTabCount(name, n) {
        const tab = modalCliente.querySelector(`[data-cc-tab="${name}"]`);
        if (!tab) return;
        const base = { deudas: 'Deudas', cobros: 'Cobros' }[name] || name;
        tab.innerHTML = `${base}${n ? ` <span class="cc-tab-count">${n}</span>` : ''}`;
    }

    function activarTab(name) {
        modalCliente.querySelectorAll('[data-cc-tab]').forEach((t) => {
            const activa = t.dataset.ccTab === name;
            t.classList.toggle('is-active', activa);
            t.setAttribute('aria-selected', String(activa));
            t.tabIndex = activa ? 0 : -1;
        });
        modalCliente.querySelectorAll('[data-cc-panel]').forEach((pn) => {
            const activo = pn.dataset.ccPanel === name;
            pn.classList.toggle('is-active', activo);
            pn.hidden = !activo;
        });
    }
    modalCliente.querySelectorAll('[data-cc-tab]').forEach((tab) => {
        tab.addEventListener('click', () => activarTab(tab.dataset.ccTab));
    });
    modalCliente.querySelector('.cc-det-tabs').addEventListener('keydown', (e) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const tabs = [...modalCliente.querySelectorAll('[data-cc-tab]')];
        const actual = Math.max(0, tabs.indexOf(document.activeElement));
        const destino = e.key === 'Home' ? 0
            : e.key === 'End' ? tabs.length - 1
                : (actual + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        activarTab(tabs[destino].dataset.ccTab);
        tabs[destino].focus();
    });

    // Delegación: convertir deuda / anular cobro / imprimir recibo
    $('ccClienteBody').addEventListener('click', async (e) => {
        const conv = e.target.closest('[data-conv]');
        const anular = e.target.closest('[data-anular]');
        const recibo = e.target.closest('[data-recibo]');

        if (e.target.closest('#ccBtnMovimientos') && typeof ccMovimientosImprimir === 'function') {
            abrirSelectorImpresion({
                titulo: 'Imprimir movimientos',
                descripcion: `Extracto de movimientos de ${resumenActual.cliente_nombre}.`,
                alElegir: (formato) => ccMovimientosImprimir(
                    resumenActual.cliente_nombre, resumenActual.historial, formato),
            });
            return;
        }
        if (recibo && typeof ccReciboImprimir === 'function') {
            const cobro = (resumenActual.cobros || []).find((c) => String(c.pk) === recibo.dataset.recibo);
            if (cobro) {
                const win = window.open('', '_blank', 'width=760,height=920');
                ccReciboImprimir(cobro, resumenActual.cliente_nombre, cobro.saldo_posterior, win);
            }
            return;
        }
        if (conv) {
            const ok = await confirmar(
                'Pasar esta deuda a saldo libre descarta el plan de cuotas pendiente (lo cobrado queda). '
                + 'Después vas a poder cobrar cualquier monto contra ella. ¿Seguir?');
            if (!ok) return;
            try {
                await postJSON(urls.convertirLibre.replace('/0/', `/${conv.dataset.conv}/`), {});
                toast('Deuda pasada a saldo libre.', 'success');
                await abrirCliente(clienteActual.pk);
            } catch (err) { toast(err.message, 'danger'); }
            return;
        }
        if (anular) {
            const ok = await confirmar(
                'Anular este cobro revierte todas sus imputaciones: las deudas vuelven a deber lo que se les descontó. ¿Seguir?',
                { danger: true, confirmText: 'Anular' });
            if (!ok) return;
            try {
                const data = await postJSON(urls.anularCobro.replace('/0/', `/${anular.dataset.anular}/`), {});
                resumenActual = data.resumen;
                renderDetalle();
                cargarLista(true);
                toast('Cobro anulado.', 'success');
            } catch (err) { toast(err.message, 'danger'); }
        }
    });

    function abrirSelectorImpresion(config) {
        if (window.KaiPrintSelector && window.KaiPrintSelector.abrir(config)) return;
        // Compatibilidad defensiva si el recurso del selector no llegara a
        // cargar: el documento sigue disponible en A4.
        config.alElegir('a4');
    }

    // Estado de cuenta imprimible (reusa cliente_deuda_total_imprimir.js)
    $('ccBtnEstadoCuenta').addEventListener('click', () => {
        if (!resumenActual || typeof clienteDeudaTotalImprimir !== 'function') return;
        abrirSelectorImpresion({
            titulo: 'Imprimir deuda actual',
            descripcion: `Estado de cuenta de ${resumenActual.cliente_nombre}.`,
            alElegir: (formato) => clienteDeudaTotalImprimir(
                { pk: resumenActual.cliente_pk, nombre: resumenActual.cliente_nombre },
                resumenActual.deudas, formato),
        });
    });

    // ══════════════════════════════════════════════════════════════
    //  MODAL COBRAR  (+ preview de imputación en vivo)
    // ══════════════════════════════════════════════════════════════
    const modalCobrar = $('ccModalCobrar');
    const inMonto = $('ccCobrarMonto');
    const selCuenta = $('ccCobrarCuenta');
    const inFecha = $('ccCobrarFecha');
    const msgCobrar = $('ccCobrarMsg');
    const preview = $('ccPreview');
    let cobrarCtx = null;   // { pk, nombre, saldoTotal, deudas[] }

    async function abrirCobrarDesdeLista(pk) {
        try {
            const data = await (await fetch(urls.detalleCliente.replace('/0/', `/${pk}/`))).json();
            prepararCobro(data.resumen);
        } catch (e) { toast('No se pudo abrir el cobro. Probá de nuevo.', 'danger'); }
    }
    function abrirCobrarDesdeDetalle() {
        if (resumenActual) prepararCobro(resumenActual);
    }

    function prepararCobro(resumen) {
        cobrarCtx = {
            pk: resumen.cliente_pk,
            nombre: resumen.cliente_nombre,
            saldoTotal: num(resumen.saldo_total),
            deudas: [...resumen.deudas].sort((a, b) => a.fecha_inicio.localeCompare(b.fecha_inicio)),
        };
        if (cobrarCtx.saldoTotal <= 0) { toast('Este cliente no tiene saldo para cobrar.', 'warning'); return; }

        $('ccCobrarCliente').textContent = cobrarCtx.nombre;
        $('ccCobrarSaldo').innerHTML = `Debe <strong>${fmt(cobrarCtx.saldoTotal)}</strong>`;
        inMonto.value = '';
        inMonto.max = cobrarCtx.saldoTotal;
        $('ccCobrarComprobante').value = '';
        $('ccCobrarNotas').value = '';
        inFecha.value = today;
        msgCobrar.textContent = '';

        const ars = CUENTAS.filter((c) => c.moneda === 'ARS');
        selCuenta.innerHTML = '<option value="">— Elegí una cuenta —</option>' +
            ars.map((c) => `<option value="${c.pk}">${esc(c.nombre)}${c.titular ? ' · ' + esc(c.titular) : ''}</option>`).join('');
        const pref = ars.find((c) => c.preferida);
        if (pref) selCuenta.value = String(pref.pk);

        renderPreview();
        abrirModal(modalCobrar);
        setTimeout(() => inMonto.focus(), 50);
    }
    function cerrarCobrar() { cerrarModal(modalCobrar); cobrarCtx = null; }
    modalCobrar.querySelectorAll('[data-cc-cobrar-cerrar]').forEach((el) => el.addEventListener('click', cerrarCobrar));
    $('ccBtnCobrar')?.addEventListener('click', abrirCobrarDesdeDetalle);
    $('ccCobrarTodo').addEventListener('click', () => {
        if (cobrarCtx) { inMonto.value = cobrarCtx.saldoTotal.toFixed(2); renderPreview(); }
    });
    inMonto.addEventListener('input', renderPreview);

    // Cascada FIFO en el cliente — espejo exacto de
    // registrar_cobro_cuenta_corriente (caja/models.py). Solo para el
    // preview: el server vuelve a calcular y es la fuente de verdad.
    function simularCascada(deudas, monto) {
        let restante = monto;
        const lineas = [];
        let bloqueo = null;
        for (const d of deudas) {
            const saldo = num(d.saldo_pendiente);
            if (saldo <= 0.001) continue;
            if (restante <= 0.001) break;

            if (d.modo_cuotas === 'libre') {
                const aplicar = Math.min(restante, saldo);
                lineas.push({ titulo: d.titulo, monto: aplicar, cancela: aplicar >= saldo - 0.001 });
                restante -= aplicar;
            } else {
                const pend = (d.cuotas || [])
                    .filter((c) => c.estado === 'pendiente')
                    .sort((a, b) => a.numero - b.numero);
                let aqui = 0;
                for (const c of pend) {
                    const cm = num(c.monto);
                    if (restante < cm - 0.001) break;
                    aqui += cm;
                    restante -= cm;
                }
                if (aqui > 0) lineas.push({ titulo: d.titulo, monto: aqui, cancela: aqui >= saldo - 0.001, fija: true });
                if (restante > 0.01 && aqui < saldo - 0.001) {
                    const prox = pend.find((c) => restante < num(c.monto));
                    bloqueo = { titulo: d.titulo, proxima: prox ? num(prox.monto) : saldo };
                    break;
                }
            }
        }
        return { lineas, restante, bloqueo, imputado: monto - restante };
    }

    function renderPreview() {
        if (!cobrarCtx) return;
        const monto = num(inMonto.value);
        const btn = $('ccCobrarConfirmar');

        if (!monto || monto <= 0) {
            preview.innerHTML = '<span class="cc-preview--vacio">Escribí un monto y te muestro a qué deudas va.</span>';
            btn.disabled = true;
            return;
        }
        if (monto - cobrarCtx.saldoTotal > 0.01) {
            preview.innerHTML = `<div class="cc-preview-alerta">El monto ($ ${monto.toLocaleString('es-AR')}) es mayor a lo que debe (${fmt(cobrarCtx.saldoTotal)}).</div>`;
            btn.disabled = true;
            return;
        }

        const { lineas, bloqueo, imputado } = simularCascada(cobrarCtx.deudas, monto);
        const queda = cobrarCtx.saldoTotal - imputado;

        let html = '<div class="cc-preview-titulo">Se va a imputar así</div>';
        html += lineas.map((l) => `
            <div class="cc-preview-linea ${l.cancela ? 'cc-preview-linea--cancela' : 'cc-preview-linea--parcial'}">
                <span>${l.cancela ? '<span class="cc-preview-check">✓</span>' : ''}${esc(l.titulo)}${l.cancela ? ' — se salda' : ' — abona en parte'}</span>
                <span>${fmt(l.monto)}</span>
            </div>`).join('');
        html += `<div class="cc-preview-total"><span>Queda debiendo</span><span>${fmt(queda)}</span></div>`;

        if (bloqueo) {
            html += `<div class="cc-preview-alerta">
                No se puede imputar todo: <strong>${esc(bloqueo.titulo)}</strong> es de cuotas fijas y su próxima
                cuota es de ${fmt(bloqueo.proxima)} (no se paga por la mitad). Cobrá ${fmt(imputado)},
                o pasá esa deuda a saldo libre desde su detalle.
            </div>`;
        }
        preview.innerHTML = html;
        btn.disabled = !!bloqueo;
    }

    $('ccCobrarConfirmar').addEventListener('click', async () => {
        msgCobrar.textContent = '';
        const monto = num(inMonto.value);
        if (!monto || monto <= 0) { msgCobrar.textContent = 'Poné un monto.'; return; }
        if (!selCuenta.value) { msgCobrar.textContent = 'Elegí a qué cuenta entra.'; selCuenta.focus(); return; }

        const btn = $('ccCobrarConfirmar');
        btn.disabled = true;
        try {
            const data = await postJSON(urls.cobrar.replace('/0/', `/${cobrarCtx.pk}/`), {
                monto,
                cuenta_pk: selCuenta.value,
                fecha: inFecha.value || null,
                numero_comprobante: $('ccCobrarComprobante').value.trim(),
                notas: $('ccCobrarNotas').value.trim(),
            });
            const eraDetalle = !modalCliente.hidden;
            resumenActual = data.resumen;
            cerrarCobrar();
            cargarLista(true);
            if (eraDetalle) {
                renderDetalle();
                activarTab('cobros');   // el cobro recién hecho, con su botón "Recibo"
            }
            toast('Cobro registrado.', 'success');
        } catch (err) {
            btn.disabled = false;
            msgCobrar.textContent = err.message;
        }
    });

    // ══════════════════════════════════════════════════════════════
    //  LISTADO DE DEUDORES (imprimible)
    // ══════════════════════════════════════════════════════════════
    $('ccBtnListado').addEventListener('click', () => {
        if (!filas.length) { toast('No hay clientes con deuda para listar.', 'warning'); return; }
        const arr = ordenar(filas);
        const total = arr.reduce((s, f) => s + num(f.saldo_total), 0);
        const rows = arr.map((f) => `
            <tr>
                <td>${esc(f.cliente_nombre)}${f.en_mora ? ' <span style="color:#A84B08;font-weight:700">(en mora)</span>' : ''}</td>
                <td>${esc(f.doc || '')}</td>
                <td style="text-align:center">${f.cant_deudas}</td>
                <td>${fmtFecha(f.deuda_mas_vieja)}</td>
                <td style="text-align:right;white-space:nowrap">${fmt(f.saldo_total)}</td>
            </tr>`).join('');
        const html = `<!doctype html><html lang="es"><head><meta charset="utf-8">
        <title>Deudores — ${new Date().toLocaleDateString('es-AR')}</title>
        <style>
            body{font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;padding:32px;max-width:760px;margin:0 auto}
            h1{font-size:1.25rem;margin:0 0 4px}
            .sub{color:#555;font-size:.875rem;margin:0 0 18px}
            .tot{display:flex;justify-content:space-between;background:#FFF0E6;border:1px solid #C9500C;border-radius:8px;padding:12px 16px;margin-bottom:20px;font-size:.95rem}
            .tot strong{font-size:1.3rem;color:#A63D06}
            table{width:100%;border-collapse:collapse;font-size:.82rem}
            th,td{border:1px solid #ddd;padding:6px 8px;text-align:left}
            th{background:#f7f7f7}
            .foot{margin-top:20px;font-size:.72rem;color:#888}
            @media print{body{padding:0}}
        </style></head><body>
        <h1>Clientes con deuda</h1>
        <p class="sub">Al ${new Date().toLocaleDateString('es-AR')} — ${arr.length} cliente${arr.length === 1 ? '' : 's'}</p>
        <div class="tot"><span>Total a cobrar</span><strong>${fmt(total)}</strong></div>
        <table><thead><tr><th>Cliente</th><th>Doc.</th><th style="text-align:center">Deudas</th><th>Debe desde</th><th style="text-align:right">Saldo</th></tr></thead>
        <tbody>${rows}</tbody></table>
        <p class="foot">Generado desde Kairos.</p>
        <script>window.onload=function(){setTimeout(function(){window.print()},150)}<\/script>
        </body></html>`;
        const win = window.open('', '_blank', 'width=820,height=950');
        if (!win) { toast('El navegador bloqueó la ventana. Permití popups para este sitio.', 'warning', 6000); return; }
        win.document.write(html);
        win.document.close();
    });

    // ══════════════════════════════════════════════════════════════
    //  MODALES: apertura / cierre / foco
    // ══════════════════════════════════════════════════════════════
    const focoOrigenModal = new WeakMap();

    function sincronizarBloqueoModal() {
        const hayModalAbierto = document.querySelector('.modal:not([hidden])');
        document.body.classList.toggle('cc-modal-open', Boolean(hayModalAbierto));
    }

    function abrirModal(m) {
        if (!m || !m.hidden) return;
        focoOrigenModal.set(m, document.activeElement);
        m.hidden = false;
        sincronizarBloqueoModal();
    }
    function cerrarModal(m) {
        if (!m || m.hidden) return;
        m.hidden = true;
        sincronizarBloqueoModal();
        const origen = focoOrigenModal.get(m);
        focoOrigenModal.delete(m);
        if (origen && origen.isConnected && typeof origen.focus === 'function') {
            requestAnimationFrame(() => origen.focus());
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  ATAJOS DE TECLADO
    // ══════════════════════════════════════════════════════════════
    const overlayAtajos = $('ccAtajos');
    function toggleAtajos(mostrar) {
        const abierto = !overlayAtajos.hidden;
        const nuevo = mostrar === undefined ? !abierto : mostrar;
        overlayAtajos.hidden = !nuevo;
        document.body.classList.toggle('cc-atajos-open', nuevo);
        if (nuevo) requestAnimationFrame(() => $('ccAtajosCerrar').focus());
    }
    $('ccAtajosCerrar').addEventListener('click', () => toggleAtajos(false));
    overlayAtajos.addEventListener('click', (e) => { if (e.target === overlayAtajos) toggleAtajos(false); });

    function moverMarca(delta) {
        if (!ordenActual.length) return;
        marcada = (marcada + delta + ordenActual.length) % ordenActual.length;
        renderLista(true);
        const el = lista.querySelector(`.cc-fila[data-idx="${marcada}"]`);
        if (el) { el.focus(); el.scrollIntoView({ block: 'nearest' }); }
    }

    document.addEventListener('keydown', (e) => {
        const enInput = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)
            || document.activeElement.isContentEditable;

        // Overlay de atajos: Esc lo cierra
        if (!overlayAtajos.hidden) {
            if (e.key === 'Escape' || e.key === '?') { e.preventDefault(); toggleAtajos(false); }
            return;
        }
        // Modal cobrar
        if (!modalCobrar.hidden) {
            if (e.key === 'Escape') { e.preventDefault(); cerrarCobrar(); }
            else if (e.key === 'Enter') {
                if (document.activeElement === inMonto) { e.preventDefault(); selCuenta.focus(); }
                else if (document.activeElement.tagName !== 'TEXTAREA') { e.preventDefault(); $('ccCobrarConfirmar').click(); }
            }
            return;
        }
        // Modal detalle cliente
        if (!modalCliente.hidden) {
            if (e.key === 'Escape') { e.preventDefault(); cerrarCliente(); }
            else if (!enInput && e.key >= '1' && e.key <= '4') {
                const t = ['deudas', 'movimientos', 'cobros', 'pagare'][+e.key - 1];
                activarTab(t);
            }
            return;
        }
        // Lista
        if (e.key === '?') { e.preventDefault(); toggleAtajos(true); return; }
        if (enInput) {
            if (e.key === 'Escape' && document.activeElement === buscar) { buscar.blur(); }
            if (e.key === 'ArrowDown' && document.activeElement === buscar) { e.preventDefault(); moverMarca(1); }
            return;
        }
        if (e.key === '/') { e.preventDefault(); buscar.focus(); buscar.select(); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); moverMarca(1); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); moverMarca(-1); }
        else if (e.key === 'Enter' && marcada >= 0 && ordenActual[marcada]) {
            abrirCliente(ordenActual[marcada].cliente_pk);
        }
        else if (e.key.toLowerCase() === 'c' && marcada >= 0 && ordenActual[marcada] && puedeCobrar) {
            abrirCobrarDesdeLista(ordenActual[marcada].cliente_pk);
        }
    });

    // ── arranque ─────────────────────────────────────────────────────
    cargarLista(false);
});
