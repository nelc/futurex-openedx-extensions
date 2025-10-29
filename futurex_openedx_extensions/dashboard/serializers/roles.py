"""Role-related serializers for the dashboard API."""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.fields import empty

from futurex_openedx_extensions.helpers.constants import COURSE_ACCESS_ROLES_GLOBAL
from futurex_openedx_extensions.helpers.roles import (
    RoleType,
    get_course_access_roles_queryset,
    get_user_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import get_tenants_by_org


class UserRolesSerializer(serializers.ModelSerializer):
    """Serializer for user roles."""
    user_id = serializers.SerializerMethodField(help_text='User ID in edx-platform')
    full_name = serializers.SerializerMethodField(help_text='Full name of the user')
    alternative_full_name = serializers.SerializerMethodField(help_text='Arabic name (if available)')
    username = serializers.SerializerMethodField(help_text='Username of the user in edx-platform')
    national_id = serializers.SerializerMethodField(help_text='National ID of the user (if available)')
    email = serializers.SerializerMethodField(help_text='Email of the user in edx-platform')
    tenants = serializers.SerializerMethodField()
    global_roles = serializers.SerializerMethodField()

    def __init__(self, instance: Any | None = None, data: Any = empty, **kwargs: Any):
        """Initialize the serializer."""
        self._org_tenant: dict[str, list[int]] = {}
        self._roles_data: dict[Any, Any] = {}

        permission_info = kwargs['context']['request'].fx_permission_info
        self.orgs_filter = permission_info['view_allowed_any_access_orgs']
        self.permitted_tenant_ids = permission_info['view_allowed_tenant_ids_any_access']
        self.query_params = self.parse_query_params(kwargs['context']['request'].query_params)

        if instance:
            self.construct_roles_data(instance if isinstance(instance, list) else [instance])

        super().__init__(instance, data, **kwargs)

    @staticmethod
    def parse_query_params(query_params: dict[str, Any]) -> dict[str, Any]:
        """
        Parse the query parameters.

        :param query_params: The query parameters.
        :type query_params: dict[str, Any]
        """
        result = {
            'search_text': query_params.get('search_text', ''),
            'course_ids_filter': query_params[
                'only_course_ids'
            ].split(',') if query_params.get('only_course_ids') else [],
            'roles_filter': query_params.get('only_roles', '').split(',') if query_params.get('only_roles') else [],
            'include_hidden_roles': query_params.get('include_hidden_roles', '0') == '1',
        }

        if query_params.get('active_users_filter') is not None:
            result['active_filter'] = query_params['active_users_filter'] == '1'
        else:
            result['active_filter'] = None

        excluded_role_types = query_params.get('excluded_role_types', '').split(',') \
            if query_params.get('excluded_role_types') else []

        result['excluded_role_types'] = []
        if 'global' in excluded_role_types:
            result['excluded_role_types'].append(RoleType.GLOBAL)

        if 'tenant' in excluded_role_types:
            result['excluded_role_types'].append(RoleType.ORG_WIDE)

        if 'course' in excluded_role_types:
            result['excluded_role_types'].append(RoleType.COURSE_SPECIFIC)

        return result

    def get_org_tenants(self, org: str) -> list[int]:
        """
        Get the tenants for an organization.

        :param org: The organization to get the tenants for.
        :type org: str
        :return: The tenants.
        :rtype: list[int]
        """
        result = self._org_tenant.get(org)
        if not result:
            result = get_tenants_by_org(org)
            self._org_tenant[org] = result

        return result or []

    def construct_roles_data(self, users: list[get_user_model]) -> None:
        """
        Construct the roles data.

        {
            "<userID>": {
                "<tenantID>": {
                    "tenant_roles": ["<roleName>", "<roleName>"],
                    "course_roles": {
                        "<courseID>": ["<roleName>", "<roleName>"],
                        "<courseID>": ["<roleName>", "<roleName>"],
                    },
                },
                ....
            },
            ....
        }

        :param users: The user instances.
        :type users: list[get_user_model]
        """
        self._roles_data = {}
        for user in users:
            self._roles_data[user.id] = {}

        records = get_course_access_roles_queryset(
            self.orgs_filter,
            remove_redundant=True,
            users=users,
            search_text=self.query_params['search_text'],
            roles_filter=self.query_params['roles_filter'],
            active_filter=self.query_params['active_filter'],
            course_ids_filter=self.query_params['course_ids_filter'],
            excluded_role_types=self.query_params['excluded_role_types'],
            excluded_hidden_roles=not self.query_params['include_hidden_roles'],
        )

        for record in records or []:
            usr_data = self._roles_data[record.user_id]
            for tenant_id in self.get_org_tenants(record.org):
                if tenant_id not in self.permitted_tenant_ids:
                    continue

                if tenant_id not in usr_data:
                    usr_data[tenant_id] = {
                        'tenant_roles': [],
                        'course_roles': {},
                    }

                course_id = str(record.course_id) if record.course_id else None
                if course_id and course_id not in usr_data[tenant_id]['course_roles']:
                    usr_data[tenant_id]['course_roles'][course_id] = []

                if course_id:
                    usr_data[tenant_id]['course_roles'][course_id].append(record.role)
                elif record.role not in usr_data[tenant_id]['tenant_roles']:
                    usr_data[tenant_id]['tenant_roles'].append(record.role)

    @property
    def roles_data(self) -> dict[Any, Any] | None:
        """Get the roles data."""
        return self._roles_data

    def _get_user(self, obj: Any = None) -> get_user_model | None:  # pylint: disable=no-self-use
        """
        Retrieve the associated user for the given object.

        This method can be overridden in child classes to provide a different
        implementation for accessing the user, depending on how the user is
        related to the object (e.g., `obj.user`, `obj.profile.user`, etc.).
        """
        return obj

    def _get_profile_field(self: Any, obj: get_user_model, field_name: str) -> Any:
        """Get the profile field value."""
        user = self._get_user(obj)
        return getattr(user.profile, field_name) if hasattr(user, 'profile') and user.profile else None

    def _get_extra_field(self: Any, obj: get_user_model, field_name: str) -> Any:
        """Get the extra field value."""
        user = self._get_user(obj)
        return getattr(user.extrainfo, field_name) if hasattr(user, 'extrainfo') and user.extrainfo else None

    def get_user_id(self, obj: get_user_model) -> int:
        """Return user ID."""
        return self._get_user(obj).id  # type: ignore

    def get_email(self, obj: get_user_model) -> str:
        """Return user ID."""
        return self._get_user(obj).email  # type: ignore

    def get_username(self, obj: get_user_model) -> str:
        """Return user ID."""
        return self._get_user(obj).username  # type: ignore

    def get_national_id(self, obj: get_user_model) -> Any:
        """Return national ID."""
        return self._get_extra_field(obj, 'national_id')

    def get_full_name(self, obj: get_user_model) -> Any:
        """Return full name."""
        from futurex_openedx_extensions.helpers.extractors import extract_full_name_from_user
        return extract_full_name_from_user(self._get_user(obj))

    def get_alternative_full_name(self, obj: get_user_model) -> Any:
        """Return alternative full name."""
        from futurex_openedx_extensions.helpers.extractors import (
            extract_arabic_name_from_user,
            extract_full_name_from_user,
        )
        return (
            extract_arabic_name_from_user(self._get_user(obj)) or
            extract_full_name_from_user(self._get_user(obj), alternative=True)
        )

    def get_tenants(self, obj: get_user_model) -> Any:
        """Return the tenants."""
        return self.roles_data.get(obj.id, {}) if self.roles_data else {}

    def get_global_roles(self, obj: get_user_model) -> Any:  # pylint:disable=no-self-use
        """Return the global roles."""
        roles_dict = get_user_course_access_roles(obj)['roles']
        return [role for role in roles_dict if role in COURSE_ACCESS_ROLES_GLOBAL]

    class Meta:
        model = get_user_model()
        fields = [
            'user_id',
            'email',
            'username',
            'national_id',
            'full_name',
            'alternative_full_name',
            'global_roles',
            'tenants',
        ]
