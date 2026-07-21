document.addEventListener('DOMContentLoaded', function () {

    // ══════════════════════════════════════════════════════════════════
    //  CONFIGURACIÓN Y HELPERS
    // ══════════════════════════════════════════════════════════════════

    const container = document.getElementById('cajaGrande');
    if (!container) return;

    const urls = {
        balance: container.dataset.urlBalance,
    };

    // Estado de la aplicación
    let monedaActual = 'ARS';

    // Helpers
    function getCookie(name) {
        let v = null;
        document.cookie.split(';').forEach(c => {
            const [k, val] = c.trim().split('=');
            if (k === name) v = decodeURIComponent(val);
        });
        return v;
    }

    function formatMonto(monto, moneda) {
        const num = parseFloat(monto);
        return new Intl.NumberFormat('es-AR', {
            style: 'currency',
            currency: moneda || 'ARS'
        }).format(num);
    }

    function formatDate(fecha) {
        const d = new Date(fecha);
        return d.toLocaleDateString('es-AR');
    }

    // ══════════════════════════════════════════════════════════════════
    //  SELECTOR DE MONEDA
    // ══════════════════════════════════════════════════════════════════

    const monedaSelector = document.getElementById('monedaSelector');
    if (monedaSelector) {
        monedaSelector.addEventListener('click', function (e) {
            if (e.target.classList.contains('cg-moneda-btn')) {
                const moneda = e.target.dataset.moneda;
                cambiarMoneda(moneda);
            }
        });
    }

    function cambiarMoneda(moneda) {
        monedaActual = moneda;

        // Actualizar botones
        document.querySelectorAll('.cg-moneda-btn').forEach(btn => {
            btn.classList.remove('cg-moneda-btn--active');
            if (btn.dataset.moneda === moneda) {
                btn.classList.add('cg-moneda-btn--active');
            }
        });

        // Recargar datos
        cargarBalance();
    }

    // ══════════════════════════════════════════════════════════════════
    //  CARGAR BALANCE
    // ══════════════════════════════════════════════════════════════════

    async function cargarBalance() {
        try {
            const response = await fetch(urls.balance);
            const data = await response.json();

            renderizarBalancePorMoneda(data.balance_por_moneda);
        } catch (error) {
            console.error('Error al cargar balance:', error);
        }
    }

    function renderizarBalancePorMoneda(balance) {
        const grid = document.getElementById('monedasGrid');
        const emptyHint = document.getElementById('monedasEmptyHint');
        const cuentasGrid = document.getElementById('cuentasGrid');
        const cuentasSection = document.getElementById('cuentasSection');
        const movimientosList = document.getElementById('movimientosList');
        const movimientosSection = document.getElementById('movimientosSection');

        if (!balance || !balance[monedaActual]) {
            grid.innerHTML = '';
            emptyHint.hidden = false;
            if (cuentasSection) cuentasSection.hidden = true;
            if (movimientosSection) movimientosSection.hidden = true;
            return;
        }

        emptyHint.hidden = true;
        const datos = balance[monedaActual];
        const esNegativo = parseFloat(datos.saldo) < 0;

        grid.innerHTML = `
            <div class="cg-balance-hero ${esNegativo ? 'cg-balance-hero--negativo' : ''}">
                <div class="cg-balance-hero-info">
                    <div class="cg-balance-hero-icon">
                        <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
                            <path d="M3.5 19.5C3.5 11 7.5 5 13 5C18.5 5 22.5 11 22.5 19.5" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
                            <path d="M3.5 19.5H22.5" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
                            <circle cx="13" cy="13" r="2.3" stroke="white" stroke-width="1.8"/>
                        </svg>
                    </div>
                    <div>
                        <div class="cg-balance-hero-label">Balance ${monedaActual}</div>
                        <div class="cg-balance-hero-saldo">${formatMonto(datos.saldo, monedaActual)}</div>
                    </div>
                </div>
                <div class="cg-balance-hero-tag">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        ${esNegativo
                ? '<path d="M3 5L7 9L11 5" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
                : '<path d="M3 9L7 5L11 9" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'}
                    </svg>
                    ${esNegativo ? 'Saldo negativo' : 'Saldo positivo'}
                </div>
            </div>
        `;

        renderizarCuentas(datos.cuentas, cuentasGrid, cuentasSection);
        renderizarUltimosMovimientos(datos.ultimos_movimientos, movimientosList, movimientosSection);
    }

    // ══════════════════════════════════════════════════════════════════
    //  DESGLOSE POR CUENTA (Efectivo, Transferencia, Débito, etc.)
    // ══════════════════════════════════════════════════════════════════

    const ICONOS_TIPO_CUENTA = {
        efectivo: '<rect x="2" y="5" width="12" height="8" rx="1.3" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="9" r="1.4" stroke="currentColor" stroke-width="1.3"/>',
        banco: '<rect x="2" y="6.5" width="12" height="6.5" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M1.5 6.5L8 2L14.5 6.5" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>',
        otra: '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><path d="M8 5.5V8.5L10 10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>',
    };

    function renderizarCuentas(cuentas, cuentasGrid, cuentasSection) {
        if (!cuentasGrid || !cuentasSection) return;

        if (!cuentas || cuentas.length === 0) {
            cuentasSection.hidden = true;
            return;
        }

        cuentasSection.hidden = false;
        cuentasGrid.innerHTML = cuentas.map(cuenta => {
            const esNegativo = parseFloat(cuenta.saldo) < 0;
            const icono = ICONOS_TIPO_CUENTA[cuenta.tipo] || ICONOS_TIPO_CUENTA.otra;
            const detalle = [
                cuenta.terminada_en ? `term. en ${cuenta.terminada_en}` : null,
                cuenta.titular || null,
            ].filter(Boolean).join(' · ');
            return `
                <div class="cg-cuenta-card">
                    <div class="cg-cuenta-icon">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${icono}</svg>
                    </div>
                    <div class="cg-cuenta-info">
                        <div class="cg-cuenta-nombre">
                            <span class="cg-cuenta-nombre-texto">${cuenta.nombre}</span>
                            ${cuenta.es_credito ? '<span class="cg-cuenta-badge">Crédito</span>' : ''}
                        </div>
                        <div class="cg-cuenta-saldo ${esNegativo ? 'cg-cuenta-saldo--negativo' : ''}">
                            ${formatMonto(cuenta.saldo, monedaActual)}
                        </div>
                        ${detalle ? `<div class="cg-cuenta-detalle">${detalle}</div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    // ══════════════════════════════════════════════════════════════════
    //  ÚLTIMOS MOVIMIENTOS (vistazo rápido — venta, compra, gasto manual,
    //  transacción interna, deuda/cuota, cheque, ajuste de turno)
    // ══════════════════════════════════════════════════════════════════

    const ICONOS_ORIGEN = {
        venta: '<path d="M2 3H3.5L5.2 10.6C5.3 11.1 5.75 11.46 6.26 11.46H12.5C13 11.46 13.4 11.1 13.5 10.6L14.5 4H4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7" cy="14" r="1" stroke="currentColor" stroke-width="1.2"/><circle cx="12" cy="14" r="1" stroke="currentColor" stroke-width="1.2"/>',
        compra: '<path d="M2 3H3.5L5.2 10.6C5.3 11.1 5.75 11.46 6.26 11.46H12.5C13 11.46 13.4 11.1 13.5 10.6L14.5 4H4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7" cy="14" r="1" stroke="currentColor" stroke-width="1.2"/><circle cx="12" cy="14" r="1" stroke="currentColor" stroke-width="1.2"/>',
        manual: '<path d="M8 2.5V13.5M2.5 8H13.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
        ajuste: '<path d="M2 12L5.5 7.5L8.5 9.5L11.5 5L14 8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>',
        transaccion: '<path d="M3 6H12L9.5 3.5M13 10H4L6.5 12.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>',
        deuda: '<rect x="2" y="4" width="12" height="8.5" rx="1.2" stroke="currentColor" stroke-width="1.3"/><path d="M2 7H14" stroke="currentColor" stroke-width="1.3"/>',
        cuota_deuda: '<rect x="2" y="4" width="12" height="8.5" rx="1.2" stroke="currentColor" stroke-width="1.3"/><path d="M2 7H14" stroke="currentColor" stroke-width="1.3"/>',
        cheque: '<rect x="1.5" y="3.5" width="13" height="9" rx="1.2" stroke="currentColor" stroke-width="1.3"/><path d="M4 9.5L6.5 7L8.5 8.5L12 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>',
    };

    function renderizarUltimosMovimientos(movimientos, lista, seccion) {
        if (!lista || !seccion) return;

        if (!movimientos || movimientos.length === 0) {
            seccion.hidden = true;
            return;
        }

        seccion.hidden = false;
        lista.innerHTML = movimientos.map(mov => {
            const esIngreso = mov.tipo === 'ingreso';
            const icono = ICONOS_ORIGEN[mov.origen] || ICONOS_ORIGEN.manual;
            return `
                <div class="cg-mov-item">
                    <div class="cg-mov-icon ${esIngreso ? 'cg-mov-icon--ingreso' : 'cg-mov-icon--egreso'}">
                        <svg width="15" height="15" viewBox="0 0 16 16" fill="none">${icono}</svg>
                    </div>
                    <div class="cg-mov-info">
                        <span class="cg-mov-titulo">${mov.titulo}</span>
                        <span class="cg-mov-detalle">${mov.cuenta_nombre} · ${formatDate(mov.fecha)}</span>
                    </div>
                    <div class="cg-mov-monto ${esIngreso ? 'cg-mov-monto--ingreso' : 'cg-mov-monto--egreso'}">
                        ${esIngreso ? '+' : '−'}${formatMonto(mov.monto, monedaActual)}
                    </div>
                </div>
            `;
        }).join('');
    }

    // ══════════════════════════════════════════════════════════════════
    //  INICIALIZACIÓN
    // ══════════════════════════════════════════════════════════════════

    cargarBalance();
});