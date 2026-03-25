from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entity', '0009_entityattribute_order_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='entityposition',
            name='z_order_id',
            field=models.IntegerField(db_index=True, default=0, verbose_name='Z-Order'),
        ),
    ]
