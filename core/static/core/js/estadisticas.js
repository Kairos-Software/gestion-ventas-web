// core/static/core/js/estadisticas.js
//
// Gráficos de las páginas de Estadísticas con Chart.js. Requiere que
// Chart.js ya esté cargado (vía CDN, en cada template que lo necesita)
// y que el template llame a la función de init correspondiente con
// los datos ya serializados desde la vista.
//
// Los colores usan la misma paleta de marca que base.css
// (--brand-orange, --success, --brand-blue, --warning, --danger, etc.)

// ── Resumen: tendencia mensual de vendido vs. ganancia (últimos 12 meses) ──
function initChartTendencia(serieMensual) {
    const el = document.getElementById('chartTendencia');
    if (!el) return;

    new Chart(el, {
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

// ── Ventas: ingresos por día de la semana (para saber qué días
//    conviene reforzar personal) — una sola serie, sin leyenda. ──
function initChartDiaSemana(porDiaSemana) {
    const el = document.getElementById('chartDiaSemana');
    if (!el) return;

    new Chart(el, {
        type: 'bar',
        data: {
            labels: porDiaSemana.map(f => f.dia),
            datasets: [{
                data: porDiaSemana.map(f => f.ingresos),
                backgroundColor: '#F26A1B',
                borderRadius: 4,
                maxBarThickness: 40,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { callback: (v) => '$' + v.toLocaleString('es-AR') },
                    grid: { color: 'rgba(0,0,0,.05)' },
                },
                x: { grid: { display: false } },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `$${ctx.parsed.y.toLocaleString('es-AR')}`,
                    },
                },
            },
        },
    });
}

// ── Compras: tendencia mensual de total comprado (últimos 12 meses) ──
function initChartComprasTendencia(serieMensual) {
    const el = document.getElementById('chartComprasTendencia');
    if (!el) return;

    new Chart(el, {
        type: 'line',
        data: {
            labels: serieMensual.map(f => f.mes),
            datasets: [{
                label: 'Comprado',
                data: serieMensual.map(f => f.total),
                borderColor: '#1E6FA8',
                backgroundColor: 'rgba(30,111,168,.10)',
                tension: 0.3,
                fill: true,
            }],
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
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `Comprado: $${ctx.parsed.y.toLocaleString('es-AR')}`,
                    },
                },
            },
        },
    });
}

// ── Torta/donut genérico para distribuciones categóricas (parte de un
//    todo): nivel de riesgo y estado de cartera de clientes, medio de
//    pago. `items` trae {label, <valueKey>}, `colores` mapea label ->
//    color hex. `formatValue` da formato al número (cantidad simple
//    por defecto, o "$1.234" para montos). ──
function initChartDonut(elementId, items, colores, opciones) {
    const el = document.getElementById(elementId);
    if (!el || !items.length) return;

    const valueKey = (opciones && opciones.valueKey) || 'cantidad';
    const formatValue = (opciones && opciones.formatValue) || (v => v);

    new Chart(el, {
        type: 'doughnut',
        data: {
            labels: items.map(i => i.label),
            datasets: [{
                data: items.map(i => i[valueKey]),
                backgroundColor: items.map(i => colores[i.label] || '#8A9BB0'),
                borderWidth: 2,
                borderColor: '#fff',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        boxWidth: 10,
                        padding: 12,
                        generateLabels: (chart) => {
                            const data = chart.data;
                            const total = data.datasets[0].data.reduce((a, b) => a + b, 0);
                            return data.labels.map((label, i) => {
                                const value = data.datasets[0].data[i];
                                const pct = total ? Math.round((value / total) * 100) : 0;
                                return {
                                    text: `${label}: ${formatValue(value)} (${pct}%)`,
                                    fillStyle: data.datasets[0].backgroundColor[i],
                                    index: i,
                                };
                            });
                        },
                    },
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.label}: ${formatValue(ctx.parsed)}`,
                    },
                },
            },
        },
    });
}

// ── Caja y Finanzas: gastos por categoría (barra horizontal — se lee
//    la magnitud relativa mejor que en una torta, y escala mejor con
//    varias categorías). Una sola serie: el color identifica "gasto",
//    no hace falta leyenda ni una paleta categórica acá. ──
function initChartGastos(gastosCategoria) {
    const el = document.getElementById('chartGastos');
    if (!el || !gastosCategoria.length) return;

    new Chart(el, {
        type: 'bar',
        data: {
            labels: gastosCategoria.map(g => g.categoria),
            datasets: [{
                data: gastosCategoria.map(g => g.total),
                backgroundColor: '#F26A1B',
                borderRadius: 4,
                maxBarThickness: 28,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { callback: (v) => '$' + v.toLocaleString('es-AR') },
                    grid: { color: 'rgba(0,0,0,.05)' },
                },
                y: { grid: { display: false } },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `$${ctx.parsed.x.toLocaleString('es-AR')}`,
                    },
                },
            },
        },
    });
}
