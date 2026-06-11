/* ═══════════════════════════════════════════════════════
   mi_perfil.js — Kai-Cart
   Funcionalidades:
     1. Toggle mostrar/ocultar contraseña (botones ojo)
     2. Medidor de fortaleza de contraseña
     3. Cierre de alertas Django (botón ×)
     4. Scroll automático a la sección con errores al cargar
   ═══════════════════════════════════════════════════════ */

(function () {
    'use strict';

    /* ──────────────────────────────────────
       1. TOGGLE OJO — mostrar/ocultar password
    ────────────────────────────────────── */
    document.querySelectorAll('.perfil-eye-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var targetId = btn.dataset.target;
            var input = document.getElementById(targetId);
            if (!input) return;

            var isHidden = input.type === 'password';
            input.type = isHidden ? 'text' : 'password';

            var iconEye    = btn.querySelector('.icon-eye');
            var iconEyeOff = btn.querySelector('.icon-eye-off');

            if (iconEye)    iconEye.style.display    = isHidden ? 'none'  : '';
            if (iconEyeOff) iconEyeOff.style.display = isHidden ? ''      : 'none';

            btn.setAttribute('aria-label',
                isHidden ? 'Ocultar contraseña' : 'Mostrar contraseña'
            );
        });
    });

    /* ──────────────────────────────────────
       2. FORTALEZA DE CONTRASEÑA
    ────────────────────────────────────── */
    var pwdNuevaInput = document.getElementById('id_password_nueva');
    var strengthWrap  = document.getElementById('pwdStrength');
    var strengthFill  = document.getElementById('pwdStrengthFill');
    var strengthLabel = document.getElementById('pwdStrengthLabel');

    var levelClasses = [
        'perfil-strength--weak',
        'perfil-strength--fair',
        'perfil-strength--good',
        'perfil-strength--strong',
    ];

    var levelLabels = ['Débil', 'Regular', 'Buena', 'Fuerte'];

    function calcStrength(pwd) {
        if (!pwd || pwd.length === 0) return -1;
        var score = 0;
        if (pwd.length >= 8)  score++;
        if (pwd.length >= 12) score++;
        if (/[A-Z]/.test(pwd) && /[a-z]/.test(pwd)) score++;
        if (/[0-9]/.test(pwd)) score++;
        if (/[^A-Za-z0-9]/.test(pwd)) score++;
        // Comprimir a 0-3
        if (score <= 1) return 0; // débil
        if (score === 2) return 1; // regular
        if (score === 3) return 2; // buena
        return 3;                  // fuerte
    }

    if (pwdNuevaInput && strengthWrap && strengthFill && strengthLabel) {
        pwdNuevaInput.addEventListener('input', function () {
            var val   = pwdNuevaInput.value;
            var level = calcStrength(val);

            // Quitar clases anteriores
            levelClasses.forEach(function (cls) {
                strengthWrap.classList.remove(cls);
            });

            if (level < 0 || val.length === 0) {
                strengthWrap.classList.remove('visible');
                return;
            }

            strengthWrap.classList.add('visible');
            strengthWrap.classList.add(levelClasses[level]);
            strengthLabel.textContent = levelLabels[level];
        });
    }

    /* ──────────────────────────────────────
       3. CERRAR ALERTAS
    ────────────────────────────────────── */
    document.querySelectorAll('.perfil-alert-close').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var alert = btn.closest('.alert');
            if (!alert) return;
            alert.style.transition = 'opacity 0.18s ease, transform 0.18s ease';
            alert.style.opacity    = '0';
            alert.style.transform  = 'translateY(-4px)';
            setTimeout(function () {
                alert.remove();
            }, 200);
        });
    });

    /* ──────────────────────────────────────
       4. SCROLL A SECCIÓN CON ERRORES
       Si hay un .has-error dentro de una
       .perfil-edit-card, se hace scroll a ella.
    ────────────────────────────────────── */
    var errorGroup = document.querySelector('.perfil-edit-card .has-error');
    if (errorGroup) {
        var card = errorGroup.closest('.perfil-edit-card');
        if (card) {
            // Pequeño delay para que el layout esté listo
            setTimeout(function () {
                card.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 80);
        }
    }

})();