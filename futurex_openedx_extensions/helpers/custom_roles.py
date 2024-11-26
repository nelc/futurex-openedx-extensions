"""New roles for FutureX Open edX Extensions."""
from __future__ import annotations

import logging
from typing import Any

from common.djangoapps.student.admin import CourseAccessRoleForm
from common.djangoapps.student.roles import REGISTERED_ACCESS_ROLES, CourseRole, OrgRole, RoleBase

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes

log = logging.getLogger(__name__)


def register_custom_access_role(cls: Any) -> Any:
    """
    Decorator that adds the new access role to the list of registered access roles to be accessible in the Django admin.

    Note: roles inheritances is not supported

    :param cls: The class to register
    :type cls: Any
    """
    def _hacky_update_django_admin_choices(choices: list[tuple[str, str]]) -> None:
        """
        Update the choices of the role field in django admin.

        :param choices: The choices to update
        :type choices: list[tuple[str, str]]
        """
        CourseAccessRoleForm.COURSE_ACCESS_ROLES = choices
        CourseAccessRoleForm.declared_fields['role'].choices = choices

    try:
        role_name = cls.ROLE
        if role_name in REGISTERED_ACCESS_ROLES:
            raise FXCodedException(
                code=FXExceptionCodes.CUSTOM_ROLE_DUPLICATE_DECLARATION,
                message=f'Trying to register a custom role {role_name} that is already registered!'
            )
    except AttributeError:
        log.exception('Role class %s does not have a ROLE attribute', cls.__name__)
    except FXCodedException as exc:
        log.exception(str(exc))
    else:
        REGISTERED_ACCESS_ROLES[role_name] = cls
        _hacky_update_django_admin_choices([(role.ROLE, role.ROLE) for role in REGISTERED_ACCESS_ROLES.values()])

    return cls


@register_custom_access_role
class FXAPIAccessRoleCourse(CourseRole):  # pylint: disable=too-few-public-methods
    """Course specific access to the FutureX APIs."""
    ROLE = 'fx_api_access'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(self.ROLE, *args, **kwargs)


class FXAPIAccessRoleOrg(OrgRole):  # pylint: disable=too-few-public-methods
    """Tenant-wide access to the FutureX APIs."""
    ROLE = 'fx_api_access'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(self.ROLE, *args, **kwargs)


@register_custom_access_role
class FXAPIAccessRoleGlobal(RoleBase):  # pylint: disable=too-few-public-methods
    """Global access to the FutureX APIs."""
    ROLE = 'fx_api_access_global'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(self.ROLE, *args, **kwargs)
