// core/static/core/js/estadisticas.js
//
// Gráficos de las páginas de Estadísticas con Chart.js. Requiere que
// Chart.js ya esté cargado (vía CDN, en cada template que lo necesita)
// y que el template llame a la función de init correspondiente con
// los datos ya serializados desde la vista.
//
// Los colores usan la misma paleta de marca que base.css
// (--brand-orange, --success, --brand-blue, --warning, --danger, etc.)

// Tooltip consistente en todos los gráficos: fondo blanco con borde
// fino, no el tooltip negro por defecto de Chart.js — para que se
// sienta parte del mismo panel, no un componente aparte.
const EST_TOOLTIP_BASE = {
    backgroundColor: '#fff',
    titleColor: '#0b0b0b',
    bodyColor: '#52514e',
    borderColor: '#e1e0d9',
    borderWidth: 1,
    padding: 10,
    boxPadding: 4,
    usePointStyle: true,
};

const EST_GRID_COLOR = '#e1e0d9';

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
                    borderWidth: 2,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: '#F26A1B',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    tension: 0.3,
                    fill: true,
                },
                {
                    label: 'Ganaste',
                    data: serieMensual.map(f => f.ganancia),
                    borderColor: '#10B981',
                    backgroundColor: 'rgba(12,148,100,.10)',
                    borderWidth: 2,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: '#10B981',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
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
                    grid: { color: EST_GRID_COLOR },
                    border: { display: false },
                },
                x: {
                    grid: { display: false },
                    border: { color: '#c3c2b7' },
                },
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 16 },
                },
                tooltip: {
                    ...EST_TOOLTIP_BASE,
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString('es-AR')}`,
                    },
                },
            },
        },
    });
}

// ── Sparkline mini-tendencia para tarjetas KPI: línea de-énfasis en
//    gris, con un punto de acento (color de la serie) solo en el
//    último período. SVG puro — no hace falta Chart.js para esto. ──
function initSparkline(elementId, values, accentColor) {
    const el = document.getElementById(elementId);
    if (!el) return;
    if (!values || values.length < 2 || values.every(v => !v)) {
        el.style.display = 'none';
        return;
    }

    const w = 96, h = 32, pad = 3;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = (max - min) || 1;
    const stepX = (w - pad * 2) / (values.length - 1);
    const pts = values.map((v, i) => [
        pad + i * stepX,
        h - pad - ((v - min) / range) * (h - pad * 2),
    ]);
    const path = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const last = pts[pts.length - 1];

    el.innerHTML =
        `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" fill="none">` +
        `<path d="${path}" stroke="#c3c2b7" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>` +
        `<circle cx="${last[0]}" cy="${last[1]}" r="3" fill="${accentColor}" stroke="#fff" stroke-width="1.5"/>` +
        `</svg>`;
}

// ── "Resumen completo del período" / "Posición financiera neta":
//    convierte la lista de +/- en algo también legible a simple vista
//    — una barra proporcional al monto de cada fila, corrida detrás
//    del texto. Agrupa por tabla (.est-resumen-tabla) porque Caja y
//    Finanzas puede mostrar una tabla por moneda (ARS/USD) y no tiene
//    sentido comparar el máximo de una contra la otra. ──
function initResumenBars() {
    const filas = document.querySelectorAll('.est-resumen-fila[data-monto]');
    if (!filas.length) return;

    const grupos = new Map();
    filas.forEach(f => {
        const grupo = f.closest('.est-resumen-tabla') || f.parentElement;
        if (!grupos.has(grupo)) grupos.set(grupo, []);
        grupos.get(grupo).push(f);
    });

    grupos.forEach(lista => {
        const max = Math.max(...lista.map(f => Math.abs(parseFloat(f.dataset.monto)) || 0));
        if (!max) return;
        lista.forEach(f => {
            const v = Math.abs(parseFloat(f.dataset.monto)) || 0;
            const bar = f.querySelector('.est-resumen-bar');
            if (bar) bar.style.width = Math.max(1.5, (v / max) * 100) + '%';
        });
    });
}

// ── Rankings (empleados, productos, categorías, medios de pago…):
//    misma idea que initResumenBars pero cada lista compite solo
//    contra sí misma — un ranking de 3 productos no se mezcla con
//    el de medios de pago en la tarjeta de al lado. ──
function initRankingBars() {
    const filas = document.querySelectorAll('.est-ranking-row[data-valor]');
    if (!filas.length) return;

    const grupos = new Map();
    filas.forEach(f => {
        const grupo = f.parentElement;
        if (!grupos.has(grupo)) grupos.set(grupo, []);
        grupos.get(grupo).push(f);
    });

    grupos.forEach(lista => {
        const max = Math.max(...lista.map(f => Math.abs(parseFloat(f.dataset.valor)) || 0));
        if (!max) return;
        lista.forEach(f => {
            const v = Math.abs(parseFloat(f.dataset.valor)) || 0;
            const bar = f.querySelector('.est-ranking-bar');
            if (bar) bar.style.width = Math.max(1.5, (v / max) * 100) + '%';
        });
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
                    grid: { color: EST_GRID_COLOR },
                    border: { display: false },
                },
                x: { grid: { display: false }, border: { color: '#c3c2b7' } },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...EST_TOOLTIP_BASE,
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
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                pointBackgroundColor: '#1E6FA8',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
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
                    grid: { color: EST_GRID_COLOR },
                    border: { display: false },
                },
                x: { grid: { display: false }, border: { color: '#c3c2b7' } },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...EST_TOOLTIP_BASE,
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
                    ...EST_TOOLTIP_BASE,
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
function initChartGastos(gastosCategoria, elId, color) {
    const el = document.getElementById(elId || 'chartGastos');
    if (!el || !gastosCategoria.length) return;

    new Chart(el, {
        type: 'bar',
        data: {
            labels: gastosCategoria.map(g => g.categoria),
            datasets: [{
                data: gastosCategoria.map(g => g.total),
                backgroundColor: color || '#F26A1B',
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
                    grid: { color: EST_GRID_COLOR },
                    border: { display: false },
                },
                y: { grid: { display: false } },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...EST_TOOLTIP_BASE,
                    callbacks: {
                        label: (ctx) => `$${ctx.parsed.x.toLocaleString('es-AR')}`,
                    },
                },
            },
        },
    });
}

// ── Caja: cuánto se gasta por mes en cada rubro (barras apiladas) ──
//    data = { meses: [...], series: [{concepto, valores: [...]}, ...] }
const EST_CONCEPTO_COLORS = [
    '#F26A1B', '#1E6FA8', '#16a34a', '#b45309', '#7c3aed', '#0891b2', '#94a3b8',
];

function initChartConceptosMensual(data) {
    const el = document.getElementById('chartConceptosMensual');
    if (!el || !data.series || !data.series.length) return;

    new Chart(el, {
        type: 'bar',
        data: {
            labels: data.meses,
            datasets: data.series.map((s, i) => ({
                label: s.concepto,
                data: s.valores,
                backgroundColor: s.concepto === 'Otros'
                    ? '#94a3b8'
                    : EST_CONCEPTO_COLORS[i % EST_CONCEPTO_COLORS.length],
                borderRadius: 3,
                maxBarThickness: 46,
            })),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { stacked: true, grid: { display: false }, border: { color: '#c3c2b7' } },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    ticks: { callback: (v) => '$' + v.toLocaleString('es-AR') },
                    grid: { color: EST_GRID_COLOR },
                    border: { display: false },
                },
            },
            plugins: {
                legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } },
                tooltip: {
                    ...EST_TOOLTIP_BASE,
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString('es-AR')}`,
                    },
                },
            },
        },
    });
}
