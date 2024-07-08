"""Models for the dashboard app."""
from django.db import models
from simple_history.models import HistoricalRecords


class ViewAllowedRoles(models.Model):
    """Allowed roles for every supported view"""
    view_name = models.CharField(max_length=255)
    view_description = models.CharField(null=True, blank=True, max_length=255)
    allowed_role = models.CharField(max_length=255)
    allow_write = models.BooleanField(default=False)

    history = HistoricalRecords()

    class Meta:
        """Metaclass for the model"""
        verbose_name = 'View Allowed Role'
        verbose_name_plural = 'View Allowed Roles'
        unique_together = ('view_name', 'allowed_role')

    def save(self, *args, **kwargs):
        """Override the save method to apply data cleanup"""
        self.clean()
        super().save(*args, **kwargs)
