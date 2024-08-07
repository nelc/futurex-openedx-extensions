# Generated by Django 3.2.25 on 2024-07-25 08:54

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('fx_helpers', '0002_add_allow_write'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoricalClickhouseQuery',
            fields=[
                ('id', models.IntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('scope', models.CharField(choices=[('course', 'course'), ('platform', 'platform'), ('tenant', 'tenant'), ('user', 'user')], max_length=16)),
                ('slug', models.CharField(max_length=255)),
                ('version', models.CharField(max_length=4)),
                ('description', models.TextField(blank=True, null=True)),
                ('query', models.TextField()),
                ('params_config', models.JSONField(blank=True, default=dict)),
                ('paginated', models.BooleanField(default=True)),
                ('enabled', models.BooleanField(default=True)),
                ('modified_at', models.DateTimeField(blank=True, editable=False)),
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField()),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical Clickhouse Query',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': 'history_date',
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='ClickhouseQuery',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope', models.CharField(choices=[('course', 'course'), ('platform', 'platform'), ('tenant', 'tenant'), ('user', 'user')], max_length=16)),
                ('slug', models.CharField(max_length=255)),
                ('version', models.CharField(max_length=4)),
                ('description', models.TextField(blank=True, null=True)),
                ('query', models.TextField()),
                ('params_config', models.JSONField(blank=True, default=dict)),
                ('paginated', models.BooleanField(default=True)),
                ('enabled', models.BooleanField(default=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Clickhouse Query',
                'verbose_name_plural': 'Clickhouse Queries',
                'unique_together': {('scope', 'slug', 'version')},
            },
        ),
    ]
