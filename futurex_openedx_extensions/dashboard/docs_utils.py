"""Helpers for generating Swagger documentation for the FutureX Open edX Extensions API."""
from __future__ import annotations

import copy
from typing import Any, Callable

from edx_api_doc_tools import schema, schema_for

from futurex_openedx_extensions.dashboard.docs_src import docs_src


def docs(class_method_name: str) -> Callable:
    """
    Decorator to add documentation to a class method.

    :param class_method_name: The name of the class method.
    :type class_method_name
    :return: The documentation for the class method.
    :rtype: dict
    """
    def _schema(view_func: Any) -> Any:
        """Decorate a view class with the specified schema."""
        if not callable(view_func):
            raise ValueError(
                f'docs decorator must be applied to a callable function or class. Got: {view_func.__class__.__name__}'
            )

        try:
            docs_copy = copy.deepcopy(docs_src[class_method_name])
        except KeyError as error:
            raise ValueError(f'docs_utils Error: no documentation found for {class_method_name}') from error

        if view_func.__class__.__name__ == 'function':
            return schema(**docs_src[class_method_name])(view_func)

        method_name = class_method_name.split('.')[1]
        docstring = docs_copy.pop('summary', '') + '\n' + docs_copy.pop('description', '')
        if docstring == '\n':
            docstring = None
        return schema_for(
            method_name,
            docstring=docstring,
            **docs_copy
        )(view_func)

    return _schema
