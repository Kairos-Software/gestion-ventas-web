// core/static/core/js/estadisticas.js
//
// Renderiza los gráficos del dashboard de Estadísticas con Chart.js.
// Requiere que Chart.js ya esté cargado (se agrega vía CDN en el
// template estadisticas.html) y que el template haya llamado a
// initEstadisticasCharts(serieMensual, gastosCategoria) con los datos
// serializados desde la vista (ver estadisticas.html, block extra_js).
//
// Los colores usan la misma paleta de marca que base.css
// (--brand-orange, --success, --brand-blue, --warning, --danger, etc.)

function initEstadisticasCharts(serieMensual, gastosCategoria) {

    // ── Tendencia mensual: vendido vs. ganancia (últimos 12 meses) ──
    const elTendencia = document.getElementById('chartTendencia');
    if (elTendencia) {
        new Chart(elTendencia, {
            type: 'line',
            data: {
                labels: serieMensual.map(f => f.mes),
                datasets: [
                    {
                        label: 'Vendiste',
                        data: serieMensual.map(f => f.ingresos),
                        borderColor: '#F26A1B',
                        backgroundColor: 'rgba(242,106,27,.08)',
                        tension: 0.3,
                        fill: true,
                    },
                    {
                        label: 'Ganaste',
                        data: serieMensual.map(f => f.ganancia),
                        borderColor: '#10B981',
                        backgroundColor: 'rgba(16,185,129,.10)',
                        tension: 0.3,
                        fill: true,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { callback: (v) => '$' + v.toLocaleString('es-AR') },
                    },
                },
                plugins: {
                    legend: { position: 'bottom' },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString('es-AR')}`,
                        },
                    },
                },
            },
        });
    }

    // ── Gastos por categoría (doughnut) ──
    const elGastos = document.getElementById('chartGastos');
    if (elGastos && gastosCategoria.length) {
        new Chart(elGastos, {
            type: 'doughnut',
            data: {
                labels: gastosCategoria.map(g => g.categoria),
                datasets: [{
                    data: gastosCategoria.map(g => g.total),
                    backgroundColor: [
                        '#F26A1B', '#1E6FA8', '#10B981', '#F59E0B',
                        '#EF4444', '#8b5cf6', '#06b6d4', '#84cc16',
                    ],
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { boxWidth: 10, font: { size: 11 } },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.label}: $${ctx.parsed.toLocaleString('es-AR')}`,
                        },
                    },
                },
            },
        });
    }
}