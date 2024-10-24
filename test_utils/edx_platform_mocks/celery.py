"""Mock celery shared task to run tests independent of celery"""


def shared_task(base):  # pylint: disable=unused-argument
    """Empty decorator to mock shared_task and celery delay"""
    def decorator(func):
        class DummyTask:
            """Mock celery task delay method"""
            @staticmethod
            def __call__(*args, **kwargs):
                return func(*args, **kwargs)

            @staticmethod
            def delay():
                return None
        return DummyTask()
    return decorator
