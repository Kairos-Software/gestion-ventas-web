/* core/static/core/js/format.js
   Kai-Cart — formateo de números para pantalla, en español argentino.

   El backend siempre manda los números como los usa una computadora
   (punto decimal: "5.000" = cinco). Mostrado tal cual a alguien que
   lee en español, "5.000" se lee como "cinco mil" — exactamente al
   revés de lo que es. Todo número que se muestre en una pantalla
   (no en un <input>, ahí el navegador ya usa su propio formato) tiene
   que pasar por acá antes de imprimirse.

     KaiFormat.cantidad('5.000')   → "5"        (sin decimales de más)
     KaiFormat.cantidad('0.300')   → "0,3"
     KaiFormat.cantidad('1234.5')  → "1.234,5"
     KaiFormat.moneda('1234.5')    → "1.234,50" (siempre 2 decimales)
*/
(function () {
    'use strict';

    function _num(valor) {
        return typeof valor === 'number' ? valor : parseFloat(valor);
    }

    function cantidad(valor, decimales) {
        const num = _num(valor);
        if (isNaN(num)) return valor == null ? '' : String(valor);
        return num.toLocaleString('es-AR', {
            minimumFractionDigits: 0,
            maximumFractionDigits: decimales == null ? 3 : decimales,
        });
    }

    function moneda(valor, decimales) {
        const num = _num(valor);
        if (isNaN(num)) return valor == null ? '' : String(valor);
        const d = decimales == null ? 2 : decimales;
        return num.toLocaleString('es-AR', {
            minimumFractionDigits: d,
            maximumFractionDigits: d,
        });
    }

    window.KaiFormat = { cantidad, moneda };
})();
