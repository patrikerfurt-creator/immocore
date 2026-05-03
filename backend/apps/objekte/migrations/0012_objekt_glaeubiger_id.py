from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0011_remove_vs101'),
    ]

    operations = [
        migrations.AddField(
            model_name='objekt',
            name='glaeubiger_id',
            field=models.CharField(blank=True, max_length=35, verbose_name='Gläubiger-ID'),
        ),
    ]
