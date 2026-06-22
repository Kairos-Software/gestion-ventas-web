document.addEventListener('DOMContentLoaded', function () {
    const urls = window.gastosUrls;
    const today = window.gastosToday;
    
    // Construir URLs base reemplazando el placeholder 0
    const urlEditarBase = urls.editar.replace('/0/', '/');
    const urlEliminarBase = urls.eliminar.replace('/0/', '/');
    
    let paginaActual = 1;
    let porPagina = 50;
    
    // ── Elementos DOM ───────────────────────────────────────────────
    const btnNuevoGasto = document.getElementById('btnNuevoGasto');
    const btnToggleFiltros = document.getElementById('btnToggleFiltros');
    const formFiltros = document.getElementById('formFiltros');
    const btnLimpiarFiltros = document.getElementById('btnLimpiarFiltros');
    const gastosBody = document.getElementById('gastosBody');
    const paginacionContainer = document.getElementById('paginacionContainer');
    
    // Modal
    const modalGasto = document.getElementById('modalGasto');
    const modalBackdrop = document.getElementById('modalBackdrop');
    const btnCerrarModal = document.getElementById('btnCerrarModal');
    const btnCancelarModal = document.getElementById('btnCancelarModal');
    const formGasto = document.getElementById('formGasto');
    const modalTitle = document.getElementById('modalTitle');
    const btnGuardarGasto = document.getElementById('btnGuardarGasto');
    
    // ── Cargar gastos ───────────────────────────────────────────────
    async function cargarGastos() {
        const params = new URLSearchParams({
            pagina: paginaActual,
            por_pagina: porPagina,
            ...getFiltrosActivos(),
        });
        
        try {
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();
            
            renderizarGastos(data.results);
            renderizarPaginacion(data.total, data.pagina, data.por_pagina);
        } catch (error) {
            console.error('Error al cargar gastos:', error);
            gastosBody.innerHTML = '<tr><td colspan="7" class="gastos-tabla-loading">Error al cargar gastos</td></tr>';
        }
    }
    
    function getFiltrosActivos() {
        const desde = document.getElementById('fDesde').value;
        const hasta = document.getElementById('fHasta').value;
        const moneda = document.getElementById('fMoneda').value;
        const q = document.getElementById('fQ').value;
        
        const filtros = {};
        if (desde) filtros.desde = desde;
        if (hasta) filtros.hasta = hasta;
        if (moneda) filtros.moneda = moneda;
        if (q) filtros.q = q;
        
        return filtros;
    }
    
    function renderizarGastos(gastos) {
        if (!gastos || gastos.length === 0) {
            gastosBody.innerHTML = '<tr><td colspan="7" class="gastos-tabla-loading">No hay gastos registrados</td></tr>';
            return;
        }
        
        gastosBody.innerHTML = gastos.map(g => `
            <tr>
                <td>${g.fecha}</td>
                <td>${g.hora}</td>
                <td>${g.descripcion || '-'}</td>
                <td class="gastos-monto">${g.monto}</td>
                <td>${g.moneda}</td>
                <td>${g.creado_por || '-'}</td>
                <td>
                    <div class="gastos-tabla-acciones">
                        <button type="button" class="icon-btn" onclick="editarGasto(${g.pk})" title="Editar">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M2.5 13.5L13.5 2.5M13.5 2.5V7.5M13.5 2.5H8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        </button>
                        <button type="button" class="icon-btn" onclick="eliminarGasto(${g.pk})" title="Eliminar">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                                <path d="M3 3L13 13M3 13L13 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }
    
    function renderizarPaginacion(total, pagina, porPagina) {
        const totalPaginas = Math.ceil(total / porPagina);
        
        if (totalPaginas <= 1) {
            paginacionContainer.innerHTML = '';
            return;
        }
        
        let html = '<span class="gastos-paginacion-info">Página ' + pagina + ' de ' + totalPaginas + ' (' + total + ' registros)</span>';
        
        html += '<div class="gastos-paginacion-botones">';
        
        if (pagina > 1) {
            html += '<button type="button" class="btn btn-ghost btn--sm" onclick="cambiarPagina(' + (pagina - 1) + ')">Anterior</button>';
        }
        
        if (pagina < totalPaginas) {
            html += '<button type="button" class="btn btn-ghost btn--sm" onclick="cambiarPagina(' + (pagina + 1) + ')">Siguiente</button>';
        }
        
        html += '</div>';
        paginacionContainer.innerHTML = html;
    }
    
    window.cambiarPagina = function (nuevaPagina) {
        paginaActual = nuevaPagina;
        cargarGastos();
    };
    
    // ── Modal ───────────────────────────────────────────────────────
    function abrirModal(titulo = 'Nuevo gasto') {
        modalTitle.textContent = titulo;
        modalGasto.hidden = false;
        document.body.style.overflow = 'hidden';
    }
    
    function cerrarModal() {
        modalGasto.hidden = true;
        document.body.style.overflow = '';
        formGasto.reset();
        document.getElementById('gastoPk').value = '';
        document.getElementById('gFecha').value = today;
    }
    
    btnNuevoGasto.addEventListener('click', () => {
        document.getElementById('gFecha').value = today;
        abrirModal('Nuevo gasto');
    });
    
    btnCerrarModal.addEventListener('click', cerrarModal);
    btnCancelarModal.addEventListener('click', cerrarModal);
    modalBackdrop.addEventListener('click', cerrarModal);
    
    // ── Crear/Editar gasto ───────────────────────────────────────────
    formGasto.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const pk = document.getElementById('gastoPk').value;
        const formData = new FormData(formGasto);
        const data = Object.fromEntries(formData.entries());
        
        btnGuardarGasto.disabled = true;
        
        try {
            const url = pk ? `${urlEditarBase}${pk}/` : urls.crear;
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify(data),
            });
            
            const result = await response.json();
            
            if (result.success) {
                cerrarModal();
                cargarGastos();
            } else {
                alert(result.error || 'Error al guardar gasto');
            }
        } catch (error) {
            console.error('Error al guardar gasto:', error);
            alert('Error al guardar gasto');
        } finally {
            btnGuardarGasto.disabled = false;
        }
    });
    
    window.editarGasto = async function (pk) {
        try {
            const params = new URLSearchParams(getFiltrosActivos());
            const response = await fetch(`${urls.listar}?${params}`);
            const data = await response.json();
            
            const gasto = data.results.find(g => g.pk === pk);
            if (!gasto) {
                alert('Gasto no encontrado');
                return;
            }
            
            document.getElementById('gastoPk').value = gasto.pk;
            document.getElementById('gFecha').value = gasto.fecha;
            document.getElementById('gMonto').value = gasto.monto;
            document.getElementById('gMoneda').value = gasto.moneda;
            document.getElementById('gDescripcion').value = gasto.descripcion;
            
            abrirModal('Editar gasto');
        } catch (error) {
            console.error('Error al cargar gasto:', error);
            alert('Error al cargar gasto');
        }
    };
    
    window.eliminarGasto = async function (pk) {
        if (!confirm('¿Estás seguro de eliminar este gasto?')) {
            return;
        }
        
        try {
            const response = await fetch(`${urlEliminarBase}${pk}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                },
            });
            
            const result = await response.json();
            
            if (result.success) {
                cargarGastos();
            } else {
                alert(result.error || 'Error al eliminar gasto');
            }
        } catch (error) {
            console.error('Error al eliminar gasto:', error);
            alert('Error al eliminar gasto');
        }
    };
    
    // ── Filtros ────────────────────────────────────────────────────
    btnToggleFiltros.addEventListener('click', () => {
        const expanded = btnToggleFiltros.getAttribute('aria-expanded') === 'true';
        btnToggleFiltros.setAttribute('aria-expanded', !expanded);
        formFiltros.hidden = expanded;
    });
    
    formFiltros.addEventListener('submit', (e) => {
        e.preventDefault();
        paginaActual = 1;
        cargarGastos();
    });
    
    btnLimpiarFiltros.addEventListener('click', () => {
        formFiltros.reset();
        paginaActual = 1;
        cargarGastos();
    });
    
    // ── Helpers ─────────────────────────────────────────────────────
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }
    
    // ── Inicialización ─────────────────────────────────────────────
    cargarGastos();
});
