"""
URLs for dashboard.
"""
from django.urls import re_path

from futurex_openedx_extensions.dashboard.views import TotalCountsView

app_name = 'fx_dashboard'

urlpatterns = [
    re_path(r'^api/fx/statistics/v1/total_counts', TotalCountsView.as_view(), name='total-counts'),
]
