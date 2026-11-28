"""edx-ace Mocks: Recipient"""


class Recipient:  # pylint: disable=too-few-public-methods
    """Mock of edx_ace.recipient.Recipient"""
    def __init__(self, lms_user_id, email_address=None):
        self.lms_user_id = lms_user_id
        self.email_address = email_address
