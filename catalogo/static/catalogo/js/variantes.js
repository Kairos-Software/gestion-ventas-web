/* Selector de variantes en la ficha de producto (color/sabor/talle...) —
   compartido por las 4 plantillas (cada una solo pone su propio HTML/CSS
   para los botones, ver detalle.html de cada una); si una página no
   tiene estos data-attributes, este script no hace nada.

   Resuelve todo en el cliente contra la matriz de combinaciones que ya
   manda el servidor embebida en la página (ver _variantes_contexto en
   catalogo/views.py) — elegir una opción no pide nada al servidor.

   Contrato con carrito.js: al resolver una combinación válida con stock,
   se reescribe el dataset del botón "Agregar" (data-carrito-agregar,
   data-combinacion-id, data-variante-label) — el click lo sigue
   manejando el listener de siempre en carrito.js, que no sabe nada de
   variantes. */
(function () {
    var grupos = Array.prototype.slice.call(document.querySelectorAll('[data-variante-tipo]'));
    var combinacionesEl = document.getElementById('kcVariantesCombinaciones');
    var boton = document.getElementById('btnAgregarDetalle');
    var estadoEl = document.getElementById('kcVarianteEstado');
    if (!grupos.length || !combinacionesEl || !boton) return;

    var combinaciones;
    try {
        combinaciones = JSON.parse(combinacionesEl.textContent) || [];
    } catch (e) {
        combinaciones = [];
    }

    var idBase = boton.dataset.idBase || ('prod-' + boton.dataset.productoId);

    function seleccionActual() {
        return grupos
            .map(function (g) {
                var activo = g.querySelector('[data-variante-opcion].kc-variante-activa');
                return activo ? Number(activo.dataset.varianteOpcion) : null;
            })
            .filter(function (v) { return v !== null; })
            .sort(function (a, b) { return a - b; });
    }

    function deshabilitar(mensaje) {
        boton.disabled = true;
        delete boton.dataset.carritoAgregar;
        delete boton.dataset.combinacionId;
        delete boton.dataset.varianteLabel;
        if (estadoEl) estadoEl.textContent = mensaje;
    }

    function habilitar(combinacion) {
        boton.disabled = false;
        boton.dataset.carritoAgregar = idBase + '-combo-' + combinacion.pk;
        boton.dataset.combinacionId = combinacion.pk;
        boton.dataset.varianteLabel = combinacion.descripcion;
        if (estadoEl) estadoEl.textContent = Math.floor(combinacion.stock) + ' disponibles';
    }

    function resolver() {
        var seleccion = seleccionActual();
        if (seleccion.length !== grupos.length) {
            deshabilitar('Elegí una opción');
            return;
        }
        var match = combinaciones.filter(function (c) {
            return c.opciones.length === seleccion.length &&
                c.opciones.every(function (id, i) { return id === seleccion[i]; });
        })[0];
        if (!match) { deshabilitar('Esa combinación no está disponible'); return; }
        if (!match.disponible) { deshabilitar('Sin stock en esta combinación'); return; }
        habilitar(match);
    }

    grupos.forEach(function (grupo) {
        grupo.addEventListener('click', function (e) {
            var op = e.target.closest('[data-variante-opcion]');
            if (!op || !grupo.contains(op)) return;
            grupo.querySelectorAll('[data-variante-opcion]').forEach(function (b) {
                b.classList.toggle('kc-variante-activa', b === op);
            });
            resolver();
        });
    });

    resolver();
})();
