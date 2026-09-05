"""Filtros de formato compartidos.

`pesos` — importe con separador de miles es-AR (1.234.567,89), igual que el
`toLocaleString('es-AR')` que usan los carritos de Ventas/Compras en el front.
El proyecto corre con LANGUAGE_CODE=es-es y USE_THOUSAND_SEPARATOR=False, así
que `floatformat` sale sin separador de miles ("2250,00") y queda distinto a lo
que muestra el JS al lado. Este filtro unifica ese formato en las plantillas.

`cantidad` — cantidades de stock/unidades. Los campos de cantidad son
DecimalField(decimal_places=3): con el locale es-es, `{{ x }}` muestra 850
unidades como "850,000" y parece 850 mil. Este filtro las muestra con
separador de miles es-AR y SIN los ceros decimales de relleno:
850.000 → "850", 2.500 → "2,5", 1234.5 → "1.234,5".
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


def _miles(entero):
    """'1234' -> '1.234' (agrupa de a 3 con punto, estilo es-AR)."""
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    return '.'.join(grupos)


@register.filter(is_safe=True)
def cantidad(value):
    """850.000 -> '850'; 2.500 -> '2,5'; 0.250 -> '0,25'; 1234.5 -> '1.234,5'.
    Devuelve el valor tal cual si no es numérico."""
    if value is None or value == '':
        return ''
    try:
        monto = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value

    negativo = monto < 0
    monto = abs(monto)
    # entero exacto -> sin decimales; si no, normalize() saca los ceros
    # de relleno (2.500 -> 2.5). El quantize evita 850.000 -> '8.5E+2'.
    if monto == monto.to_integral_value():
        monto = monto.quantize(Decimal(1))
    else:
        monto = monto.normalize()

    entero, _, decimales = format(monto, 'f').partition('.')
    txt = f'{_miles(entero)},{decimales}' if decimales else _miles(entero)
    return f'-{txt}' if negativo else txt
