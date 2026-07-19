/* core/static/core/js/help.js
   Botones de ayuda ("?") que despliegan un texto explicativo al hacer clic,
   en vez de tener el texto siempre visible ocupando lugar en el formulario.

   Uso:
     <label class="kai-label-help">
         Campo
         <button type="button" class="kai-help-btn" data-help-target="ayuda_campo" aria-label="Ayuda">?</button>
     </label>
     <input ...>
     <div class="kai-help-popover" id="ayuda_campo">Texto explicativo acá.</div>
*/
(function () {
    'use strict';

    function cerrarTodos(excepto) {
        document.querySelectorAll('.kai-help-popover.is-visible').forEach((pop) => {
            if (pop !== excepto) pop.classList.remove('is-visible');
        });
        document.querySelectorAll('.kai-help-btn.is-active').forEach((btn) => {
            if (btn.dataset.helpTarget !== (excepto && excepto.id)) btn.classList.remove('is-active');
        });
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.kai-help-btn');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            const pop = document.getElementById(btn.dataset.helpTarget);
            if (!pop) return;
            const yaVisible = pop.classList.contains('is-visible');
            cerrarTodos(null);
            if (!yaVisible) {
                pop.classList.add('is-visible');
                btn.classList.add('is-active');
            }
            return;
        }
        if (!e.target.closest('.kai-help-popover')) {
            cerrarTodos(null);
        }
    });
})();
