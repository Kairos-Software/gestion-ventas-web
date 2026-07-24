// base.js — Kai-Cart
document.addEventListener('DOMContentLoaded', function () {

    const sidebar = document.querySelector('.sidebar');

    // ── Sidebar collapse / expand (desktop) ───────────────────────────
    if (sidebar && localStorage.getItem('sidebarCollapsed') === 'true' && window.innerWidth >= 768) {
        sidebar.classList.add('collapsed');
    }

    // ── Mobile sidebar con overlay ─────────────────────────────────────
    const overlay      = document.getElementById('sidebarOverlay');
    const closeBtn     = document.getElementById('sidebarCloseBtn');
    const mobileToggle = document.getElementById('sidebarToggle');

    function openMobileSidebar() {
        sidebar.classList.add('mobile-open');
        if (overlay) overlay.classList.add('visible');
        document.body.style.overflow = 'hidden';
    }

    function closeMobileSidebar() {
        sidebar.classList.remove('mobile-open');
        if (overlay) overlay.classList.remove('visible');
        document.body.style.overflow = '';
    }

    function isMobile() { return window.innerWidth < 768; }

    // El sidebarToggle en móvil abre el drawer; en desktop colapsa
    if (mobileToggle && sidebar) {
        mobileToggle.addEventListener('click', function () {
            if (isMobile()) {
                sidebar.classList.contains('mobile-open')
                    ? closeMobileSidebar()
                    : openMobileSidebar();
            } else {
                sidebar.classList.toggle('collapsed');
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
            }
        });
    }

    if (closeBtn)  closeBtn.addEventListener('click', closeMobileSidebar);
    if (overlay)   overlay.addEventListener('click', closeMobileSidebar);

    // Cerrar con Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && isMobile()) closeMobileSidebar();
    });

    // Cerrar sidebar en móvil al navegar (click en un nav-item)
    // NOTA: la marca de "veníamos en fullscreen" para persistirlo en la
    // próxima página ya la hace fullscreen-persist.js sobre estos mismos
    // links, así que acá NO la repetimos (antes se hacía en los dos
    // archivos a la vez, y eso rompía la persistencia real).
    if (sidebar) {
        sidebar.querySelectorAll('.nav-item, .nav-subitem').forEach(function(link) {
            link.addEventListener('click', function() {
                if (isMobile()) closeMobileSidebar();
            });
        });
    }

    // ── Nav groups: restaurar estado ───────────────────────────────────
    try {
        const state = JSON.parse(sessionStorage.getItem('navGroupState') || '{}');
        document.querySelectorAll('.nav-group').forEach(function (group) {
            const tieneActivo = group.querySelector('.nav-subitem.active');
            if (!tieneActivo && group.id in state) {
                group.classList.toggle('open', state[group.id]);
            }
        });
    } catch (e) { /* sessionStorage no disponible */ }

    // ── User Dropdown ──────────────────────────────────────────────────
    const dropdownBtn  = document.getElementById('userDropdownBtn');
    const dropdownMenu = document.getElementById('userDropdownMenu');

    if (dropdownBtn && dropdownMenu) {
        dropdownBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            const isOpen = dropdownMenu.classList.contains('open');
            dropdownMenu.classList.toggle('open', !isOpen);
            dropdownBtn.setAttribute('aria-expanded', String(!isOpen));
        });

        // Cerrar al hacer click fuera
        document.addEventListener('click', function (e) {
            if (!dropdownBtn.contains(e.target) && !dropdownMenu.contains(e.target)) {
                dropdownMenu.classList.remove('open');
                dropdownBtn.setAttribute('aria-expanded', 'false');
            }
        });

        // Cerrar con Escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                dropdownMenu.classList.remove('open');
                dropdownBtn.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // ── Campanita de notificaciones (pedidos del catálogo) ──────────────
    (function () {
        const btn  = document.getElementById('notifBellBtn');
        const menu = document.getElementById('notifMenu');
        const badge = document.getElementById('notifBadge');
        const lista = document.getElementById('notifList');
        if (!btn || !menu || !window.PEDIDOS_URLS) return;

        function fmtFecha(iso) {
            const d = new Date(iso);
            const ahora = new Date();
            const minutos = Math.round((ahora - d) / 60000);
            if (minutos < 1) return 'recién';
            if (minutos < 60) return `hace ${minutos} min`;
            const horas = Math.round(minutos / 60);
            if (horas < 24) return `hace ${horas} h`;
            return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
        }

        function fmtMoneda(n) {
            return '$' + Number(n).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str || '';
            return div.innerHTML;
        }

        function renderLista(pedidos) {
            if (!pedidos.length) {
                lista.innerHTML = '<p class="notif-menu-vacio">Todavía no llegó ningún pedido del catálogo.</p>';
                return;
            }
            lista.innerHTML = pedidos.map(function (p) {
                const vendido = p.estado === 'vendido';
                return `
                    <div class="notif-item ${!p.leido ? 'notif-item--no-leido' : ''} ${vendido ? 'notif-item--vendido' : ''}">
                        <div class="notif-item-top">
                            <span class="notif-item-contacto">${p.contacto_nombre || p.contacto_telefono}</span>
                            <span class="notif-item-fecha">${fmtFecha(p.fecha_alta)}</span>
                        </div>
                        <div class="notif-item-resumen">
                            ${p.cantidad_items} producto${p.cantidad_items === 1 ? '' : 's'} · <span class="notif-item-total">${fmtMoneda(p.total)}</span>
                            ${vendido ? ' · Ya convertido en venta' : ''}
                        </div>
                        ${p.notas ? `<div class="notif-item-notas">📝 ${escapeHtml(p.notas)}</div>` : ''}
                        <div class="notif-item-acciones">
                            <a class="notif-btn" href="${p.wa_link}" target="_blank" rel="noopener">Hablar por WhatsApp</a>
                            <button type="button" class="notif-btn notif-btn--vender" data-pedido-vender="${p.pk}">
                                ${vendido ? 'Ver venta' : 'Vender'}
                            </button>
                        </div>
                    </div>`;
            }).join('');
        }

        let noLeidosPrevio = null; // null = todavía no hicimos el primer chequeo

        async function actualizarBadge() {
            try {
                const res = await fetch(window.PEDIDOS_URLS.noLeidos);
                if (!res.ok) return;
                const data = await res.json();
                badge.textContent = data.no_leidos;
                badge.hidden = !data.no_leidos;

                // Avisa con un toast si aparecieron pedidos nuevos desde el
                // último chequeo — así no hace falta refrescar la página ni
                // abrir la campanita para enterarse. No en el primer chequeo
                // (recién cargó la página, no es "nuevo").
                if (noLeidosPrevio !== null && data.no_leidos > noLeidosPrevio && window.KaiToast) {
                    const nuevos = data.no_leidos - noLeidosPrevio;
                    KaiToast.show(
                        nuevos === 1 ? 'Llegó un pedido nuevo del catálogo.' : `Llegaron ${nuevos} pedidos nuevos del catálogo.`,
                        'info',
                    );
                }
                noLeidosPrevio = data.no_leidos;

                // Si la campanita ya estaba abierta, refresca la lista sola
                // en vez de dejar al usuario mirando algo desactualizado.
                if (menu.classList.contains('open')) abrirLista();
            } catch (e) { /* silencioso — no interrumpe el resto del sistema */ }
        }

        async function abrirLista() {
            lista.innerHTML = '<p class="notif-menu-vacio">Cargando...</p>';
            try {
                const res = await fetch(window.PEDIDOS_URLS.lista);
                if (!res.ok) { lista.innerHTML = '<p class="notif-menu-vacio">No se pudo cargar.</p>'; return; }
                const data = await res.json();
                renderLista(data.resultados);
                badge.hidden = true; // se acaban de marcar como leídos en el server
            } catch (e) {
                lista.innerHTML = '<p class="notif-menu-vacio">Error de conexión.</p>';
            }
        }

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            const isOpen = menu.classList.contains('open');
            menu.classList.toggle('open', !isOpen);
            btn.setAttribute('aria-expanded', String(!isOpen));
            if (!isOpen) abrirLista();
        });

        document.addEventListener('click', function (e) {
            if (!btn.contains(e.target) && !menu.contains(e.target)) {
                menu.classList.remove('open');
                btn.setAttribute('aria-expanded', 'false');
            }
        });

        lista.addEventListener('click', async function (e) {
            const venderBtn = e.target.closest('[data-pedido-vender]');
            if (!venderBtn) return;
            const pk = venderBtn.dataset.pedidoVender;
            venderBtn.disabled = true;
            try {
                const res = await fetch(window.PEDIDOS_URLS.venderBase + pk + '/vender/', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCookie('csrftoken') },
                });
                const data = await res.json();
                if (data.ok) {
                    window.location.href = data.redirect;
                } else {
                    KaiToast.show(data.error || 'No se pudo cargar el pedido en Nueva Venta.', 'danger');
                    venderBtn.disabled = false;
                }
            } catch (e) {
                KaiToast.show('Error de conexión.', 'danger');
                venderBtn.disabled = false;
            }
        });

        actualizarBadge();
        setInterval(actualizarBadge, 15000);
    })();

    // Agrega un <span class="logo-shine"> dentro del .logo y lo anima
    // con un sweep periódico (cada 7s, con variación aleatoria de ±2s).
    const logoLink = document.querySelector('.sidebar-header .logo');

    if (logoLink) {
        const shine = document.createElement('span');
        shine.className = 'logo-shine';
        logoLink.appendChild(shine);

        function triggerShine() {
            if (sidebar && sidebar.classList.contains('collapsed')) {
                scheduleShine();
                return;
            }
            shine.classList.remove('sweep');
            void shine.offsetWidth;
            shine.classList.add('sweep');
            shine.addEventListener('animationend', () => {
                shine.classList.remove('sweep');
            }, { once: true });
            scheduleShine();
        }

        function scheduleShine() {
            const delay = 6000 + Math.random() * 4000;
            setTimeout(triggerShine, delay);
        }

        setTimeout(triggerShine, 2500);
    }

    // ── Modo pantalla completa (Fullscreen API) ────────────────────────
    // Este bloque es el ÚNICO responsable de la Fullscreen API manual
    // (Ctrl+Alt+P). La persistencia entre navegaciones (mostrar el
    // banner "Reanudar" en la página siguiente) es responsabilidad
    // exclusiva de fullscreen-persist.js — antes también vivía acá
    // duplicada, y las dos copias se pisaban entre sí (una consumía la
    // bandera de sessionStorage antes de que la otra pudiera usarla).
    // Combinación elegida: Ctrl + Alt + P. No choca con F11, F12/devtools
    // ni con las combinaciones Ctrl+Alt+F1..F7 de Linux (esas usan teclas
    // de función, no la letra).
    function isFullscreenActive() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement ||
                   document.mozFullScreenElement || document.msFullscreenElement);
    }

    function enterFullscreen() {
        const el = document.documentElement;
        const req = el.requestFullscreen || el.webkitRequestFullscreen ||
                    el.mozRequestFullScreen || el.msRequestFullscreen;
        if (req) req.call(el).catch(function () { /* el navegador denegó el pedido */ });
    }

    function exitFullscreen() {
        const exit = document.exitFullscreen || document.webkitExitFullscreen ||
                     document.mozCancelFullScreen || document.msExitFullscreen;
        if (exit) exit.call(document).catch(function () {});
    }

    function toggleFullscreen() {
        isFullscreenActive() ? exitFullscreen() : enterFullscreen();
    }

    // ── Recuperar fullscreen cuando lo corta un diálogo nativo ──────────
    // alert(), confirm() y prompt() hacen que el navegador salga de
    // pantalla completa por su cuenta apenas se abren — no es una
    // decisión del usuario, es una medida de seguridad del browser.
    // Como esta app usa esos diálogos todo el tiempo (validaciones,
    // "poner en 0", reiniciar sistema), envolvemos las tres funciones:
    // si justo antes de llamarlas estábamos en fullscreen y justo
    // después ya no, reintentamos entrar de nuevo. Funciona porque el
    // cierre del diálogo (son bloqueantes) sigue ocurriendo dentro del
    // mismo gesto de click que lo disparó, así que el navegador todavía
    // nos deja pedir fullscreen ahí.
    //
    // A propósito esto NO reacciona si el usuario sale con Esc o con el
    // botón ×: esos casos no pasan por alert/confirm/prompt, así que
    // nunca entran acá. No hay forma de diferenciar "se cortó por un
    // diálogo" de "se cortó porque se abrieron las devtools" u otras
    // causas del navegador — para esos casos no hay API que nos avise
    // el motivo, así que quedan sin cubrir.
    ['alert', 'confirm', 'prompt'].forEach(function (nombre) {
        const original = window[nombre];
        window[nombre] = function () {
            const estabaEnFullscreen = isFullscreenActive();
            const resultado = original.apply(window, arguments);
            if (estabaEnFullscreen && !isFullscreenActive()) {
                enterFullscreen();
            }
            return resultado;
        };
    });

    function showFullscreenHint(text) {
        let hint = document.getElementById('fsHint');
        if (!hint) {
            hint = document.createElement('div');
            hint.id = 'fsHint';
            hint.style.cssText = [
                'position:fixed', 'bottom:20px', 'left:50%', 'transform:translateX(-50%)',
                'background:rgba(20,20,20,0.88)', 'color:#fff', 'padding:8px 16px',
                'border-radius:8px', 'font-size:13px', 'font-family:inherit',
                'z-index:99999', 'pointer-events:none', 'opacity:0',
                'transition:opacity .25s ease'
            ].join(';');
            document.body.appendChild(hint);
        }
        hint.textContent = text;
        requestAnimationFrame(function () { hint.style.opacity = '1'; });
        clearTimeout(hint._timeout);
        hint._timeout = setTimeout(function () { hint.style.opacity = '0'; }, 2200);
    }

    document.addEventListener('keydown', function (e) {
        const key = (e.key || '').toLowerCase();
        if (e.ctrlKey && e.altKey && !e.shiftKey && (key === 'p' || e.code === 'KeyP')) {
            e.preventDefault();
            toggleFullscreen();
        }
    });

    document.addEventListener('fullscreenchange', function () {
        showFullscreenHint(isFullscreenActive()
            ? 'Pantalla completa activada — Esc o Ctrl+Alt+P para salir'
            : 'Pantalla completa desactivada');
    });
    ['webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(function (evt) {
        document.addEventListener(evt, function () {
            showFullscreenHint(isFullscreenActive()
                ? 'Pantalla completa activada — Esc o Ctrl+Alt+P para salir'
                : 'Pantalla completa desactivada');
        });
    });

    // ── Atajos de teclado: navegación rápida (Ctrl + Alt + letra) ──────
    //   Ctrl+Alt+I → Inventario
    //   Ctrl+Alt+S → Stock
    //   Ctrl+Alt+C → Compras (nueva compra)
    //   Ctrl+Alt+V → Ventas (nueva venta)
    //   Ctrl+Alt+G → Caja Grande
    //   Ctrl+Alt+D → Caja Diaria
    // (Ctrl+Alt+B y Ctrl+Alt+U — herramientas flotantes — se manejan
    // en floating-tools.js, no acá.)
    if (window.NAV_SHORTCUTS_URLS) {
        const navShortcuts = {
            'i': 'inventario',
            's': 'stock',
            'c': 'compras',
            'v': 'ventas',
            'g': 'cajaGrande',
            'd': 'cajaDiaria'
        };

        function isTypingContext(el) {
            if (!el) return false;
            const tag = el.tagName;
            return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
        }

        document.addEventListener('keydown', function (e) {
            if (!e.ctrlKey || !e.altKey || e.shiftKey) return;
            if (isTypingContext(e.target)) return;

            const key = (e.key || '').toLowerCase();
            const destino = navShortcuts[key];
            if (!destino) return;

            const url = window.NAV_SHORTCUTS_URLS[destino];
            if (!url) return;

            e.preventDefault();
            // Acá SÍ hace falta marcar la bandera de fullscreen a mano:
            // es una navegación programática (no un click real), así que
            // el listener de click de fullscreen-persist.js no la ve.
            if (isFullscreenActive()) sessionStorage.setItem('fsPersist', '1');
            window.location.href = url;
        });
    }

});

// ── Reiniciar sistema (solo superusuarios, solo DEBUG) ──────────────────
function reiniciarSistema() {
    const FRASE = 'REINICIAR';

    const confirmacion = window.prompt(
        'Esto borra TODOS los datos de la app (clientes, ventas, compras, stock, etc.), ' +
        'menos los superusuarios. NO se puede deshacer.\n\n' +
        'Escribí ' + FRASE + ' para confirmar:'
    );
    if (confirmacion === null) return;
    if (confirmacion.trim() !== FRASE) {
        KaiToast.show('Cancelado: el texto no coincide con "' + FRASE + '".', 'warning');
        return;
    }

    const password = window.prompt('Confirmá tu contraseña para continuar:');
    if (!password) return;

    if (!window.RESET_SISTEMA_URL) {
        KaiToast.show('No se encontró la URL de reinicio.', 'danger');
        return;
    }

    const formData = new FormData();
    formData.append('confirmacion', confirmacion.trim());
    formData.append('password', password);

    fetch(window.RESET_SISTEMA_URL, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: formData
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.ok) {
                KaiToast.show('Listo, se reinició la base de datos. La página se va a recargar.', 'success', 2200);
                setTimeout(function () { window.location.reload(); }, 1800);
            } else {
                KaiToast.show('No se pudo reiniciar: ' + (data.error || 'error desconocido.'), 'danger');
            }
        })
        .catch(function () {
            KaiToast.show('Error de red al intentar reiniciar el sistema.', 'danger');
        });
}

// ── Datos de prueba del catálogo (solo superusuarios, solo DEBUG) ───────
async function cargarDatosDemoCatalogo(btn) {
    if (!window.DEMO_CATALOGO_CARGAR_URL) return;
    if (!await KaiConfirm('Esto crea categorías, productos, paquetes y ofertas de prueba (con el prefijo "DEMO - ") para ver cómo queda el catálogo. No toca nada cargado a mano.')) return;

    if (btn) btn.disabled = true;
    // Baja imágenes reales de internet — puede tardar varios segundos.
    // Sin este aviso, el click se siente "colgado" y da ganas de reintentar.
    const cargando = KaiToast.show('Cargando datos de prueba… puede tardar unos segundos (está bajando imágenes).', 'info', 0);

    try {
        const res = await fetch(window.DEMO_CATALOGO_CARGAR_URL, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
        });
        const data = await res.json();
        if (data.ok) {
            const c = data.creados;
            KaiToast.show(
                `Listo: ${c.categorias} categorías, ${c.productos} productos, ${c.paquetes} paquetes, ${c.ofertas} ofertas.`,
                'success', 3000,
            );
        } else {
            KaiToast.show('No se pudo cargar: ' + (data.error || 'error desconocido.'), 'danger');
        }
    } catch {
        KaiToast.show('Error de red al cargar los datos de prueba.', 'danger');
    } finally {
        cargando.querySelector('.kai-toast-close')?.click();
        if (btn) btn.disabled = false;
    }
}

async function eliminarDatosDemoCatalogo(btn) {
    if (!window.DEMO_CATALOGO_ELIMINAR_URL) return;
    if (!await KaiConfirm('¿Eliminar todos los datos de prueba del catálogo? Solo borra lo que creó esta misma herramienta, nada cargado a mano.', { danger: true, confirmText: 'Eliminar' })) return;

    if (btn) btn.disabled = true;
    try {
        const res = await fetch(window.DEMO_CATALOGO_ELIMINAR_URL, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
        });
        const data = await res.json();
        if (data.ok) {
            KaiToast.show(`Listo: se eliminaron ${data.eliminados} registros de prueba.`, 'success', 2500);
        } else {
            KaiToast.show('No se pudo eliminar: ' + (data.error || 'error desconocido.'), 'danger');
        }
    } catch {
        KaiToast.show('Error de red al eliminar los datos de prueba.', 'danger');
    } finally {
        if (btn) btn.disabled = false;
    }
}

function getCookie(name) {
    const value = '; ' + document.cookie;
    const parts = value.split('; ' + name + '=');
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

// ── Nav groups toggle ──────────────────────────────────────────────────
function toggleNavGroup(id) {
    const group = document.getElementById(id);
    if (!group) return;
    group.classList.toggle('open');

    const state = {};
    document.querySelectorAll('.nav-group').forEach(function (g) {
        state[g.id] = g.classList.contains('open');
    });
    sessionStorage.setItem('navGroupState', JSON.stringify(state));
}