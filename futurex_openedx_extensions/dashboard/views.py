"""Views for the dashboard app"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from common.djangoapps.student.models import get_user_by_username_or_email
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.paginator import EmptyPage
from django.db.models.query import QuerySet
from django.http import JsonResponse
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
)
from futurex_openedx_extensions.dashboard.statistics.learners import get_learners_count
from futurex_openedx_extensions.helpers import clickhouse_operations as ch
from futurex_openedx_extensions.helpers.constants import (
    CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS,
    CLICKHOUSE_FX_BUILTIN_ORG_IN_TENANTS,
    COURSE_STATUS_SELF_PREFIX,
    COURSE_STATUSES,
)
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from futurex_openedx_extensions.helpers.models import ClickhouseQuery
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
    get_course_access_roles_queryset,
    get_usernames_with_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import (
    get_accessible_tenant_ids,
    get_tenants_info,
    get_user_id_from_username_tenants,
)


class TotalCountsView(APIView, FXViewRoleInfoMixin):
    """
    View to get the total count statistics

    TODO: there is a better way to get info per tenant without iterating over all tenants
    """
    STAT_CERTIFICATES = 'certificates'
    STAT_COURSES = 'courses'
    STAT_HIDDEN_COURSES = 'hidden_courses'
    STAT_LEARNERS = 'learners'

    valid_stats = [STAT_CERTIFICATES, STAT_COURSES, STAT_HIDDEN_COURSES, STAT_LEARNERS]
    STAT_RESULT_KEYS = {
        STAT_CERTIFICATES: 'certificates_count',
        STAT_COURSES: 'courses_count',
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
    def _get_learners_count_data(one_tenant_permission_info: dict, tenant_id: int) -> int:
        """Get the count of learners for the given tenant"""
        collector_result = get_learners_count(one_tenant_permission_info)
        return collector_result[tenant_id]['learners_count'] + \
            collector_result[tenant_id]['learners_count_no_enrollment']

    def _get_stat_count(self, stat: str, tenant_id: int) -> int:
        """Get the count of the given stat for the given tenant"""
        one_tenant_permission_info = get_tenant_limited_fx_permission_info(self.fx_permission_info, tenant_id)
        if stat == self.STAT_CERTIFICATES:
            return self._get_certificates_count_data(one_tenant_permission_info)

        if stat == self.STAT_COURSES:
            return self._get_courses_count_data(one_tenant_permission_info, visible_filter=True)

        if stat == self.STAT_HIDDEN_COURSES:
            return self._get_courses_count_data(one_tenant_permission_info, visible_filter=False)

        return self._get_learners_count_data(one_tenant_permission_info, tenant_id)

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
            return Response(error_details_to_dictionary(reason='Invalid stats type', invalid=invalid_stats), status=400)

        tenant_ids = self.fx_permission_info['permitted_tenant_ids']

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
        return get_learners_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
        )


class CoursesView(ListAPIView, FXViewRoleInfoMixin):
    """View to get the list of courses"""
    serializer_class = serializers.CourseDetailsSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    filter_backends = [DefaultOrderingFilter]
    ordering_fields = [
        'id', 'self_paced', 'enrolled_count', 'active_count',
        'certificates_count', 'display_name', 'org',
    ]
    ordering = ['display_name']
    fx_view_name = 'courses_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/courses/v1/courses/: Get the list of courses'

    def get_queryset(self) -> QuerySet:
        """Get the list of learners"""
        search_text = self.request.query_params.get('search_text')
        return get_courses_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
            visible_filter=None,
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
        tenant_ids = self.fx_permission_info['permitted_tenant_ids']
        user_id = get_user_id_from_username_tenants(username, tenant_ids)

        if not user_id:
            return Response(error_details_to_dictionary(reason=f'User not found {username}'), status=404)

        user = get_learner_info_queryset(self.fx_permission_info, user_id).first()

        return JsonResponse(
            serializers.LearnerDetailsExtendedSerializer(user, context={'request': request}).data
        )


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
        tenant_ids = self.fx_permission_info['permitted_tenant_ids']
        user_id = get_user_id_from_username_tenants(username, tenant_ids)

        if not user_id:
            return Response(error_details_to_dictionary(reason=f'User not found {username}'), status=404)

        courses = get_learner_courses_info_queryset(
            fx_permission_info=self.fx_permission_info,
            user_id=user_id,
            visible_filter=None,
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


class LearnersDetailsForCourseView(ListAPIView, FXViewRoleInfoMixin):
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

        return get_learners_by_course_queryset(
            course_id=course_id,
            search_text=search_text,
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
                    user_id_distinct=True,
                )
            ).select_related('profile').order_by('id')
        except ValueError as exc:
            raise ParseError(f'Invalid parameter: {exc}') from exc

        return q_set

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Create a new user role"""
        return Response(error_details_to_dictionary(reason='Not implemented yet'), status=501)

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Update a user role"""
        return Response(error_details_to_dictionary(reason='Not implemented yet'), status=501)

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Delete a user role"""
        return Response(error_details_to_dictionary(reason='Not implemented yet'), status=501)


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
            return Response(error_details_to_dictionary(reason=f'Query not found {scope}.v1.{slug}'), status=404)

        if not clickhouse_query.enabled:
            return Response(error_details_to_dictionary(reason=f'Query is disabled {scope}.v1.{slug}'), status=400)

        params = request.query_params.dict()
        self.get_page_url_with_page(request.build_absolute_uri(), 9)

        page, page_size = self.pop_out_page_params(params, clickhouse_query.paginated)

        orgs = request.fx_permission_info['view_allowed_full_access_orgs'].copy()
        orgs.extend(request.fx_permission_info['view_allowed_course_access_orgs'])
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
            error_response = Response(error_details_to_dictionary(reason=str(exc)), status=404)
        except (ch.ClickhouseClientNotConfiguredError, ch.ClickhouseClientConnectionError) as exc:
            error_response = Response(error_details_to_dictionary(reason=str(exc)), status=503)
        except (ch.ClickhouseBaseError, ValueError) as exc:
            error_response = Response(error_details_to_dictionary(reason=str(exc)), status=400)
        except ValidationError as exc:
            error_response = Response(error_details_to_dictionary(reason=exc.message), status=400)

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
