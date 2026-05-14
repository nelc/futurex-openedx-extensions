"""fake zeitlabs_payments models"""
from fake_models.models import Cart, Invoice  # pylint: disable=unused-import


class CatalogueItem:  # pylint: disable=too-few-public-methods
    @classmethod
    def valid_item_types(cls):
        """Return all valid item types."""
        return ['paid_course', 'bulk_course']
