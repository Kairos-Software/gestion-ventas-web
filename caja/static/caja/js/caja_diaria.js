let cdEfectivoEsperado = 0;
let cdFilaIdx = { abrir: 0, cerrar: 0 };

// ══════════════════════════════════════════════════════════════════
//  FILAS DINÁMICAS DE CAJAS FÍSICAS (abrir y cerrar comparten lógica)
// ══════════════════════════════════════════════════════════════════

function cdCrearFilaCaja(modo, nombre, monto, cajaId) {
    const idx = cdFilaIdx[modo]++;
    const lista = document.getElementById(`cd-cajas-${modo}-list`);
    const fila = document.createElement('div');
    fila.className = 'cd-caja-fila';
    fila.dataset.idx = idx;
    if (cajaId) fila.dataset.cajaId = cajaId;

    fila.innerHTML = `
        <input type="text" class="vta-control cd-caja-nombre" value="${nombre}" placeholder="Nombre de la caja">
        <div class="cd-caja-monto-wrap">
            <span class="cd-caja-monto-sign">$</span>
            <input type="number" class="vta-control cd-caja-monto" placeholder="0.00" step="0.01" min="0"
                value="${monto !== undefined && monto !== null ? monto : ''}">
        </div>
        <button type="button" class="cd-caja-quitar" onclick="cdQuitarCaja(this, '${modo}')" title="Quitar caja">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
        </button>
    `;
    lista.appendChild(fila);

    fila.querySelector('.cd-caja-monto').addEventListener('input', () => cdActualizarTotales(modo));
    cdActualizarQuitarVisible(modo);
    return fila;
}

function cdAgregarCaja(modo) {
    const cantidadActual = document.querySelectorAll(`#cd-cajas-${modo}-list .cd-caja-fila`).length;
    cdCrearFilaCaja(modo, `Caja ${cantidadActual + 1}`, '');
    cdActualizarTotales(modo);
}

function cdQuitarCaja(btn, modo) {
    const lista = document.getElementById(`cd-cajas-${modo}-list`);
    if (lista.querySelectorAll('.cd-caja-fila').length <= 1) return; // siempre al menos una
    btn.closest('.cd-caja-fila').remove();
    cdActualizarTotales(modo);
    cdActualizarQuitarVisible(modo);
}

function cdActualizarQuitarVisible(modo) {
    const filas = document.querySelectorAll(`#cd-cajas-${modo}-list .cd-caja-fila`);
    filas.forEach(f => {
        f.querySelector('.cd-caja-quitar').style.visibility = filas.length > 1 ? 'visible' : 'hidden';
    });
}

function cdLeerCajas(modo) {
    const filas = document.querySelectorAll(`#cd-cajas-${modo}-list .cd-caja-fila`);
    return Array.from(filas).map((f, i) => ({
        id: f.dataset.cajaId ? parseInt(f.dataset.cajaId, 10) : null,
        nombre: f.querySelector('.cd-caja-nombre').value.trim() || `Caja ${i + 1}`,
        monto: parseFloat(f.querySelector('.cd-caja-monto').value) || 0,
    }));
}

function cdTotalCajas(modo) {
    return cdLeerCajas(modo).reduce((sum, c) => sum + c.monto, 0);
}

function cdActualizarTotales(modo) {
    const total = cdTotalCajas(modo);
    if (modo === 'abrir') {
        document.getElementById('cd-abrir-total').textContent = `$${total.toFixed(2)}`;
    } else {
        document.getElementById('cd-cerrar-total').textContent = `$${total.toFixed(2)}`;
        cdActualizarComparacion();
    }
}

// ══════════════════════════════════════════════════════════════════
//  ABRIR TURNO
// ══════════════════════════════════════════════════════════════════

function cdAbrirTurno() {
    document.getElementById('cd-cajas-abrir-list').innerHTML = '';
    cdFilaIdx.abrir = 0;
    cdCrearFilaCaja('abrir', 'Caja 1', 0);
    cdActualizarTotales('abrir');
    document.getElementById('cd-modal-abrir').style.display = 'flex';
}

async function cdConfirmarAbrir() {
    const cajas = cdLeerCajas('abrir');
    const btn = document.querySelector('#cd-modal-abrir .vta-btn-primary');

    btn.disabled = true;
    btn.textContent = 'Abriendo...';

    try {
        const res = await fetch(CD_URLS.abrir, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CD_URLS.csrf },
            body: JSON.stringify({ cajas: cajas })
        });
        const data = await res.json();
        if (data.ok) { cdCerrarModal('cd-modal-abrir'); location.reload(); }
        else { KaiToast.show(data.error || 'Error al abrir turno', 'danger'); }
    } catch (e) {
        KaiToast.show('Error de conexión', 'danger');
    }

    btn.disabled = false;
    btn.textContent = 'Abrir Turno';
}

// ══════════════════════════════════════════════════════════════════
//  CERRAR TURNO
// ══════════════════════════════════════════════════════════════════

async function cdCerrarTurno() {
    const btn = document.querySelector('.cd-btn-cerrar');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = 'Cargando...';
    }

    try {
        const res = await fetch(CD_URLS.estado);
        const data = await res.json();

        if (data.hay_turno) {
            cdEfectivoEsperado = parseFloat(data.turno.efectivo_total) || 0;

            // Pre-cargar una fila por cada caja declarada en la apertura
            document.getElementById('cd-cajas-cerrar-list').innerHTML = '';
            cdFilaIdx.cerrar = 0;
            const cajasApertura = (data.turno.cajas && data.turno.cajas.length)
                ? data.turno.cajas
                : [{ id: null, nombre: 'Caja 1' }];
            cajasApertura.forEach(c => cdCrearFilaCaja('cerrar', c.nombre, '', c.id));

            document.getElementById('cd-comparacion-cierre').style.display = 'none';
            cdActualizarTotales('cerrar');
            document.getElementById('cd-modal-cerrar').style.display = 'flex';
        } else {
            KaiToast.show('No hay un turno abierto para cerrar.', 'warning');
            setTimeout(() => location.reload(), 1800);
        }
    } catch (e) {
        KaiToast.show('Error al obtener el estado de la caja.', 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8H13M8 3V13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg> Cerrar Turno`;
        }
    }
}

function cdActualizarComparacion() {
    const cajas = cdLeerCajas('cerrar');
    const compBox = document.getElementById('cd-comparacion-cierre');

    if (cajas.length === 0) {
        compBox.style.display = 'none';
        return;
    }

    const declarado = cdTotalCajas('cerrar');
    const esperado = cdEfectivoEsperado;
    const diferencia = declarado - esperado;

    document.getElementById('cd-comp-esperado').textContent = `$${esperado.toFixed(2)}`;
    document.getElementById('cd-comp-declarado').textContent = `$${declarado.toFixed(2)}`;

    const diffEl = document.getElementById('cd-comp-diferencia');
    const labelEl = document.getElementById('cd-comp-estado-lbl');

    compBox.classList.remove('coincide', 'sobra', 'falta');

    if (Math.abs(diferencia) < 0.01) {
        compBox.classList.add('coincide');
        labelEl.textContent = 'Diferencia (Coincide):';
        diffEl.textContent = `$${diferencia.toFixed(2)}`;
    } else if (diferencia > 0) {
        compBox.classList.add('sobra');
        labelEl.textContent = 'Diferencia (Sobra efectivo):';
        diffEl.textContent = `+$${diferencia.toFixed(2)}`;
    } else {
        compBox.classList.add('falta');
        labelEl.textContent = 'Diferencia (Falta efectivo):';
        diffEl.textContent = `-$${Math.abs(diferencia).toFixed(2)}`;
    }

    compBox.style.display = 'flex';
}

function cdCerrarModal(id) {
    document.getElementById(id).style.display = 'none';
}

async function cdConfirmarCerrar() {
    const cajas = cdLeerCajas('cerrar');
    const notas = document.getElementById('cd-notas').value;

    const btn = document.querySelector('#cd-modal-cerrar .vta-btn-primary');
    btn.disabled = true;
    btn.textContent = 'Cerrando...';

    try {
        const res = await fetch(CD_URLS.cerrar, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CD_URLS.csrf },
            body: JSON.stringify({ cajas: cajas, notas: notas })
        });
        const data = await res.json();
        if (data.ok) {
            cdCerrarModal('cd-modal-cerrar');
            // Si hubo diferencia entre lo esperado y lo declarado, se
            // avisa con urgencia ANTES de recargar la página — no se
            // "esconde" silenciosamente detrás de un reload.
            if (data.alerta && data.alerta.hay_diferencia) {
                KaiToast.show(data.alerta.mensaje, 'warning', 3200);
                setTimeout(() => location.reload(), 2600);
            } else {
                location.reload();
            }
        }
        else { KaiToast.show(data.error || 'Error al cerrar turno', 'danger'); }
    } catch (e) {
        KaiToast.show('Error de conexión', 'danger');
    }

    btn.disabled = false;
    btn.textContent = 'Cerrar Turno';
}
