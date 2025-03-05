"""Django admin view for the models."""
from __future__ import annotations

from typing import Any, List, Tuple

import yaml  # type: ignore
from common.djangoapps.student.admin import CourseAccessRoleForm
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.core.cache import cache
from django.http import Http404, HttpResponseRedirect
from django.urls import path
from django.utils import timezone
from django.utils.translation.trans_null import gettext_lazy
from django_mysql.models import QuerySet
from eox_tenant.models import TenantConfig
from openedx.core.lib.api.authentication import BearerAuthentication
from rest_framework.response import Response
from simple_history.admin import SimpleHistoryAdmin

from futurex_openedx_extensions.helpers.constants import CACHE_NAMES
from futurex_openedx_extensions.helpers.models import (
    ClickhouseQuery,
    ConfigAccessControl,
    DataExportTask,
    ViewAllowedRoles,
    ViewUserMapping,
)
from futurex_openedx_extensions.helpers.roles import get_fx_view_with_roles


class YesNoFilter(SimpleListFilter):
    """Filter for the Yes/No fields."""
    title = 'Yes / No'
    parameter_name = 'not_yet_set_must_be_replaced'

    def lookups(self, request: Any, model_admin: Any) -> List[Tuple[str, str]]:
        """
        Define filter options.

        :param request: The request object
        :type request: Request
        :param model_admin: The model admin object
        :type model_admin: Any
        :return: List of filter options
        """
        return [
            ('yes', gettext_lazy('Yes')),
            ('no', gettext_lazy('No')),
        ]

    def queryset(self, request: Any, queryset: QuerySet) -> QuerySet:
        """
        Filter the queryset based on the selected option.

        :param request: The request object
        :type request: Request
        :param queryset: The queryset to filter
        :type queryset: QuerySet
        :return: The filtered queryset
        """
        filter_params = {self.parameter_name: self.value() == 'yes'}

        if self.value() in ('yes', 'no'):
            return queryset.filter(**filter_params)

        return queryset


class ClickhouseQueryAdmin(SimpleHistoryAdmin):
    """Admin view for the ClickhouseQuery model."""
    change_list_template = 'clickhouse_query_change_list.html'

    def changelist_view(self, request: Any, extra_context: dict | None = None) -> Response:
        """Override the default changelist_view to add missing queries info."""
        extra_context = extra_context or {}
        extra_context['fx_missing_queries_count'] = ClickhouseQuery.get_missing_queries_count()

        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self) -> list:
        """Override the default get_urls to add custom cache invalidation URL."""
        urls = super().get_urls()
        urls.append(
            path(
                r'load_missing_queries',
                self.admin_site.admin_view(self.load_missing_queries),
                name='fx_helpers_clickhousequery_load_missing_queries'
            ),
        )
        return urls

    def load_missing_queries(self, request: Any) -> HttpResponseRedirect:  # pylint: disable=no-self-use
        """
        Load the missing Clickhouse queries.

        :param request: The request object
        :type request: Request
        :return: HttpResponseRedirect to the previous page
        """
        ClickhouseQuery.load_missing_queries()

        full_path = request.get_full_path()
        full_path = full_path[:len(full_path) - 1]
        one_step_back_path = full_path.rsplit('/', 1)[0]
        return HttpResponseRedirect(one_step_back_path)

    list_display = ('id', 'scope', 'version', 'slug', 'description', 'enabled', 'modified_at')


class ViewAllowedRolesModelForm(forms.ModelForm):
    """Model form for the ViewAllowedRoles model."""
    class Meta:
        """Meta class for the ViewAllowedRoles model form."""
        model = ViewAllowedRoles
        fields = '__all__'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the form with the dynamic choices."""
        super().__init__(*args, **kwargs)

        self.fields['view_name'] = forms.TypedChoiceField()
        self.fields['view_name'].choices = sorted([
            (view_name, view_name) for view_name in get_fx_view_with_roles()['_all_view_names']
        ])

        self.fields['allowed_role'] = forms.TypedChoiceField()
        self.fields['allowed_role'].choices = CourseAccessRoleForm.COURSE_ACCESS_ROLES


class ViewAllowedRolesHistoryAdmin(SimpleHistoryAdmin):
    """Admin view for the ViewAllowedRoles model."""
    form = ViewAllowedRolesModelForm

    list_display = ('view_name', 'view_description', 'allowed_role')
    list_filter = ('view_name', 'allowed_role')


class IsUserActiveFilter(YesNoFilter):
    """Filter for the is_user_active field."""
    title = 'Is User Active'
    parameter_name = 'is_user_active'


class IsUserSystemStaffFilter(YesNoFilter):
    """Filter for the is_user_system_staff field."""
    title = 'Is User System Staff'
    parameter_name = 'is_user_system_staff'


class UsableFilter(YesNoFilter):
    """Filter for the usable field."""
    title = 'Usable'
    parameter_name = 'usable'


class HasAccessRomeFilter(YesNoFilter):
    """Filter for the usable field."""
    title = 'Has Access Role'
    parameter_name = 'has_access_role'


class ViewUserMappingModelForm(forms.ModelForm):
    """Model form for the ViewUserMapping model."""
    class Meta:
        """Meta class for the ViewUserMapping model form."""
        model = ViewUserMapping
        fields = '__all__'

    @staticmethod
    def get_all_supported_view_names() -> List[Any]:
        """Get all the supported view names."""
        result = []

        for view_name, view_class in get_fx_view_with_roles()['_all_view_names'].items():
            if hasattr(
                view_class, 'authentication_classes',
            ) and BearerAuthentication in view_class.authentication_classes:
                result.append(view_name)

        return sorted(result)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the form with the dynamic choices."""
        super().__init__(*args, **kwargs)

        self.fields['view_name'] = forms.TypedChoiceField()
        self.fields['view_name'].choices = [(view_name, view_name) for view_name in self.get_all_supported_view_names()]


class ViewUserMappingHistoryAdmin(SimpleHistoryAdmin):
    """Admin view for the ViewUserMapping model."""
    form = ViewUserMappingModelForm

    list_display = (
        'user', 'view_name', 'enabled', 'expires_at', 'is_user_active',
        'is_user_system_staff', 'has_access_role', 'usable',
    )
    list_filter = (
        'view_name', 'enabled', 'expires_at',
        IsUserActiveFilter, IsUserSystemStaffFilter, HasAccessRomeFilter, UsableFilter,
    )
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)

    def is_user_active(self, obj: ViewUserMapping) -> bool:  # pylint: disable=no-self-use
        """Check if the user is active or not."""
        return obj.get_is_user_active()

    def is_user_system_staff(self, obj: ViewUserMapping) -> bool:  # pylint: disable=no-self-use
        """Check if the user is system staff or not."""
        return obj.get_is_user_system_staff()

    def has_access_role(self, obj: ViewUserMapping) -> bool:  # pylint: disable=no-self-use
        """Check if the user has access role."""
        return obj.get_has_access_role()

    def usable(self, obj: ViewUserMapping) -> bool:  # pylint: disable=no-self-use
        """Check if the mapping link is usable."""
        return obj.get_usable()

    is_user_active.short_description = 'Is User Active'  # type: ignore
    is_user_active.boolean = True  # type: ignore
    is_user_active.admin_order_field = 'is_user_active'  # type: ignore

    is_user_system_staff.short_description = 'Is User System Staff'  # type: ignore
    is_user_system_staff.boolean = True  # type: ignore
    is_user_system_staff.admin_order_field = 'is_user_system_staff'  # type: ignore

    has_access_role.short_description = 'Has Access Role'  # type: ignore
    has_access_role.boolean = True  # type: ignore
    has_access_role.admin_order_field = 'has_access_role'  # type: ignore

    usable.short_description = 'Usable'  # type: ignore
    usable.boolean = True  # type: ignore
    usable.admin_order_field = 'usable'  # type: ignore


class CacheInvalidator(ViewAllowedRoles):
    """Dummy class to be able to register the Non-Model admin view CacheInvalidatorAdmin."""
    class Meta:
        """Meta class for the CacheInvalidator model."""
        proxy = True
        verbose_name = 'Cache Invalidator'
        verbose_name_plural = 'Cache Invalidators'
        abstract = True  # to be ignored by makemigrations


class CacheInvalidatorAdmin(admin.ModelAdmin):
    """Admin view for the CacheInvalidator model."""
    change_list_template = 'cache_invalidator_change_list.html'
    change_list_title = 'Cache Invalidator'

    def changelist_view(self, request: Any, extra_context: dict | None = None) -> Response:
        """Override the default changelist_view to add cache info."""
        now_datetime = timezone.now()

        extra_context = extra_context or {}
        cache_info = {}
        for cache_name, info in CACHE_NAMES.items():
            data = cache.get(cache_name)
            remaining_minutes = (data['expiry_datetime'] - now_datetime).total_seconds() / 60 if data else None
            remaining_minutes = round(remaining_minutes, 2) if remaining_minutes else None
            cache_info[cache_name] = {
                'short_description': info['short_description'],
                'long_description': info['long_description'],
                'available': 'Yes' if data is not None else 'No',
                'created_datetime': data['created_datetime'] if data else None,
                'expiry_datetime': data['expiry_datetime'] if data else None,
                'remaining_minutes': remaining_minutes,
                'data': yaml.dump(data['data'], default_flow_style=False) if data else None,
            }

        extra_context['fx_cache_info'] = cache_info
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self) -> list:
        """Override the default get_urls to add custom cache invalidation URL."""
        custom_urls = [
            path(
                r'',
                self.admin_site.admin_view(self.changelist_view),
                name='fx_helpers_cacheinvalidator_changelist'
            ),
            path(
                'invalidate_<str:cache_name>',
                self.admin_site.admin_view(self.invalidate_cache),
                name='fx_helpers_cacheinvalidator_invalidate_cache'
            ),
        ]

        return custom_urls

    def invalidate_cache(self, request: Any, cache_name: str) -> HttpResponseRedirect:  # pylint: disable=no-self-use
        """
        Invalidate the cache with the given name.

        :param request: The request object
        :type request: Request
        :param cache_name: The name of the cache to invalidate
        :type cache_name: str
        :return: HttpResponseRedirect to the previous page
        """
        if cache_name not in CACHE_NAMES:
            raise Http404(f'Cache name {cache_name} not found')

        cache.set(cache_name, None)
        full_path = request.get_full_path()
        full_path = full_path[:len(full_path) - 1]
        one_step_back_path = full_path.rsplit('/', 1)[0]
        return HttpResponseRedirect(one_step_back_path)


class DataExportTaskAdmin(admin.ModelAdmin):
    """Admin class of DataExportTask model"""
    raw_id_fields = ('user', 'tenant')
    list_display = ('id', 'view_name', 'status', 'progress', 'user', 'notes',)
    search_fields = ('filename', 'user__email', 'user__username', 'notes')


class ConfigAccessControlForm(forms.ModelForm):
    """Admin class of ConfigAccessControl model"""

    class Meta:
        model = ConfigAccessControl
        fields = '__all__'

    def clean_path(self) -> str:
        """Validates path with default tenant config."""
        key_path = self.data['path']

        if ' ' in key_path:
            raise forms.ValidationError('Key path must not contain spaces.')

        try:
            default_config = TenantConfig.objects.get(route__domain=settings.FX_DEFAULT_TENANT_SITE).lms_configs
        except TenantConfig.DoesNotExist as exc:
            raise forms.ValidationError('Unable to update path as default TenantConfig not found.') from exc

        path_parts = key_path.split('.')
        data_pointer = default_config
        found_path = []

        for part in path_parts:
            try:
                data_pointer = data_pointer[part]
                found_path.append(part)
            except (KeyError, TypeError) as exc:
                if found_path:
                    joined_found_path = '.'.join(found_path)
                    raise forms.ValidationError(
                        f'Path "{joined_found_path}" found in default config but '
                        f'unable to find "{part}" in "{joined_found_path}"'
                    ) from exc
                raise forms.ValidationError(
                    f'Invalid path: "{part}" does not exist in the default config.'
                ) from exc
        return key_path


class ConfigAccessControlAdmin(admin.ModelAdmin):
    form = ConfigAccessControlForm
    list_display = ('id', 'key_name', 'path', 'writable',)


def register_admins() -> None:
    """Register the admin views."""
    CacheInvalidator._meta.abstract = False  # to be able to register the admin view

    admin.site.register(CacheInvalidator, CacheInvalidatorAdmin)
    admin.site.register(ClickhouseQuery, ClickhouseQueryAdmin)
    admin.site.register(ViewAllowedRoles, ViewAllowedRolesHistoryAdmin)
    admin.site.register(ViewUserMapping, ViewUserMappingHistoryAdmin)
    admin.site.register(DataExportTask, DataExportTaskAdmin)
    admin.site.register(ConfigAccessControl, ConfigAccessControlAdmin)


register_admins()
