"""
Catálogo de "Herramientas de desarrollador" — panel web (solo
superusuarios) que expone un subconjunto de los management commands del
sistema, para no depender de tener acceso SSH al servidor para usarlos.

Es la ÚNICA fuente de verdad de qué se puede ejecutar desde ese panel:
`core/views_herramientas_dev.py` nunca acepta el nombre de un command
directo del cliente, siempre busca un slug acá adentro. Si el slug no
está en `HERRAMIENTAS`, no hay ninguna forma de ejecutar nada.

Los textos (label/descripcion/interpretacion) están escritos para que los
entienda cualquier dueño de negocio, no solo un programador — evitar
jerga técnica (WSAA, dry-run, idempotente, backfill, etc.) acá adentro,
no solo en el frontend.

Deliberadamente NO están acá (ver memoria de la sesión que armó esto):
  - `probar_asistencia` / `generar_datos_prueba`: su propio código dice
    "jamás correr esto en producción" (mails reales sin dedupe, pisan
    configuración real, duplican ventas/compras de prueba).
  - `arca_probar --emitir`: se expone solo la parte de solo-lectura
    (FEDummy + FECompUltimoAutorizado) — pedir un CAE de prueba ya no
    aporta nada una vez que la conexión está probada, y emitir un
    comprobante fiscal solo para "probar" es innecesario.
  - `convertir_cxc_a_libre --aplicar`: cambia un modelo de negocio sin
    "deshacer" automático — el panel solo puede pedir la simulación
    (`aplicar` está fijo en False, ver `params_fijos`), la conversión
    real queda a propósito fuera de un botón de un clic.

Cada entrada de `HERRAMIENTAS`:
  command        nombre real del management command (Command class).
                 NUNCA se serializa al frontend.
  label          título corto para la card.
  categoria      agrupa las cards en el template ('diagnostico',
                 'mantenimiento', 'notificaciones', 'fiscal').
  riesgo         cómo la UI decide qué botón(es)/confirmación mostrar:
                   lectura                    -> un botón, sin confirmar
                   accion_real_bajo_impacto    -> un botón, confirmar simple
                   muta_seguro                 -> un botón, confirmar simple
                   muta_con_preview             -> "Vista previa" (sin
                                                    confirmar) + "Aplicar"
                                                    (confirmar fuerte)
                   dry_run_forzado              -> un botón "Ver
                                                    simulación", sin
                                                    confirmar, banner fijo
                   fiscal_fuerte                -> un botón, confirmar
                                                    fuerte, muestra el
                                                    ambiente ARCA actual
                   notificaciones_fuerte        -> un botón, confirmar
                                                    fuerte (manda mail real)
  descripcion    qué hace, en español llano, para alguien que no lee código.
  interpretacion cómo leer los resultados posibles, en español llano.
  params         lista de parámetros aceptados desde el front (ver
                 `_validar_param` para los tipos soportados). Un param
                 puede traer "opciones": [{"value":..., "label":...}] para
                 mostrarse como un desplegable con nombres entendibles en
                 vez de un número o código crudo (ver `arca_probar.tipo` y
                 `correr_asistencia.tipo`).
  params_fijos   kwargs que SIEMPRE se agregan al final, pisando
                 cualquier cosa que el cliente haya mandado con ese
                 mismo nombre — es lo que hace imposible, no solo
                 "no soportado", que el front dispare `--emitir` o
                 `--aplicar` en las herramientas que no deben.
  modo_preview   (opcional) para 'muta_con_preview': qué param y valores
                 separan la vista previa de la aplicación real.
  mostrar_ambiente_arca (opcional) la vista inyecta el ambiente ARCA
                 actual en el contexto para que la card lo muestre.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


TIPOS_ASISTENCIA_OPCIONES = [
    {"value": "todos", "label": "Todos los avisos"},
    {"value": "periodico_mensual", "label": "Reporte mensual"},
    {"value": "periodico_semanal", "label": "Reporte semanal"},
    {"value": "vencimiento", "label": "Productos por vencer"},
    {"value": "deuda", "label": "Deudas por vencer"},
    {"value": "deuda_pagada", "label": "Deudas pagadas"},
    {"value": "cuota_cobro_confirmada", "label": "Cobros confirmados"},
    {"value": "stock", "label": "Stock sin movimiento"},
    {"value": "cheques", "label": "Cheques por vencer"},
]
TIPOS_ASISTENCIA = [o["value"] for o in TIPOS_ASISTENCIA_OPCIONES]

TIPOS_COMPROBANTE_OPCIONES = [
    {"value": 11, "label": "Factura C"},
    {"value": 1, "label": "Factura A"},
    {"value": 6, "label": "Factura B"},
    {"value": 13, "label": "Nota de Crédito C"},
    {"value": 3, "label": "Nota de Crédito A"},
    {"value": 8, "label": "Nota de Crédito B"},
]


HERRAMIENTAS = {

    "estado_sistema": {
        "command": "estado_sistema",
        "label": "¿Está todo al día en este servidor?",
        "categoria": "diagnostico",
        "riesgo": "lectura",
        "descripcion": (
            "Como tenés el mismo sistema instalado por separado para cada "
            "cliente, esto te muestra un resumen de ESTA instalación "
            "puntual: qué versión del código tiene, si le falta aplicar "
            "alguna actualización de la base de datos, cuánto pesa la "
            "base y cuánto espacio ocupan las fotos y comprobantes "
            "subidos."
        ),
        "interpretacion": (
            "Si dice que la base de datos está al día, no hace falta "
            "nada. Si dice que faltan actualizaciones pendientes, hay que "
            "correr \"python manage.py migrate\" en ese servidor antes de "
            "que algo nuevo deje de funcionar bien ahí. El espacio libre "
            "en disco te avisa con tiempo si un servidor se está por "
            "quedar sin lugar."
        ),
        "params": [],
        "params_fijos": {},
    },

    "arca_certificado_info": {
        "command": "arca_certificado_info",
        "label": "¿Cuándo vence el certificado de ARCA?",
        "categoria": "fiscal",
        "riesgo": "lectura",
        "descripcion": (
            "El certificado digital que permite facturar electrónicamente "
            "tiene fecha de vencimiento y hay que renovarlo a mano en el "
            "portal de ARCA — si se vence sin darse cuenta, la "
            "facturación deja de funcionar de un día para el otro. Esto "
            "te avisa con anticipación a nombre de quién está y cuánto le "
            "queda."
        ),
        "interpretacion": (
            "Si falta poco (30 días o menos), aparece en amarillo como "
            "aviso. Si ya venció, aparece en rojo — hay que renovarlo en "
            "el portal de ARCA antes de poder seguir facturando."
        ),
        "params": [],
        "params_fijos": {},
    },

    "rastrear_stock": {
        "command": "rastrear_stock",
        "label": "¿De dónde salió el stock de un producto?",
        "categoria": "diagnostico",
        "riesgo": "lectura",
        "descripcion": (
            "Buscá un producto por su código o nombre y vas a ver de dónde "
            "vino cada unidad que tiene en stock: si entró por una compra, "
            "por la carga inicial, o si alguien lo ajustó a mano. También "
            "te dice si el stock que ves en el sistema coincide con la "
            "suma de todo eso."
        ),
        "interpretacion": (
            "Al final vas a ver \"COINCIDE\" (todo el stock se explica con "
            "lo de arriba) o \"NO COINCIDE\" (hay una diferencia que no "
            "viene de ninguna compra ni ajuste registrado — puede ser un "
            "dato viejo cargado directo en el sistema, sin que quede "
            "registro de quién lo hizo)."
        ),
        "params": [
            {"nombre": "busqueda", "posicional": True, "tipo": "str",
             "label": "Código o nombre del producto", "requerido": True,
             "max_length": 150},
            {"nombre": "todos", "tipo": "bool", "requerido": False, "default": False,
             "label": "Mostrar todas las coincidencias, no solo las primeras"},
        ],
        "params_fijos": {},
    },

    "reconstruir_producto_eliminado": {
        "command": "reconstruir_producto_eliminado",
        "label": "¿Qué tenía un producto que ya borraron?",
        "categoria": "diagnostico",
        "riesgo": "lectura",
        "descripcion": (
            "Si alguien borró un producto que todavía tenía stock, esto "
            "busca lo que quedó de rastro: de qué compra o factura inicial "
            "salió, cuánto stock exacto le quedaba justo al momento de "
            "borrarse, y cuánto valía. No revive el producto ni carga "
            "nada — solo te muestra los datos para que decidas si lo "
            "volvés a dar de alta a mano."
        ),
        "interpretacion": (
            "Buscá por el código o nombre que recuerdes (dejalo vacío para "
            "ver TODOS los productos eliminados con rastro detectable). El "
            "\"stock al momento de eliminarse\" es exacto, no una "
            "aproximación — lo único que no se puede reconstruir es el "
            "detalle de ajustes manuales de stock hechos antes de "
            "borrarlo, eso sí se pierde sin dejar rastro."
        ),
        "params": [
            {"nombre": "busqueda", "posicional": True, "tipo": "str", "requerido": False,
             "max_length": 150, "label": "Código o nombre del producto (dejalo vacío para ver todos)"},
        ],
        "params_fijos": {},
    },

    "arca_probar": {
        "command": "arca_probar",
        "label": "Revisar la conexión con ARCA",
        "categoria": "fiscal",
        "riesgo": "lectura",
        "descripcion": (
            "Se conecta con ARCA (el organismo que autoriza las facturas "
            "electrónicas) para confirmar que todo esté bien configurado, "
            "sin emitir ningún comprobante. Sirve, por ejemplo, para saber "
            "si ya se puede emitir una Nota de Crédito antes de probarlo "
            "con una devolución real."
        ),
        "interpretacion": (
            "Si sale bien, vas a ver un número (el último comprobante de "
            "ese tipo que ARCA tiene registrado) y el aviso de que está "
            "habilitado. Si da error de conexión, revisá el certificado "
            "cargado en Configuración; si el error es sobre el tipo de "
            "comprobante elegido, hay que habilitarlo primero en el "
            "portal de ARCA."
        ),
        "params": [
            {"nombre": "tipo", "tipo": "int", "requerido": False, "default": 11, "min": 1,
             "label": "Tipo de comprobante a revisar",
             "opciones": TIPOS_COMPROBANTE_OPCIONES},
            {"nombre": "cuit", "tipo": "str", "requerido": False, "max_length": 20,
             "label": "CUIT (dejalo vacío para usar el de tu empresa)"},
        ],
        "params_fijos": {},  # "emitir" no está declarado -> imposible de setear desde el front.
    },

    "procesar_lotes_vencidos": {
        "command": "procesar_lotes_vencidos",
        "label": "Dar de baja productos vencidos",
        "categoria": "mantenimiento",
        "riesgo": "muta_seguro",
        "descripcion": (
            "Busca productos con stock cuya fecha de vencimiento ya pasó "
            "y los da de baja registrándolos como pérdida. Esto ya pasa "
            "solo cada vez que alguien entra a Inventario — este botón lo "
            "fuerza ahora mismo, sin esperar a que alguien abra esa "
            "pantalla."
        ),
        "interpretacion": (
            "Si dice que no había nada vencido, no hacía falta hacer "
            "nada. Si aparece una lista, cada producto ya quedó "
            "registrado como pérdida — lo podés ver en Inventario o en "
            "Pérdidas."
        ),
        "params": [],
        "params_fijos": {},
    },

    "recalcular_scoring": {
        "command": "recalcular_scoring",
        "label": "Actualizar el puntaje de riesgo de los clientes",
        "categoria": "mantenimiento",
        "riesgo": "muta_seguro",
        "descripcion": (
            "Vuelve a calcular qué tan buen pagador es cada cliente (el "
            "puntaje de 0 a 1000 que se ve en su ficha). El sistema ya lo "
            "actualiza solo todos los días — usá esto si necesitás verlo "
            "al instante, o para revisar un cliente puntual."
        ),
        "interpretacion": (
            "\"cambios\" te dice cuántos clientes tuvieron un puntaje "
            "distinto al que tenían antes. Con \"mostrar detalle\" "
            "tildado, vas a ver el puntaje de cada cliente uno por uno."
        ),
        "params": [
            {"nombre": "cliente", "tipo": "int", "requerido": False, "min": 1,
             "label": "Cliente puntual, por ID (dejalo vacío para actualizar a todos)"},
            {"nombre": "detalle", "tipo": "bool", "requerido": False, "default": False,
             "label": "Mostrar el detalle de cada cliente"},
        ],
        "params_fijos": {},
    },

    "backfill_historial_scoring": {
        "command": "backfill_historial_scoring",
        "label": "Rellenar el historial de puntaje de los clientes",
        "categoria": "mantenimiento",
        "riesgo": "muta_seguro",
        "descripcion": (
            "Completa el gráfico \"Historial de scoring\" de cada cliente "
            "con datos de pagos pasados, para que no aparezca vacío. Es "
            "una aproximación (usa la situación actual de cada cuenta) — "
            "pensado para completarlo la primera vez, no para corregir "
            "números que ya están bien."
        ),
        "interpretacion": (
            "Te dice cuántos clientes y cuántos puntos del gráfico se "
            "completaron. Si un cliente no tiene pagos recientes, no se "
            "le agrega nada (no es un error)."
        ),
        "params": [
            {"nombre": "cliente", "tipo": "int", "requerido": False, "min": 1,
             "label": "Cliente puntual, por ID (dejalo vacío para todos)"},
        ],
        "params_fijos": {},
    },

    "historial_notificaciones": {
        "command": "historial_notificaciones",
        "label": "¿Los avisos automáticos siguen llegando?",
        "categoria": "notificaciones",
        "riesgo": "lectura",
        "descripcion": (
            "Muestra los últimos avisos automáticos que el sistema mandó "
            "(o intentó mandar): reportes periódicos, productos por "
            "vencer, deudas, stock parado, cheques. No manda nada nuevo, "
            "solo te deja ver el historial — sirve para confirmar que el "
            "envío diario automático sigue funcionando en este servidor."
        ),
        "interpretacion": (
            "Cada línea que dice \"FALLÓ\" tiene el motivo abajo — un "
            "aviso que se intentó mandar pero no llegó, sin que nadie se "
            "enterara en su momento. Si hace muchos días que no aparece "
            "nada, puede ser que simplemente no hubo nada para avisar, o "
            "que el envío automático dejó de correr en el servidor — "
            "conviene revisarlo si esperabas algo más reciente."
        ),
        "params": [
            {"nombre": "cantidad", "tipo": "int", "requerido": False, "default": 15, "min": 1,
             "label": "Cuántos avisos recientes mostrar"},
        ],
        "params_fijos": {},
    },

    "probar_mail": {
        "command": "probar_mail",
        "label": "Enviar un correo de prueba",
        "categoria": "notificaciones",
        "riesgo": "accion_real_bajo_impacto",
        "descripcion": (
            "Manda un correo real al destino que indiques, para "
            "confirmar que el sistema puede enviar mails antes de "
            "depender de eso para las alertas automáticas."
        ),
        "interpretacion": (
            "Si dice que se envió, revisá esa casilla (y la carpeta de "
            "spam) para confirmar que llegó de verdad."
        ),
        "params": [
            {"nombre": "to", "tipo": "str", "requerido": False, "max_length": 254,
             "formato": "email", "label": "Enviar a este correo"},
        ],
        "params_fijos": {},
    },

    "backfill_tarjetas": {
        "command": "backfill_tarjetas",
        "label": "Corregir saldos de tarjeta en compras viejas",
        "categoria": "mantenimiento",
        "riesgo": "muta_con_preview",
        "descripcion": (
            "Corrige compras en cuotas hechas con tarjeta ANTES de que "
            "existiera el seguimiento de saldo de tarjeta, para que "
            "también aparezcan bien reflejadas ahí. No toca préstamos ni "
            "cuentas normales."
        ),
        "interpretacion": (
            "\"Vista previa\" muestra qué se corregiría, sin cambiar nada "
            "todavía. \"Aplicar cambios\" lo hace de verdad. Podés apretar "
            "\"Vista previa\" las veces que quieras: si ya está todo "
            "corregido, va a mostrar 0."
        ),
        "params": [],
        "params_fijos": {},
        "modo_preview": {"param": "aplicar", "valor_preview": False, "valor_aplicar": True},
    },

    "backfill_movimientos_cuotas_turno": {
        "command": "backfill_movimientos_cuotas_turno",
        "label": "Completar movimientos de caja faltantes",
        "categoria": "mantenimiento",
        "riesgo": "muta_con_preview",
        "descripcion": (
            "Busca pagos en efectivo de cuotas que quedaron sin su "
            "movimiento visible en Caja Grande, por un problema del "
            "sistema ya solucionado. La plata siempre estuvo bien "
            "contada — esto solo agrega el registro que faltaba para "
            "poder verlo."
        ),
        "interpretacion": (
            "\"Vista previa\" lista qué movimientos faltan, sin crear "
            "nada todavía. \"Aplicar cambios\" los genera. Si ya se "
            "corrió antes y no hay nada nuevo, va a mostrar 0."
        ),
        "params": [],
        "params_fijos": {},
        "modo_preview": {"param": "aplicar", "valor_preview": False, "valor_aplicar": True},
    },

    "comprimir_imagenes_productos": {
        "command": "comprimir_imagenes_productos",
        "label": "Achicar el peso de las fotos de productos",
        "categoria": "mantenimiento",
        "riesgo": "muta_con_preview",
        "descripcion": (
            "Recomprime las fotos de productos y paquetes que ya están "
            "cargadas (las nuevas ya se comprimen solas al subirlas). "
            "Sirve para liberar espacio de fotos viejas que se subieron "
            "muy pesadas desde el celular."
        ),
        "interpretacion": (
            "\"Vista previa\" muestra cuánto espacio se ahorraría, sin "
            "tocar ninguna foto. \"Aplicar cambios\" hace la compresión "
            "de verdad — las fotos que ya estén bien comprimidas se "
            "dejan sin tocar."
        ),
        "params": [],
        "params_fijos": {},
        # Semántica invertida respecto a las otras dos: acá el flag real
        # del command es "--dry-run" (True = vista previa), no "--aplicar".
        "modo_preview": {"param": "dry_run", "valor_preview": True, "valor_aplicar": False},
    },

    "convertir_cxc_a_libre": {
        "command": "convertir_cxc_a_libre",
        "label": "Ver qué cuentas pasarían a cuenta corriente",
        "categoria": "mantenimiento",
        "riesgo": "dry_run_forzado",
        "descripcion": (
            "Muestra qué clientes con un plan de cuotas fijo pasarían a "
            "\"cuenta corriente\" (saldo libre) si activás ese modo, y "
            "cuáles no se pueden pasar todavía (por tener un cheque "
            "pendiente). Esta pantalla solo simula — el cambio real se "
            "hace por otro medio, a propósito, porque no tiene vuelta "
            "atrás fácil."
        ),
        "interpretacion": (
            "\"Convertibles\" son los que sí se podrían pasar. "
            "\"Bloqueadas\" te dice por qué cada uno no se puede pasar "
            "todavía. Nada de esto cambia datos."
        ),
        "params": [
            {"nombre": "cliente", "tipo": "int", "requerido": False, "min": 1,
             "label": "Cliente puntual, por ID (dejalo vacío para todos)"},
        ],
        "params_fijos": {"aplicar": False},  # inalcanzable desde el front: siempre simulación.
    },

    "correr_asistencia": {
        "command": "correr_asistencia",
        "label": "Mandar ahora los reportes y alertas por mail",
        "categoria": "notificaciones",
        "riesgo": "notificaciones_fuerte",
        "descripcion": (
            "Manda ya mismo, por correo, los reportes y alertas que "
            "normalmente llegan solos (reporte mensual/semanal, "
            "productos por vencer, deudas, cheques, etc.) al mail "
            "configurado en Notificaciones. No es una prueba: es el "
            "mismo correo real que recibiría el negocio."
        ),
        "interpretacion": (
            "Cada línea \"OK\" es un correo que se mandó de verdad. Si "
            "dice \"ya se avisó hace poco\", ese mismo aviso se mandó "
            "hace menos de una semana y no se repite — tildá \"Enviar "
            "aunque ya se haya avisado\" si necesitás que se mande igual."
        ),
        "params": [
            {"nombre": "tipo", "tipo": "choice", "requerido": False, "default": "todos",
             "choices": TIPOS_ASISTENCIA, "label": "Qué avisos mandar",
             "opciones": TIPOS_ASISTENCIA_OPCIONES},
            {"nombre": "fecha", "tipo": "fecha", "requerido": False,
             "label": "Simular que hoy es otra fecha (opcional, AAAA-MM-DD)"},
            {"nombre": "forzar", "tipo": "bool", "requerido": False, "default": False,
             "label": "Enviar aunque ya se haya avisado hace poco"},
        ],
        "params_fijos": {},
    },

    "emitir_nc_devolucion": {
        "command": "emitir_nc_devolucion",
        "label": "Reintentar el envío de una Nota de Crédito",
        "categoria": "fiscal",
        "riesgo": "fiscal_fuerte",
        "descripcion": (
            "Si registraste una devolución y la Nota de Crédito no se "
            "pudo emitir ante ARCA la primera vez, esto lo vuelve a "
            "intentar. La devolución en sí ya quedó bien registrada (el "
            "stock y la caja no dependen de esto) — solo falta este paso "
            "fiscal."
        ),
        "interpretacion": (
            "Si el ambiente de ARCA es Producción, esto puede emitir un "
            "comprobante fiscal real, no de prueba. Si dice que la "
            "devolución ya tiene una Nota de Crédito, no hacía falta "
            "hacer nada. Si ARCA lo rechaza, la devolución sigue intacta "
            "— podés corregir lo que haga falta y reintentar."
        ),
        "params": [
            {"nombre": "devolucion_numero", "posicional": True, "tipo": "str", "requerido": True,
             "max_length": 20,
             "label": "Número de la devolución, tal cual aparece en el detalle de la venta (ej: DEV-00001)"},
        ],
        "params_fijos": {},
        "mostrar_ambiente_arca": True,
    },

    "auditar_nc_faltantes": {
        "command": "auditar_nc_faltantes",
        "label": "¿Falta alguna Nota de Crédito?",
        "categoria": "fiscal",
        "riesgo": "lectura",
        "descripcion": (
            "Revisa todas las ventas facturadas ante ARCA y busca huecos: "
            "devoluciones que nunca llegaron a tener su Nota de Crédito, o "
            "ventas anuladas (con una versión vieja del sistema, antes de "
            "que existiera este control) que dejaron la factura vigente "
            "sin ninguna Nota de Crédito ni devolución registrada. No "
            "cambia nada, solo informa."
        ),
        "interpretacion": (
            "Si dice que no hay ningún hueco, no hace falta hacer nada. Si "
            "aparece una devolución sin Nota de Crédito, se resuelve con "
            "\"Reintentar el envío de una Nota de Crédito\" usando el "
            "número que te muestra ahí mismo. Si aparece una venta anulada "
            "sin devolución registrada, el sistema hoy no tiene forma "
            "automática de resolverlo — hay que revisarla a mano."
        ),
        "params": [],
        "params_fijos": {},
    },
}


# ── Validación de parámetros ────────────────────────────────────────

class ParametroInvalido(Exception):
    pass


def _validar_param(spec, valor_crudo):
    """Valida y normaliza un valor crudo (ya decodificado de JSON) según
    la spec declarada. Nunca deja pasar un tipo que no sea el esperado:
    call_command() no vuelve a parsear strings como lo haría la consola,
    así que un tipo incorrecto puede romper feo adentro del Command."""
    nombre = spec["nombre"]
    label = spec.get("label", nombre)
    ausente = valor_crudo is None or (isinstance(valor_crudo, str) and valor_crudo.strip() == "")

    if ausente:
        if spec.get("requerido"):
            raise ParametroInvalido(f'Falta "{label}".')
        return spec.get("default")

    tipo = spec["tipo"]

    if tipo == "int":
        try:
            valor = int(valor_crudo)
        except (TypeError, ValueError):
            raise ParametroInvalido(f'"{label}" tiene que ser un número entero.')
        if "min" in spec and valor < spec["min"]:
            raise ParametroInvalido(f'"{label}" tiene que ser mayor o igual a {spec["min"]}.')
        if "opciones" in spec and valor not in {o["value"] for o in spec["opciones"]}:
            raise ParametroInvalido(f'"{label}" tiene un valor no reconocido.')
        return valor

    if tipo == "bool":
        if not isinstance(valor_crudo, bool):
            raise ParametroInvalido(f'"{label}" tiene que ser verdadero/falso.')
        return valor_crudo

    if tipo == "str":
        if not isinstance(valor_crudo, str):
            raise ParametroInvalido(f'"{label}" tiene que ser texto.')
        valor = valor_crudo.strip()
        if "max_length" in spec and len(valor) > spec["max_length"]:
            raise ParametroInvalido(f'"{label}" es demasiado largo (máximo {spec["max_length"]} caracteres).')
        if spec.get("formato") == "email":
            try:
                validate_email(valor)
            except ValidationError:
                raise ParametroInvalido(f'"{label}" no es un email válido.')
        return valor

    if tipo == "fecha":
        if not isinstance(valor_crudo, str):
            raise ParametroInvalido(f'"{label}" tiene que ser una fecha en formato AAAA-MM-DD.')
        try:
            date.fromisoformat(valor_crudo)
        except ValueError:
            raise ParametroInvalido(f'"{label}" tiene que ser una fecha válida (AAAA-MM-DD).')
        return valor_crudo  # el Command espera el string, no un date.

    if tipo == "choice":
        if valor_crudo not in spec["choices"]:
            raise ParametroInvalido(f'"{label}" tiene que ser uno de: {", ".join(spec["choices"])}.')
        return valor_crudo

    raise ParametroInvalido(f'Tipo de parámetro desconocido para "{label}".')


def construir_args_kwargs(tool, params_crudos):
    """Valida `params_crudos` (dict ya decodificado del body JSON) contra
    `tool['params']` (+ el param de `modo_preview`, si tiene), rechazando
    cualquier clave no declarada, y arma (args, kwargs) listos para
    call_command(). `params_fijos` se aplica SIEMPRE al final, pisando
    cualquier valor que el cliente haya mandado con ese mismo nombre."""
    modo_preview = tool.get("modo_preview")
    nombres_declarados = {p["nombre"] for p in tool["params"]}
    if modo_preview:
        nombres_declarados.add(modo_preview["param"])

    extra = set(params_crudos or {}) - nombres_declarados
    if extra:
        raise ParametroInvalido(f'Parámetro no permitido: {", ".join(sorted(extra))}.')

    args = []
    kwargs = {}
    for spec in tool["params"]:
        valor = _validar_param(spec, (params_crudos or {}).get(spec["nombre"]))
        if spec.get("posicional"):
            if valor is not None:
                args.append(valor)
        elif valor is not None:
            kwargs[spec["nombre"]] = valor

    if modo_preview:
        # No es un param "de usuario": lo elige el botón que se apretó
        # (Vista previa / Aplicar), nunca un input libre — pero igual se
        # valida que sea exactamente uno de los dos valores esperados,
        # nunca confiar en que el front no mande otra cosa.
        nombre = modo_preview["param"]
        valor_crudo = (params_crudos or {}).get(nombre)
        permitidos = {modo_preview["valor_preview"], modo_preview["valor_aplicar"]}
        if not isinstance(valor_crudo, bool) or valor_crudo not in permitidos:
            raise ParametroInvalido('Modo de ejecución inválido.')
        kwargs[nombre] = valor_crudo

    kwargs.update(tool.get("params_fijos", {}))
    return args, kwargs


def serializar_para_frontend():
    """Vista pública del catálogo — nunca incluye `command` ni
    `params_fijos` (detalles internos del servidor, no le sirven ni le
    incumben al frontend)."""
    salida = []
    for slug, tool in HERRAMIENTAS.items():
        salida.append({
            "slug": slug,
            "label": tool["label"],
            "categoria": tool["categoria"],
            "riesgo": tool["riesgo"],
            "descripcion": tool["descripcion"],
            "interpretacion": tool["interpretacion"],
            "params": tool["params"],
            "modo_preview": tool.get("modo_preview"),
            "mostrar_ambiente_arca": tool.get("mostrar_ambiente_arca", False),
        })
    return salida
