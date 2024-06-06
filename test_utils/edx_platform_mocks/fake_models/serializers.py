"""edx-platform models mocks for testing purposes."""


class AccountLegacyProfileSerializer:  # pylint: disable=too-few-public-methods
    """AccountLegacyProfileSerializer Mock"""
    @staticmethod
    def get_profile_image(profile, user, request):  # pylint: disable=unused-argument
        """Return profile image."""
        return {
            "has_image": user.id == 1,
            "image_url_full": "https://example.com/image_full.jpg",
            "image_url_large": "https://example.com/image_large.jpg",
            "image_url_medium": "https://example.com/image_medium.jpg",
            "image_url_small": "https://example.com/image_small.jpg",
        }
