"""Learners details collectors"""
from __future__ import annotations

from datetime import timedelta

from common.djangoapps.student.models import CourseEnrollment
from django.contrib.auth import get_user_model
from django.db.models import BooleanField, Case, Count, Exists, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.grades.models import PersistentCourseGrade
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.extractors import get_partial_access_course_ids, verify_course_ids
from futurex_openedx_extensions.helpers.querysets import (
    check_staff_exist_queryset,
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
    return Coalesce(Subquery(
        GeneratedCertificate.objects.filter(
            user_id=OuterRef('id'),
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


def get_learners_queryset(
    fx_permission_info: dict,
    search_text: str | None = None,
    visible_courses_filter: bool | None = True,
    active_courses_filter: bool | None = None,
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
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
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
    ).select_related('profile', 'extrainfo').order_by('id')

    update_removable_annotations(queryset, removable=['courses_count', 'certificates_count'])

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


def get_learners_enrollments_queryset(
    fx_permission_info: dict,
    user_ids: list = None,
    course_ids: list = None,
    search_text: str | None = None,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the enrollment details. If no course_ids or user_ids are provided,
    all relevant data will be processed.

    :param course_ids: List of course IDs to filter by (optional).
    :param user_ids: List of user IDs to filter by (optional).
    :param search_text: Text to filter users by (optional).
    :param include_staff: Flag to include staff users (default: False).
    :return: List of dictionaries containing user and course details.
    """
    accessible_users = get_permitted_learners_queryset(
        queryset=get_learners_search_queryset(search_text),
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )
    if user_ids:
        invalid_user_ids = [user_id for user_id in user_ids if not isinstance(user_id, int)]
        if invalid_user_ids:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f'Invalid user ids: {invalid_user_ids}',
            )
        accessible_users = accessible_users.filter(id__in=user_ids)

    accessible_courses = CourseOverview.objects.filter(
        Q(id__in=get_partial_access_course_ids(fx_permission_info)) |
        Q(org__in=fx_permission_info['view_allowed_full_access_orgs'])
    )
    if course_ids:
        verify_course_ids(course_ids)
        accessible_courses = accessible_courses.filter(id__in=course_ids)

    queryset = CourseEnrollment.objects.filter(
        is_active=True,
        course__in=Subquery(accessible_courses.values('id')),
        user__in=Subquery(accessible_users.values('id'))
    ).annotate(
        certificate_available=Exists(
            GeneratedCertificate.objects.filter(
                user_id=OuterRef('user_id'),
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

    update_removable_annotations(queryset, removable=['certificate_available', 'course_score', 'active_in_course'])

    return queryset
