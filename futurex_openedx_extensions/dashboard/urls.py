"""
URLs for dashboard.
"""
from django.conf import settings
from django.urls import include, re_path
from lms.djangoapps.static_template_view import views as static_template_views_views
from rest_framework.routers import DefaultRouter

from futurex_openedx_extensions.dashboard import viewz
from futurex_openedx_extensions.dashboard.views.clickhouse import ClickhouseQueryView
from futurex_openedx_extensions.dashboard.views.admin import (
    AccessibleTenantsInfoView,
    AccessibleTenantsInfoViewV2,
    ExcludedTenantsView,
    TenantAssetsManagementView,
    VersionInfoView,
)
from futurex_openedx_extensions.dashboard.views.categories import (
    CategoriesOrderView,
    CategoriesView,
    CategoryDetailView,
    CourseCategoriesView,
)
from futurex_openedx_extensions.dashboard.views.configs import (
    ConfigEditableInfoView,
    ThemeConfigDraftView,
    ThemeConfigPublishView,
    ThemeConfigRetrieveView,
    ThemeConfigTenantView,
)
from futurex_openedx_extensions.dashboard.views.courses import (
    CoursesFeedbackView,
    CourseStatusesView,
    CoursesView,
    LibraryView,
)
from futurex_openedx_extensions.dashboard.views.learners import (
    LearnerCoursesView,
    LearnerInfoView,
    LearnersDetailsForCourseView,
    LearnersEnrollmentView,
    LearnersView,
    LearnerUnenrollView,
)
from futurex_openedx_extensions.dashboard.views.payments import PaymentOrdersView
from futurex_openedx_extensions.dashboard.views.roles import MyRolesView, UserRolesManagementView
from futurex_openedx_extensions.helpers.constants import CLICKHOUSE_QUERY_SLUG_PATTERN, COURSE_ID_REGX
from futurex_openedx_extensions.helpers.models import ClickhouseQuery

app_name = 'fx_dashboard'

QUERY_ALLOWED_SCOPES = '|'.join(ClickhouseQuery.allowed_scopes())

roles_router = DefaultRouter()
roles_router.register(r'user_roles', UserRolesManagementView, basename='user-roles')
export_router = DefaultRouter()
export_router.register(r'tasks', viewz.DataExportManagementView, basename='data-export-tasks')
tenant_assets_router = DefaultRouter()
tenant_assets_router.register(r'tenant_assets', TenantAssetsManagementView, basename='tenant-assets')

urlpatterns = [
    re_path(r'^api/fx/accessible/v1/info/$', AccessibleTenantsInfoView.as_view(), name='accessible-info'),
    re_path(r'^api/fx/accessible/v2/info/$', AccessibleTenantsInfoViewV2.as_view(), name='accessible-info-v2'),
    re_path(r'^api/fx/courses/v1/courses/$', CoursesView.as_view(), name='courses'),
    re_path(r'^api/fx/libraries/v1/libraries/$', LibraryView.as_view(), name='libraries'),
    re_path(r'^api/fx/courses/v1/feedback/$', CoursesFeedbackView.as_view(), name='courses-feedback'),
    re_path(r'^api/fx/courses/v1/categories/$', CategoriesView.as_view(), name='courses-categories'),
    re_path(
        r'^api/fx/courses/v1/categories/(?P<category_id>[^/]+)/$',
        CategoryDetailView.as_view(),
        name='courses-category-detail',
    ),
    re_path(
        r'^api/fx/courses/v1/categories_order/$',
        CategoriesOrderView.as_view(),
        name='courses-categories-order',
    ),
    re_path(
        fr'^api/fx/courses/v1/course_categories/{COURSE_ID_REGX}/$',
        CourseCategoriesView.as_view(),
        name='courses-course-categories',
    ),

    re_path(r'^api/fx/export/v1/', include(export_router.urls)),
    re_path(r'^api/fx/learners/v1/learners/$', LearnersView.as_view(), name='learners'),
    re_path(
        fr'^api/fx/learners/v1/learners/{COURSE_ID_REGX}/$',
        LearnersDetailsForCourseView.as_view(), name='learners-course'),
    re_path(
        r'^api/fx/learners/v1/enrollments/$',
        LearnersEnrollmentView.as_view(), name='learners-enrollements'),
    re_path(
        r'^api/fx/learners/v1/unenroll/$',
        LearnerUnenrollView.as_view(), name='learners-unenroll'),
    re_path(
        r'^api/fx/learners/v1/learner/' + settings.USERNAME_PATTERN + '/$',
        LearnerInfoView.as_view(),
        name='learner-info'
    ),
    re_path(
        r'^api/fx/learners/v1/learner_courses/' + settings.USERNAME_PATTERN + '/$',
        LearnerCoursesView.as_view(),
        name='learner-courses'
    ),
    re_path(r'^api/fx/roles/v1/my_roles/$', MyRolesView.as_view(), name='my-roles'),
    re_path(r'^api/fx/roles/v1/', include(roles_router.urls)),
    re_path(r'^api/fx/statistics/v1/course_statuses/$', CourseStatusesView.as_view(), name='course-statuses'),
    re_path(r'^api/fx/statistics/v1/rating/$', viewz.GlobalRatingView.as_view(), name='statistics-rating'),
    re_path(r'^api/fx/statistics/v1/total_counts/$', viewz.TotalCountsView.as_view(), name='total-counts'),
    re_path(
        r'^api/fx/statistics/v1/aggregated_counts/$',
        viewz.AggregatedCountsView.as_view(),
        name='aggregated-counts',
    ),
    re_path(r'^api/fx/tenants/v1/excluded', ExcludedTenantsView.as_view(), name='excluded-tenants'),
    re_path(r'^api/fx/tenants/v1/info/(?P<tenant_id>\d+)/$', viewz.TenantInfoView.as_view(), name='tenant-info'),
    re_path(
        fr'^api/fx/query/v1/(?P<scope>{QUERY_ALLOWED_SCOPES})/(?P<slug>{CLICKHOUSE_QUERY_SLUG_PATTERN})/$',
        ClickhouseQueryView.as_view(),
        name='clickhouse-query'
    ),
    re_path(r'^api/fx/version/v1/info/$', VersionInfoView.as_view(), name='version-info'),

    re_path(r'^api/fx/config/v1/editable/$', ConfigEditableInfoView.as_view(), name='config-editable-info'),
    re_path(
        r'^api/fx/config/v1/draft/(?P<tenant_id>\d+)/$',
        ThemeConfigDraftView.as_view(),
        name='theme-config-draft'
    ),
    re_path(r'^api/fx/config/v1/publish/$', ThemeConfigPublishView.as_view(), name='theme-config-publish'),
    re_path(r'^api/fx/config/v1/values/$', ThemeConfigRetrieveView.as_view(), name='theme-config-values'),
    re_path(r'^api/fx/config/v1/tenant/$', ThemeConfigTenantView.as_view(), name='theme-config-tenant'),
    re_path(r'^api/fx/file/v1/upload/$', viewz.FileUploadView.as_view(), name='file-upload'),
    re_path(r'^api/fx/assets/v1/', include(tenant_assets_router.urls)),

    re_path(r'^api/fx/payments/v1/orders/$', PaymentOrdersView.as_view(), name='payments-orders'),

    re_path(
        r'^api/fx/redirect/set_theme_preview/$',
        viewz.SetThemePreviewCookieView.as_view(),
        name='set-theme-preview',
    ),

    re_path(
        r'^p/[\w-]+/$',
        static_template_views_views.render,
        {'template': 'fx_custom_page.html'},
        name='fx-custom-page',
    )
]
