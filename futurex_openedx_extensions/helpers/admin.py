"""Django admin view for the models."""
from __future__ import annotations

from typing import Any

import yaml  # type: ignore
from django.contrib import admin
from django.core.cache import cache
from django.http import Http404, HttpResponseRedirect
from django.urls import path
from django.utils import timezone
from rest_framework.response import Response
from simple_history.admin import SimpleHistoryAdmin

from futurex_openedx_extensions.helpers.constants import CACHE_NAMES
from futurex_openedx_extensions.helpers.models import ClickhouseQuery, DataExportTask, ViewAllowedRoles


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


class ViewAllowedRolesHistoryAdmin(SimpleHistoryAdmin):
    """Admin view for the ViewAllowedRoles model."""
    list_display = ('view_name', 'view_description', 'allowed_role')


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
    list_display = ('id', 'view_name', 'status', 'progress', 'user', 'notes',)
    search_fields = ('filename', 'user__email', 'user__username', 'notes')


def register_admins() -> None:
    """Register the admin views."""
    CacheInvalidator._meta.abstract = False  # to be able to register the admin view

    admin.site.register(CacheInvalidator, CacheInvalidatorAdmin)
    admin.site.register(ClickhouseQuery, ClickhouseQueryAdmin)
    admin.site.register(ViewAllowedRoles, ViewAllowedRolesHistoryAdmin)
    admin.site.register(DataExportTask, DataExportTaskAdmin)


register_admins()
