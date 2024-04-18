"""URLs configuration for testing purposes."""
from django.urls import include
from django.urls import path as rpath

urlpatterns = [
    # include the urls from the dashboard app using include
    rpath('', include('futurex_openedx_extensions.dashboard.urls'), name='fx_dashboard'),
]
