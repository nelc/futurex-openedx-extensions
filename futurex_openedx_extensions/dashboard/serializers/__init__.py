"""Serializers for the dashboard API."""
# Import all serializers to make them available from the serializers package

# Common serializers
from futurex_openedx_extensions.dashboard.serializers.common import (
    DataExportTaskSerializer,
    FxPermissionInfoSerializerMixin,
    ReadOnlySerializer,
)

# Learner serializers
from futurex_openedx_extensions.dashboard.serializers.learners import (
    CourseScoreAndCertificateSerializer,
    LearnerBasicDetailsSerializer,
    LearnerDetailsExtendedSerializer,
    LearnerDetailsForCourseSerializer,
    LearnerDetailsSerializer,
    LearnerEnrollmentSerializer,
)

# Course serializers
from futurex_openedx_extensions.dashboard.serializers.courses import (
    CourseCreateSerializer,
    CourseDetailsBaseSerializer,
    CourseDetailsSerializer,
    CoursesFeedbackSerializer,
    LearnerCoursesDetailsSerializer,
    LibrarySerializer,
)

# Role serializers
from futurex_openedx_extensions.dashboard.serializers.roles import (
    UserRolesSerializer,
)

# Config serializers
from futurex_openedx_extensions.dashboard.serializers.config import (
    FileUploadSerializer,
    TenantAssetSerializer,
    TenantConfigSerializer,
)

# Statistics serializers
from futurex_openedx_extensions.dashboard.serializers.statistics import (
    AggregatedCountsAllTenantsSerializer,
    AggregatedCountsOneTenantSerializer,
    AggregatedCountsQuerySettingsSerializer,
    AggregatedCountsSerializer,
    AggregatedCountsTotalsSerializer,
    AggregatedCountsValuesSerializer,
)

__all__ = [
    # Common
    'DataExportTaskSerializer',
    'FxPermissionInfoSerializerMixin',
    'ReadOnlySerializer',
    # Learners
    'CourseScoreAndCertificateSerializer',
    'LearnerBasicDetailsSerializer',
    'LearnerDetailsExtendedSerializer',
    'LearnerDetailsForCourseSerializer',
    'LearnerDetailsSerializer',
    'LearnerEnrollmentSerializer',
    # Courses
    'CourseCreateSerializer',
    'CourseDetailsBaseSerializer',
    'CourseDetailsSerializer',
    'CoursesFeedbackSerializer',
    'LearnerCoursesDetailsSerializer',
    'LibrarySerializer',
    # Roles
    'UserRolesSerializer',
    # Config
    'FileUploadSerializer',
    'TenantAssetSerializer',
    'TenantConfigSerializer',
    # Statistics
    'AggregatedCountsAllTenantsSerializer',
    'AggregatedCountsOneTenantSerializer',
    'AggregatedCountsQuerySettingsSerializer',
    'AggregatedCountsSerializer',
    'AggregatedCountsTotalsSerializer',
    'AggregatedCountsValuesSerializer',
]
