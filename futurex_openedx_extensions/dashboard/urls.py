"""
URLs for dashboard.
"""
from django.conf import settings
from django.urls import include, re_path
from lms.djangoapps.static_template_view import views as static_template_views_views
from rest_framework.routers import DefaultRouter

from futurex_openedx_extensions.dashboard import views
from futurex_openedx_extensions.helpers.constants import CLICKHOUSE_QUERY_SLUG_PATTERN, COURSE_ID_REGX
from futurex_openedx_extensions.helpers.models import ClickhouseQuery

app_name = 'fx_dashboard'

QUERY_ALLOWED_SCOPES = '|'.join(ClickhouseQuery.allowed_scopes())

roles_router = DefaultRouter()
roles_router.register(r'user_roles', views.UserRolesManagementView, basename='user-roles')
export_router = DefaultRouter()
export_router.register(r'tasks', views.DataExportManagementView, basename='data-export-tasks')
tenant_assets_router = DefaultRouter()
tenant_assets_router.register(r'tenant_assets', views.TenantAssetsManagementView, basename='tenant-assets')

urlpatterns = [
    re_path(r'^api/fx/accessible/v1/info/$', views.AccessibleTenantsInfoView.as_view(), name='accessible-info'),
    re_path(r'^api/fx/accessible/v2/info/$', views.AccessibleTenantsInfoViewV2.as_view(), name='accessible-info-v2'),
    re_path(r'^api/fx/courses/v1/courses/$', views.CoursesView.as_view(), name='courses'),
    re_path(r'^api/fx/libraries/v1/libraries/$', views.LibraryView.as_view(), name='libraries'),
    re_path(r'^api/fx/courses/v1/feedback/$', views.CoursesFeedbackView.as_view(), name='courses-feedback'),
    re_path(r'^api/fx/courses/v1/categories/$', views.CategoriesView.as_view(), name='courses-categories'),
    re_path(
        r'^api/fx/courses/v1/categories/(?P<category_id>[^/]+)/$',
        views.CategoryDetailView.as_view(),
        name='courses-category-detail',
    ),
    re_path(
        r'^api/fx/courses/v1/categories_order/$',
        views.CategoriesOrderView.as_view(),
        name='courses-categories-order',
    ),
    re_path(
        fr'^api/fx/courses/v1/course_categories/{COURSE_ID_REGX}/$',
        views.CourseCategoriesView.as_view(),
        name='courses-course-categories',
    ),

    re_path(r'^api/fx/export/v1/', include(export_router.urls)),
    re_path(r'^api/fx/learners/v1/learners/$', views.LearnersView.as_view(), name='learners'),
    re_path(
        fr'^api/fx/learners/v1/learners/{COURSE_ID_REGX}/$',
        views.LearnersDetailsForCourseView.as_view(), name='learners-course'),
    re_path(
        r'^api/fx/learners/v1/enrollments/$',
        views.LearnersEnrollmentView.as_view(), name='learners-enrollements'),
    re_path(
        r'^api/fx/learners/v1/unenroll/$',
        views.LearnerUnenrollView.as_view(), name='learners-unenroll'),
    re_path(
        r'^api/fx/learners/v1/learner/' + settings.USERNAME_PATTERN + '/$',
        views.LearnerInfoView.as_view(),
        name='learner-info'
    ),
    re_path(
        r'^api/fx/learners/v1/learner_courses/' + settings.USERNAME_PATTERN + '/$',
        views.LearnerCoursesView.as_view(),
        name='learner-courses'
    ),
    re_path(r'^api/fx/roles/v1/my_roles/$', views.MyRolesView.as_view(), name='my-roles'),
    re_path(r'^api/fx/roles/v1/', include(roles_router.urls)),
    re_path(r'^api/fx/statistics/v1/course_statuses/$', views.CourseStatusesView.as_view(), name='course-statuses'),
    re_path(r'^api/fx/statistics/v1/rating/$', views.GlobalRatingView.as_view(), name='statistics-rating'),
    re_path(r'^api/fx/statistics/v1/total_counts/$', views.TotalCountsView.as_view(), name='total-counts'),
    re_path(
        r'^api/fx/statistics/v1/aggregated_counts/$',
        views.AggregatedCountsView.as_view(),
        name='aggregated-counts',
    ),
    re_path(r'^api/fx/tenants/v1/excluded', views.ExcludedTenantsView.as_view(), name='excluded-tenants'),
    re_path(r'^api/fx/tenants/v1/info/(?P<tenant_id>\d+)/$', views.TenantInfoView.as_view(), name='tenant-info'),
    re_path(
        fr'^api/fx/query/v1/(?P<scope>{QUERY_ALLOWED_SCOPES})/(?P<slug>{CLICKHOUSE_QUERY_SLUG_PATTERN})/$',
        views.ClickhouseQueryView.as_view(),
        name='clickhouse-query'
    ),
    re_path(r'^api/fx/version/v1/info/$', views.VersionInfoView.as_view(), name='version-info'),

    re_path(r'^api/fx/config/v1/editable/$', views.ConfigEditableInfoView.as_view(), name='config-editable-info'),
    re_path(
        r'^api/fx/config/v1/draft/(?P<tenant_id>\d+)/$',
        views.ThemeConfigDraftView.as_view(),
        name='theme-config-draft'
    ),
    re_path(r'^api/fx/config/v1/publish/$', views.ThemeConfigPublishView.as_view(), name='theme-config-publish'),
    re_path(r'^api/fx/config/v1/values/$', views.ThemeConfigRetrieveView.as_view(), name='theme-config-values'),
    re_path(r'^api/fx/config/v1/tenant/$', views.ThemeConfigTenantView.as_view(), name='theme-config-tenant'),
    re_path(r'^api/fx/file/v1/upload/$', views.FileUploadView.as_view(), name='file-upload'),
    re_path(r'^api/fx/assets/v1/', include(tenant_assets_router.urls)),

    re_path(r'^api/fx/payments/v1/orders/$', views.PaymentOrdersView.as_view(), name='payments-orders'),
    re_path(r'^api/fx/statistics/v1/payments/$', views.PaymentStatisticsView.as_view(), name='payment-statistics'),


    re_path(
        r'^api/fx/redirect/set_theme_preview/$',
        views.SetThemePreviewCookieView.as_view(),
        name='set-theme-preview',
    ),

    re_path(
        r'^p/[\w-]+/$',
        static_template_views_views.render,
        {'template': 'fx_custom_page.html'},
        name='fx-custom-page',
    )
]
