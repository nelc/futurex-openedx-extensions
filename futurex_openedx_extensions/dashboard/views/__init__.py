"""Views for the dashboard app"""
from futurex_openedx_extensions.dashboard.views.assets import FileUploadView, TenantAssetsManagementView
from futurex_openedx_extensions.dashboard.views.config import (
    ConfigEditableInfoView,
    ThemeConfigDraftView,
    ThemeConfigPublishView,
    ThemeConfigRetrieveView,
    ThemeConfigTenantView,
)
from futurex_openedx_extensions.dashboard.views.courses import (
    CoursesFeedbackView,
    CoursesView,
    CourseStatusesView,
    GlobalRatingView,
    LibraryView,
)
from futurex_openedx_extensions.dashboard.views.learners import (
    LearnerCoursesView,
    LearnerInfoView,
    LearnersDetailsForCourseView,
    LearnersEnrollmentView,
    LearnersView,
)
from futurex_openedx_extensions.dashboard.views.roles import MyRolesView, UserRolesManagementView
from futurex_openedx_extensions.dashboard.views.statistics import AggregatedCountsView, TotalCountsView
from futurex_openedx_extensions.dashboard.views.system import (
    AccessibleTenantsInfoView,
    AccessibleTenantsInfoViewV2,
    ClickhouseQueryView,
    DataExportManagementView,
    ExcludedTenantsView,
    SetThemePreviewCookieView,
    TenantInfoView,
    VersionInfoView,
)

__all__ = [
    # Assets
    'FileUploadView',
    'TenantAssetsManagementView',
    # Config
    'ConfigEditableInfoView',
    'ThemeConfigDraftView',
    'ThemeConfigPublishView',
    'ThemeConfigRetrieveView',
    'ThemeConfigTenantView',
    # Courses
    'CoursesFeedbackView',
    'CoursesView',
    'CourseStatusesView',
    'GlobalRatingView',
    'LibraryView',
    # Learners
    'LearnerCoursesView',
    'LearnerInfoView',
    'LearnersDetailsForCourseView',
    'LearnersEnrollmentView',
    'LearnersView',
    # Roles
    'MyRolesView',
    'UserRolesManagementView',
    # Statistics
    'AggregatedCountsView',
    'TotalCountsView',
    # System
    'AccessibleTenantsInfoView',
    'AccessibleTenantsInfoViewV2',
    'ClickhouseQueryView',
    'DataExportManagementView',
    'ExcludedTenantsView',
    'SetThemePreviewCookieView',
    'TenantInfoView',
    'VersionInfoView',
]
