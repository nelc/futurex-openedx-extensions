"""Views for the dashboard app"""
from common.djangoapps.student.models import get_user_by_username_or_email
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.details.courses import get_courses_queryset, get_learner_courses_info_queryset
from futurex_openedx_extensions.dashboard.details.learners import (
    get_learner_info_queryset,
    get_learners_by_course_queryset,
    get_learners_queryset,
)
from futurex_openedx_extensions.dashboard.statistics.certificates import get_certificates_count
from futurex_openedx_extensions.dashboard.statistics.courses import get_courses_count, get_courses_count_by_status
from futurex_openedx_extensions.dashboard.statistics.learners import get_learners_count
from futurex_openedx_extensions.helpers.constants import COURSE_STATUS_SELF_PREFIX, COURSE_STATUSES
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import (
    HasCourseAccess,
    HasTenantAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
)
from futurex_openedx_extensions.helpers.tenants import (
    get_accessible_tenant_ids,
    get_selected_tenants,
    get_tenants_info,
    get_user_id_from_username_tenants,
)
from futurex_openedx_extensions.helpers.throttles import AnonymousDataRetrieveRateThrottle


class TotalCountsView(APIView):
    """View to get the total count statistics"""
    STAT_CERTIFICATES = 'certificates'
    STAT_COURSES = 'courses'
    STAT_HIDDEN_COURSES = 'hidden_courses'
    STAT_LEARNERS = 'learners'

    valid_stats = [STAT_CERTIFICATES, STAT_COURSES, STAT_HIDDEN_COURSES, STAT_LEARNERS]
    STAT_RESULT_KEYS = {
        STAT_CERTIFICATES: 'certificates_count',
        STAT_COURSES: 'courses_count',
        STAT_HIDDEN_COURSES: 'hidden_courses_count',
        STAT_LEARNERS: 'learners_count'
    }

    permission_classes = [HasTenantAccess]

    @staticmethod
    def _get_certificates_count_data(tenant_id):
        """Get the count of certificates for the given tenant"""
        collector_result = get_certificates_count([tenant_id])
        return sum(certificate_count for certificate_count in collector_result.values())

    @staticmethod
    def _get_courses_count_data(tenant_id, visible_filter):
        """Get the count of courses for the given tenant"""
        collector_result = get_courses_count([tenant_id], visible_filter=visible_filter)
        return sum(org_count['courses_count'] for org_count in collector_result)

    @staticmethod
    def _get_learners_count_data(tenant_id):
        """Get the count of learners for the given tenant"""
        collector_result = get_learners_count([tenant_id])
        return collector_result[tenant_id]['learners_count'] + \
            collector_result[tenant_id]['learners_count_no_enrollment']

    def _get_stat_count(self, stat, tenant_id):
        """Get the count of the given stat for the given tenant"""
        if stat == self.STAT_CERTIFICATES:
            return self._get_certificates_count_data(tenant_id)

        if stat == self.STAT_COURSES:
            return self._get_courses_count_data(tenant_id, visible_filter=True)

        if stat == self.STAT_HIDDEN_COURSES:
            return self._get_courses_count_data(tenant_id, visible_filter=False)

        return self._get_learners_count_data(tenant_id)

    def get(self, request, *args, **kwargs):
        """
        GET /api/fx/statistics/v1/total_counts/?stats=<countTypesList>&tenant_ids=<tenantIds>

        <countTypesList> (required): a comma-separated list of the types of count statistics to include in the
            response. Available count statistics are:
        certificates: total number of issued certificates in the selected tenants
        courses: total number of courses in the selected tenants
        learners: total number of learners in the selected tenants
        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        stats = request.query_params.get('stats', '').split(',')
        invalid_stats = list(set(stats) - set(self.valid_stats))
        if invalid_stats:
            return Response(error_details_to_dictionary(reason="Invalid stats type", invalid=invalid_stats), status=400)

        tenant_ids = get_selected_tenants(request)

        result = dict({tenant_id: {} for tenant_id in tenant_ids})
        result.update({
            f'total_{self.STAT_RESULT_KEYS[stat]}': 0 for stat in stats
        })
        for tenant_id in tenant_ids:
            for stat in stats:
                count = self._get_stat_count(stat, tenant_id)
                result[tenant_id][self.STAT_RESULT_KEYS[stat]] = count
                result[f'total_{self.STAT_RESULT_KEYS[stat]}'] += count

        return JsonResponse(result)


class LearnersView(ListAPIView):
    """View to get the list of learners"""
    serializer_class = serializers.LearnerDetailsSerializer
    permission_classes = [HasTenantAccess]
    pagination_class = DefaultPagination

    def get_queryset(self):
        """Get the list of learners"""
        tenant_ids = get_selected_tenants(self.request)
        search_text = self.request.query_params.get('search_text')
        return get_learners_queryset(
            tenant_ids=tenant_ids,
            search_text=search_text,
        )


class CoursesView(ListAPIView):
    """View to get the list of courses"""
    serializer_class = serializers.CourseDetailsSerializer
    permission_classes = [HasTenantAccess]
    pagination_class = DefaultPagination
    filter_backends = [DefaultOrderingFilter]
    ordering_fields = [
        'id', 'self_paced', 'enrolled_count', 'active_count',
        'certificates_count', 'display_name', 'org',
    ]
    ordering = ['display_name']

    def get_queryset(self):
        """Get the list of learners"""
        tenant_ids = get_selected_tenants(self.request)
        search_text = self.request.query_params.get('search_text')
        return get_courses_queryset(
            tenant_ids=tenant_ids,
            search_text=search_text,
            visible_filter=None,
        )


class CourseStatusesView(APIView):
    """View to get the course statuses"""
    permission_classes = [HasTenantAccess]

    @staticmethod
    def to_json(result):
        """Convert the result to JSON format"""
        dict_result = {
            f"{COURSE_STATUS_SELF_PREFIX if self_paced else ''}{status}": 0
            for status in COURSE_STATUSES
            for self_paced in [False, True]
        }

        for item in result:
            status = f"{COURSE_STATUS_SELF_PREFIX if item['self_paced'] else ''}{item['status']}"
            dict_result[status] = item['courses_count']
        return dict_result

    def get(self, request, *args, **kwargs):
        """
        GET /api/fx/statistics/v1/course_statuses/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        tenant_ids = get_selected_tenants(request)

        result = get_courses_count_by_status(tenant_ids=tenant_ids)

        return JsonResponse(self.to_json(result))


class LearnerInfoView(APIView):
    """View to get the information of a learner"""
    permission_classes = [HasTenantAccess]

    def get(self, request, username, *args, **kwargs):  # pylint: disable=no-self-use
        """
        GET /api/fx/learners/v1/learner/<username>/
        """
        tenant_ids = get_selected_tenants(request)
        user_id = get_user_id_from_username_tenants(username, tenant_ids)

        if not user_id:
            return Response(error_details_to_dictionary(reason=f"User not found {username}"), status=404)

        user = get_learner_info_queryset(tenant_ids, user_id).first()

        return JsonResponse(
            serializers.LearnerDetailsExtendedSerializer(user, context={'request': request}).data
        )


class LearnerCoursesView(APIView):
    """View to get the list of courses for a learner"""
    permission_classes = [HasTenantAccess]
    pagination_class = DefaultPagination

    def get(self, request, username, *args, **kwargs):  # pylint: disable=no-self-use
        """
        GET /api/fx/learners/v1/learner_courses/<username>/
        """
        tenant_ids = get_selected_tenants(request)
        user_id = get_user_id_from_username_tenants(username, tenant_ids)

        if not user_id:
            return Response(error_details_to_dictionary(reason=f"User not found {username}"), status=404)

        courses = get_learner_courses_info_queryset(tenant_ids, user_id, visible_filter=None)

        return Response(serializers.LearnerCoursesDetailsSerializer(
            courses, context={'request': request}, many=True
        ).data)


class VersionInfoView(APIView):
    """View to get the version information"""
    permission_classes = [IsSystemStaff]

    def get(self, request, *args, **kwargs):  # pylint: disable=no-self-use
        """
        GET /api/fx/version/v1/info/
        """
        import futurex_openedx_extensions  # pylint: disable=import-outside-toplevel
        return JsonResponse({
            'version': futurex_openedx_extensions.__version__,
        })


class AccessibleTenantsInfoView(APIView):
    """View to get the list of accessible tenants"""
    permission_classes = [IsAnonymousOrSystemStaff]
    throttle_classes = [AnonymousDataRetrieveRateThrottle]

    def get(self, request, *args, **kwargs):  # pylint: disable=no-self-use
        """
        GET /api/fx/tenants/v1/accessible_tenants/?username_or_email=<usernameOrEmail>
        """
        username_or_email = request.query_params.get("username_or_email")
        try:
            user = get_user_by_username_or_email(username_or_email)
        except ObjectDoesNotExist:
            user = None

        if not user:
            return JsonResponse({})

        tenant_ids = get_accessible_tenant_ids(user)
        return JsonResponse(get_tenants_info(tenant_ids))


class LearnersDetailsForCourseView(ListAPIView):
    """View to get the list of learners for a course"""
    serializer_class = serializers.LearnerDetailsForCourseSerializer
    permission_classes = [HasCourseAccess]
    pagination_class = DefaultPagination

    def get_queryset(self, *args, **kwargs):
        """Get the list of learners for a course"""
        search_text = self.request.query_params.get('search_text')
        course_id = self.kwargs.get('course_id')

        return get_learners_by_course_queryset(
            course_id=course_id,
            search_text=search_text,
        )
