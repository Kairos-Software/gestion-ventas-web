/* carrito.js — carrito de compras client-side (localStorage) + el paso
   de contacto que confirma el Pedido real contra el backend (ver
   catalogo:pedido_crear). Lo único que no existe todavía es lo que pasa
   DESPUÉS de eso (pago/envío) — eso se coordina a mano por WhatsApp. */
(function () {
    'use strict';

    var CLAVE = 'kc_carrito_v1';

    function getCookie(name) {
        var value = '; ' + document.cookie;
        var parts = value.split('; ' + name + '=');
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    /* sessionStorage (no localStorage): sin login, el carrito debe
       arrancar vacío en cada sesión nueva del navegador — si no, dos
       personas distintas usando el mismo navegador/equipo heredarían el
       pedido de la visita anterior. Dentro de la misma sesión (misma
       pestaña, navegando entre páginas) sigue persistiendo con normalidad. */
    function leer() {
        try {
            var datos = JSON.parse(sessionStorage.getItem(CLAVE) || '{}');
            return (datos && typeof datos === 'object') ? datos : {};
        } catch (e) {
            return {};
        }
    }

    function guardar(carrito) {
        try { sessionStorage.setItem(CLAVE, JSON.stringify(carrito)); } catch (e) { /* modo privado, etc. */ }
    }

    function fmt(n) {
        return '$' + Number(n).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }

    function _pkDeId(id) {
        // Un ítem con variante tiene id "prod-{pk}-combo-{combinacion_pk}"
        // — el "-combo-N" se pela antes de sacar el pk, así las ofertas
        // NXM/umbral (que matchean por producto) siguen andando igual.
        return parseInt(String(id).replace(/-combo-\d+$/, '').replace(/^(prod|paq)-/, ''), 10);
    }

    function agregar(id, datos) {
        var carrito = leer();
        var actual = carrito[id] || { cantidad: 0 };
        actual.cantidad += 1;
        actual.nombre = datos.nombre;
        actual.precio = datos.precio;
        actual.precioLista = datos.precioLista;
        actual.categoriaId = datos.categoriaId;
        actual.imagen = datos.imagen;
        actual.combinacionId = datos.combinacionId || null;
        actual.varianteLabel = datos.varianteLabel || '';
        carrito[id] = actual;
        guardar(carrito);
        render();
    }

    function cambiarCantidad(id, delta) {
        var carrito = leer();
        if (!carrito[id]) return;
        carrito[id].cantidad += delta;
        if (carrito[id].cantidad <= 0) delete carrito[id];
        guardar(carrito);
        render();
    }

    function quitar(id) {
        var carrito = leer();
        if (!carrito[id]) return;
        delete carrito[id];
        guardar(carrito);
        render();
    }

    function cantidadEnCarrito(id) {
        var carrito = leer();
        return carrito[id] ? carrito[id].cantidad : 0;
    }

    function totalItems(carrito) {
        return Object.keys(carrito).reduce(function (acc, k) { return acc + carrito[k].cantidad; }, 0);
    }

    /* Ofertas "gastá $X o más y llevate Y% off" (tipo=umbral, automáticas
       — ver window.KC_OFERTAS_UMBRAL en base_catalogo.html). Se resuelven
       acá con el mismo criterio que usa el servidor al crear el pedido
       (ver _resolver_oferta_global en catalogo/views_pedidos.py) para que
       el total que ve el cliente sea el mismo que termina guardado —
       antes esta oferta solo se aplicaba recién al vender internamente. */
    function _mejorOfertaGlobal(subtotal, totalLista) {
        var ofertas = window.KC_OFERTAS_UMBRAL || [];
        var mejor = null;
        for (var i = 0; i < ofertas.length; i++) {
            var o = ofertas[i];
            var monto = o.base_calculo === 'bruto' ? totalLista : subtotal;
            var pct = parseFloat(o.porcentaje) || 0;
            if (monto >= (parseFloat(o.monto_minimo) || 0) && pct > 0 && (!mejor || pct > mejor.pct)) {
                mejor = { nombre: o.nombre, pct: pct };
            }
        }
        return mejor;
    }

    /* Ofertas "llevá X, pagá Y" (NXM, automáticas — ver window.KC_OFERTAS_NXM).
       El % efectivo depende de la cantidad de ESA línea (2x1 con 1 unidad
       no da nada; con 2, sí) — mismo cálculo que Oferta.descuento_equivalente
       en productos/models.py y que _pctEfectivoOferta en ventas/nueva_venta.js.
       Sin esto, el 2x1 se veía como badge pero nunca descontaba nada. */
    function _pctEfectivoNxm(oferta, cantidad) {
        var n = oferta.cantidad_lleva, m = oferta.cantidad_paga;
        var qty = Math.floor(parseFloat(cantidad) || 0);
        if (!n || !m || qty < n) return 0;
        var grupos = Math.floor(qty / n);
        var resto = qty % n;
        var unidadesAPagar = grupos * m + resto;
        return (1 - unidadesAPagar / qty) * 100;
    }

    function _ofertaNxmParaItem(id, categoriaId) {
        var ofertas = window.KC_OFERTAS_NXM || [];
        var productoPk = _pkDeId(id);
        for (var i = 0; i < ofertas.length; i++) {
            var o = ofertas[i];
            var sinAlcance = !o.productos.length && !o.categorias.length;
            var aplica = sinAlcance || o.productos.indexOf(productoPk) !== -1 ||
                (categoriaId != null && o.categorias.indexOf(categoriaId) !== -1);
            if (aplica) return o;
        }
        return null;
    }

    /* Precio efectivo de la línea (ya con el % de NXM descontado según su
       cantidad actual, si corresponde) — es lo que se muestra y lo que se
       usa para el subtotal; el servidor recalcula lo mismo al crear el
       pedido (ver _info_oferta en catalogo/views.py), así que coinciden. */
    function _precioEfectivo(id, item) {
        var oferta = _ofertaNxmParaItem(id, item.categoriaId != null ? Number(item.categoriaId) : null);
        if (!oferta) return { precio: item.precio, oferta: null, pct: 0 };
        var pct = _pctEfectivoNxm(oferta, item.cantidad);
        if (pct <= 0) return { precio: item.precio, oferta: null, pct: 0 };
        var base = item.precioLista != null ? item.precioLista : item.precio;
        return { precio: base * (1 - pct / 100), oferta: oferta, pct: pct };
    }

    function actualizarBotonesTarjeta() {
        var carrito = leer();
        document.querySelectorAll('[data-carrito-agregar]').forEach(function (btn) {
            var id = btn.dataset.carritoAgregar;
            var cant = carrito[id] ? carrito[id].cantidad : 0;
            var contenedor = btn.closest('[data-carrito-slot]');
            if (!contenedor) return;
            var indicador = contenedor.querySelector('.kc-en-pedido');
            if (cant > 0) {
                if (!indicador) {
                    indicador = document.createElement('span');
                    indicador.className = 'kc-en-pedido';
                    contenedor.appendChild(indicador);
                }
                indicador.textContent = 'Ya en tu pedido (' + cant + ')';
            } else if (indicador) {
                indicador.remove();
            }
        });
    }

    function render() {
        var carrito = leer();

        var badge = document.getElementById('kcCarritoBadge');
        if (badge) {
            var total = totalItems(carrito);
            badge.textContent = total;
            badge.hidden = total === 0;
        }

        var cont = document.getElementById('kcDrawerItems');
        var subtotalEl = document.getElementById('kcDrawerSubtotal');
        var descuentoRow = document.getElementById('kcDrawerDescuentoRow');
        var descuentoLabel = document.getElementById('kcDrawerDescuentoLabel');
        var descuentoMonto = document.getElementById('kcDrawerDescuentoMonto');
        var totalRow = document.getElementById('kcDrawerTotalRow');
        var totalEl = document.getElementById('kcDrawerTotal');
        if (cont) {
            var ids = Object.keys(carrito);
            if (!ids.length) {
                cont.innerHTML = '<p class="kc-drawer-vacio">Todavía no agregaste nada. Elegí productos del catálogo para armar tu pedido.</p>';
                if (descuentoRow) descuentoRow.hidden = true;
                if (totalRow) totalRow.hidden = true;
            } else {
                var subtotal = 0;
                var totalLista = 0;
                cont.innerHTML = ids.map(function (id) {
                    var item = carrito[id];
                    var efectivo = _precioEfectivo(id, item);
                    subtotal += efectivo.precio * item.cantidad;
                    totalLista += (item.precioLista != null ? item.precioLista : item.precio) * item.cantidad;
                    var img = item.imagen
                        ? '<img src="' + item.imagen + '" alt="">'
                        : '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="6" width="14" height="11" rx="1.2" stroke="currentColor" stroke-width="1.4"/><path d="M3 9H17" stroke="currentColor" stroke-width="1.4"/><path d="M7 6V4.5C7 3.4 7.9 2.5 9 2.5H11C12.1 2.5 13 3.4 13 4.5V6" stroke="currentColor" stroke-width="1.4"/></svg>';
                    var nxmTag = efectivo.oferta
                        ? '<span class="kc-drawer-item-oferta">' + efectivo.oferta.cantidad_lleva + 'x' + efectivo.oferta.cantidad_paga + ' aplicado</span>'
                        : '';
                    var varianteTag = item.varianteLabel
                        ? '<span class="kc-drawer-item-variante">' + item.varianteLabel + '</span>'
                        : '';
                    return (
                        '<div class="kc-drawer-item">' +
                        '<div class="kc-drawer-item-img">' + img + '</div>' +
                        '<div class="kc-drawer-item-info">' +
                        '<div class="kc-drawer-item-top">' +
                        '<span class="kc-drawer-item-nombre">' + item.nombre + '</span>' +
                        '<button type="button" class="kc-drawer-item-quitar" data-carrito-quitar="' + id + '" aria-label="Quitar producto">' +
                        '<svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M1 1L11 11M11 1L1 11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>' +
                        '</button>' +
                        '</div>' +
                        varianteTag +
                        nxmTag +
                        '<div class="kc-drawer-item-row">' +
                        '<div class="kc-stepper">' +
                        '<button type="button" data-carrito-menos="' + id + '" aria-label="Quitar uno">' +
                        '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6H10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>' +
                        '</button>' +
                        '<span>' + item.cantidad + '</span>' +
                        '<button type="button" data-carrito-mas="' + id + '" aria-label="Agregar uno">' +
                        '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 2V10M2 6H10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>' +
                        '</button>' +
                        '</div>' +
                        '<span class="kc-drawer-item-precio">' + fmt(efectivo.precio * item.cantidad) + '</span>' +
                        '</div></div></div>'
                    );
                }).join('');
                if (subtotalEl) subtotalEl.textContent = fmt(subtotal);

                var oferta = _mejorOfertaGlobal(subtotal, totalLista);
                if (oferta) {
                    var monto = subtotal * oferta.pct / 100;
                    if (descuentoLabel) descuentoLabel.textContent = oferta.nombre + ' (-' + oferta.pct + '%)';
                    if (descuentoMonto) descuentoMonto.textContent = '-' + fmt(monto);
                    if (totalEl) totalEl.textContent = fmt(subtotal - monto);
                    if (descuentoRow) descuentoRow.hidden = false;
                    if (totalRow) totalRow.hidden = false;
                } else {
                    if (descuentoRow) descuentoRow.hidden = true;
                    if (totalRow) totalRow.hidden = true;
                }
            }
            if (subtotalEl && !ids.length) subtotalEl.textContent = fmt(0);
        }

        actualizarBotonesTarjeta();
    }

    document.addEventListener('click', function (e) {
        var btnAgregar = e.target.closest('[data-carrito-agregar]');
        if (btnAgregar) {
            agregar(btnAgregar.dataset.carritoAgregar, {
                nombre: btnAgregar.dataset.nombre,
                precio: parseFloat(btnAgregar.dataset.precio),
                precioLista: parseFloat(btnAgregar.dataset.precioLista || btnAgregar.dataset.precio),
                categoriaId: btnAgregar.dataset.categoriaId ? Number(btnAgregar.dataset.categoriaId) : null,
                imagen: btnAgregar.dataset.imagen || '',
                combinacionId: btnAgregar.dataset.combinacionId ? Number(btnAgregar.dataset.combinacionId) : null,
                varianteLabel: btnAgregar.dataset.varianteLabel || '',
            });
            return;
        }
        var btnMas = e.target.closest('[data-carrito-mas]');
        if (btnMas) { cambiarCantidad(btnMas.dataset.carritoMas, 1); return; }
        var btnMenos = e.target.closest('[data-carrito-menos]');
        if (btnMenos) { cambiarCantidad(btnMenos.dataset.carritoMenos, -1); return; }
        var btnQuitar = e.target.closest('[data-carrito-quitar]');
        if (btnQuitar) { quitar(btnQuitar.dataset.carritoQuitar); return; }

        if (e.target.closest('#kcBtnCarrito')) { abrir(); return; }
        if (e.target.closest('#kcDrawerCerrar') || e.target === document.getElementById('kcOverlay')) { cerrar(); return; }

        if (e.target.closest('#kcBtnIrAlContacto')) { mostrarPaso('contacto'); return; }
        if (e.target.closest('#kcBtnVolverCarrito')) { mostrarPaso('carrito'); return; }
        if (e.target.closest('#kcBtnConfirmarPedido')) { confirmarPedido(); return; }
        if (e.target.closest('#kcBtnSeguirComprando')) { cerrar(); mostrarPaso('carrito'); return; }
    });

    function mostrarPaso(paso) {
        var pasos = {
            carrito: document.getElementById('kcDrawerFootCarrito'),
            contacto: document.getElementById('kcDrawerFootContacto'),
            exito: document.getElementById('kcDrawerExito'),
        };
        Object.keys(pasos).forEach(function (key) {
            if (pasos[key]) pasos[key].hidden = key !== paso;
        });
        var items = document.getElementById('kcDrawerItems');
        if (items) items.hidden = paso === 'exito';
    }

    async function confirmarPedido() {
        var telefono = document.getElementById('kcContactoTelefono').value.trim();
        var errBox = document.getElementById('kcContactoError');
        if (!telefono) {
            errBox.textContent = 'Dejanos tu WhatsApp para poder coordinar el pedido.';
            errBox.hidden = false;
            return;
        }
        errBox.hidden = true;

        var carrito = leer();
        var items = Object.keys(carrito).map(function (id) {
            return {
                producto_id: _pkDeId(id),
                cantidad: carrito[id].cantidad,
                combinacion_id: carrito[id].combinacionId || null,
            };
        });

        var boton = document.getElementById('kcBtnConfirmarPedido');
        boton.disabled = true;
        try {
            var res = await fetch(window.KC_URLS.pedidoCrear, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    contacto_nombre: document.getElementById('kcContactoNombre').value.trim(),
                    contacto_telefono: telefono,
                    notas: document.getElementById('kcContactoNotas').value.trim(),
                    items: items,
                }),
            });
            var data = await res.json();
            if (data.ok) {
                guardar({});
                render();
                mostrarPaso('exito');
            } else {
                errBox.textContent = data.error || 'No pudimos registrar el pedido. Probá de nuevo.';
                errBox.hidden = false;
            }
        } catch (e) {
            errBox.textContent = 'Error de conexión. Probá de nuevo.';
            errBox.hidden = false;
        } finally {
            boton.disabled = false;
        }
    }

    function abrir() {
        var overlay = document.getElementById('kcOverlay');
        var drawer = document.getElementById('kcDrawer');
        if (overlay) overlay.classList.add('kc-abierto');
        if (drawer) drawer.classList.add('kc-abierto');
        document.body.style.overflow = 'hidden';
        mostrarPaso('carrito');
    }

    function cerrar() {
        var overlay = document.getElementById('kcOverlay');
        var drawer = document.getElementById('kcDrawer');
        if (overlay) overlay.classList.remove('kc-abierto');
        if (drawer) drawer.classList.remove('kc-abierto');
        document.body.style.overflow = '';
    }

    window.KaiCarrito = { cantidadEnCarrito: cantidadEnCarrito, render: render };

    document.addEventListener('DOMContentLoaded', render);
})();
