"""Mock"""


class CartSerializer:  # pylint: disable=too-few-public-methods
    """Mock serializer for testing Cart data."""

    def __init__(self, instance=None, data=None, many=False, **kwargs):
        self.instance = instance
        self.data = data
        self.many = many
