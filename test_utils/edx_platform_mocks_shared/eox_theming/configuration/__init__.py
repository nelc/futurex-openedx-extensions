"""eox-theming Mocks: the config sources loop of eox_theming.configuration.ThemingConfiguration"""
from typing import Any


class ThemingConfiguration:  # pylint: disable=too-few-public-methods
    """Mock of eox-theming's ThemingConfiguration (same `source_functions` loop as the real class)"""
    source_functions: list = []

    @classmethod
    def options(cls, *args: Any, **kwargs: Any) -> Any:
        """Return the first value that is not None from the sources, else the default"""
        value = None
        for source in cls.source_functions:
            value = source(*args)
            if value is not None:
                break
        if value is None:
            value = kwargs.pop('default', None)
        return value
