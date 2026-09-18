/**
 * herramientas_dev.js
 * ─────────────────────────────────────────────────────────────────
 * Motor genérico del panel de Herramientas de desarrollador. Lee el
 * catálogo serializado desde #herramientasDevData (armado en el
 * backend por core/herramientas_dev_catalogo.py) y arma una card por
 * herramienta — nada de esto tiene HTML hardcodeado por herramienta:
 * agregar una nueva es agregar una entrada al diccionario Python.
 *
 * Depende de: KaiToast / KaiConfirm (core/static/core/js/notify.js) y
 * getCookie() (core/static/core/js/base.js), ambos cargados globalmente
 * en base.html.
 * ─────────────────────────────────────────────────────────────────
 */
'use strict';

const HDEV_RIESGO_INFO = {
    lectura:                 { badge: 'Solo mirar, no cambia nada', clase: 'hdev-badge--lectura' },
    accion_real_bajo_impacto:{ badge: 'Envía un correo real',       clase: 'hdev-badge--accion' },
    muta_seguro:             { badge: 'Cambia datos',               clase: 'hdev-badge--muta' },
    muta_con_preview:        { badge: 'Cambia datos',               clase: 'hdev-badge--muta' },
    dry_run_forzado:         { badge: 'Solo una simulación',        clase: 'hdev-badge--lectura' },
    fiscal_fuerte:           { badge: 'Trámite fiscal real',        clase: 'hdev-badge--peligro' },
    notificaciones_fuerte:   { badge: 'Envía correos reales',       clase: 'hdev-badge--peligro' },
};

document.addEventListener('DOMContentLoaded', () => {
    const dataEl = document.getElementById('herramientasDevData');
    if (!dataEl) return;

    let herramientas = [];
    try {
        herramientas = JSON.parse(dataEl.textContent);
    } catch (e) {
        console.error('herramientas_dev.js: no se pudo parsear el catálogo.', e);
        return;
    }

    herramientas.forEach(tool => {
        const contenedor = document.querySelector(`.hdev-grid[data-categoria="${tool.categoria}"]`);
        if (!contenedor) return;
        contenedor.appendChild(crearCard(tool));
    });
});

/* ════════════════════════════════════════════════════════════════
   ARMADO DE LA CARD
════════════════════════════════════════════════════════════════ */

function crearCard(tool) {
    const info = HDEV_RIESGO_INFO[tool.riesgo] || { badge: tool.riesgo, clase: '' };

    const card = document.createElement('article');
    card.className = 'hdev-card';
    card.dataset.slug = tool.slug;

    card.innerHTML = `
        <header class="hdev-card-header">
            <h3>${_esc(tool.label)}</h3>
            <span class="hdev-badge ${info.clase}">${_esc(info.badge)}</span>
        </header>
        <p class="hdev-desc">${_esc(tool.descripcion)}</p>
        <details class="hdev-interpretacion">
            <summary>Cómo interpretar el resultado</summary>
            <p>${_esc(tool.interpretacion)}</p>
        </details>
        ${tool.mostrar_ambiente_arca ? `
        <div class="hdev-ambiente ${window.HDEV_AMBIENTE_ARCA === 'produccion' ? 'hdev-ambiente--danger' : ''}">
            Ambiente ARCA actual: <strong>${_esc(window.HDEV_AMBIENTE_ARCA_DISPLAY)}</strong>
        </div>` : ''}
        <div class="hdev-params"></div>
        <div class="hdev-actions"></div>
        <div class="hdev-resultado" hidden>
            <div class="hdev-resultado-header">
                <span class="hdev-resultado-estado"></span>
                <button type="button" class="hdev-resultado-toggle">Ver salida completa</button>
            </div>
            <pre class="hdev-resultado-salida" hidden></pre>
        </div>
    `;

    const paramsBox = card.querySelector('.hdev-params');
    tool.params.forEach(spec => paramsBox.appendChild(crearInput(spec, tool)));

    const acciones = card.querySelector('.hdev-actions');
    crearBotones(tool, card).forEach(btn => acciones.appendChild(btn));

    card.querySelector('.hdev-resultado-toggle').addEventListener('click', (e) => {
        const pre = card.querySelector('.hdev-resultado-salida');
        const oculto = pre.hasAttribute('hidden');
        if (oculto) pre.removeAttribute('hidden'); else pre.setAttribute('hidden', '');
        e.target.textContent = oculto ? 'Ocultar salida completa' : 'Ver salida completa';
    });

    return card;
}

function crearInput(spec, tool) {
    const wrap = document.createElement('label');
    wrap.className = 'hdev-input-wrap';

    if (spec.tipo === 'bool') {
        wrap.className += ' hdev-input-wrap--checkbox';
        wrap.innerHTML = `<input type="checkbox" data-param="${spec.nombre}"> <span>${_esc(spec.label)}</span>`;
        return wrap;
    }

    let inputHtml;
    if (spec.opciones) {
        // Desplegable con nombres entendibles (ej. "Factura C" en vez de
        // "11") — el valor real que se manda al servidor sigue siendo el
        // código crudo (spec.opciones[].value), ver leerParams().
        const opciones = spec.opciones.map(o => `<option value="${_esc(o.value)}" ${String(o.value) === String(spec.default) ? 'selected' : ''}>${_esc(o.label)}</option>`).join('');
        inputHtml = `<select data-param="${spec.nombre}">${opciones}</select>`;
    } else if (spec.tipo === 'choice') {
        const opciones = spec.choices.map(c => `<option value="${_esc(c)}" ${c === spec.default ? 'selected' : ''}>${_esc(c)}</option>`).join('');
        inputHtml = `<select data-param="${spec.nombre}">${opciones}</select>`;
    } else if (spec.tipo === 'fecha') {
        inputHtml = `<input type="date" data-param="${spec.nombre}">`;
    } else if (spec.tipo === 'int') {
        inputHtml = `<input type="number" data-param="${spec.nombre}" ${spec.min != null ? `min="${spec.min}"` : ''}>`;
    } else {
        const tipoHtml = spec.formato === 'email' ? 'email' : 'text';
        const valorDefault = (tool.slug === 'probar_mail' && spec.nombre === 'to' && window.HDEV_EMAIL_EMPRESA_DEFAULT)
            ? ` value="${_esc(window.HDEV_EMAIL_EMPRESA_DEFAULT)}"` : '';
        inputHtml = `<input type="${tipoHtml}" data-param="${spec.nombre}"${valorDefault} ${spec.max_length ? `maxlength="${spec.max_length}"` : ''}>`;
    }

    wrap.innerHTML = `
        <span class="hdev-input-label">${_esc(spec.label)}${spec.requerido ? ' *' : ''}</span>
        ${inputHtml}
        ${spec.help_input ? `<span class="hdev-input-help">${_esc(spec.help_input)}</span>` : ''}
    `;
    return wrap;
}

function crearBotones(tool, card) {
    if (tool.riesgo === 'muta_con_preview') {
        const btnPreview = document.createElement('button');
        btnPreview.type = 'button';
        btnPreview.className = 'hdev-btn hdev-btn--secundario';
        btnPreview.textContent = 'Vista previa';
        btnPreview.addEventListener('click', () => ejecutar(tool, card, {
            confirm: null,
            overrideParam: { nombre: tool.modo_preview.param, valor: tool.modo_preview.valor_preview },
            esPreview: true,
        }));

        const btnAplicar = document.createElement('button');
        btnAplicar.type = 'button';
        btnAplicar.className = 'hdev-btn hdev-btn--peligro';
        btnAplicar.textContent = 'Aplicar cambios';
        btnAplicar.disabled = true;
        btnAplicar.title = 'Corré primero "Vista previa" en esta página.';
        btnAplicar.addEventListener('click', () => ejecutar(tool, card, {
            confirm: 'fuerte',
            confirmMessage: `Vas a aplicar de verdad "${tool.label}" — esto modifica datos. ¿Confirmás?`,
            overrideParam: { nombre: tool.modo_preview.param, valor: tool.modo_preview.valor_aplicar },
        }));
        card._btnAplicar = btnAplicar;

        return [btnPreview, btnAplicar];
    }

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'hdev-btn hdev-btn--primario';

    if (tool.riesgo === 'dry_run_forzado') {
        btn.textContent = 'Ver simulación';
        btn.addEventListener('click', () => ejecutar(tool, card, { confirm: null }));
    } else if (tool.riesgo === 'lectura') {
        btn.textContent = 'Ejecutar';
        btn.addEventListener('click', () => ejecutar(tool, card, { confirm: null }));
    } else if (tool.riesgo === 'fiscal_fuerte') {
        btn.className = 'hdev-btn hdev-btn--peligro';
        btn.textContent = 'Ejecutar';
        btn.addEventListener('click', () => ejecutar(tool, card, {
            confirm: 'fuerte',
            confirmMessage: `Ambiente ARCA actual: ${window.HDEV_AMBIENTE_ARCA_DISPLAY}. `
                + (window.HDEV_AMBIENTE_ARCA === 'produccion'
                    ? 'Esto puede emitir un comprobante fiscal REAL. ¿Confirmás?'
                    : 'Esto emite contra el ambiente de prueba. ¿Confirmás?'),
        }));
    } else if (tool.riesgo === 'notificaciones_fuerte') {
        btn.className = 'hdev-btn hdev-btn--peligro';
        btn.textContent = 'Ejecutar';
        btn.addEventListener('click', () => ejecutar(tool, card, {
            confirm: 'fuerte',
            confirmMessage: 'Esto manda mails REALES al destino configurado en Notificaciones. ¿Confirmás?',
        }));
    } else {
        // muta_seguro / accion_real_bajo_impacto
        btn.textContent = 'Ejecutar';
        btn.addEventListener('click', () => ejecutar(tool, card, {
            confirm: 'simple',
            confirmMessage: `¿Ejecutar "${tool.label}"?`,
        }));
    }

    return [btn];
}

/* ════════════════════════════════════════════════════════════════
   LECTURA DE PARÁMETROS Y EJECUCIÓN
════════════════════════════════════════════════════════════════ */

function leerParams(card, tool) {
    const params = {};
    tool.params.forEach(spec => {
        const input = card.querySelector(`[data-param="${spec.nombre}"]`);
        if (!input) return;
        if (spec.tipo === 'bool') {
            params[spec.nombre] = input.checked;
        } else if (spec.tipo === 'int') {
            params[spec.nombre] = input.value === '' ? null : Number(input.value);
        } else {
            params[spec.nombre] = input.value === '' ? null : input.value;
        }
    });
    return params;
}

async function ejecutar(tool, card, opts) {
    if (opts.confirm) {
        const ok = await KaiConfirm(opts.confirmMessage || `¿Ejecutar "${tool.label}"?`, {
            danger: opts.confirm === 'fuerte',
            title: opts.confirm === 'fuerte' ? 'Acción real — confirmar' : '¿Confirmar acción?',
        });
        if (!ok) return;
    }

    const params = leerParams(card, tool);
    if (opts.overrideParam) {
        params[opts.overrideParam.nombre] = opts.overrideParam.valor;
    }

    const botones = Array.from(card.querySelectorAll('.hdev-btn'));
    botones.forEach(b => { b.disabled = true; });

    try {
        const resp = await fetch(window.HDEV_EJECUTAR_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ herramienta: tool.slug, params }),
        });
        const data = await resp.json();
        mostrarResultado(card, data);

        if (data.ok) {
            KaiToast.show(`"${tool.label}" ejecutado correctamente.`, 'success');
            if (opts.esPreview) card.dataset.previewOk = '1';
        } else {
            KaiToast.show(data.error || 'No se pudo ejecutar la herramienta.', 'danger', 6000);
        }
    } catch (e) {
        KaiToast.show('Error de conexión al ejecutar la herramienta.', 'danger');
    } finally {
        // El botón "Aplicar" (muta_con_preview) solo se reactiva si ya
        // hubo una vista previa exitosa en esta card — el resto siempre.
        botones.forEach(b => {
            if (b === card._btnAplicar) {
                b.disabled = card.dataset.previewOk !== '1';
                if (!b.disabled) b.title = '';
            } else {
                b.disabled = false;
            }
        });
    }
}

function mostrarResultado(card, data) {
    const box = card.querySelector('.hdev-resultado');
    const estado = card.querySelector('.hdev-resultado-estado');
    const pre = card.querySelector('.hdev-resultado-salida');

    box.hidden = false;
    box.classList.toggle('hdev-resultado--ok', !!data.ok);
    box.classList.toggle('hdev-resultado--error', !data.ok);
    estado.textContent = data.ok ? 'OK' : `Error: ${data.error || 'desconocido'}`;

    let texto = data.salida || data.salida_parcial || '(sin salida)';
    if (data.truncado) texto += '\n\n[salida truncada]';
    pre.textContent = texto;
}

function _esc(s) {
    const div = document.createElement('div');
    div.textContent = s == null ? '' : String(s);
    return div.innerHTML;
}
