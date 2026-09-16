// core/static/core/js/estadisticas_cliente_scoring.js
//
// Gráfico "Historial de scoring" en la ficha de cliente (Estadísticas >
// Clientes). Un punto por cada vez que el puntaje de riesgo de pago
// realmente cambió (ver Cliente.recalcular_scoring / core.models.HistorialScoring).
// Al hacer click en un punto se muestra el desglose completo de ESE día,
// reusando el mismo formato de tabla que la ficha de Personas > Clientes
// (clases .sco-tabla / .sco-td-concepto / .sco-td-puntos, definidas en
// detalle_cliente.css — ya está cargado en esta página). Requiere que
// estadisticas.js se haya cargado antes (usa EST_TOOLTIP_BASE/EST_GRID_COLOR).

const SCO_BANDA_COLOR = {
    excelente: '#15803d',
    bueno:     '#4d7c0f',
    regular:   '#b45309',
    riesgo:    '#c2410c',
    critico:   '#b91c1c',
};

function scoFechaCorta(iso) {
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y.slice(2)}`;
}

function initChartScoringHistorial(puntos) {
    const el = document.getElementById('chartScoringHistorial');
    if (!el || !puntos.length) return;

    new Chart(el, {
        type: 'line',
        data: {
            labels: puntos.map(p => scoFechaCorta(p.fecha)),
            datasets: [{
                label: 'Scoring',
                data: puntos.map(p => p.score),
                borderColor: '#F26A1B',
                backgroundColor: 'rgba(242,106,27,.08)',
                borderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBackgroundColor: puntos.map(p => SCO_BANDA_COLOR[p.banda] || '#F26A1B'),
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                tension: 0.25,
                fill: true,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: 0,
                    max: 1000,
                    ticks: { stepSize: 250 },
                    grid: { color: EST_GRID_COLOR },
                    border: { display: false },
                },
                x: {
                    grid: { display: false },
                    border: { color: '#c3c2b7' },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...EST_TOOLTIP_BASE,
                    callbacks: {
                        title: (items) => puntos[items[0].dataIndex].fecha.split('-').reverse().join('/'),
                        label: (ctx) => `Scoring: ${ctx.parsed.y} pts`,
                        afterLabel: (ctx) => puntos[ctx.dataIndex].es_backfill
                            ? 'Estimado a partir del historial real' : '',
                    },
                },
            },
            onClick: (evt, elements) => {
                if (!elements.length) return;
                scoRenderizarDesglose(puntos[elements[0].index]);
            },
        },
    });

    // Al cargar, mostrar el desglose del último punto (el vigente).
    scoRenderizarDesglose(puntos[puntos.length - 1]);
}

function scoRenderizarDesglose(punto) {
    const cont = document.getElementById('scoHistDesglose');
    if (!cont) return;

    const fecha = punto.fecha.split('-').reverse().join('/');
    const filas = (punto.desglose || []).map(d => `
        <tr>
            <td class="sco-td-concepto">${d.concepto}<span class="sco-td-detalle">${d.detalle}</span></td>
            <td class="sco-td-puntos ${d.puntos > 0 ? 'sco-pos' : d.puntos < 0 ? 'sco-neg' : ''}">${d.puntos > 0 ? '+' : ''}${d.puntos}</td>
        </tr>
    `).join('');

    cont.innerHTML = `
        <div class="sco-hist-desglose-header">
            <strong>${fecha}</strong>
            <span class="sco-badge sco-badge--${punto.banda}">${punto.banda_label}</span>
            <span class="sco-hist-desglose-score">${punto.score} / 1000</span>
            ${punto.es_backfill
                ? '<span class="cp-pill" title="Reconstruido a partir de fechas reales de cuotas y cheques — no fue registrado en el momento">Estimado</span>'
                : ''}
        </div>
        <table class="sco-tabla">
            <tbody>${filas}</tbody>
        </table>
    `;
}
