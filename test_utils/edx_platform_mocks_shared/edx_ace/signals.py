"""edx-ace Mocks: the signal ace sends after a message was delivered"""
from django.dispatch import Signal

ACE_MESSAGE_SENT = Signal()
