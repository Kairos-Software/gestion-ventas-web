// core/static/core/js/estadisticas_cliente_scoring.js
//
// Gráfico "Historial de scoring" en la ficha de cliente (Estadísticas >
// Clientes). Un punto por cada vez que el puntaje de riesgo de pago
// realmente cambió (ver Cliente.recalcular_scoring / core.models.HistorialScoring).
//
// Todo lo de acá se deriva de un solo array (scoPuntos, el subconjunto
// vigente según el filtro de rango elegido) y se sincroniza entre sí —
// clickear cualquiera selecciona el mismo punto en el resto:
//   1. Filtro de rango (3 meses / 1 año / todo) — pensado para cuando el
//      historial crezca con el tiempo y ya no entre cómodo de un vistazo.
//   2. Resumen rápido: mejor momento, peor momento, cuántas veces subió/
//      bajó, tendencia reciente (mismo markup .est-mini-stat que el resto
//      de la página, cero CSS nuevo para esa parte).
//   3. El gráfico de línea, con el fondo coloreado por banda (Excelente/
//      Bueno/Regular/Riesgo/Crítico) + una leyenda de colores debajo.
//   4. La "línea de eventos": lista en texto plano, más reciente primero,
//      de CADA cambio real — subió o bajó, cuántos puntos, y el motivo
//      principal (el concepto de mayor magnitud de ESE día). Navegable
//      con mouse o teclado (Enter/Espacio).
//   5. El desglose completo del punto seleccionado, como gráfico de
//      cascada (barras +/- desde el cero) en vez de una tabla plana —
//      se ve de un vistazo qué pesó más sin tener que leer cada número.
//
// Requiere que estadisticas.js se haya cargado antes (usa
// EST_TOOLTIP_BASE/EST_GRID_COLOR).

const SCO_BANDA_COLOR = {
    excelente: '#15803d',
    bueno:     '#4d7c0f',
    regular:   '#b45309',
    riesgo:    '#c2410c',
    critico:   '#b91c1c',
};

// Mismos umbrales que core/scoring.py BANDAS — para pintar el fondo del
// gráfico en franjas de color, la leyenda, y saber en qué franja cae un
// score dado.
const SCO_BANDAS_DEF = [
    { desde: 850, hasta: 1000, clase: 'excelente', label: 'Excelente' },
    { desde: 700, hasta: 850,  clase: 'bueno',     label: 'Bueno' },
    { desde: 500, hasta: 700,  clase: 'regular',   label: 'Regular' },
    { desde: 300, hasta: 500,  clase: 'riesgo',    label: 'Riesgo' },
    { desde: 0,   hasta: 300,  clase: 'critico',   label: 'Crítico' },
];

const SCO_FILTROS_RANGO = [
    { id: '3m',   label: '3 meses',  dias: 90 },
    { id: '1a',   label: '1 año',    dias: 365 },
    { id: 'todo', label: 'Todo',     dias: null },
];

function scoFranjaColorFondo(clase) {
    const c = SCO_BANDA_COLOR[clase] || '#F26A1B';
    // mismo color de la banda, muy translúcido, para el fondo del gráfico
    const r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
    return `rgba(${r},${g},${b},.08)`;
}

// Plugin de Chart.js "a mano" (sin librería aparte): dibuja las franjas
// de banda como rectángulos detrás de la línea, usando la escala Y ya
// calculada por Chart.js para saber a qué píxel corresponde cada umbral.
const scoFondoFranjasPlugin = {
    id: 'scoFondoFranjas',
    beforeDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        if (!chartArea) return;
        const y = scales.y;
        ctx.save();
        SCO_BANDAS_DEF.forEach(f => {
            const yDesde = y.getPixelForValue(f.hasta);
            const yHasta = y.getPixelForValue(f.desde);
            ctx.fillStyle = scoFranjaColorFondo(f.clase);
            ctx.fillRect(chartArea.left, yDesde, chartArea.right - chartArea.left, yHasta - yDesde);
        });
        ctx.restore();
    },
};

function scoFechaCorta(iso) {
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y.slice(2)}`;
}
function scoFechaLarga(iso) {
    return iso.split('-').reverse().join('/');
}

function scoIconoDireccion(direccion) {
    if (direccion === 'sube') {
        return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="4,17 10,11 14,15 20,7"/><polyline points="14,7 20,7 20,13"/></svg>`;
    }
    if (direccion === 'baja') {
        return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="4,7 10,13 14,9 20,17"/><polyline points="14,17 20,17 20,11"/></svg>`;
    }
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="5"/></svg>`;
}

// Concepto de mayor magnitud (positiva o negativa) del desglose de ese
// día — es el motivo principal que explica el movimiento, en una sola
// frase corta. Se excluyen las filas puramente mecánicas ("Base", el
// clampeo final "Ajuste de rango"): nunca son la CAUSA de nada, son
// housekeeping numérico, y mostrarlas como "motivo" confundiría más de
// lo que explica. "Tope por mora activa" sí queda adentro — a diferencia
// del ajuste de rango, ese sí es una causa real (explica por qué la
// caída fue tan grande).
function scoMotivoPrincipal(desglose) {
    const filas = (desglose || []).filter(d =>
        d.concepto !== 'Base' && !d.concepto.startsWith('Ajuste de rango') && d.puntos !== 0);
    if (!filas.length) return null;
    return filas.reduce((peor, d) => Math.abs(d.puntos) > Math.abs(peor.puntos) ? d : peor);
}

function scoEstiloBanda(clase) {
    if (clase === 'excelente' || clase === 'bueno') return 'success';
    if (clase === 'regular') return 'warning';
    return 'danger'; // riesgo, critico
}

let scoChart = null;
let scoPuntosTodos = [];   // dataset completo, nunca se filtra in-place
let scoPuntos = [];        // subconjunto actualmente mostrado (según el filtro de rango)
let scoRangoActual = 'todo';
let scoSeleccionado = -1;

function initChartScoringHistorial(puntos) {
    const el = document.getElementById('chartScoringHistorial');
    if (!el || !puntos.length) return;

    scoPuntosTodos = puntos;
    scoRenderizarLeyenda();
    scoRenderizarFiltro();
    scoAplicarFiltro('todo');
}

// Filtra `scoPuntosTodos` por antigüedad y vuelve a dibujar todo lo que
// depende del rango — pensado para cuando el historial crezca con los
// años y ya no entre cómodo de un vistazo en un solo gráfico.
function scoAplicarFiltro(rangoId) {
    scoRangoActual = rangoId;
    scoRenderizarFiltro();

    const filtro = SCO_FILTROS_RANGO.find(f => f.id === rangoId);
    if (!filtro || filtro.dias === null) {
        scoPuntos = scoPuntosTodos;
    } else {
        const corte = new Date();
        corte.setDate(corte.getDate() - filtro.dias);
        scoPuntos = scoPuntosTodos.filter(p => new Date(p.fecha + 'T00:00:00') >= corte);
    }

    if (!scoPuntos.length) {
        if (scoChart) { scoChart.destroy(); scoChart = null; }
        document.getElementById('chartSinDatosRango').style.display = '';
        document.getElementById('chartScoringHistorial').style.display = 'none';
        document.getElementById('scoResumen').innerHTML = '';
        document.getElementById('scoEventosLista').innerHTML = '';
        document.getElementById('scoHistDesglose').innerHTML = '';
        return;
    }

    document.getElementById('chartSinDatosRango').style.display = 'none';
    document.getElementById('chartScoringHistorial').style.display = '';

    scoConstruirChart(scoPuntos);
    scoRenderizarResumen(scoPuntos);
    scoRenderizarEventos(scoPuntos);
    scoSeleccionar(scoPuntos.length - 1);
}

function scoRenderizarFiltro() {
    const cont = document.getElementById('scoFiltroRango');
    if (!cont) return;
    cont.innerHTML = SCO_FILTROS_RANGO.map(f => `
        <button type="button" class="sco-filtro-btn${f.id === scoRangoActual ? ' sco-filtro-btn--activo' : ''}"
                onclick="scoAplicarFiltro('${f.id}')">${f.label}</button>
    `).join('');
}

function scoConstruirChart(puntos) {
    if (scoChart) { scoChart.destroy(); scoChart = null; }
    const el = document.getElementById('chartScoringHistorial');
    if (!el) return;

    scoChart = new Chart(el, {
        type: 'line',
        data: {
            labels: puntos.map(p => scoFechaCorta(p.fecha)),
            datasets: [{
                label: 'Scoring',
                data: puntos.map(p => p.score),
                borderColor: '#F26A1B',
                backgroundColor: 'rgba(242,106,27,.08)',
                borderWidth: 2,
                pointRadius: puntos.map(() => 4),
                pointHoverRadius: 7,
                pointBackgroundColor: puntos.map(p => SCO_BANDA_COLOR[p.banda] || '#F26A1B'),
                pointBorderColor: puntos.map(() => '#fff'),
                pointBorderWidth: 2,
                tension: 0.25,
                fill: true,
            }],
        },
        plugins: [scoFondoFranjasPlugin],
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
                        title: (items) => scoFechaLarga(puntos[items[0].dataIndex].fecha),
                        label: (ctx) => `Scoring: ${ctx.parsed.y} pts (${puntos[ctx.dataIndex].banda_label})`,
                        afterLabel: (ctx) => {
                            const lineas = [];
                            const i = ctx.dataIndex;
                            if (i > 0) {
                                const delta = puntos[i].score - puntos[i - 1].score;
                                if (delta > 0) lineas.push(`▲ Subió ${delta} pts desde el punto anterior`);
                                else if (delta < 0) lineas.push(`▼ Bajó ${Math.abs(delta)} pts desde el punto anterior`);
                            } else {
                                lineas.push('Primer punto de este rango');
                            }
                            if (puntos[i].es_actual) lineas.push('Vigente ahora — todavía no se guardó como punto');
                            else if (puntos[i].es_backfill) lineas.push('Estimado a partir del historial real');
                            return lineas;
                        },
                    },
                },
            },
            onClick: (evt, elements) => {
                if (!elements.length) return;
                scoSeleccionar(elements[0].index);
            },
        },
    });
}

function scoPill(punto) {
    if (punto.es_actual) {
        return '<span class="cp-pill" title="Es el valor vigente ahora mismo — todavía nadie disparó un recálculo hoy que lo guarde como punto real">Hoy · sin guardar aún</span>';
    }
    if (punto.es_backfill) {
        return '<span class="cp-pill" title="Reconstruido a partir de fechas reales de cuotas y cheques — no fue registrado en el momento">Estimado</span>';
    }
    return '';
}

// Franjas de color + su rango — para que nadie tenga que adivinar qué
// significa cada color del gráfico. No depende del filtro de rango (los
// umbrales de banda son siempre los mismos), se pinta una sola vez.
function scoRenderizarLeyenda() {
    const cont = document.getElementById('scoLeyenda');
    if (!cont) return;
    cont.innerHTML = SCO_BANDAS_DEF.map(f => `
        <span class="sco-leyenda-item">
            <i class="sco-leyenda-dot" style="background:${SCO_BANDA_COLOR[f.clase]}"></i>
            ${f.label} <span class="sco-leyenda-rango">${f.desde}-${f.hasta}</span>
        </span>
    `).join('');
}

// Mejor momento, peor momento, cuántas subidas/bajadas, tendencia
// reciente — todo lo que se pueda recopilar del historial en un vistazo,
// arriba del gráfico. Mismo markup .est-mini-stat que ya usa el resto de
// la página (comportamiento de pago) — cero CSS nuevo para esto. Se
// recalcula sobre el rango actualmente filtrado, no siempre sobre todo
// el historial.
function scoRenderizarResumen(puntos) {
    const cont = document.getElementById('scoResumen');
    if (!cont) return;

    const mejor = puntos.reduce((a, b) => b.score >= a.score ? b : a);
    const peor = puntos.reduce((a, b) => b.score <= a.score ? b : a);

    let subidas = 0, bajadas = 0;
    for (let i = 1; i < puntos.length; i++) {
        const d = puntos[i].score - puntos[i - 1].score;
        if (d > 0) subidas++; else if (d < 0) bajadas++;
    }

    let tendenciaTexto = 'Sin cambios todavía';
    let tendenciaEstilo = '';
    if (puntos.length > 1) {
        const delta = puntos[puntos.length - 1].score - puntos[puntos.length - 2].score;
        if (delta > 0) { tendenciaTexto = `Mejorando (+${delta} pts)`; tendenciaEstilo = 'success'; }
        else if (delta < 0) { tendenciaTexto = `Empeorando (${delta} pts)`; tendenciaEstilo = 'danger'; }
        else tendenciaTexto = 'Estable';
    }

    const stat = (valor, label, estilo) => `
        <div class="est-mini-stat${estilo ? ' est-mini-stat--' + estilo : ''}">
            <div class="est-mini-stat-valor">${valor}</div>
            <div class="est-mini-stat-label">${label}</div>
        </div>`;

    cont.innerHTML = `
        ${stat(`${mejor.score}`, `Mejor momento (${mejor.banda_label}) · ${scoFechaLarga(mejor.fecha)}`, 'success')}
        ${stat(`${peor.score}`, `Peor momento (${peor.banda_label}) · ${scoFechaLarga(peor.fecha)}`, scoEstiloBanda(peor.banda))}
        ${stat(`${subidas} / ${bajadas}`, 'Veces que subió / que bajó')}
        ${stat(tendenciaTexto, 'Tendencia más reciente', tendenciaEstilo)}
    `;
}

// Sincroniza gráfico + lista de eventos + panel de desglose sobre el
// mismo punto (índice dentro de `scoPuntos`, el subconjunto filtrado
// actual) — se llama desde un click/Enter en el gráfico o en la lista.
function scoSeleccionar(index) {
    scoSeleccionado = index;
    const punto = scoPuntos[index];
    if (!punto) return;

    if (scoChart) {
        const ds = scoChart.data.datasets[0];
        ds.pointRadius = scoPuntos.map((_, i) => i === index ? 8 : 4);
        ds.pointBorderColor = scoPuntos.map((_, i) => i === index ? '#0b0b0b' : '#fff');
        ds.pointBorderWidth = scoPuntos.map((_, i) => i === index ? 3 : 2);
        scoChart.update();
    }

    document.querySelectorAll('.sco-evento-row').forEach(row => {
        row.classList.toggle('sco-evento-row--activo', Number(row.dataset.index) === index);
    });

    scoRenderizarDesglose(punto);
}

// Activa la fila con el teclado (Enter/Espacio) — las filas son
// role="button" pero antes solo reaccionaban al mouse.
function scoEventoKeydown(evt, index) {
    if (evt.key === 'Enter' || evt.key === ' ') {
        evt.preventDefault();
        scoSeleccionar(index);
    }
}

// Lista en texto plano, más reciente primero: fecha, dirección, cuántos
// puntos, y el motivo principal — la respuesta directa a "cuándo subió,
// cuándo bajó, cuánto, por qué".
function scoRenderizarEventos(puntos) {
    const cont = document.getElementById('scoEventosLista');
    if (!cont) return;

    const filas = puntos.map((p, i) => {
        const previo = i > 0 ? puntos[i - 1] : null;
        const delta = previo ? p.score - previo.score : null;
        const direccion = delta === null ? 'inicio' : (delta > 0 ? 'sube' : (delta < 0 ? 'baja' : 'igual'));
        const motivo = scoMotivoPrincipal(p.desglose);

        let textoPrincipal;
        if (direccion === 'inicio') {
            textoPrincipal = `Primer punto de este rango — quedó en <strong>${p.score}</strong> (${p.banda_label})`;
        } else if (direccion === 'igual') {
            textoPrincipal = `Se recalculó, sin cambios — sigue en <strong>${p.score}</strong>`;
        } else {
            const signo = delta > 0 ? '+' : '';
            textoPrincipal = `${direccion === 'sube' ? 'Subió' : 'Bajó'} de ${previo.score} a <strong>${p.score}</strong> (${signo}${delta} pts)`;
        }

        return { i, p, direccion, motivo, textoPrincipal };
    });

    cont.innerHTML = filas.slice().reverse().map(f => `
        <div class="sco-evento-row sco-evento-row--${f.direccion}" data-index="${f.i}"
             onclick="scoSeleccionar(${f.i})" onkeydown="scoEventoKeydown(event, ${f.i})"
             role="button" tabindex="0">
            <div class="sco-evento-icono">${scoIconoDireccion(f.direccion)}</div>
            <div class="sco-evento-cuerpo">
                <div class="sco-evento-fecha">${scoFechaLarga(f.p.fecha)} ${scoPill(f.p)}</div>
                <div class="sco-evento-texto">${f.textoPrincipal}</div>
                ${f.motivo ? `<div class="sco-evento-motivo">Motivo principal: ${f.motivo.concepto} (${f.motivo.puntos > 0 ? '+' : ''}${f.motivo.puntos})</div>` : ''}
            </div>
        </div>
    `).join('');
}

// Desglose del punto seleccionado como gráfico de cascada: una barra por
// concepto, verde hacia la derecha si suma, roja hacia la izquierda si
// resta, escaladas todas contra la de mayor magnitud de ESE desglose
// (sin contar "Base", que se muestra aparte como punto de partida) — se
// ve de un vistazo qué pesó más, sin tener que comparar números.
function scoRenderizarDesglose(punto) {
    const cont = document.getElementById('scoHistDesglose');
    if (!cont) return;

    const fecha = scoFechaLarga(punto.fecha);
    const filas = (punto.desglose || []).filter(d => d.concepto !== 'Base');
    const base = (punto.desglose || []).find(d => d.concepto === 'Base');
    const maxAbs = Math.max(1, ...filas.map(d => Math.abs(d.puntos)));

    const filasHtml = filas.map(d => {
        const pos = d.puntos >= 0;
        const pct = Math.min(50, Math.abs(d.puntos) / maxAbs * 50);
        return `
        <div class="sco-wf-row">
            <div class="sco-wf-label">${d.concepto}${d.detalle ? `<span class="sco-wf-detalle">${d.detalle}</span>` : ''}</div>
            <div class="sco-wf-barzone">
                <div class="sco-wf-zero"></div>
                <div class="sco-wf-bar ${pos ? 'pos' : 'neg'}" style="${pos ? 'left' : 'right'}:50%; width:${pct}%;"></div>
            </div>
            <div class="sco-wf-val ${pos ? 'sco-pos' : 'sco-neg'}">${pos ? '+' : ''}${d.puntos}</div>
        </div>`;
    }).join('');

    cont.innerHTML = `
        <div class="sco-hist-desglose-header">
            <strong>${fecha}</strong>
            <span class="sco-badge sco-badge--${punto.banda}">${punto.banda_label}</span>
            <span class="sco-hist-desglose-score">${punto.score} / 1000</span>
            ${scoPill(punto)}
        </div>
        ${base ? `<div class="sco-wf-base">Base: ${base.puntos} puntos iniciales</div>` : ''}
        <div class="sco-wf-list">${filasHtml || '<div class="sco-wf-base">Sin ajustes ese día — quedó en el puntaje base.</div>'}</div>
    `;
}
