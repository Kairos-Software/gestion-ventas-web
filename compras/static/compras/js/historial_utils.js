/**
 * historial_utils.js
 * Helpers globales, modal de confirmación y toasts.
 * Debe cargarse PRIMERO, antes de los demás módulos.
 */
'use strict';

/* ════════════════════════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════════════════════════ */
function _esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatMoney(val) {
    const n = parseFloat(val);
    if (isNaN(n)) return val;
    return '$ ' + n.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPeso(v) {
    return '$ ' + v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtMoneda(v, moneda) {
    const sym = { USD: 'U$S ', EUR: '€ ', ARS: '$ ' }[moneda] || '$ ';
    return sym + v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/* ════════════════════════════════════════════════════════════════
   SVG ICONS
════════════════════════════════════════════════════════════════ */
function iconExterna() {
    return `<svg width="11" height="11" viewBox="0 0 12 12" fill="none">
        <path d="M5 2H2C1.45 2 1 2.45 1 3V10C1 10.55 1.45 11 2 11H9C9.55 11 10 10.55 10 10V7"
              stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        <path d="M7 1H11V5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M11 1L5.5 6.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
    </svg>`;
}
function iconAnular() {
    return `<svg width="13" height="13" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4"/>
        <path d="M5 5L11 11M11 5L5 11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
    </svg>`;
}
function iconEditar() {
    return `<svg width="13" height="13" viewBox="0 0 16 16" fill="none">
        <path d="M11 2L14 5L5 14H2V11L11 2Z" stroke="currentColor" stroke-width="1.4"
              stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
}
function iconEliminar() {
    return `<svg width="13" height="13" viewBox="0 0 16 16" fill="none">
        <path d="M3 4H13M6 4V2.5C6 2.22 6.22 2 6.5 2H9.5C9.78 2 10 2.22 10 2.5V4"
              stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        <path d="M5 6L5.5 13H10.5L11 6" stroke="currentColor" stroke-width="1.4"
              stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
}
function iconDoc() {
    return `<svg width="13" height="13" viewBox="0 0 16 16" fill="none">
        <path d="M4 2H9.5L13 5.5V14H4V2Z" stroke="currentColor" stroke-width="1.4"
              stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M9.5 2V5.5H13" stroke="currentColor" stroke-width="1.4"
              stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M6.5 9H10.5M6.5 11.5H9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
    </svg>`;
}

/* ════════════════════════════════════════════════════════════════
   POST HELPER
════════════════════════════════════════════════════════════════ */
function postAccion(url, payload, onSuccess, onError) {
    fetch(url, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
        body:    JSON.stringify(payload),
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) onSuccess(data);
        else         onError(data.error || 'Ocurrió un error inesperado.');
    })
    .catch(() => onError('Error de red. Intentá de nuevo.'));
}

/* ════════════════════════════════════════════════════════════════
   TOASTS
════════════════════════════════════════════════════════════════ */
function mostrarToastExito(msg) {
    _crearToast(msg, 'historial-toast--ok', 3500);
}
function mostrarToastError(msg) {
    _crearToast(msg, 'historial-toast--error', 5000);
}
function _crearToast(msg, cls, dur) {
    const t = document.createElement('div');
    t.className   = `historial-toast ${cls}`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.classList.add('visible'), 10);
    setTimeout(() => { t.classList.remove('visible'); setTimeout(() => t.remove(), 300); }, dur);
}

/* ════════════════════════════════════════════════════════════════
   MODAL DE CONFIRMACIÓN
════════════════════════════════════════════════════════════════ */
const _modalOverlay = document.getElementById('modalOverlay');
const _modalIcon    = document.getElementById('modalIcon');
const _modalTitle   = document.getElementById('modalTitle');
const _modalBody    = document.getElementById('modalBody');
const _modalWarning = document.getElementById('modalWarning');
const _modalWarnTx  = document.getElementById('modalWarningText');
const _modalCancel  = document.getElementById('modalCancel');
const _modalConfirm = document.getElementById('modalConfirm');
let   _modalCb      = null;

function abrirModal({ icon, title, body, warning, confirmLabel, confirmClass, onConfirm }) {
    _modalIcon.innerHTML      = icon || '';
    _modalTitle.textContent   = title || '';
    _modalBody.textContent    = body || '';
    _modalConfirm.textContent = confirmLabel || 'Confirmar';
    _modalConfirm.className   = `modal-btn modal-btn-confirm ${confirmClass || ''}`;
    _modalWarning.style.display = warning ? 'flex' : 'none';
    if (warning) _modalWarnTx.textContent = warning;
    _modalCb = onConfirm;
    _modalOverlay.classList.add('open');
}
function cerrarModal() {
    _modalOverlay.classList.remove('open');
    _modalCb = null;
}

_modalCancel.addEventListener('click', cerrarModal);
_modalOverlay.addEventListener('click', e => { if (e.target === _modalOverlay) cerrarModal(); });
_modalConfirm.addEventListener('click', () => { if (typeof _modalCb === 'function') _modalCb(); cerrarModal(); });