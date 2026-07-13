/* core/static/core/js/notify.js
   Kai-Cart — notificaciones y confirmaciones globales.
   Reemplaza alert()/confirm() nativos del navegador por componentes
   propios, consistentes con el resto del diseño. Se carga en
   base.html para TODAS las páginas — cualquier script puede usar:

     KaiToast.show('Guardado correctamente.', 'success');
     const ok = await KaiConfirm('¿Eliminar este registro?', { danger: true });

   Tipos de toast: 'success' | 'danger' | 'warning' | 'info'
*/
(function () {
    'use strict';

    const ICONS = {
        success: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4"/><path d="M5.2 8.2L7.1 10L10.8 6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        danger: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4"/><path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
        warning: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1.5L15 13.5H1L8 1.5Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 6.5V9.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="11.5" r="0.75" fill="currentColor"/></svg>',
        info: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 7.2V11.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="4.8" r="0.85" fill="currentColor"/></svg>',
    };

    /* ══════════════════════════════════════════════════════════════
       TOAST
    ══════════════════════════════════════════════════════════════ */
    let toastContainer = null;

    function getToastContainer() {
        if (!toastContainer || !document.body.contains(toastContainer)) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'kai-toast-container';
            document.body.appendChild(toastContainer);
        }
        return toastContainer;
    }

    function showToast(message, type = 'success', duration = 4200) {
        const container = getToastContainer();
        const tipo = ICONS[type] ? type : 'success';

        const toast = document.createElement('div');
        toast.className = `kai-toast kai-toast--${tipo}`;
        toast.innerHTML = `
            <span class="kai-toast-icon">${ICONS[tipo]}</span>
            <span class="kai-toast-msg"></span>
            <button type="button" class="kai-toast-close" aria-label="Cerrar">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1 1L11 11M11 1L1 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>`;
        toast.querySelector('.kai-toast-msg').textContent = message;

        const close = () => {
            toast.classList.add('kai-toast--out');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        };
        toast.querySelector('.kai-toast-close').addEventListener('click', close);

        container.appendChild(toast);
        if (duration > 0) setTimeout(close, duration);
        return toast;
    }

    window.KaiToast = { show: showToast };

    /* ══════════════════════════════════════════════════════════════
       CONFIRM — reemplaza confirm() nativo. Devuelve una Promise<bool>.
    ══════════════════════════════════════════════════════════════ */
    function confirmDialog(message, options = {}) {
        const { title = '¿Confirmar acción?', danger = false, confirmText = 'Confirmar', cancelText = 'Cancelar' } = options;

        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'kai-confirm-overlay';
            overlay.innerHTML = `
                <div class="kai-confirm-box" role="alertdialog" aria-modal="true" aria-labelledby="kaiConfirmTitle">
                    <div class="kai-confirm-icon ${danger ? 'kai-confirm-icon--danger' : ''}">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                    </div>
                    <h6 id="kaiConfirmTitle"></h6>
                    <p></p>
                    <div class="kai-confirm-actions">
                        <button type="button" class="kai-confirm-btn kai-confirm-btn--cancel"></button>
                        <button type="button" class="kai-confirm-btn ${danger ? 'kai-confirm-btn--danger' : 'kai-confirm-btn--primary'}"></button>
                    </div>
                </div>`;

            overlay.querySelector('h6').textContent = title;
            overlay.querySelector('p').textContent = message;
            const btnCancel = overlay.querySelector('.kai-confirm-btn--cancel');
            const btnOk = overlay.querySelector('.kai-confirm-btn--danger, .kai-confirm-btn--primary');
            btnCancel.textContent = cancelText;
            btnOk.textContent = confirmText;

            const finish = (result) => {
                overlay.classList.add('kai-confirm-overlay--out');
                overlay.addEventListener('animationend', () => overlay.remove(), { once: true });
                document.removeEventListener('keydown', onKeydown);
                resolve(result);
            };
            const onKeydown = (e) => {
                if (e.key === 'Escape') finish(false);
                if (e.key === 'Enter') finish(true);
            };

            btnCancel.addEventListener('click', () => finish(false));
            btnOk.addEventListener('click', () => finish(true));
            overlay.addEventListener('click', (e) => { if (e.target === overlay) finish(false); });
            document.addEventListener('keydown', onKeydown);

            document.body.appendChild(overlay);
            btnOk.focus();
        });
    }

    window.KaiConfirm = confirmDialog;
})();
