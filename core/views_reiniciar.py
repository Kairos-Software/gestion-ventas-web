# core/views_reiniciar.py
"""
Reinicio de datos para desarrollo.

Borra TODOS los registros de TODAS las tablas de las apps del proyecto
(menos las internas de Django) para poder arrancar de cero sin tener
que dropear la base, recrearla, correr migraciones y volver a crear el
superusuario cada vez.

Candados de seguridad (los cuatro tienen que cumplirse):
  1. Usuario autenticado.
  2. Usuario superusuario.
  3. settings.DEBUG == True  → esto garantiza que en producción
     (DEBUG=False) el endpoint responda 403 pase lo que pase, aunque
     alguien arme el request a mano.
  4. Confirmación explícita: el front manda un texto exacto
     ("REINICIAR") + la contraseña del usuario logueado.

IMPORTANTE — versión corregida:
El modelo de usuario se excluye por IDENTIDAD real (`get_user_model()`),
no por nombre de app. Si tu modelo de usuario es custom y vive en tu
propia app (no en 'auth'), excluir solo por app_label no alcanza y
termina borrando también a los superusuarios.

Además, antes de borrar nada, se calcula qué otras filas son
alcanzables desde los superusuarios que van a sobrevivir (rol,
sucursal, empresa, lo que sea que el usuario referencie por FK/O2O) y
esas filas puntuales quedan protegidas, para que un borrado en cascada
de esas tablas no se lleve puesto al superusuario.
"""
import logging

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.models import ProtectedError, RestrictedError
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)

FRASE_CONFIRMACION = 'REINICIAR'

# Apps internas de Django que jamás se tocan.
APPS_EXCLUIDAS = {'admin', 'auth', 'contenttypes', 'sessions'}


def _es_superuser_activo(user):
    return user.is_authenticated and user.is_active and user.is_superuser


@method_decorator(login_required, name='dispatch')
@method_decorator(user_passes_test(_es_superuser_activo), name='dispatch')
class ReiniciarSistemaAjax(View):

    def post(self, request):
        if not settings.DEBUG:
            logger.error(
                'Intento de reiniciar la base con DEBUG=False. Usuario: %s',
                request.user.username
            )
            return JsonResponse(
                {'ok': False, 'error': 'Esta acción solo está habilitada en modo DEBUG.'},
                status=403,
            )

        confirmacion = (request.POST.get('confirmacion') or '').strip()
        password = request.POST.get('password') or ''
        dry_run = request.POST.get('dry_run') == '1'

        if confirmacion != FRASE_CONFIRMACION:
            return JsonResponse(
                {'ok': False, 'error': f'Tenés que escribir "{FRASE_CONFIRMACION}" tal cual, sin errores.'},
                status=400,
            )

        if not password or not request.user.check_password(password):
            return JsonResponse(
                {'ok': False, 'error': 'Contraseña incorrecta.'},
                status=400,
            )

        try:
            resumen = self._reiniciar_todo(dry_run=dry_run)
        except Exception:
            logger.exception('Error al reiniciar la base de datos.')
            return JsonResponse(
                {'ok': False, 'error': 'Ocurrió un error reiniciando la base. Revisá los logs.'},
                status=500,
            )

        logger.warning(
            '%s DE BASE DE DATOS ejecutado por %s. Detalle: %s',
            'DRY-RUN (simulación)' if dry_run else 'RESET REAL',
            request.user.username, resumen
        )
        return JsonResponse({'ok': True, 'dry_run': dry_run, 'borrados': resumen})

    # ── Helpers ──────────────────────────────────────────────────────

    def _objetos_protegidos(self, objetos_raiz):
        """
        BFS desde los objetos que van a sobrevivir (los superusuarios),
        siguiendo únicamente relaciones "hacia afuera" (ForeignKey /
        OneToOne que el propio objeto define, no las que apuntan hacia
        él). Devuelve {modelo: {pks protegidos}}.

        Esto es lo que evita que, por ejemplo, borrar todos los `Rol`
        se lleve puesto al superusuario que tiene un rol asignado con
        on_delete=CASCADE.
        """
        protegidos = {}
        pendientes = list(objetos_raiz)
        visitados = set()

        while pendientes:
            obj = pendientes.pop()
            if obj is None:
                continue
            clave = (obj.__class__, obj.pk)
            if clave in visitados:
                continue
            visitados.add(clave)
            protegidos.setdefault(obj.__class__, set()).add(obj.pk)

            for campo in obj._meta.get_fields():
                if not getattr(campo, 'is_relation', False):
                    continue
                # Solo relaciones que el objeto define hacia afuera
                # (forward FK / O2O), no las reversas (related_name).
                if not (getattr(campo, 'many_to_one', False) or getattr(campo, 'one_to_one', False)):
                    continue
                if not getattr(campo, 'concrete', False):
                    continue
                try:
                    relacionado = getattr(obj, campo.name, None)
                except Exception:
                    continue
                if relacionado is not None:
                    pendientes.append(relacionado)

        return protegidos

    def _reiniciar_todo(self, dry_run=False):
        User = get_user_model()
        resumen = {}

        # Excluimos el modelo de usuario por IDENTIDAD, no por app_label
        # (si tu User es custom, puede vivir en cualquier app tuya).
        modelos = [
            m for m in apps.get_models()
            if m._meta.app_label not in APPS_EXCLUIDAS and m is not User
        ]

        with transaction.atomic():
            superusuarios = list(User.objects.filter(is_superuser=True))
            if not superusuarios:
                # Salvaguarda extra: si por algún motivo no hay ningún
                # superusuario detectado, frenamos en seco. Mejor
                # abortar que arriesgarse a un reinicio sin nadie que
                # pueda volver a entrar.
                raise RuntimeError('No se encontró ningún superusuario activo. Abortado por seguridad.')

            protegidos = self._objetos_protegidos(superusuarios)

            # 1) Usuarios no-superusuario primero.
            qs_usuarios = User.objects.filter(is_superuser=False)
            total_usuarios = qs_usuarios.count()
            if total_usuarios and not dry_run:
                qs_usuarios.delete()
            if total_usuarios:
                resumen[User._meta.label] = total_usuarios

            # 2) Resto de las tablas, salvo las filas protegidas.
            pendientes = list(modelos)
            for _ in range(5):
                if not pendientes:
                    break
                siguientes = []
                for modelo in pendientes:
                    pks_protegidos = protegidos.get(modelo, set())
                    qs = modelo.objects.all()
                    if pks_protegidos:
                        qs = qs.exclude(pk__in=pks_protegidos)
                    try:
                        if dry_run:
                            cantidad = qs.count()
                        else:
                            cantidad, _detalle = qs.delete()
                        if cantidad:
                            resumen[modelo._meta.label] = resumen.get(modelo._meta.label, 0) + cantidad
                    except (ProtectedError, RestrictedError):
                        siguientes.append(modelo)
                pendientes = siguientes

            if pendientes:
                nombres = ', '.join(m._meta.label for m in pendientes)
                raise RuntimeError(
                    f'No se pudieron borrar (dependencias PROTECT sin resolver): {nombres}'
                )

            if not dry_run:
                # Reiniciar secuencias (PKs) de lo que tocamos, para que
                # los IDs vuelvan a arrancar desde 1.
                style = no_style()
                statements = connection.ops.sequence_reset_sql(style, modelos)
                if statements:
                    with connection.cursor() as cursor:
                        for stmt in statements:
                            cursor.execute(stmt)
            else:
                # No confirmamos nada: es solo una simulación.
                transaction.set_rollback(True)

        return resumen