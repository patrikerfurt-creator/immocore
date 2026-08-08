from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0048_sollstellung_typ_saldovortrag'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='hausgeldsollstellung',
            name='negative_betrag_nur_korrektur',
        ),
        migrations.AddConstraint(
            model_name='hausgeldsollstellung',
            constraint=models.CheckConstraint(
                name='negative_betrag_nur_korrektur',
                check=(
                    Q(soll_betrag__gte=0)
                    | Q(sollstellungs_typ__in=['korrektur', 'abrechnungsergebnis', 'saldovortrag'])
                ),
            ),
        ),
    ]
