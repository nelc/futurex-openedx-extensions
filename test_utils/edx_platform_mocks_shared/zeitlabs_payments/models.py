"""fake zeitlabs_payments models"""
# pylint: skip-file
from django.db import models


class Cart(models.Model):
    """Mock Cart model"""
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True)
    status = models.CharField(max_length=20)
    updated_at = models.DateTimeField(auto_now=True)

    class Status:
        """Mock Status class"""
        PAID = 'paid'
        PENDING = 'pending'

    @classmethod
    def valid_statuses(cls):
        """Return all valid status values."""
        return [cls.Status.PENDING, cls.Status.PAID]

    class Meta:
        app_label = 'fake_models'


class CatalogueItem(models.Model):
    """Mock CatalogueItem model"""
    item_ref_id = models.CharField(max_length=255)
    sku = models.CharField(max_length=255, null=True)
    type = models.CharField(max_length=255, null=True)
    title = models.CharField(max_length=255, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    currency = models.CharField(max_length=10, null=True)

    @classmethod
    def valid_item_types(cls):
        """Return all valid item types."""
        return ['paid_course', 'bulk_course']

    class Meta:
        app_label = 'fake_models'


class CartItem(models.Model):
    """Mock CartItem model"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    catalogue_item = models.ForeignKey(CatalogueItem, on_delete=models.CASCADE)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        app_label = 'fake_models'
