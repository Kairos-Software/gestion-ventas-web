/**
 * panel_cobro.js — columna de cobro anclada sobre /ventas/nueva/
 *
 * El carrito (nueva_venta.js) es LA pantalla; todo el detalle borrador
 * (fecha, cliente, medios de pago, facturación, confirmar, tickets) vive
 * en una columna FIJA a la derecha, siempre visible. No flota, no se
 * arrastra, no se minimiza ni se oculta.
 *
 * La columna arranca con un placeholder. Apenas se agrega el primer
 * producto al carrito, se guarda el borrador y se trae el fragmento
 * (CobroFragmentoAjax → _panel_cobro_*.html + _detalle_venta_datos.html
 * + _detalle_venta_modales.html), que maneja el mismo detalle_venta.js
 * de siempre vía window.initDetalleVenta().
 *
 * Requiere: window.VTA_CONFIG, window.ventaCarrito (nueva_venta.js),
 * window.initDetalleVenta (detalle_venta.js).
 */
'use strict';

(function () {

    const CFG = window.VTA_CONFIG || {};

    const panel = document.getElementById('vtaPanelCobro');
    const body  = document.getElementById('vtaPanelCobroBody');
    if (!panel || !body) return;   // sin permiso 'crear_ventas' → no se renderiza

    const PLACEHOLDER_HTML = body.innerHTML;   // el placeholder ya está en el template

    const estado = {
        ventaPk:    CFG.ventaEditarPk || null,  // borrador vivo de esta sesión
        confirmada: false,                      // ya se confirmó → no se re-sincroniza
        montado:    false,                      // el fragmento está cargado e inicializado
        montando:   false,                      // guarda contra montar dos veces a la vez
    };

    // ── Toast (reusa el de nueva_venta.js si está) ──
    function toast(titulo, cuerpo) {
        const t = document.getElementById('vtaToast');
        if (t) {
            document.getElementById('vtaToastTitle').textContent = titulo;
            document.getElementById('vtaToastBody').textContent = cuerpo || '';
            t.classList.add('show');
            clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 3500);
        } else {
            console.warn('[panel_cobro]', titulo, cuerpo);
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  RE-EJECUTAR <script> del fragmento inyectado
    //  (innerHTML no ejecuta scripts — hay que recrearlos)
    // ══════════════════════════════════════════════════════════════
    function reejecutarScripts(root) {
        root.querySelectorAll('script').forEach(viejo => {
            const s = document.createElement('script');
            for (const a of viejo.attributes) s.setAttribute(a.name, a.value);
            s.textContent = viejo.textContent;
            viejo.replaceWith(s);
        });
    }

    async function traerFragmento(pk) {
        // ?_=<ts> — el fragmento refleja el estado vivo del borrador, nunca
        // se debe servir de la caché del navegador.
        const res  = await fetch(CFG.urlCobroFragmento + pk + '/?_=' + Date.now(), { cache: 'no-store' });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'No se pudo traer el panel de cobro.');
        body.innerHTML = data.html;
        reejecutarScripts(body);          // corre VDT_CONFIG / TICKET_DATA / data blocks
        if (typeof window.initDetalleVenta === 'function') window.initDetalleVenta();
        estado.montado = true;
        estado.confirmada = (data.estado === 'confirmada');
        return data;
    }

    // ══════════════════════════════════════════════════════════════
    //  MONTAR — guarda el borrador y trae el fragmento. Se dispara solo
    //  la primera vez que el carrito tiene algo (o al cargar en modo
    //  edición). No hay botón: la columna ya está a la vista.
    // ══════════════════════════════════════════════════════════════
    async function montar() {
        if (estado.montado || estado.montando || estado.confirmada) return;
        if (window.ventaCarrito.estaVacio()) return;
        estado.montando = true;
        try {
            const guardado = await window.ventaCarrito.guardarBorrador(estado.ventaPk);
            if (!guardado.ok) {
                toast('No se pudo iniciar el cobro', guardado.error || 'Intentá de nuevo.');
                return;
            }
            estado.ventaPk = guardado.pk;
            await traerFragmento(estado.ventaPk);
        } catch (e) {
            toast('Error de conexión', e.message || 'Intentá de nuevo.');
        } finally {
            estado.montando = false;
        }
        // El carrito puede haber cambiado mientras montábamos (se agregaron
        // más productos): reconciliamos el borrador y el total del panel.
        if (estado.montado && !window.ventaCarrito.estaVacio()) onCartChange();
    }

    // ══════════════════════════════════════════════════════════════
    //  SINCRONIZACIÓN CON EL CARRITO
    //  Cada cambio del carrito: si todavía no se montó y ya hay ítems,
    //  monta; si ya está montado, re-guarda el borrador y actualiza el
    //  total del panel conservando las líneas de pago cargadas.
    // ══════════════════════════════════════════════════════════════
    let syncTimer = null;
    function onCartChange() {
        if (estado.confirmada) return;

        if (!estado.montado) { montar(); return; }
        if (!estado.ventaPk) return;

        clearTimeout(syncTimer);
        syncTimer = setTimeout(async () => {
            if (window.ventaCarrito.estaVacio()) return;
            try {
                const data = await window.ventaCarrito.guardarBorrador(estado.ventaPk);
                if (data.ok && typeof window.detalleVentaSetTotal === 'function') {
                    window.detalleVentaSetTotal(data.total);
                }
            } catch { /* reintenta en el próximo cambio */ }
        }, 450);
    }

    // ══════════════════════════════════════════════════════════════
    //  HOOKS que llama detalle_venta.js
    // ══════════════════════════════════════════════════════════════
    window.panelCobroOnConfirmada = async function (data) {
        estado.confirmada = true;
        if (data && data.factura_error) {
            toast('Venta confirmada — no se pudo facturar', data.factura_error);
        }
        try {
            await traerFragmento(estado.ventaPk);   // ahora trae el panel "confirmada"
        } catch (e) {
            toast('Error', e.message);
        }
        _wireConfirmada();
    };

    window.panelCobroRefrescar = async function () {
        if (!estado.ventaPk) return;
        try {
            await traerFragmento(estado.ventaPk);
            if (estado.confirmada) _wireConfirmada();
        } catch (e) { toast('Error', e.message); }
    };

    // "Cancelar venta" dentro del panel — detalle_venta.js ya borró el
    // borrador; acá solo reseteamos la pantalla, sin recargar.
    window.panelCobroOnCancelada = function () {
        _resetTodo();
    };

    function _wireConfirmada() {
        body.querySelector('#vdtBtnNuevaVentaPanel')?.addEventListener('click', nuevaVenta);
        body.querySelector('#vdtBtnEditarVentaPanel')?.addEventListener('click', editarVentaConfirmada);
    }

    // ══════════════════════════════════════════════════════════════
    //  EDITAR VENTA CONFIRMADA — sin salir de la pantalla: anula (revierte
    //  stock; el modelo ya bloquea solo si hay comprobante ARCA, cheques o
    //  devoluciones de por medio), reactiva como borrador y recarga esta
    //  misma página en modo edición (?editar=pk), igual que "Editar" desde
    //  el Historial — ver ventas/static/ventas/js/historial_ventas.js.
    // ══════════════════════════════════════════════════════════════
    async function editarVentaConfirmada() {
        const pk = estado.ventaPk;
        if (!pk) return;

        const ok = await window.KaiConfirm(
            'Se va a reabrir esta venta para agregar o quitar productos. Vas a tener que confirmarla de nuevo.',
            { title: 'Editar esta venta', confirmText: 'Sí, editar' }
        );
        if (!ok) return;

        const btn = body.querySelector('#vdtBtnEditarVentaPanel');
        if (btn) btn.disabled = true;

        try {
            const post = (url) => fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                body: JSON.stringify({ pk }),
            }).then(r => r.json());

            const anulado = await post(CFG.urlAnular);
            if (!anulado.ok) {
                toast('No se pudo editar la venta', anulado.error || 'Intentá de nuevo.');
                return;
            }
            const reactivado = await post(CFG.urlReactivar);
            if (!reactivado.ok) {
                toast('No se pudo editar la venta', reactivado.error || 'Intentá de nuevo.');
                return;
            }
            window.location.href = window.location.pathname + '?editar=' + pk;
        } catch (e) {
            toast('Error de conexión', e.message || 'Intentá de nuevo.');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  NUEVA VENTA / RESET
    // ══════════════════════════════════════════════════════════════
    function _resetTodo() {
        estado.ventaPk = null;
        estado.confirmada = false;
        estado.montado = false;
        estado.montando = false;
        window.ventaCarrito.reset();
        body.innerHTML = PLACEHOLDER_HTML;
        document.getElementById('vtaSearchInput')?.focus();
    }

    async function nuevaVenta() {
        if (estado.ventaPk && !estado.confirmada) {
            try {
                await fetch(CFG.urlEliminarBorrador, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrfToken },
                    body: JSON.stringify({ venta_pk: estado.ventaPk }),
                });
            } catch { /* el barrido de borradores vencidos lo limpia igual */ }
        }
        _resetTodo();
    }

    // ══════════════════════════════════════════════════════════════
    //  WIRING
    // ══════════════════════════════════════════════════════════════
    // "Ir al cobro" del pie del carrito: en desktop la columna ya está a
    // la vista (solo enfoca); en pantalla angosta baja el scroll hasta ella.
    document.getElementById('vtaBtnCobrar')?.addEventListener('click', () => {
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        setTimeout(() => {
            (body.querySelector('#vdtPagoLineas .vdt-pago-monto')
                || body.querySelector('#vdtFecha')
                || body.querySelector('input, select, button'))?.focus();
        }, 220);
    });

    if (window.ventaCarrito && typeof window.ventaCarrito.onChange === 'function') {
        window.ventaCarrito.onChange(onCartChange);
    }

    // F4 confirma (si el botón del fragmento está habilitado).
    document.addEventListener('keydown', e => {
        if (e.key === 'F4') {
            e.preventDefault();
            const btn = body.querySelector('#vdtBtnConfirmar');
            if (btn && !btn.disabled) btn.click();
        }
    });

    // Modo edición (?editar=<pk>) o cualquier carrito ya cargado al abrir
    // la página: montar sin esperar un cambio.
    if (!window.ventaCarrito.estaVacio()) montar();

    window.panelCobro = { montar, nuevaVenta };
})();
