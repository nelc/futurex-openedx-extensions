# Generated by Django 4.0.10 on 2025-02-24 22:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fx_helpers', '0005_view_user_mapping'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfigAccessControl',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key_name', models.CharField(help_text='Key name, e.g., linkedin_url', max_length=255, unique=True)),
                ('path', models.CharField(help_text='Dot-separated path, e.g., theme_v2.footer.linkedin_url', max_length=500)),
                ('writable', models.BooleanField(default=False, help_text='Indicates if the field is writable')),
            ],
            options={
                'verbose_name': 'Config Access Control',
                'verbose_name_plural': 'Config Access Controls',
            },
        ),
        migrations.AlterModelOptions(
            name='historicalclickhousequery',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical Clickhouse Query', 'verbose_name_plural': 'historical Clickhouse Queries'},
        ),
        migrations.AlterModelOptions(
            name='historicalviewallowedroles',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical View Allowed Role', 'verbose_name_plural': 'historical View Allowed Roles'},
        ),
        migrations.AlterModelOptions(
            name='historicalviewusermapping',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical View-User Mapping', 'verbose_name_plural': 'historical Views-Users Mapping'},
        ),
        migrations.AlterField(
            model_name='dataexporttask',
            name='notes',
            field=models.CharField(blank=True, default='', help_text='Optional note for the task', max_length=255),
        ),
    ]
