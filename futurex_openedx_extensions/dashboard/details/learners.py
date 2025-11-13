"""Learners details collectors"""
from __future__ import annotations

from datetime import timedelta

from common.djangoapps.student.models import CourseEnrollment
from completion_aggregator.models import Aggregator
from django.contrib.auth import get_user_model
from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.grades.models import PersistentCourseGrade

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.querysets import (
    check_staff_exist_queryset,
    get_base_queryset_courses,
    get_course_search_queryset,
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

    queryset = queryset.annotate(
        certificate_available=Exists(
            GeneratedCertificate.objects.filter(
                user_id=OuterRef('id'),
                user__is_active=True,
                course_id=course_id,
                status='downloadable'
            )
        )
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
    :return: List of dictionaries containing user and course details.
    """
    accessible_users = get_permitted_learners_queryset(
        queryset=get_learners_search_queryset(
            search_text=learner_search,
            user_ids=user_ids,
            usernames=usernames,
        ),
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )

    accessible_courses = get_course_search_queryset(
        fx_permission_info=fx_permission_info,
        search_text=course_search,
        course_ids=course_ids,
    )

    queryset = CourseEnrollment.objects.filter(
        is_active=True,
        course__in=Subquery(accessible_courses.values('id')),
        user__in=Subquery(accessible_users.values('id'))
    ).annotate(
        certificate_available=Exists(
            GeneratedCertificate.objects.filter(
                user_id=OuterRef('user_id'),
                user__is_active=True,
                course_id=OuterRef('course_id'),
                status='downloadable'
            )
        )
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
