"""Filtros de formato compartidos.

`pesos` — importe con separador de miles es-AR (1.234.567,89), igual que el
`toLocaleString('es-AR')` que usan los carritos de Ventas/Compras en el front.
El proyecto corre con LANGUAGE_CODE=es-es y USE_THOUSAND_SEPARATOR=False, así
que `floatformat` sale sin separador de miles ("2250,00") y queda distinto a lo
que muestra el JS al lado. Este filtro unifica ese formato en las plantillas.
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(is_safe=True)
def pesos(value):
    """1234567.5 -> '1.234.567,50'. Cadena vacía si el valor no es numérico."""
    if value is None or value == '':
        return ''
    try:
        monto = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value

    negativo = monto < 0
    entero, _, decimales = f'{abs(monto):.2f}'.partition('.')

    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)

    return f'{"-" if negativo else ""}{".".join(grupos)},{decimales}'
