"""Add the per-course progress count to CourseStat (the total of the bulk progress feed)."""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Schema only; the values are filled by sync_course_stats."""

    dependencies = [
        ('fx_helpers', '0012_coursecertificateissuance'),
    ]

    operations = [
        migrations.AddField(
            model_name='coursestat',
            name='progress_count',
            field=models.IntegerField(default=0),
        ),
    ]
