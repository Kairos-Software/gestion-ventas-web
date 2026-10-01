/* core/static/core/js/manual_buscador.js
   Motor del buscador del manual. La gente no busca el nombre exacto de
   una pantalla: escribe su problema ("cambiar contraseña", "devolver
   mercadería", "como anulo una venta", con errores de tipeo). Esto arma
   un índice de temas (cada .manual-sub, con su título, subtítulos y
   texto) y los ordena por qué tan bien responden a la consulta:

   - Sin tildes ni mayúsculas, ignorando palabras de relleno ("cómo",
     "quiero", "hago"…).
   - Raíces: "devoluciones" = "devolución", "cambiar" ≈ "cambio".
   - Sinónimos del negocio: "clave" = "contraseña", "fiado" = "cuenta
     corriente", "borrar" = "eliminar"… (SINONIMOS, más abajo).
   - Errores de tipeo: hasta 1 letra de diferencia en palabras de 5+
     letras, 2 en las de 8+ ("revolucione" → "devoluciones").
   - Pesa más el título del tema que el texto, y premia los temas que
     cubren TODAS las palabras buscadas.

   Cada .manual-sub puede sumar palabras propias con data-claves="..."
   (cómo lo diría alguien que no conoce el sistema).

   Uso (ver manual.js):
     const indice = ManualBuscador.crearIndice(contenedor);
     const resultados = ManualBuscador.buscar(indice, 'cambiar contraseña');
*/
(function () {
    'use strict';

    const normalizar = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

    const RELLENO = new Set((
        'a al algo algun alguna alguno ante antes aqui asi cada como con contra cual cuales cuando cuanto de debo del desde ' +
        'donde e el ella ellos en entre era es esa ese eso esta estan estar este esto estos favor fue ha hace hacer hacerlo hago hay ' +
        'la las le les lo los mas me mi mis muy necesito no nos o otra otro para pero poder por porque puedo pueda que quiero ' +
        'se ser si sin sistema sobre solo son su sus tambien te tengo tener tiene tu tus un una uno unos unas y ya yo quisiera ' +
        'deberia saber ver veo hola ayuda'
    ).split(' '));

    // Grupos de palabras que la gente usa para lo mismo. Se comparan por
    // raíz, así que alcanza con una forma de cada una.
    const SINONIMOS = [
        'contraseña clave password pass pin',
        'olvide olvidar recuperar perdi',
        'usuario user login ingresar entrar sesion acceso',
        'devolucion devolver reintegro reembolso reintegrar',
        'anular cancelar deshacer revertir',
        'eliminar borrar quitar suprimir',
        'editar modificar corregir cambiar arreglar actualizar',
        'mercaderia producto articulo item',
        'stock inventario existencia cantidad',
        'precio valor tarifa',
        'aumentar subir aumento remarcar',
        'cliente comprador',
        'proveedor distribuidor mayorista',
        'venta vender vendido',
        'compra comprar compre',
        'factura facturar comprobante boleta afip arca electronica',
        'imprimir impresora ticket pdf reimprimir',
        'caja cajon efectivo plata dinero',
        'turno jornada',
        'arqueo cierre cerrar',
        'apertura abrir',
        'fiado fiar fiada libreta',
        'cuota cuotas financiar financiado',
        'cobrar cobro cobranza',
        'pagar pago abonar',
        'cheque cheques',
        'tarjeta debito credito mercadopago transferencia qr',
        'descuento oferta promocion rebaja 2x1 liquidacion',
        'combo paquete kit',
        'vencimiento vencido vence caducado expirado',
        'perdida rotura merma roto rompio robo tirar',
        'codigo barras escaner lector escanear',
        'balanza peso pesar kilo kg',
                'permiso rol autorizar habilitar',
        'gasto egreso',
        'ingreso',
        'estadistica reporte informe ganancia balance resultado gane ganar ganado rentabilidad',
        'presupuesto cotizacion cotizar',
        'catalogo tienda pagina web online sitio',
        'pedido encargo whatsapp',
        'excel planilla importar exportar masivo',
        'empresa negocio local comercio cuit razon',
        'logo marca',
        'celular recarga saldo telefono',
        'foto imagen',
        'variante talle color sabor',
        'fraccionar granel suelto',
        'prestamo prestar prestaron',
        'bien patrimonio auto maquina',
        'nota anotador recordatorio apunte',
        'apariencia tema oscuro noche colores',
        'notificacion aviso alerta mail correo email',
        'recargo interes',
        'transaccion transferir mover',
        'scoring puntaje riesgo moroso',
        'historial registro anteriores pasadas',
        'buscar encontrar',
        'agregar alta nuevo crear añadir sumar incorporar',
        'empleado personal cajero vendedor trabajador',
        'billete contar vuelto',
    ];

    // ── Raíz liviana para español ──
    const SUFIJOS = ['amientos', 'imientos', 'amiento', 'imiento', 'aciones', 'iciones', 'acion', 'icion',
        'mente', 'ando', 'iendo', 'ados', 'idos', 'adas', 'idas', 'ado', 'ido', 'ada', 'ida', 'ar', 'er', 'ir'];
    function raiz(w) {
        if (w.length <= 3) return w;
        if (w.endsWith('s') && w.length > 4) w = w.slice(0, -1);
        for (const s of SUFIJOS) {
            if (w.endsWith(s) && w.length - s.length >= 4) return w.slice(0, -s.length);
        }
        if (/[aeo]$/.test(w) && w.length > 4) return w.slice(0, -1);
        return w;
    }

    const palabras = (txt) => normalizar(txt).match(/[a-z0-9ñ]+/g) || [];
    const limpio = (txt) => ' ' + palabras(txt).join(' ') + ' ';

    function raices(txt) {
        return palabras(txt).filter(w => !RELLENO.has(w)).map(raiz);
    }

    // raíz → raíces del mismo grupo de sinónimos
    const sinonimosDe = new Map();
    SINONIMOS.forEach(grupo => {
        const rs = [...new Set(grupo.split(' ').map(w => raiz(normalizar(w))))];
        rs.forEach(r => {
            const set = sinonimosDe.get(r) || new Set();
            rs.forEach(x => { if (x !== r) set.add(x); });
            sinonimosDe.set(r, set);
        });
    });

    // Damerau-Levenshtein con corte temprano (devuelve max+1 si se pasa).
    function distancia(a, b, max) {
        if (Math.abs(a.length - b.length) > max) return max + 1;
        const prev2 = new Array(b.length + 1);
        let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
        for (let i = 1; i <= a.length; i++) {
            const cur = [i];
            let minFila = i;
            for (let j = 1; j <= b.length; j++) {
                const costo = a[i - 1] === b[j - 1] ? 0 : 1;
                let v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + costo);
                if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
                cur[j] = v;
                if (v < minFila) minFila = v;
            }
            if (minFila > max) return max + 1;
            for (let j = 0; j <= b.length; j++) prev2[j] = prev[j];
            prev = cur;
        }
        return prev[b.length];
    }

    // Qué tan bien la raíz buscada q coincide con la raíz del texto w (0-1).
    function parecido(q, w) {
        if (q === w) return 1;
        if (q.length >= 3 && w.startsWith(q)) return 0.85;            // "contra" → contraseña
        if (w.length >= 4 && q.startsWith(w)) return 0.7;
        if (q.length < 4 || w.length < 4) return 0;
        const max = q.length >= 8 ? 2 : 1;
        const d = distancia(q, w, max);
        return d <= max ? 0.8 - 0.12 * (d - 1) : 0;
    }

    const PESO = { titulo: 6, claves: 5, subtitulo: 4, seccion: 2.5, texto: 1 };

    // Texto visible de un título, sin el "#" del enlace permanente.
    function textoTitulo(el) {
        const c = el.cloneNode(true);
        c.querySelectorAll('.manual-anchor').forEach(a => a.remove());
        return c.textContent.replace(/\s+/g, ' ').trim();
    }

    function crearIndice(raizDom) {
        const temas = [];
        const vocabulario = new Set();

        function contar(txt) {
            const m = new Map();
            raices(txt).forEach(r => { m.set(r, (m.get(r) || 0) + 1); vocabulario.add(r); });
            return m;
        }
        // Oraciones para el fragmento de cada resultado: sin los números de
        // los marcadores ni los epígrafes de las capturas ("Tocá o pasá el
        // mouse por los números").
        function oraciones(el) {
            const c = el.cloneNode(true);
            c.querySelectorAll('.manual-hotspot, .manual-anchor, figcaption, .manual-where-label').forEach(x => x.remove());
            c.querySelectorAll('p, li, h3, h4, td, th, div, figure').forEach(x => x.append(' '));
            const t = c.textContent.replace(/\s+/g, ' ').trim();
            return t.split(/(?<=[.!?])\s+/).filter(o => o.length > 12).map(o => ({ texto: o, raices: new Set(raices(o)) }));
        }

        raizDom.querySelectorAll('.manual-section').forEach(sec => {
            const h2 = sec.querySelector('h2');
            const nombreSeccion = h2 ? textoTitulo(h2) : '';
            const subs = Array.from(sec.querySelectorAll('.manual-sub'));

            subs.forEach(sub => {
                const h3 = sub.querySelector('h3');
                if (!h3) return;
                const h4s = Array.from(sub.querySelectorAll('h4'));
                const titulo = textoTitulo(h3);
                temas.push({
                    el: sub, destino: h3, seccionEl: sec,
                    titulo, seccion: nombreSeccion,
                    secuencias: [raices(titulo), raices(sub.dataset.claves || '')],
                    frases: [limpio(titulo), limpio(sub.dataset.claves || '')],
                    campos: {
                        titulo: contar(titulo),
                        claves: contar(sub.dataset.claves || ''),
                        subtitulo: contar(h4s.map(h => h.textContent).join(' ')),
                        seccion: contar(nombreSeccion),
                        texto: contar(sub.textContent),
                    },
                    subtitulos: h4s.map(h => ({ el: h, raices: new Set(raices(h.textContent)) })),
                    oraciones: oraciones(sub),
                });
            });

            // Lo que la sección dice fuera de sus subtemas (introducción, tablas).
            const intro = sec.cloneNode(true);
            intro.querySelectorAll('.manual-sub').forEach(s => s.remove());
            const textoIntro = intro.textContent;
            if (raices(textoIntro).length > 8 || !subs.length) {
                temas.push({
                    el: sec, destino: h2 || sec, seccionEl: sec,
                    titulo: nombreSeccion, seccion: subs.length ? 'Introducción' : '',
                    secuencias: [raices(nombreSeccion), raices(sec.dataset.claves || '')],
                    frases: [limpio(nombreSeccion), limpio(sec.dataset.claves || '')],
                    campos: {
                        titulo: contar(nombreSeccion),
                        claves: contar(sec.dataset.claves || ''),
                        subtitulo: new Map(), seccion: new Map(),
                        texto: contar(textoIntro),
                    },
                    subtitulos: [],
                    oraciones: oraciones(intro),
                });
            }
        });
        // Palabras raras pesan más que las que están en todos lados
        // ("devolución" distingue; "producto" aparece en medio manual).
        const df = new Map();
        temas.forEach(t => {
            const unicas = new Set();
            Object.values(t.campos).forEach(m => m.forEach((_, w) => unicas.add(w)));
            unicas.forEach(w => df.set(w, (df.get(w) || 0) + 1));
        });
        const N = temas.length || 1;
        const rareza = new Map();
        df.forEach((n, w) => rareza.set(w, Math.max(0.35, Math.min(2, Math.log(1 + N / n) / Math.log(11)))));
        return { temas, vocabulario: [...vocabulario], vocabularioSet: vocabulario, rareza };
    }

    function buscar(indice, consulta, limite = 7) {
        const grupos = [...new Set(raices(consulta))].map(r => {
            // Cada palabra buscada + sus sinónimos → raíces del manual que se le parecen.
            const alternativas = [[r, 1]];
            (sinonimosDe.get(r) || []).forEach(s => alternativas.push([s, 0.85]));
            const coinciden = new Map();   // raíz del vocabulario → puntaje
            indice.vocabulario.forEach(w => {
                let mejor = 0;
                alternativas.forEach(([a, f]) => { const p = parecido(a, w) * f; if (p > mejor) mejor = p; });
                if (mejor > 0) coinciden.set(w, mejor);
            });
            // Si la palabra buscada no está tal cual pero sí parecida, también
            // sumar los sinónimos de lo parecido ("revolucione" → devolución →
            // devolver/reintegro).
            [...coinciden.entries()].filter(([, p]) => p >= 0.6).forEach(([w, p]) => {
                (sinonimosDe.get(w) || []).forEach(s => {
                    if (indice.vocabularioSet.has(s) && !coinciden.has(s)) coinciden.set(s, p * 0.85);
                });
            });
            return coinciden;
        }).filter(g => g.size);

        const totalPalabras = new Set(raices(consulta)).size;
        const orden = raices(consulta);   // en orden, para premiar frases
        const fraseTalCual = limpio(consulta);
        if (!totalPalabras) return { resultados: [], raices: new Set() };

        const resultados = [];
        indice.temas.forEach(tema => {
            let puntos = 0, cubiertas = 0;
            const usadas = new Set();
            let mejorSubtitulo = null, puntosSubtitulo = 0;
            grupos.forEach(coinciden => {
                let mejor = 0;
                Object.entries(tema.campos).forEach(([campo, mapa]) => {
                    mapa.forEach((cant, w) => {
                        const p = coinciden.get(w);
                        if (!p) return;
                        const extra = campo === 'texto' ? Math.min(1.6, 1 + (cant - 1) * 0.15) : 1;
                        const v = PESO[campo] * p * extra * (indice.rareza.get(w) || 1);
                        if (v > mejor) mejor = v;
                        usadas.add(w);
                    });
                });
                if (mejor > 0) { puntos += mejor; cubiertas++; }
                tema.subtitulos.forEach(st => {
                    let s = 0;
                    st.raices.forEach(w => { s += coinciden.get(w) || 0; });
                    if (s > 0) { st._p = (st._p || 0) + s; }
                });
            });
            tema.subtitulos.forEach(st => {
                if ((st._p || 0) > puntosSubtitulo) { puntosSubtitulo = st._p; mejorSubtitulo = st.el; }
                st._p = 0;
            });
            if (!puntos) return;
            const cobertura = cubiertas / totalPalabras;
            let total = puntos * Math.pow(cobertura, 2);
            total += bonoFrase(orden, tema.secuencias);
            // La frase tal cual, con "qué", "una"… ("qué comprar", "hacer una factura").
            if (fraseTalCual.split(' ').length >= 4 && tema.frases.some(f => f.includes(fraseTalCual))) total += 6;
            resultados.push({ tema, puntos: total, usadas, subtitulo: mejorSubtitulo });
        });

        resultados.sort((a, b) => b.puntos - a.puntos);
        const tope = resultados.length ? resultados[0].puntos : 0;
        const elegidos = resultados.filter(r => r.puntos >= tope * 0.3).slice(0, limite);

        const todas = new Set();
        elegidos.forEach(r => {
            r.usadas.forEach(w => todas.add(w));
            r.fragmento = fragmento(r.tema, r.usadas);
        });
        return { resultados: elegidos, raices: todas };
    }

    // Palabras buscadas que aparecen juntas y en el mismo orden en el
    // título o en data-claves ("cambio de producto", "cliente me pagó"):
    // +4 por cada par, +6 si está la frase entera.
    function bonoFrase(orden, secuencias) {
        if (orden.length < 2) return 0;
        const textos = secuencias.map(sq => ' ' + sq.join(' ') + ' ');
        let bono = 0;
        for (let i = 0; i < orden.length - 1; i++) {
            const par = ` ${orden[i]} ${orden[i + 1]} `;
            if (textos.some(t => t.includes(par))) bono += 4;
        }
        if (orden.length > 2 && textos.some(t => t.includes(' ' + orden.join(' ') + ' '))) bono += 6;
        return bono;
    }

    // La oración del tema que más palabras buscadas contiene.
    function fragmento(tema, usadas) {
        let mejor = null, max = 0;
        tema.oraciones.forEach(o => {
            let n = 0;
            o.raices.forEach(r => { if (usadas.has(r)) n++; });
            if (!n) return;
            // A igual coincidencia, mejor una oración que explique algo
            // ("Tocá Cerrar Turno." dice poco).
            n += o.texto.length >= 45 ? 0.6 : 0;
            if (n > max) { max = n; mejor = o.texto; }
        });
        if (!mejor) mejor = tema.oraciones.length ? tema.oraciones[0].texto : '';
        if (mejor.startsWith(tema.titulo)) mejor = mejor.slice(tema.titulo.length).replace(/^[\s:·#.-]+/, '');
        return mejor.length > 170 ? mejor.slice(0, 167).replace(/\s+\S*$/, '') + '…' : mejor;
    }

    // Rangos de las palabras encontradas dentro de un elemento (para resaltarlas).
    function rangosEn(el, raicesBuscadas) {
        const rangos = [];
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
            acceptNode: n => n.nodeValue.trim() && !n.parentElement.closest('script, style, .manual-anchor')
                ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
        });
        const re = /[A-Za-zÀ-ÿñÑ0-9]+/g;
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            let m;
            re.lastIndex = 0;
            while ((m = re.exec(n.nodeValue))) {
                const w = normalizar(m[0]);
                if (RELLENO.has(w)) continue;
                if (raicesBuscadas.has(raiz(w))) {
                    const r = new Range();
                    r.setStart(n, m.index);
                    r.setEnd(n, m.index + m[0].length);
                    rangos.push(r);
                }
            }
        }
        return rangos;
    }

    window.ManualBuscador = { crearIndice, buscar, rangosEn, normalizar, raiz };
})();
