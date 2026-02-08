# Generated migration to remove choices constraint from DatasetType.name

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('xero', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasettype',
            name='name',
            field=models.CharField(help_text='Internal identifier (lowercase, no spaces)', max_length=50, unique=True),
        ),
        migrations.AlterModelOptions(
            name='datasettype',
            options={'ordering': ['display_name'], 'verbose_name': 'Dataset Type', 'verbose_name_plural': 'Dataset Types'},
        ),
    ]
