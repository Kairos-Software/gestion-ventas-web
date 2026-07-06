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
            renderizarMetricasPorMoneda(data.metricas_por_moneda);
        } catch (error) {
            console.error('Error al cargar balance:', error);
        }
    }

    function renderizarBalancePorMoneda(balance) {
        const grid = document.getElementById('monedasGrid');
        const emptyHint = document.getElementById('monedasEmptyHint');
        const cuentasGrid = document.getElementById('cuentasGrid');
        const cuentasSection = document.getElementById('cuentasSection');

        if (!balance || !balance[monedaActual]) {
            grid.innerHTML = '';
            emptyHint.hidden = false;
            if (cuentasSection) cuentasSection.hidden = true;
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
            return `
                <div class="cg-cuenta-card">
                    <div class="cg-cuenta-icon">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${icono}</svg>
                    </div>
                    <div class="cg-cuenta-info">
                        <div class="cg-cuenta-nombre">${cuenta.nombre}</div>
                        <div class="cg-cuenta-saldo ${esNegativo ? 'cg-cuenta-saldo--negativo' : ''}">
                            ${formatMonto(cuenta.saldo, monedaActual)}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    function renderizarMetricasPorMoneda(metricas) {
        const grid = document.getElementById('metricasGrid');

        if (!metricas || !metricas[monedaActual]) {
            grid.innerHTML = '<p class="cg-empty-hint">No hay métricas disponibles para esta moneda.</p>';
            return;
        }

        const datos = metricas[monedaActual];
        const netoPositivo = parseFloat(datos.neto) >= 0;

        const iconRecaudado = '<rect x="2" y="6" width="12" height="8" rx="1.3" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="10" r="1.6" stroke="currentColor" stroke-width="1.4"/><path d="M5 6V4.7C5 3.76 5.76 3 6.7 3H9.3C10.24 3 11 3.76 11 4.7V6" stroke="currentColor" stroke-width="1.4"/>';
        const iconGastos = '<path d="M8 13L13 8H10V1H6V8H3L8 13Z" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>';
        const iconNetoPos = '<path d="M8 13.5V2.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M3 5.5H13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M3 5.5L1.5 9.5H4.5L3 5.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M13 5.5L11.5 9.5H14.5L13 5.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>';
        const iconNetoNeg = iconNetoPos;
        const iconVentas = '<path d="M3 14L7 8L10.5 11L15 4.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M11.5 4.5H15V8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>';
        const iconCompras = '<path d="M2 4H3.5L5.2 11.5H12.5L14 6H4.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="14" r="1" fill="currentColor"/><circle cx="11.5" cy="14" r="1" fill="currentColor"/>';
        const iconMovimientos = '<path d="M2 5H14M2 5L4 3M2 5L4 7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M14 11H2M14 11L12 9M14 11L12 13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>';

        grid.innerHTML = `
            <div class="cg-metrica-card">
                <div class="cg-metrica-icon cg-metrica-icon--positivo">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${iconRecaudado}</svg>
                </div>
                <div class="cg-metrica-titulo">Recaudado</div>
                <div class="cg-metrica-valor cg-metrica-valor--positivo">${formatMonto(datos.recaudado, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-icon cg-metrica-icon--negativo">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${iconGastos}</svg>
                </div>
                <div class="cg-metrica-titulo">Gastos</div>
                <div class="cg-metrica-valor cg-metrica-valor--negativo">${formatMonto(datos.gastos, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-icon ${netoPositivo ? 'cg-metrica-icon--positivo' : 'cg-metrica-icon--negativo'}">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${netoPositivo ? iconNetoPos : iconNetoNeg}</svg>
                </div>
                <div class="cg-metrica-titulo">Neto</div>
                <div class="cg-metrica-valor ${netoPositivo ? 'cg-metrica-valor--positivo' : 'cg-metrica-valor--negativo'}">
                    ${formatMonto(datos.neto, monedaActual)}
                </div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-icon cg-metrica-icon--positivo">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${iconVentas}</svg>
                </div>
                <div class="cg-metrica-titulo">Ventas</div>
                <div class="cg-metrica-valor cg-metrica-valor--positivo">${formatMonto(datos.ventas, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-icon cg-metrica-icon--negativo">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${iconCompras}</svg>
                </div>
                <div class="cg-metrica-titulo">Compras</div>
                <div class="cg-metrica-valor cg-metrica-valor--negativo">${formatMonto(datos.compras, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-icon cg-metrica-icon--neutro">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">${iconMovimientos}</svg>
                </div>
                <div class="cg-metrica-titulo">Total movimientos</div>
                <div class="cg-metrica-valor">${datos.total_movimientos}</div>
            </div>
        `;
    }

    // ══════════════════════════════════════════════════════════════════
    //  INICIALIZACIÓN
    // ══════════════════════════════════════════════════════════════════

    cargarBalance();
});