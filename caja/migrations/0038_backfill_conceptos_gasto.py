"""
Backfill del catálogo de conceptos (ConceptoGasto) a partir de las
descripciones ya cargadas: cada Gasto histórico con descripción queda
vinculado a su concepto, y también se siembran los conceptos de los
movimientos programados (aunque todavía no tengan Gasto confirmado).

Reversible: en la vuelta atrás se desvinculan los Gastos y se borran
los ConceptoGasto (la tabla se elimina igual al revertir 0037).
"""

from django.db import migrations


def _normalizar(nombre):
    return ' '.join((nombre or '').split()).lower()[:120]


def backfill(apps, schema_editor):
    Gasto = apps.get_model('caja', 'Gasto')
    ConceptoGasto = apps.get_model('caja', 'ConceptoGasto')
    MovimientoProgramado = apps.get_model('caja', 'MovimientoProgramado')

    cache = {}  # nombre_normalizado -> ConceptoGasto

    def resolver(nombre, tipo):
        norm = _normalizar(nombre)
        if not norm:
            return None
        if norm not in cache:
            obj, _ = ConceptoGasto.objects.get_or_create(
                nombre_normalizado=norm,
                defaults={'nombre': ' '.join(nombre.split())[:120], 'tipo': tipo or 'egreso'},
            )
            cache[norm] = obj
        return cache[norm]

    # Siembra desde los programados (así aparecen en el autocompletado
    # aunque nunca se haya confirmado una instancia todavía).
    for p in MovimientoProgramado.objects.all().iterator():
        resolver(p.descripcion, p.tipo)

    # Vincula los gastos históricos, en tandas.
    pendientes = []
    for g in Gasto.objects.filter(concepto__isnull=True).exclude(descripcion='').iterator():
        concepto = resolver(g.descripcion, g.tipo)
        if concepto is None:
            continue
        g.concepto_id = concepto.pk
        pendientes.append(g)
        if len(pendientes) >= 500:
            Gasto.objects.bulk_update(pendientes, ['concepto'])
            pendientes = []
    if pendientes:
        Gasto.objects.bulk_update(pendientes, ['concepto'])


def limpiar(apps, schema_editor):
    Gasto = apps.get_model('caja', 'Gasto')
    ConceptoGasto = apps.get_model('caja', 'ConceptoGasto')
    Gasto.objects.exclude(concepto__isnull=True).update(concepto=None)
    ConceptoGasto.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('caja', '0037_conceptogasto_gasto_concepto'),
    ]

    operations = [
        migrations.RunPython(backfill, limpiar),
    ]
