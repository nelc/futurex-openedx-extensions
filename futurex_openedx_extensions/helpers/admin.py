"""Django admin view for the models."""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from futurex_openedx_extensions.helpers.models import ViewAllowedRoles


class ViewAllowedRolesHistoryAdmin(SimpleHistoryAdmin):
    list_display = ('view_name', 'view_description', 'allowed_role')


admin.site.register(ViewAllowedRoles, ViewAllowedRolesHistoryAdmin)
