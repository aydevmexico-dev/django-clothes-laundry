# Añade la fecha de alta del cliente. Las filas existentes reciben la fecha de
# la migración como "one-off default" (mismo efecto que la opción 1 interactiva
# de makemigrations); a partir de ahí auto_now_add gobierna las altas nuevas.
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('client', '0002_remove_client_unique_client_email_per_laundry'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='Fecha de alta',
            ),
            preserve_default=False,
        ),
    ]
