"""Learners details collectors"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from common.djangoapps.student.models import CourseEnrollment
from completion_aggregator.models import Aggregator
from django.contrib.auth import get_user_model
from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    DateTimeField,
    Exists,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.grades.models import PersistentCourseGrade

from futurex_openedx_extensions.dashboard.toggles import is_learner_certificates_enabled
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import CourseStat
from futurex_openedx_extensions.helpers.querysets import (
    check_staff_exist_queryset,
    get_accessible_users_and_courses,
    get_base_queryset_courses,
    get_learners_search_queryset,
    get_one_user_queryset,
    get_permitted_learners_queryset,
    update_removable_annotations,
)


def get_courses_count_for_learner_queryset(
    fx_permission_info: dict,
    visible_courses_filter: bool | None = True,
    active_courses_filter: bool | None = None,
    include_staff: bool = False,
) -> Coalesce:
    """
    Annotate the given queryset with the courses count for the learner.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool | None
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool | None
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: Count of enrolled courses
    :rtype: Coalesce
    """
    if not include_staff:
        is_staff_queryset = check_staff_exist_queryset(
            ref_user_id='user_id', ref_org='course__org', ref_course_id='course_id',
        )
    else:
        is_staff_queryset = Q(Value(False, output_field=BooleanField()))

    return Coalesce(Subquery(
        CourseEnrollment.objects.filter(
            user_id=OuterRef('id'),
            course_id__in=get_base_queryset_courses(
                fx_permission_info,
                visible_filter=visible_courses_filter,
                active_filter=active_courses_filter,
            ),
            is_active=True,
        ).filter(
            ~is_staff_queryset,
        ).values('user_id').annotate(count=Count('id')).values('count'),
        output_field=IntegerField(),
    ), 0)


def get_certificates_count_for_learner_queryset(
    fx_permission_info: dict,
    visible_courses_filter: bool | None = True,
    active_courses_filter: bool | None = None,
) -> Coalesce:
    """
    Annotate the given queryset with the certificate counts.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool | None
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool | None
    :return: Count of certificates
    :rtype: Coalesce
    """
    if not is_learner_certificates_enabled():
        return Value(0, output_field=IntegerField())

    return Coalesce(Subquery(
        GeneratedCertificate.objects.filter(
            user_id=OuterRef('id'),
            user__is_active=True,
            course_id__in=Subquery(
                get_base_queryset_courses(
                    fx_permission_info,
                    visible_filter=visible_courses_filter,
                    active_filter=active_courses_filter
                ).values_list('id', flat=True)
            ),
            status='downloadable',
        ).values('user_id').annotate(count=Count('id')).values('count'),
        output_field=IntegerField(),
    ), 0)


def get_learners_queryset(  # pylint: disable=too-many-arguments
    fx_permission_info: dict,
    search_text: str | None = None,
    visible_courses_filter: bool | None = True,
    active_courses_filter: bool | None = None,
    enrollments_filter: tuple[int, int] = (-1, -1),
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the learners queryset for the given tenant IDs and search text.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param search_text: Search text to filter the learners by
    :type search_text: str | None
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter
    :type active_courses_filter: bool
    :param enrollments_filter: Tuple containing the minimum and maximum number of enrollments
    :type enrollments_filter: tuple[int]
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    if not isinstance(enrollments_filter, (tuple, list)):
        raise FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message='Enrollments filter must be a tuple or a list.',
        )

    if len(enrollments_filter) != 2 or not all(isinstance(x, int) for x in enrollments_filter):
        raise FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message='Enrollments filter must be a tuple or a list of two integer values.',
        )

    queryset = get_learners_search_queryset(search_text)

    queryset = get_permitted_learners_queryset(
        queryset=queryset,
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )

    queryset = queryset.annotate(
        courses_count=get_courses_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
            include_staff=include_staff,
        )
    ).annotate(
        certificates_count=get_certificates_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    )

    if enrollments_filter[0] >= 0:
        queryset = queryset.filter(courses_count__gte=enrollments_filter[0])

    if enrollments_filter[1] >= 0:
        queryset = queryset.filter(courses_count__lte=enrollments_filter[1])

    queryset = queryset.select_related('profile', 'extrainfo').order_by('id')

    if enrollments_filter[0] < 0 and enrollments_filter[1] < 0:
        update_removable_annotations(queryset, removable=['courses_count'])

    update_removable_annotations(queryset, removable=['certificates_count'])

    return queryset


def get_learners_by_course_queryset(
    course_id: str, search_text: str | None = None, include_staff: bool = False,
) -> QuerySet:
    """
    Get the learners queryset for the given course ID.

    :param course_id: The course ID to get the learners for
    :type course_id: str
    :param search_text: Search text to filter the learners by
    :type search_text: str | None
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    queryset = get_learners_search_queryset(search_text)
    queryset = queryset.filter(
        courseenrollment__course_id=course_id,
        courseenrollment__is_active=True,
    )

    if not include_staff:
        queryset = queryset.filter(
            ~check_staff_exist_queryset('id', 'courseenrollment__course__org', Value(course_id)),
        )

    if is_learner_certificates_enabled():
        certificate_available_expr = Exists(
            GeneratedCertificate.objects.filter(
                user_id=OuterRef('id'),
                user__is_active=True,
                course_id=course_id,
                status='downloadable'
            )
        )
    else:
        certificate_available_expr = Value(False, output_field=BooleanField())

    queryset = queryset.annotate(
        certificate_available=certificate_available_expr,
    ).annotate(
        course_score=Subquery(
            PersistentCourseGrade.objects.filter(
                user_id=OuterRef('id'),
                course_id=course_id
            ).values('percent_grade')[:1]
        )
    ).annotate(
        active_in_course=Case(
            When(
                Exists(
                    StudentModule.objects.filter(
                        student_id=OuterRef('id'),
                        course_id=course_id,
                        modified__gte=timezone.now() - timedelta(days=30)
                    )
                ),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        )
    ).select_related('profile').order_by('id')

    update_removable_annotations(queryset, removable=['certificate_available', 'course_score', 'active_in_course'])

    return queryset


def get_learner_info_queryset(
    fx_permission_info: dict,
    user_key: get_user_model | int | str,
    visible_courses_filter: bool | None = True,
    active_courses_filter: bool | None = None,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the learner queryset for the given user ID. This method assumes a valid user ID.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param user_key: The user key to get the learner for
    :type user_key: get_user_model | int | str
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_courses_filter: bool | None
    :param active_courses_filter: Value to filter courses on active status. None means no filter
    :type active_courses_filter: bool | None
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    queryset = get_one_user_queryset(
        fx_permission_info=fx_permission_info,
        user_key=user_key,
        include_staff=include_staff
    )

    queryset = queryset.annotate(
        courses_count=get_courses_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
            include_staff=include_staff,
        )
    ).annotate(
        certificates_count=get_certificates_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).select_related('profile')

    update_removable_annotations(queryset, removable=['courses_count', 'certificates_count'])

    return queryset


def get_learners_enrollments_queryset(  # pylint: disable=too-many-arguments
    fx_permission_info: dict,
    user_ids: list = None,
    course_ids: list = None,
    usernames: list = None,
    learner_search: str | None = None,
    course_search: str | None = None,
    include_staff: bool = False,
    progress_filter: tuple[float, float] = (-1, -1),
    visible_filter: bool | None = None,
) -> QuerySet:
    """
    Get the enrollment details. If no course_ids or user_ids are provided,
    all relevant data will be processed.

    :param fx_permission_info: Dictionary containing permission information.
    :param course_ids: List of course IDs to filter by (optional).
    :param user_ids: List of user IDs to filter by (optional).
    :param usernames: List of usernames to filter by (optional).
    :param learner_search: Text to search enrollments by user (username, email or national_id) (optional).
    :param course_search: Text to search enrollments by course (display name, id) (optional).
    :param include_staff: Flag to include staff users (default: False).
    :param progress_filter: Tuple containing min and max progress percentage to filter by. -1 means no filter.
    :param visible_filter: Value to filter courses on catalog visibility. None (the default) means no
        filter. Pass True to cover the same courses the `total_counts` enrollments stat counts.
    :return: List of dictionaries containing user and course details.
    """
    accessible_users, accessible_courses = get_accessible_users_and_courses(
        fx_permission_info=fx_permission_info,
        user_ids=user_ids,
        course_ids=course_ids,
        usernames=usernames,
        learner_search=learner_search,
        course_search=course_search,
        include_staff=include_staff,
        visible_filter=visible_filter,
    )

    if is_learner_certificates_enabled():
        certificate_available_expr = Exists(
            GeneratedCertificate.objects.filter(
                user_id=OuterRef('user_id'),
                user__is_active=True,
                course_id=OuterRef('course_id'),
                status='downloadable'
            )
        )
    else:
        certificate_available_expr = Value(False, output_field=BooleanField())

    queryset = CourseEnrollment.objects.filter(
        is_active=True,
        course__in=Subquery(accessible_courses.values('id')),
        user__in=Subquery(accessible_users.values('id'))
    ).annotate(
        certificate_available=certificate_available_expr,
    ).annotate(
        course_score=Subquery(
            PersistentCourseGrade.objects.filter(
                user_id=OuterRef('user_id'),
                course_id=OuterRef('course_id')
            ).values('percent_grade')[:1]
        )
    ).annotate(
        active_in_course=Case(
            When(
                Exists(
                    StudentModule.objects.filter(
                        student_id=OuterRef('user_id'),
                        course_id=OuterRef('course_id'),
                        modified__gte=timezone.now() - timedelta(days=30)
                    )
                ),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        )
    ).select_related('user', 'user__profile')

    progress_filter_qs = Q()
    if progress_filter[0] > 0:
        progress_filter_qs = Q(
            progress__gte=progress_filter[0],
        )
    if progress_filter[1] > 0:
        progress_filter_qs &= Q(
            Q(progress__lte=progress_filter[1]) | Q(progress__isnull=True),
        )

    if progress_filter_qs != Q():
        queryset = queryset.annotate(
            progress=Subquery(
                Aggregator.objects.filter(
                    user=OuterRef('user'),
                    course_key=OuterRef('course_id'),
                ).order_by().values('percent')[:1],
                output_field=FloatField()
            )
        ).filter(
            progress_filter_qs
        )
    else:
        queryset = queryset.annotate(
            progress=Value(-1, output_field=FloatField())
        )

    update_removable_annotations(queryset, removable=[
        'certificate_available', 'course_score', 'active_in_course', 'progress',
    ])

    return queryset


PROGRESS_RANGE_FILTERS = ('progress', 'course_score')


def parse_progress_filters(query_params: Any) -> dict:
    """
    Read the optional value filters of the bulk progress feed from the query parameters.

    `<field>_min` / `<field>_max` for `progress` and `course_score` take a number from 0 to 1 (inclusive), `grade` takes
    one or more letter grades separated by commas (exact match), and `passed` takes 1 or 0. Raises INVALID_INPUT on a
    bad value, and returns only the filters that were given.

    :param query_params: The request query parameters
    :return: {'progress_min': float, ..., 'grade': [str, ...], 'passed': bool}
    """
    filters: dict = {}
    for field in PROGRESS_RANGE_FILTERS:
        for bound in ('min', 'max'):
            name = f'{field}_{bound}'
            raw = query_params.get(name)
            if raw in (None, ''):
                continue
            try:
                value = float(raw)
            except ValueError as exc:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT, message=f'{name} must be a number from 0 to 1',
                ) from exc
            if not 0 <= value <= 1:
                raise FXCodedException(code=FXExceptionCodes.INVALID_INPUT, message=f'{name} must be from 0 to 1')
            filters[name] = value
        low, high = filters.get(f'{field}_min'), filters.get(f'{field}_max')
        if low is not None and high is not None and low > high:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT, message=f'{field}_min cannot be greater than {field}_max',
            )

    grades = [grade.strip() for grade in (query_params.get('grade') or '').split(',') if grade.strip()]
    if grades:
        filters['grade'] = grades

    passed = query_params.get('passed')
    if passed not in (None, ''):
        if passed not in ('0', '1'):
            raise FXCodedException(code=FXExceptionCodes.INVALID_INPUT, message='passed must be 1 or 0')
        filters['passed'] = passed == '1'

    return filters


def _apply_progress_filters(queryset: QuerySet, filters: dict) -> QuerySet:
    """Filter the annotated feed rows by the value filters from parse_progress_filters"""
    lookups: dict = {}
    for field in PROGRESS_RANGE_FILTERS:
        if f'{field}_min' in filters:
            lookups[f'{field}__gte'] = filters[f'{field}_min']
        if f'{field}_max' in filters:
            lookups[f'{field}__lte'] = filters[f'{field}_max']
    if 'grade' in filters:
        lookups['letter_grade__in'] = filters['grade']
    if 'passed' in filters:
        lookups['passed_timestamp__isnull'] = not filters['passed']
    return queryset.filter(**lookups)


def _get_learners_progress_base(
    fx_permission_info: dict,
    include_staff: bool = False,
    modified_since: datetime | None = None,
) -> tuple[QuerySet, QuerySet, QuerySet, QuerySet]:
    """
    Build the filtered enrollments of the bulk progress feed, without the per-row columns, together with the three
    correlated querysets the columns are read from.

    :return: (enrollments, course completion, course grade, certificate) querysets
    """
    accessible_users, accessible_courses = get_accessible_users_and_courses(
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )

    course_completion = Aggregator.objects.filter(
        user_id=OuterRef('user_id'),
        aggregation_name='course',
        course_key=OuterRef('course_id'),
    )
    course_grade = PersistentCourseGrade.objects.filter(
        user_id=OuterRef('user_id'),
        course_id=OuterRef('course_id'),
    )
    certificate = GeneratedCertificate.objects.filter(
        user_id=OuterRef('user_id'),
        course_id=OuterRef('course_id'),
    )

    queryset = CourseEnrollment.objects.filter(
        is_active=True,
        course__in=Subquery(accessible_courses.values('id')),
        user__in=Subquery(accessible_users.values('id')),
    ).filter(
        Exists(course_completion.filter(percent__gt=0)),
    )

    if modified_since:
        queryset = queryset.filter(
            Exists(course_completion.filter(modified__gte=modified_since)) |
            Exists(course_grade.filter(modified__gte=modified_since)) |
            Exists(certificate.filter(modified_date__gte=modified_since)),
        )

    return queryset, course_completion, course_grade, certificate


def get_learners_progress_count(
    fx_permission_info: dict,
    include_staff: bool = False,
    modified_since: datetime | None = None,
    filters: dict | None = None,
) -> int | None:
    """
    The total rows of the bulk progress feed, read from the per-course counts that sync_course_stats keeps in
    CourseStat, summed over the caller's courses. Counting the rows live scans the caller's whole scope and takes
    minutes for a platform-wide caller; this sum takes milliseconds. It is as fresh as the last sync, so it can
    differ slightly from the rows walked. A total of changed or filtered rows cannot be kept in advance, so with
    `modified_since` or any value filter the result is None.

    :param fx_permission_info: Dictionary containing permission information
    :param include_staff: Flag to include staff users
    :param modified_since: When given, there is no total (None)
    :param filters: Value filters from parse_progress_filters; when any is given, there is no total (None)
    :return: number of rows, or None
    """
    if modified_since or filters:
        return None
    _, accessible_courses = get_accessible_users_and_courses(
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )
    return CourseStat.objects.filter(
        course_key__in=Subquery(accessible_courses.values('id')),
    ).aggregate(total=Sum('progress_count'))['total'] or 0


def get_learners_progress_queryset(
    fx_permission_info: dict,
    include_staff: bool = False,
    modified_since: datetime | None = None,
    filters: dict | None = None,
) -> QuerySet:
    """
    Get the progress of every active enrollment of the caller's learners and courses, for bulk sync. Only
    enrollments with course completion above zero are included. Every value is read from a stored column in the
    same SQL query (no per-row query and no live grade computation), and the result is a values() queryset ordered
    later by the paginator on the enrollment id.

    :param fx_permission_info: Dictionary containing permission information
    :param include_staff: Flag to include staff users
    :param modified_since: Only enrollments whose completion, grade or certificate changed at or after this time
    :param filters: Value filters from parse_progress_filters (progress, course_score, grade, passed)
    :return: values() QuerySet of CourseEnrollment rows
    """
    queryset, course_completion, course_grade, certificate = _get_learners_progress_base(
        fx_permission_info, include_staff, modified_since,
    )

    if is_learner_certificates_enabled():
        certificate_date_expr = Subquery(
            certificate.filter(status='downloadable', user__is_active=True).values('created_date')[:1],
            output_field=DateTimeField(),
        )
    else:
        certificate_date_expr = Value(None, output_field=DateTimeField())

    queryset = queryset.annotate(
        progress=Subquery(course_completion.values('percent')[:1], output_field=FloatField()),
        course_score=Subquery(course_grade.values('percent_grade')[:1], output_field=FloatField()),
        letter_grade=Subquery(course_grade.values('letter_grade')[:1], output_field=CharField()),
        passed_timestamp=Subquery(course_grade.values('passed_timestamp')[:1], output_field=DateTimeField()),
        certificate_date=certificate_date_expr,
    )
    if filters:
        queryset = _apply_progress_filters(queryset, filters)

    return queryset.values(
        'id',
        'user_id',
        'course_id',
        'user__email',
        'user__date_joined',
        'user__last_login',
        'user__extrainfo__national_id',
        'progress',
        'course_score',
        'letter_grade',
        'passed_timestamp',
        'certificate_date',
    )
