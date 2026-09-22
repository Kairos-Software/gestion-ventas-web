document.addEventListener('DOMContentLoaded', function () {
    const urls = window.resumenesTarjetaUrls;
    const wrap = document.getElementById('resumenesTarjetaWrap');
    if (!urls || !wrap) return;

    function fmtMoneda(v, moneda) {
        return `$ ${parseFloat(v || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${moneda || ''}`.trim();
    }

    function fmtFecha(fechaIso) {
        if (!fechaIso) return '—';
        const partes = String(fechaIso).split('-').map(Number);
        if (partes.length !== 3 || partes.some(Number.isNaN)) return fechaIso;
        return new Intl.DateTimeFormat('es-AR').format(new Date(partes[0], partes[1] - 1, partes[2]));
    }

    function esc(str) {
        return String(str == null ? '' : str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    function renderTarjeta(r) {
        const estadoLabel = { pendiente: 'Pendiente', parcial: 'Pago parcial', pagado: 'Pagado' }[r.estado] || r.estado_display;
        return `
            <a class="deudas-resumen-card" href="${urls.pagina}?resumen=${r.pk}">
                <div class="deudas-resumen-card-top">
                    <span class="deudas-resumen-card-tarjeta">${esc(r.cuenta_tarjeta_nombre)}</span>
                    <span class="deudas-badge-estado deudas-badge-estado--${r.estado}">${estadoLabel}</span>
                </div>
                <div class="deudas-resumen-card-periodo">${esc(r.periodo_label)}</div>
                <div class="deudas-resumen-card-monto">${fmtMoneda(r.monto_total, r.moneda)}</div>
                <div class="deudas-resumen-card-meta">${r.fecha_vencimiento ? 'Vence ' + fmtFecha(r.fecha_vencimiento) : 'Configurá el día de vencimiento en la tarjeta'}</div>
            </a>
        `;
    }

    async function cargarResumenes() {
        try {
            const response = await fetch(urls.listar);
            const data = await response.json();
            const results = data.results || [];
            // Acá solo interesa "lo próximo a pagar" de cada tarjeta — un
            // negocio suele tener pocas tarjetas, así que esto se mantiene
            // compacto sin importar cuántos meses/cuotas tenga cada una. El
            // historial completo (pagados, filtros) vive en la pantalla
            // dedicada (ver botón "Ver todos").
            // Un resumen de un mes que todavía no llegó no tiene nada que
            // pagar todavía (recién se termina de armar a medida que vencen
            // cuotas ese mes) — no tiene sentido mostrarlo acá apenas se
            // paga el de este mes. Solo se destaca lo que ya venció o vence
            // este mes; lo de meses futuros se ve en la pantalla dedicada.
            const hoy = new Date();
            const hoyPeriodo = hoy.getFullYear() * 12 + hoy.getMonth();
            const vistos = new Set();
            const destacados = [];
            for (const r of results) {
                if (r.estado === 'pagado' || vistos.has(r.cuenta_tarjeta_pk)) continue;
                if ((r.anio * 12 + (r.mes - 1)) > hoyPeriodo) continue;
                vistos.add(r.cuenta_tarjeta_pk);
                destacados.push(r);
            }
            if (destacados.length === 0) {
                wrap.innerHTML = '<p class="deudas-tabla-loading">No hay resúmenes de tarjeta pendientes.</p>';
                return;
            }
            wrap.innerHTML = `<div class="deudas-resumenes-grid">${destacados.map(renderTarjeta).join('')}</div>`;
        } catch (error) {
            wrap.innerHTML = '<p class="deudas-tabla-loading">Error al cargar los resúmenes.</p>';
            console.error('Error al cargar resúmenes de tarjeta:', error);
        }
    }

    cargarResumenes();
});
