/* ══════════════════════════════════════════════════════════════════
   transacciones.js — Kai-Cart
   Módulo de Transacciones de Caja Grande
   ══════════════════════════════════════════════════════════════════ */

'use strict';

const Transacciones = (() => {

    const URL = {
        cuentas:  window.URL_TRANSACCIONES_CUENTAS,
        calcular: window.URL_TRANSACCIONES_CALCULAR,
        crear:    window.URL_TRANSACCIONES_CREAR,
        listar:   window.URL_TRANSACCIONES_LISTAR,
        detalle:  window.URL_TRANSACCIONES_DETALLE,
        anular:   window.URL_TRANSACCIONES_ANULAR,
    };

    let _cuentas       = [];
    let _transacciones = [];
    let _paginaActual  = 1;
    let _totalPaginas  = 1;
    let _calcTimer     = null;

    /* ── CSRF ──────────────────────────────────────────────────── */
    function getCsrf() {
        return document.cookie.split('; ')
            .find(r => r.startsWith('csrftoken='))
            ?.split('=')[1] ?? '';
    }

    async function postJSON(url, body) {
        const r = await fetch(url, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
            body:    JSON.stringify(body),
        });
        return r.json();
    }

    async function getJSON(url) {
        const r = await fetch(url);
        return r.json();
    }

    /* ══════════════════════════════════════════════════════════════
       INIT
    ══════════════════════════════════════════════════════════════ */
    async function init() {
        await _cargarCuentas();
        await _cargarListado();
        _bindEventos();
    }

    /* ══════════════════════════════════════════════════════════════
       CUENTAS
    ══════════════════════════════════════════════════════════════ */
    async function _cargarCuentas() {
        try {
            const res = await getJSON(URL.cuentas);
            if (res.ok) {
                _cuentas = res.cuentas;
                _poblarSelectCuentas();
            }
        } catch (e) {
            console.error('Error cargando cuentas:', e);
        }
    }

    function _poblarSelectCuentas() {
        const selOrigen  = document.getElementById('trx-cuenta-origen');
        const selDestino = document.getElementById('trx-cuenta-destino');
        const selFiltro  = document.getElementById('filtro-cuenta');

        const opciones = _cuentas.map(c =>
            `<option value="${c.id}" data-moneda="${c.moneda}">${c.nombre} (${c.moneda})</option>`
        ).join('');

        if (selOrigen)  selOrigen.innerHTML  = '<option value="">— Seleccionar —</option>' + opciones;
        if (selDestino) selDestino.innerHTML = '<option value="">— Seleccionar —</option>' + opciones;
        if (selFiltro)  selFiltro.innerHTML  = '<option value="">Todas</option>' + opciones;
    }

    /* ══════════════════════════════════════════════════════════════
       LISTADO
    ══════════════════════════════════════════════════════════════ */
    async function _cargarListado(pagina = 1) {
        _paginaActual = pagina;

        const params = new URLSearchParams({ page: pagina, page_size: 20 });

        const filtroTipo   = document.getElementById('filtro-tipo')?.value;
        const filtroCuenta = document.getElementById('filtro-cuenta')?.value;
        const filtroDesde  = document.getElementById('filtro-desde')?.value;
        const filtroHasta  = document.getElementById('filtro-hasta')?.value;

        if (filtroTipo)   params.set('tipo',   filtroTipo);
        if (filtroCuenta) params.set('cuenta', filtroCuenta);
        if (filtroDesde)  params.set('desde',  filtroDesde);
        if (filtroHasta)  params.set('hasta',  filtroHasta);

        try {
            const res = await getJSON(`${URL.listar}?${params}`);
            if (res.ok) {
                _transacciones = res.transacciones;
                _totalPaginas  = res.paginas;
                _renderListado();
                _renderPaginacion();
            }
        } catch (e) {
            console.error('Error cargando transacciones:', e);
        }
    }

    function _renderListado() {
        const tbody = document.getElementById('trx-tbody');
        if (!tbody) return;

        if (!_transacciones.length) {
            tbody.innerHTML = `
                <tr>
                  <td colspan="7" class="text-center py-5">
                    <div class="empty-state">
                      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
                        <path d="M8 7h12M8 12h12M8 17h8"/>
                        <path d="M3 7h.01M3 12h.01M3 17h.01"/>
                      </svg>
                      <h3>Sin transacciones</h3>
                      <p>Todavía no hay movimientos registrados.</p>
                    </div>
                  </td>
                </tr>`;
            return;
        }

        const badgeCfg = {
            deposito:      { cls: 'badge-success',  label: 'Depósito' },
            extraccion:    { cls: 'badge-warning',  label: 'Extracción' },
            compra_divisa: { cls: 'badge-info',     label: 'Compra divisa' },
            venta_divisa:  { cls: 'badge-primary',  label: 'Venta divisa' },
        };

        tbody.innerHTML = _transacciones.map(t => {
            const cfg = badgeCfg[t.tipo] ?? { cls: 'badge-secondary', label: t.tipo_label };
            const costoHtml = t.costo_extra
                ? `<div class="trx-costo-extra">− ${_fmt(t.costo_extra)} <span>${t.descripcion_costo || 'costo extra'}</span></div>`
                : '';
            return `
            <tr>
              <td class="ps-4">${_fmtFecha(t.fecha)}</td>
              <td><span class="trx-badge ${cfg.cls}">${cfg.label}</span></td>
              <td>${t.cuenta_origen}</td>
              <td>${t.cuenta_destino}</td>
              <td>
                <span class="trx-monto trx-monto--egreso">− ${_fmt(t.monto_origen)}</span>
                ${costoHtml}
              </td>
              <td>
                <span class="trx-monto trx-monto--ingreso">+ ${_fmt(t.monto_destino)}</span>
              </td>
              <td class="pe-4 text-end">
                <button class="trx-btn-accion" onclick="Transacciones.verDetalle(${t.id})" title="Ver detalle">
                  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.3"/>
                    <path d="M1 8C1 8 3.5 2.5 8 2.5S15 8 15 8s-2.5 5.5-7 5.5S1 8 1 8Z" stroke="currentColor" stroke-width="1.3"/>
                  </svg>
                </button>
                <button class="trx-btn-accion trx-btn-accion--danger" onclick="Transacciones.confirmarAnular(${t.id})" title="Anular">
                  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/>
                    <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                  </svg>
                </button>
              </td>
            </tr>`;
        }).join('');
    }

    function _renderPaginacion() {
        const el = document.getElementById('trx-paginacion');
        if (!el) return;
        if (_totalPaginas <= 1) { el.innerHTML = ''; return; }

        let html = '<div class="trx-paginacion">';
        for (let i = 1; i <= _totalPaginas; i++) {
            html += `<button class="trx-pag-btn ${i === _paginaActual ? 'active' : ''}"
                             onclick="Transacciones.irPagina(${i})">${i}</button>`;
        }
        html += '</div>';
        el.innerHTML = html;
    }

    /* ══════════════════════════════════════════════════════════════
       MODAL — CREAR
    ══════════════════════════════════════════════════════════════ */
    function abrirModalCrear() {
        _resetFormulario();
        const modal = bootstrap.Modal.getOrCreateInstance(
            document.getElementById('modalTransaccion')
        );
        modal.show();
    }

    function _resetFormulario() {
        // Reset manual de cada campo (el contenedor es un div, no un form)
        const ids = [
            'trx-tipo', 'trx-cuenta-origen', 'trx-cuenta-destino',
            'trx-monto-origen', 'trx-tipo-cambio', 'trx-costo-extra',
            'trx-descripcion-costo', 'trx-descripcion',
        ];
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.value = '';
        });
        document.getElementById('trx-fecha').value = _hoy();
        document.getElementById('trx-label-origen').textContent  = 'Cuenta origen';
        document.getElementById('trx-label-destino').textContent = 'Cuenta destino';
        document.getElementById('trx-seccion-divisa').style.display = 'none';
        document.getElementById('trx-tipo-cambio').required = false;
        _limpiarPreview();
        _limpiarError();
    }

    function _onTipoChange() {
        const tipo = document.getElementById('trx-tipo').value;
        const esDivisa = ['compra_divisa', 'venta_divisa'].includes(tipo);

        document.getElementById('trx-seccion-divisa').style.display = esDivisa ? '' : 'none';
        document.getElementById('trx-tipo-cambio').required = esDivisa;

        const labels = {
            deposito:      ['Cuenta efectivo (origen)', 'Cuenta banco (destino)'],
            extraccion:    ['Cuenta banco (origen)',    'Cuenta efectivo (destino)'],
            compra_divisa: ['Cuenta en moneda origen',  'Cuenta en divisa destino'],
            venta_divisa:  ['Cuenta en divisa (origen)', 'Cuenta en moneda destino'],
        };

        if (labels[tipo]) {
            document.getElementById('trx-label-origen').textContent  = labels[tipo][0];
            document.getElementById('trx-label-destino').textContent = labels[tipo][1];
        }

        _dispararCalculo();
    }

    /* ── Preview en tiempo real ───────────────────────────────── */
    function _dispararCalculo() {
        clearTimeout(_calcTimer);
        _calcTimer = setTimeout(_calcularPreview, 350);
    }

    async function _calcularPreview() {
        const tipo        = document.getElementById('trx-tipo')?.value;
        const montoOrigen = document.getElementById('trx-monto-origen')?.value;
        const tipoCambio  = document.getElementById('trx-tipo-cambio')?.value;
        const costoExtra  = document.getElementById('trx-costo-extra')?.value;

        if (!tipo || !montoOrigen || parseFloat(montoOrigen) <= 0) {
            _limpiarPreview(); return;
        }

        try {
            const body = { tipo, monto_origen: montoOrigen };
            if (tipoCambio) body.tipo_cambio = tipoCambio;
            if (costoExtra)  body.costo_extra  = costoExtra;

            const res = await postJSON(URL.calcular, body);
            if (res.ok) _mostrarPreview(res, costoExtra);
            else        _limpiarPreview();
        } catch (e) {
            _limpiarPreview();
        }
    }

    function _mostrarPreview(res, costoExtra) {
        const el = document.getElementById('trx-preview');
        if (!el) return;

        const mOrigen  = _monedaSeleccionada('trx-cuenta-origen')  || '';
        const mDestino = _monedaSeleccionada('trx-cuenta-destino') || '';

        let html = `
            <div class="trx-preview-row">
              <span>A acreditar en destino</span>
              <strong class="color-success">+ ${_fmt(res.monto_destino)} ${mDestino}</strong>
            </div>`;

        if (costoExtra && parseFloat(costoExtra) > 0) {
            html += `
            <div class="trx-preview-row">
              <span>Total debitado (con costos)</span>
              <strong class="color-danger">− ${_fmt(res.total_egresado)} ${mOrigen}</strong>
            </div>`;
        }

        if (res.tipo_cambio) {
            html += `
            <div class="trx-preview-row">
              <span>Tipo de cambio</span>
              <span>1 ${mDestino} = ${_fmt(res.tipo_cambio)} ${mOrigen}</span>
            </div>`;
        }

        el.innerHTML = html;
        el.classList.remove('trx-preview--hidden');
    }

    function _limpiarPreview() {
        const el = document.getElementById('trx-preview');
        if (el) { el.innerHTML = ''; el.classList.add('trx-preview--hidden'); }
    }

    /* ── Guardar ──────────────────────────────────────────────── */
    async function guardar() {
        _limpiarError();

        const body = {
            tipo:              document.getElementById('trx-tipo')?.value,
            cuenta_origen_id:  document.getElementById('trx-cuenta-origen')?.value,
            cuenta_destino_id: document.getElementById('trx-cuenta-destino')?.value,
            monto_origen:      document.getElementById('trx-monto-origen')?.value,
            tipo_cambio:       document.getElementById('trx-tipo-cambio')?.value || null,
            costo_extra:       document.getElementById('trx-costo-extra')?.value || null,
            descripcion_costo: document.getElementById('trx-descripcion-costo')?.value || '',
            fecha:             document.getElementById('trx-fecha')?.value,
            descripcion:       document.getElementById('trx-descripcion')?.value || '',
        };

        const btn = document.getElementById('trx-btn-guardar');
        if (btn) { btn.disabled = true; btn.textContent = 'Guardando…'; }

        try {
            const res = await postJSON(URL.crear, body);
            if (res.ok) {
                bootstrap.Modal.getInstance(document.getElementById('modalTransaccion'))?.hide();
                _mostrarToast(res.mensaje, 'success');
                await _cargarListado(_paginaActual);
            } else {
                _mostrarError(res.error || 'Error al guardar.');
            }
        } catch (e) {
            _mostrarError('Error de conexión.');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Guardar'; }
        }
    }

    /* ══════════════════════════════════════════════════════════════
       DETALLE
    ══════════════════════════════════════════════════════════════ */
    async function verDetalle(pk) {
        try {
            const url = URL.detalle.replace('__pk__', pk);
            const res = await getJSON(url);
            if (!res.ok) { _mostrarToast(res.error, 'danger'); return; }

            const t  = res.transaccion;
            const el = document.getElementById('trx-detalle-body');
            if (!el) return;

            el.innerHTML = `
                <dl class="trx-detalle-dl">
                  <div class="trx-detalle-row">
                    <dt>Tipo</dt>
                    <dd>${t.tipo_label}</dd>
                  </div>
                  <div class="trx-detalle-row">
                    <dt>Fecha</dt>
                    <dd>${_fmtFecha(t.fecha)}</dd>
                  </div>
                  <div class="trx-detalle-row">
                    <dt>Cuenta origen</dt>
                    <dd>${t.cuenta_origen}</dd>
                  </div>
                  <div class="trx-detalle-row">
                    <dt>Cuenta destino</dt>
                    <dd>${t.cuenta_destino}</dd>
                  </div>
                  <div class="trx-detalle-row">
                    <dt>Monto debitado</dt>
                    <dd class="color-danger fw-600">− ${_fmt(t.monto_origen)}</dd>
                  </div>
                  <div class="trx-detalle-row">
                    <dt>Monto acreditado</dt>
                    <dd class="color-success fw-600">+ ${_fmt(t.monto_destino)}</dd>
                  </div>
                  ${t.tipo_cambio ? `
                  <div class="trx-detalle-row">
                    <dt>Tipo de cambio</dt>
                    <dd>${_fmt(t.tipo_cambio)}</dd>
                  </div>` : ''}
                  ${t.costo_extra ? `
                  <div class="trx-detalle-row">
                    <dt>Costo extra</dt>
                    <dd class="color-danger">− ${_fmt(t.costo_extra)}<br>
                      <small>${t.descripcion_costo || ''}</small></dd>
                  </div>` : ''}
                  <div class="trx-detalle-row">
                    <dt>Descripción</dt>
                    <dd>${t.descripcion || '—'}</dd>
                  </div>
                  <div class="trx-detalle-row">
                    <dt>Registrado por</dt>
                    <dd>${t.creado_por}</dd>
                  </div>
                  <div class="trx-detalle-row">
                    <dt>Fecha de alta</dt>
                    <dd>${t.fecha_alta}</dd>
                  </div>
                </dl>`;

            const btnAnular = document.getElementById('trx-detalle-btn-anular');
            if (btnAnular) btnAnular.dataset.pk = pk;

            bootstrap.Modal.getOrCreateInstance(
                document.getElementById('modalTransaccionDetalle')
            ).show();

        } catch (e) {
            _mostrarToast('Error cargando el detalle.', 'danger');
        }
    }

    /* ══════════════════════════════════════════════════════════════
       ANULAR
    ══════════════════════════════════════════════════════════════ */
    function confirmarAnular(pk) {
        const el = document.getElementById('trx-anular-pk');
        if (el) el.value = pk;
        bootstrap.Modal.getOrCreateInstance(
            document.getElementById('modalConfirmarAnular')
        ).show();
    }

    async function ejecutarAnular() {
        const pk = document.getElementById('trx-anular-pk')?.value;
        if (!pk) return;

        try {
            const url = URL.anular.replace('__pk__', pk);
            const res = await postJSON(url, {});

            bootstrap.Modal.getInstance(document.getElementById('modalConfirmarAnular'))?.hide();
            bootstrap.Modal.getInstance(document.getElementById('modalTransaccionDetalle'))?.hide();

            if (res.ok) {
                _mostrarToast(res.mensaje, 'success');
                await _cargarListado(_paginaActual);
            } else {
                _mostrarToast(res.error || 'Error al anular.', 'danger');
            }
        } catch (e) {
            _mostrarToast('Error de conexión.', 'danger');
        }
    }

    /* ══════════════════════════════════════════════════════════════
       FILTROS / PAGINACIÓN
    ══════════════════════════════════════════════════════════════ */
    function aplicarFiltros() { _cargarListado(1); }

    function limpiarFiltros() {
        ['filtro-tipo', 'filtro-cuenta', 'filtro-desde', 'filtro-hasta']
            .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        _cargarListado(1);
    }

    function irPagina(n) { _cargarListado(n); }

    /* ══════════════════════════════════════════════════════════════
       BIND EVENTOS
    ══════════════════════════════════════════════════════════════ */
    function _bindEventos() {
        document.getElementById('trx-tipo')
            ?.addEventListener('change', _onTipoChange);

        ['trx-monto-origen', 'trx-tipo-cambio', 'trx-costo-extra',
         'trx-cuenta-origen', 'trx-cuenta-destino'].forEach(id => {
            document.getElementById(id)?.addEventListener('input',  _dispararCalculo);
            document.getElementById(id)?.addEventListener('change', _dispararCalculo);
        });

        document.getElementById('trx-btn-guardar')
            ?.addEventListener('click', guardar);

        document.getElementById('trx-detalle-btn-anular')
            ?.addEventListener('click', () => {
                const pk = document.getElementById('trx-detalle-btn-anular')?.dataset.pk;
                if (pk) {
                    bootstrap.Modal.getInstance(document.getElementById('modalTransaccionDetalle'))?.hide();
                    confirmarAnular(pk);
                }
            });

        document.getElementById('trx-btn-confirmar-anular')
            ?.addEventListener('click', ejecutarAnular);

        document.getElementById('trx-btn-filtrar')
            ?.addEventListener('click', aplicarFiltros);
        document.getElementById('trx-btn-limpiar-filtros')
            ?.addEventListener('click', limpiarFiltros);
    }

    /* ══════════════════════════════════════════════════════════════
       HELPERS UI
    ══════════════════════════════════════════════════════════════ */
    function _mostrarError(msg) {
        const wrap = document.getElementById('trx-error');
        const txt  = document.getElementById('trx-error-texto');
        if (!wrap) return;
        if (txt) txt.textContent = msg;
        wrap.classList.remove('trx-hidden');
    }

    function _limpiarError() {
        const wrap = document.getElementById('trx-error');
        const txt  = document.getElementById('trx-error-texto');
        if (txt) txt.textContent = '';
        if (wrap) wrap.classList.add('trx-hidden');
    }

    function _mostrarToast(msg, tipo = 'success') {
        if (window.KaiToast) { window.KaiToast.show(msg, tipo); return; }

        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:.5rem;';
            document.body.appendChild(container);
        }

        const colores = {
            success: { bg: 'var(--success)', icon: '✓' },
            danger:  { bg: 'var(--danger)',  icon: '✕' },
            warning: { bg: 'var(--warning)', icon: '!' },
        };
        const cfg = colores[tipo] ?? colores.success;

        const toast = document.createElement('div');
        toast.style.cssText = `
            display:flex;align-items:center;gap:.75rem;
            background:white;border-radius:var(--radius-md);
            box-shadow:var(--shadow-lg);
            padding:.75rem 1rem;font-size:.875rem;
            border-left:3px solid ${cfg.bg};
            animation:trxToastIn .22s ease;
            min-width:260px;max-width:340px;
        `;
        toast.innerHTML = `
            <span style="width:20px;height:20px;border-radius:50%;background:${cfg.bg};
                         color:white;display:flex;align-items:center;justify-content:center;
                         font-size:.75rem;font-weight:700;flex-shrink:0">${cfg.icon}</span>
            <span style="flex:1;color:var(--text-primary)">${msg}</span>`;

        container.appendChild(toast);
        setTimeout(() => {
            toast.style.animation = 'trxToastOut .22s ease forwards';
            setTimeout(() => toast.remove(), 220);
        }, 3500);
    }

    function _monedaSeleccionada(selectId) {
        const sel = document.getElementById(selectId);
        return sel?.selectedOptions[0]?.dataset.moneda ?? '';
    }

    function _fmt(valor) {
        const n = parseFloat(valor);
        if (isNaN(n)) return valor;
        return n.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function _fmtFecha(iso) {
        if (!iso) return '—';
        const [y, m, d] = iso.split('-');
        return `${d}/${m}/${y}`;
    }

    function _hoy() {
        return new Date().toISOString().split('T')[0];
    }

    return { init, abrirModalCrear, verDetalle, confirmarAnular, irPagina };

})();

document.addEventListener('DOMContentLoaded', () => Transacciones.init());