/**
 * estadisticas_clientes_donut.js
 * ─────────────────────────────────────────────────────────────────
 * Dona con % grande al centro para "Nivel de riesgo" / "Estado de la
 * cartera" en Estadísticas → Clientes. Es una version propia de esta
 * página (no usa el initChartDonut compartido de estadisticas.js) para
 * poder agregar el plugin de texto central y una leyenda en HTML propia
 * sin tocar el helper que usan las demás páginas de Estadísticas.
 *
 * Expone: initDonutClientesCartera(elementId, items, colores)
 *   - items: [{label, cantidad}], ya viene del backend
 *   - colores: {label: '#hex'}
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

function initDonutClientesCartera(elementId, items, colores) {
    const el = document.getElementById(elementId);
    if (!el || !items.length) return;

    const total = items.reduce((acc, i) => acc + i.cantidad, 0);
    const dominante = items.reduce((max, i) => (i.cantidad > max.cantidad ? i : max), items[0]);
    const pctDominante = total ? Math.round((dominante.cantidad / total) * 100) : 0;

    const centroTexto = {
        id: 'centroTexto',
        afterDraw(chart) {
            const { ctx, chartArea } = chart;
            const cx = (chartArea.left + chartArea.right) / 2;
            const cy = (chartArea.top + chartArea.bottom) / 2;
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = "700 1.625rem 'Poppins', Arial, sans-serif";
            ctx.fillStyle = colores[dominante.label] || '#0D1B2A';
            ctx.fillText(`${pctDominante}%`, cx, cy - 8);
            ctx.font = "600 .625rem Arial, sans-serif";
            ctx.fillStyle = '#8A9BB0';
            ctx.fillText(dominante.label.toUpperCase(), cx, cy + 14);
            ctx.restore();
        },
    };

    new Chart(el, {
        type: 'doughnut',
        data: {
            labels: items.map(i => i.label),
            datasets: [{
                data: items.map(i => i.cantidad),
                backgroundColor: items.map(i => colores[i.label] || '#8A9BB0'),
                borderWidth: 3,
                borderColor: '#fff',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '74%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#fff',
                    titleColor: '#0b0b0b',
                    bodyColor: '#52514e',
                    borderColor: '#e1e0d9',
                    borderWidth: 1,
                    padding: 10,
                    boxPadding: 4,
                    usePointStyle: true,
                    callbacks: { label: (ctx) => `${ctx.label}: ${ctx.parsed}` },
                },
            },
        },
        plugins: [centroTexto],
    });
}
