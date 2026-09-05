# core/views_billetes.py
#
# Contador de billetes (herramienta flotante de core/base.html).
#
# Antes el estado vivía solo en el localStorage del navegador: lo que se
# cargaba en una PC no se veía en otra. Ahora hay una única fila
# compartida (ContadorBilletes, patrón singleton) para toda la
# instalación, así el arqueo de caja es el mismo desde cualquier
# navegador o dispositivo.

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from .models import ContadorBilletes


def _normalizar_denominaciones(crudas):
    """
    Deja la lista en forma canónica: [{'valor': float, 'cantidad': int}],
    sin valores <= 0, sin duplicados (suma las cantidades) y ordenada de
    mayor a menor. Tolera basura del cliente sin reventar.
    """
    acumulado = {}
    for item in (crudas or []):
        try:
            valor = float(item.get('valor'))
            cantidad = int(item.get('cantidad'))
        except (TypeError, ValueError, AttributeError):
            continue
        if valor <= 0:
            continue
        if cantidad < 0:
            cantidad = 0
        acumulado[valor] = acumulado.get(valor, 0) + cantidad
    return [
        {'valor': v, 'cantidad': acumulado[v]}
        for v in sorted(acumulado, reverse=True)
    ]


def _total(denominaciones):
    return sum(d['valor'] * d['cantidad'] for d in denominaciones)


def _payload(contador):
    denoms = contador.denominaciones or []
    return {
        'denominaciones': denoms,
        'total': _total(denoms),
        'actualizado_el': contador.actualizado_el.isoformat() if contador.actualizado_el else None,
    }


class ContadorBilletesAjax(LoginRequiredMixin, View):
    """GET devuelve el estado compartido; POST lo reemplaza entero."""

    def get(self, request):
        return JsonResponse(_payload(ContadorBilletes.get_solo()))

    def post(self, request):
        try:
            body = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        denominaciones = _normalizar_denominaciones(body.get('denominaciones'))

        contador = ContadorBilletes.get_solo()
        contador.denominaciones = denominaciones
        contador.save(update_fields=['denominaciones', 'actualizado_el'])

        return JsonResponse(_payload(contador))
