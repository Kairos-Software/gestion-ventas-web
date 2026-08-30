# Maqueta — Nueva Venta sin ventanas flotantes

Prototipo **solo de diseño front**, sin servidor ni base de datos. Sirve para
decidir si esta forma de trabajar es mejor que la actual **antes** de tocar el
código real de `ventas/`.

## Cómo probarla

Abrí **`index.html`** con doble clic (Chrome, Edge o Firefox).
No necesita Django corriendo ni internet (las tipografías son de Google Fonts;
si no hay conexión, usa las del sistema y se ve casi igual).

- Archivos: `index.html` + `estilos.css` + `datos.js` (datos de mentira) + `app.js` (lógica).
- Botón **⚙ Demo** (arriba a la derecha): alterna "sin turno de caja", ARCA on/off y reinicia.

### Qué probar
1. Escaneá/buscá productos: escribí `coca`, o un código `PRD-0003`, y Enter.
2. Código de lote puntual: `LT-2025-0003` · Etiqueta de balanza: `BAL-2025-0007`
   (cantidad y precio quedan fijos, como al pesar).
3. Producto con variantes: buscá `remera` → elegís talle/color.
4. Ofertas: subí Coca a 2 unidades → aparece el 2x1. En "Descuento / oferta"
   de cada línea hay listas y ofertas manuales. La oferta por monto total
   (`Compra +$40.000`) salta sola en el pie del carrito.
5. Cliente: buscá `kiosco` (banda **Crítico** → esconde cuotas/cheque, con
   "Habilitar de todos modos"), `laura` (**Riesgo** → solo avisa), `martin`
   (**Excelente**), `nuevo` (**sin historial**).
6. Medios de pago: efectivo, débito/crédito (tarjeta + plan + recargo + cuenta),
   QR, transferencia, **cuotas** (plan fijo o "cuotas libres" + interés),
   **cheque** (se cargan de a uno en un mini-modal). Pago dividido: "Agregar otro medio".
7. Cotización: elegí la cuenta "Caja en USD" → pide el tipo de cambio.
8. Facturación: sección plegable; el tipo (A/B) sale del cliente. Tildá "Emitir…".
9. **Confirmar venta** (F4) → el mismo panel pasa a estado "confirmada" con
   número, CAE y botones de impresión. **Nueva venta** (F2) reinicia.

## Qué cambia respecto del diseño actual

| Hoy | Maqueta |
|---|---|
| El cobro es un **panel flotante** que se arrastra/minimiza/oculta y tapa el carrito | El cobro es una **columna fija a la derecha, siempre visible**. Nunca tapa nada, nunca hay que ir a buscarlo. |
| "Continuar al detalle" / "Editar carrito" = saltos de pantalla o abrir/cerrar el panel | No hay salto ni "modo". Escaneás a la izquierda, el total y el pago se arman solos a la derecha. |
| Pestañas (General / Medios de pago / Facturación) que esconden campos | Una sola columna, de arriba a abajo: cliente → fecha → total → pago → (facturación y notas plegables) → confirmar. |
| El cliente está en dos lugares (carrito y panel) y se sincronizan | El cliente vive **solo** en el cobro. Una fuente de verdad. |
| Tras confirmar caés en otra pantalla completa | El panel muestra el "listo" (número, CAE, impresión) **en el mismo lugar**, sin recargar. |
| `F2` mostraba/ocultaba el panel flotante | `F2` salta el foco buscador ↔ monto; `F4` confirma. Ya no hay nada que "mostrar/ocultar". |
| Tabla del carrito con 8 columnas | Fila compacta: nombre + cantidad + precio + subtotal. Descuento/oferta/lista quedan en un "más" por línea. |

En pantallas angostas el cobro pasa **abajo** del carrito (apilado), nunca flota.

## Qué NO es esto

- No toca `ventas/` ni la base. Los datos (`datos.js`) son inventados.
- La impresión de ticket abre una vista previa de ejemplo, no genera PDF real.
- Devoluciones, historial y edición de venta confirmada quedan como están hoy
  (viven en otra pantalla).

## Si el diseño convence

El plan de implementación real reusaría el motor de pago actual
(`detalle_venta.js`) como componente y `nueva_venta.js` como carrito — igual
que el plan del panel flotante, pero anclando la columna en vez de flotarla.
Se listan los archivos a tocar cuando se decida avanzar.
