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
        monedaSelector.addEventListener('click', function(e) {
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
        
        if (!balance || !balance[monedaActual]) {
            grid.innerHTML = '';
            emptyHint.hidden = false;
            return;
        }
        
        emptyHint.hidden = true;
        const datos = balance[monedaActual];
        grid.innerHTML = `
            <div class="cg-moneda-card">
                <div class="cg-moneda-nombre">${monedaActual}</div>
                <div class="cg-moneda-saldo ${parseFloat(datos.saldo) < 0 ? 'cg-moneda-saldo--negativo' : ''}">
                    ${formatMonto(datos.saldo, monedaActual)}
                </div>
            </div>
        `;
    }
    
    function renderizarMetricasPorMoneda(metricas) {
        const grid = document.getElementById('metricasGrid');
        
        if (!metricas || !metricas[monedaActual]) {
            grid.innerHTML = '<p class="cg-empty-hint">No hay métricas disponibles para esta moneda.</p>';
            return;
        }
        
        const datos = metricas[monedaActual];
        grid.innerHTML = `
            <div class="cg-metrica-card">
                <div class="cg-metrica-titulo">Recaudado</div>
                <div class="cg-metrica-valor cg-metrica-valor--positivo">${formatMonto(datos.recaudado, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-titulo">Gastos</div>
                <div class="cg-metrica-valor cg-metrica-valor--negativo">${formatMonto(datos.gastos, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-titulo">Neto</div>
                <div class="cg-metrica-valor ${parseFloat(datos.neto) >= 0 ? 'cg-metrica-valor--positivo' : 'cg-metrica-valor--negativo'}">
                    ${formatMonto(datos.neto, monedaActual)}
                </div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-titulo">Ventas</div>
                <div class="cg-metrica-valor cg-metrica-valor--positivo">${formatMonto(datos.ventas, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
                <div class="cg-metrica-titulo">Compras</div>
                <div class="cg-metrica-valor cg-metrica-valor--negativo">${formatMonto(datos.compras, monedaActual)}</div>
            </div>
            <div class="cg-metrica-card">
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
