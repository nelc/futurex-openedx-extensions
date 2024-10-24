"""Views for the dashboard app"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from common.djangoapps.student.models import get_user_by_username_or_email
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.paginator import EmptyPage
from django.db import transaction
from django.db.models.query import QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.exceptions import ParseError
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
from futurex_openedx_extensions.dashboard.statistics.courses import (
    get_courses_count,
    get_courses_count_by_status,
    get_courses_ratings,
    get_enrollments_count,
)
from futurex_openedx_extensions.dashboard.statistics.learners import get_learners_count
from futurex_openedx_extensions.helpers import clickhouse_operations as ch
from futurex_openedx_extensions.helpers.constants import (
    CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS,
    CLICKHOUSE_FX_BUILTIN_ORG_IN_TENANTS,
    COURSE_ACCESS_ROLES_SUPPORTED_READ,
    COURSE_STATUS_SELF_PREFIX,
    COURSE_STATUSES,
)
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_mixins import ExportCSVMixin
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from futurex_openedx_extensions.helpers.models import ClickhouseQuery, DataExportTask
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
    get_tenant_limited_fx_permission_info,
)
from futurex_openedx_extensions.helpers.roles import (
    FXViewRoleInfoMixin,
    add_course_access_roles,
    delete_course_access_roles,
    get_accessible_tenant_ids,
    get_course_access_roles_queryset,
    get_usernames_with_access_roles,
    update_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import get_tenants_info
from futurex_openedx_extensions.helpers.users import get_user_by_key


class TotalCountsView(APIView, FXViewRoleInfoMixin):
    """
    View to get the total count statistics

    TODO: there is a better way to get info per tenant without iterating over all tenants
    """
    STAT_CERTIFICATES = 'certificates'
    STAT_COURSES = 'courses'
    STAT_ENROLLMENTS = 'enrollments'
    STAT_HIDDEN_COURSES = 'hidden_courses'
    STAT_LEARNERS = 'learners'

    valid_stats = [STAT_CERTIFICATES, STAT_COURSES, STAT_ENROLLMENTS, STAT_HIDDEN_COURSES, STAT_LEARNERS]
    STAT_RESULT_KEYS = {
        STAT_CERTIFICATES: 'certificates_count',
        STAT_COURSES: 'courses_count',
        STAT_ENROLLMENTS: 'enrollments_count',
        STAT_HIDDEN_COURSES: 'hidden_courses_count',
        STAT_LEARNERS: 'learners_count',
    }

    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'total_counts_statistics'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/total_counts/: Get the total count statistics'

    @staticmethod
    def _get_certificates_count_data(one_tenant_permission_info: dict) -> int:
        """Get the count of certificates for the given tenant"""
        collector_result = get_certificates_count(one_tenant_permission_info)
        return sum(certificate_count for certificate_count in collector_result.values())

    @staticmethod
    def _get_courses_count_data(one_tenant_permission_info: dict, visible_filter: bool | None) -> int:
        """Get the count of courses for the given tenant"""
        collector_result = get_courses_count(one_tenant_permission_info, visible_filter=visible_filter)
        return sum(org_count['courses_count'] for org_count in collector_result)

    @staticmethod
    def _get_enrollments_count_data(
        one_tenant_permission_info: dict, visible_filter: bool | None, include_staff: bool,
    ) -> int:
        """Get the count of enrollments for the given tenant"""
        collector_result = get_enrollments_count(
            one_tenant_permission_info, visible_filter=visible_filter, include_staff=include_staff,
        )
        return sum(org_count['enrollments_count'] for org_count in collector_result)

    @staticmethod
    def _get_learners_count_data(one_tenant_permission_info: dict, include_staff: bool) -> int:
        """Get the count of learners for the given tenant"""
        return get_learners_count(one_tenant_permission_info, include_staff=include_staff)

    def _get_stat_count(self, stat: str, tenant_id: int, include_staff: bool) -> int:
        """Get the count of the given stat for the given tenant"""
        one_tenant_permission_info = get_tenant_limited_fx_permission_info(self.fx_permission_info, tenant_id)
        if stat == self.STAT_CERTIFICATES:
            return self._get_certificates_count_data(one_tenant_permission_info)

        if stat == self.STAT_COURSES:
            return self._get_courses_count_data(one_tenant_permission_info, visible_filter=True)

        if stat == self.STAT_ENROLLMENTS:
            return self._get_enrollments_count_data(
                one_tenant_permission_info, visible_filter=True, include_staff=include_staff,
            )

        if stat == self.STAT_HIDDEN_COURSES:
            return self._get_courses_count_data(one_tenant_permission_info, visible_filter=False)

        return self._get_learners_count_data(one_tenant_permission_info, include_staff)

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response | JsonResponse:
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
            return Response(
                error_details_to_dictionary(reason='Invalid stats type', invalid=invalid_stats),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        include_staff = request.query_params.get('include_staff', '0') == '1'

        tenant_ids = self.fx_permission_info['view_allowed_tenant_ids_any_access']

        result = dict({tenant_id: {} for tenant_id in tenant_ids})
        result.update({
            f'total_{self.STAT_RESULT_KEYS[stat]}': 0 for stat in stats
        })
        for tenant_id in tenant_ids:
            for stat in stats:
                count = self._get_stat_count(stat, tenant_id, include_staff)
                result[tenant_id][self.STAT_RESULT_KEYS[stat]] = count
                result[f'total_{self.STAT_RESULT_KEYS[stat]}'] += count

        result['limited_access'] = self.fx_permission_info['view_allowed_course_access_orgs'] != []

        return JsonResponse(result)


class LearnersView(ListAPIView, FXViewRoleInfoMixin):
    """View to get the list of learners"""
    serializer_class = serializers.LearnerDetailsSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learners_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learners/: Get the list of learners'

    def get_queryset(self) -> QuerySet:
        """Get the list of learners"""
        search_text = self.request.query_params.get('search_text')
        include_staff = self.request.query_params.get('include_staff', '0') == '1'

        return get_learners_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
            include_staff=include_staff,
        )


class CoursesView(ListAPIView, FXViewRoleInfoMixin):
    """View to get the list of courses"""
    serializer_class = serializers.CourseDetailsSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    filter_backends = [DefaultOrderingFilter]
    ordering_fields = [
        'id', 'self_paced', 'enrolled_count', 'active_count',
        'certificates_count', 'display_name', 'org', 'completion_rate',
    ]
    ordering = ['display_name']
    fx_view_name = 'courses_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/courses/v1/courses/: Get the list of courses'

    def get_queryset(self) -> QuerySet:
        """Get the list of learners"""
        search_text = self.request.query_params.get('search_text')
        include_staff = self.request.query_params.get('include_staff', '0') == '1'

        return get_courses_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
            visible_filter=None,
            include_staff=include_staff,
        )


class CourseStatusesView(APIView, FXViewRoleInfoMixin):
    """View to get the course statuses"""
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'course_statuses'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/course_statuses/: Get the course statuses'

    @staticmethod
    def to_json(result: QuerySet) -> dict[str, int]:
        """Convert the result to JSON format"""
        dict_result = {
            f'{COURSE_STATUS_SELF_PREFIX if self_paced else ""}{status}': 0
            for status in COURSE_STATUSES
            for self_paced in [False, True]
        }

        for item in result:
            status = f'{COURSE_STATUS_SELF_PREFIX if item["self_paced"] else ""}{item["status"]}'
            dict_result[status] = item['courses_count']
        return dict_result

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/statistics/v1/course_statuses/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        result = get_courses_count_by_status(fx_permission_info=self.fx_permission_info)

        return JsonResponse(self.to_json(result))


class LearnerInfoView(APIView, FXViewRoleInfoMixin):
    """View to get the information of a learner"""
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'learner_detailed_info'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learner/: Get the information of a learner'

    def get(self, request: Any, username: str, *args: Any, **kwargs: Any) -> JsonResponse | Response:
        """
        GET /api/fx/learners/v1/learner/<username>/
        """
        include_staff = request.query_params.get('include_staff', '0') == '1'

        try:
            user = get_learner_info_queryset(
                fx_permission_info=self.fx_permission_info,
                user_key=username,
                include_staff=include_staff,
            ).first()
        except FXCodedException as exc:
            return_status = http_status.HTTP_404_NOT_FOUND if exc.code in (
                FXExceptionCodes.USER_QUERY_NOT_PERMITTED.value, FXExceptionCodes.USER_NOT_FOUND.value,
            ) else http_status.HTTP_400_BAD_REQUEST

            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=return_status,
            )

        return JsonResponse(
            serializers.LearnerDetailsExtendedSerializer(user, context={'request': request}).data
        )


class DataExportManagementView(viewsets.ModelViewSet, FXViewRoleInfoMixin):  # pylint: disable=too-many-ancestors
    """View to list and retrieve data export tasks."""
    serializer_class = serializers.DataExportTaskSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'exported_files_data'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_default_read_write_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_allowed_write_methods = ['PATCH']
    fx_view_description = 'api/fx/export/v1/tasks/: Data Export Task Mangement APIs.'
    http_method_names = ['get', 'patch']
    ordering = ['-created_at']

    def get_queryset(self) -> QuerySet:
        """Get the list of user tasks."""
        return DataExportTask.objects.filter(
            user=self.request.user,
            tenant_id__in=self.fx_permission_info['view_allowed_tenant_ids_any_access']
        )

    def get_object(self) -> DataExportTask:
        """Override to ensure that the user can only retrieve their own tasks."""
        task_id = self.kwargs.get('pk')  # Use 'pk' for the default lookup
        task = get_object_or_404(DataExportTask, id=task_id, user=self.request.user)
        return task

    def retrieve(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Retrieve a specific task."""
        instance = self.get_object()
        serializer = serializers.DataExportTaskDetailSerializer(instance)
        return Response(serializer.data)


class LearnerCoursesView(APIView, FXViewRoleInfoMixin):
    """View to get the list of courses for a learner"""
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learner_courses'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learner_courses/: Get the list of courses for a learner'

    def get(self, request: Any, username: str, *args: Any, **kwargs: Any) -> JsonResponse | Response:
        """
        GET /api/fx/learners/v1/learner_courses/<username>/
        """
        include_staff = request.query_params.get('include_staff', '0') == '1'

        try:
            courses = get_learner_courses_info_queryset(
                fx_permission_info=self.fx_permission_info,
                user_key=username,
                visible_filter=None,
                include_staff=include_staff,
            )
        except FXCodedException as exc:
            return_status = http_status.HTTP_404_NOT_FOUND if exc.code in (
                FXExceptionCodes.USER_QUERY_NOT_PERMITTED.value, FXExceptionCodes.USER_NOT_FOUND.value,
            ) else http_status.HTTP_400_BAD_REQUEST

            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=return_status,
            )

        return Response(serializers.LearnerCoursesDetailsSerializer(
            courses, context={'request': request}, many=True
        ).data)


class VersionInfoView(APIView):
    """View to get the version information"""
    permission_classes = [IsSystemStaff]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
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

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """
        GET /api/fx/tenants/v1/accessible_tenants/?username_or_email=<usernameOrEmail>
        """
        username_or_email = request.query_params.get('username_or_email')
        try:
            user = get_user_by_username_or_email(username_or_email)
        except ObjectDoesNotExist:
            user = None

        if not user:
            return JsonResponse({})

        tenant_ids = get_accessible_tenant_ids(user)
        return JsonResponse(get_tenants_info(tenant_ids))


class LearnersDetailsForCourseView(ExportCSVMixin, ListAPIView, FXViewRoleInfoMixin):
    """View to get the list of learners for a course"""
    serializer_class = serializers.LearnerDetailsForCourseSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learners_with_details_for_course'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learners/<course-id>: Get the list of learners for a course'

    def get_queryset(self, *args: Any, **kwargs: Any) -> QuerySet:
        """Get the list of learners for a course"""
        search_text = self.request.query_params.get('search_text')
        course_id = self.kwargs.get('course_id')
        include_staff = self.request.query_params.get('include_staff', '0') == '1'

        return get_learners_by_course_queryset(
            course_id=course_id,   # type: ignore
            search_text=search_text,
            include_staff=include_staff,
        )


class GlobalRatingView(APIView, FXViewRoleInfoMixin):
    """View to get the global rating"""
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'global_rating'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/rating/: Get the global rating for courses'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/statistics/v1/rating/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        data_result = get_courses_ratings(fx_permission_info=self.fx_permission_info)
        result = {
            'total_rating': data_result['total_rating'],
            'total_count': sum(data_result[f'rating_{index}_count'] for index in range(1, 6)),
            'courses_count': data_result['courses_count'],
            'rating_counts': {
                str(index): data_result[f'rating_{index}_count'] for index in range(1, 6)
            },
        }

        return JsonResponse(result)


class UserRolesManagementView(viewsets.ModelViewSet, FXViewRoleInfoMixin):  # pylint: disable=too-many-ancestors
    """View to get the user roles"""
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'user_roles'
    fx_default_read_only_roles = ['org_course_creator_group']
    fx_default_read_write_roles = ['org_course_creator_group']
    fx_allowed_write_methods = ['POST', 'PUT', 'DELETE']
    fx_view_description = 'api/fx/roles/v1/user_roles/: user roles management APIs'

    lookup_field = 'username'
    serializer_class = serializers.UserRolesSerializer
    pagination_class = DefaultPagination

    @transaction.non_atomic_requests
    def dispatch(self, *args: Any, **kwargs: Any) -> Response:
        return super().dispatch(*args, **kwargs)

    def get_queryset(self) -> QuerySet:
        """Get the list of users"""
        dummy_serializers = serializers.UserRolesSerializer(context={'request': self.request})

        try:
            q_set = get_user_model().objects.filter(
                id__in=get_course_access_roles_queryset(
                    orgs_filter=dummy_serializers.orgs_filter,
                    remove_redundant=True,
                    users=None,
                    search_text=dummy_serializers.query_params['search_text'],
                    roles_filter=dummy_serializers.query_params['roles_filter'],
                    active_filter=dummy_serializers.query_params['active_filter'],
                    course_ids_filter=dummy_serializers.query_params['course_ids_filter'],
                    exclude_role_type=dummy_serializers.query_params['exclude_role_type'],
                ).values('user_id').distinct().order_by()
            ).select_related('profile').order_by('id')
        except ValueError as exc:
            raise ParseError(f'Invalid parameter: {exc}') from exc

        return q_set

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response | JsonResponse:
        """Create a new user role"""
        data = request.data
        try:
            if (
                not isinstance(data['tenant_ids'], list) or
                not all(isinstance(t_id, int) for t_id in data['tenant_ids'])
            ):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='tenant_ids must be a list of integers',
                )

            if not isinstance(data['users'], list):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='users must be a list',
                )

            if not isinstance(data['role'], str):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='role must be a string',
                )

            if not isinstance(data['tenant_wide'], int):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='tenant_wide must be an integer flag',
                )

            if not isinstance(data.get('course_ids', []), list):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='course_ids must be a list',
                )

            result = add_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=data['tenant_ids'],
                user_keys=data['users'],
                role=data['role'],
                tenant_wide=data['tenant_wide'] != 0,
                course_ids=data.get('course_ids', []),
            )
        except KeyError as exc:
            return Response(
                error_details_to_dictionary(reason=f'Missing required parameter: {exc}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return JsonResponse(
            result,
            status=http_status.HTTP_201_CREATED,
        )

    @staticmethod
    def verify_username(username: str) -> Response | Dict[str, Any]:
        """Verify the username"""
        user_info = get_user_by_key(username)
        if not user_info['user']:
            return Response(
                error_details_to_dictionary(reason=f'({user_info["error_code"]}) {user_info["error_message"]}'),
                status=http_status.HTTP_404_NOT_FOUND
            )
        return user_info

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Update a user role"""
        user_info = self.verify_username(kwargs['username'])
        if isinstance(user_info, Response):
            return user_info

        result = update_course_access_roles(
            caller=self.fx_permission_info['user'],
            user=user_info['user'],
            new_roles_details=request.data or {},
            dry_run=False,
        )

        if result['error_code']:
            return Response(
                error_details_to_dictionary(reason=f'({result["error_code"]}) {result["error_message"]}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return Response(
            self.serializer_class(user_info['user'], context={'request': request}).data,
            status=http_status.HTTP_200_OK,
        )

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Delete a user role"""
        if not request.query_params.get('tenant_ids'):
            return Response(
                error_details_to_dictionary(reason="Missing required parameter: 'tenant_ids'"),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        user_info = self.verify_username(kwargs['username'])
        if isinstance(user_info, Response):
            return user_info

        try:
            delete_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=self.fx_permission_info['view_allowed_tenant_ids_any_access'],
                user=user_info['user'],
            )
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=http_status.HTTP_404_NOT_FOUND
            )

        return Response(status=http_status.HTTP_204_NO_CONTENT)


class MyRolesView(APIView, FXViewRoleInfoMixin):
    """View to get the user roles of the caller"""
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'my_roles'
    fx_default_read_only_roles = COURSE_ACCESS_ROLES_SUPPORTED_READ.copy()
    fx_view_description = 'api/fx/roles/v1/my_roles/: user roles management APIs'

    serializer_class = serializers.UserRolesSerializer

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """Get the list of users"""
        data = serializers.UserRolesSerializer(self.fx_permission_info['user'], context={'request': request}).data
        data['is_system_staff'] = self.fx_permission_info['is_system_staff_user']
        return JsonResponse(data)


class ClickhouseQueryView(APIView, FXViewRoleInfoMixin):
    """View to get the Clickhouse query"""
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'clickhouse_query_fetcher'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/query/v1/<scope>/<slug>: Get result of the related clickhouse query'

    @staticmethod
    def get_page_url_with_page(url: str, new_page_no: int | None) -> str | None:
        """
        Get the URL with the new page number

        :param url: The URL
        :type url: str
        :param new_page_no: The new page number
        :type new_page_no: int | None
        :return: The URL with the new page number
        :rtype: str | None
        """
        if new_page_no is None:
            return None

        url_parts = urlsplit(url)
        query_params = parse_qs(url_parts.query)

        page_size = query_params.get(DefaultPagination.page_size_query_param, None)
        if page_size:
            del query_params[DefaultPagination.page_size_query_param]

        if 'page' in query_params:
            del query_params['page']

        if page_size:
            query_params[DefaultPagination.page_size_query_param] = page_size
        query_params['page'] = [str(new_page_no)]

        new_query_string = urlencode(query_params, doseq=True)

        new_url_parts = (url_parts.scheme, url_parts.netloc, url_parts.path, new_query_string, url_parts.fragment)
        new_full_url = urlunsplit(new_url_parts)
        return new_full_url

    @staticmethod
    def pop_out_page_params(params: Dict[str, str], paginated: bool) -> tuple[int | None, int]:
        """
        Pop out the page and page size parameters, and return them as integers in the result. Always return the page
        as None if not paginated

        :param params: The parameters
        :type params: Dict[str, str]
        :param paginated: Whether the query is paginated
        :type paginated: bool
        :return: The page and page size parameters
        :rtype: tuple[int | None, int]
        """
        page_str: str | None = params.pop('page', None)
        page_size_str: str = params.pop(
            DefaultPagination.page_size_query_param, ''
        ) or str(DefaultPagination.page_size)

        if not paginated:
            page = None
        else:
            page = int(page_str) if page_str is not None else page_str
            page = 1 if page is None else page

        return page, int(page_size_str)

    def get(self, request: Any, scope: str, slug: str) -> JsonResponse | Response:
        """
        GET /api/fx/query/v1/<scope>/<slug>/

        :param request: The request object
        :type request: Request
        :param scope: The scope of the query (course, tenant, user)
        :type scope: str
        :param slug: The slug of the query
        :type slug: str
        """
        clickhouse_query = ClickhouseQuery.get_query_record(scope, 'v1', slug)
        if not clickhouse_query:
            return Response(
                error_details_to_dictionary(reason=f'Query not found {scope}.v1.{slug}'),
                status=http_status.HTTP_404_NOT_FOUND
            )

        if not clickhouse_query.enabled:
            return Response(
                error_details_to_dictionary(reason=f'Query is disabled {scope}.v1.{slug}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        params = request.query_params.dict()
        self.get_page_url_with_page(request.build_absolute_uri(), 9)

        page, page_size = self.pop_out_page_params(params, clickhouse_query.paginated)

        orgs = request.fx_permission_info['view_allowed_any_access_orgs'].copy()
        params[CLICKHOUSE_FX_BUILTIN_ORG_IN_TENANTS] = orgs
        if CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS in clickhouse_query.query:
            params[CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS] = get_usernames_with_access_roles(orgs)

        error_response = None
        try:
            clickhouse_query.fix_param_types(params)

            with ch.get_client() as clickhouse_client:
                records_count, next_page, result = ch.execute_query(
                    clickhouse_client,
                    query=clickhouse_query.query,
                    parameters=params,
                    page=page,
                    page_size=page_size,
                )

        except EmptyPage as exc:
            error_response = Response(
                error_details_to_dictionary(reason=str(exc)), status=http_status.HTTP_404_NOT_FOUND
            )
        except (ch.ClickhouseClientNotConfiguredError, ch.ClickhouseClientConnectionError) as exc:
            error_response = Response(
                error_details_to_dictionary(reason=str(exc)), status=http_status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except (ch.ClickhouseBaseError, ValueError) as exc:
            error_response = Response(
                error_details_to_dictionary(reason=str(exc)), status=http_status.HTTP_400_BAD_REQUEST
            )
        except ValidationError as exc:
            error_response = Response(
                error_details_to_dictionary(reason=exc.message), status=http_status.HTTP_400_BAD_REQUEST
            )

        if error_response:
            return error_response

        if clickhouse_query.paginated:
            return JsonResponse({
                'count': records_count,
                'next': self.get_page_url_with_page(request.build_absolute_uri(), next_page),
                'previous': self.get_page_url_with_page(
                    request.build_absolute_uri(),
                    None if page == 1 else page - 1 if page else None,
                ),
                'results': ch.result_to_json(result),
            })

        return JsonResponse(ch.result_to_json(result), safe=False)
