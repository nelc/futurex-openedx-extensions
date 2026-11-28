"""edx-platform Mocks: ace_common BaseMessageType"""
import uuid


class BaseMessageType:  # pylint: disable=too-few-public-methods
    """Mock of openedx.core.djangoapps.ace_common.message.BaseMessageType"""
    APP_LABEL = None

    def __init__(self, *args, **kwargs):
        self.options = {}
        self.name = self.__class__.__name__.lower()

    def personalize(self, recipient, language, user_context):
        """Return a message-like object carrying what the real personalize stores"""
        message = type('Message', (), {})()
        message.uuid = uuid.uuid4()
        message.app_label = self.APP_LABEL
        message.name = self.name
        message.options = self.options
        message.recipient = recipient
        message.language = language
        message.context = user_context
        return message
