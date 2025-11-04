"""fake zeitlabs_payments models"""


class Cart:  # pylint: disable=too-few-public-methods
    @classmethod
    def valid_statuses(cls):
        """Return all valid status values."""
        return ['pending', 'paid']


class CatalogueItem:  # pylint: disable=too-few-public-methods
    @classmethod
    def valid_item_types(cls):
        """Return all valid item types."""
        return ['paid_course', 'bulk_course']
