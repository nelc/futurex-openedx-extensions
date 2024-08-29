"""Courses details collectors"""
from __future__ import annotations

from completion.models import BlockCompletion
from django.db.models import (
    BooleanField,
    Case,
    Count,
    DateTimeField,
    Exists,
    F,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from eox_nelp.course_experience.models import FeedbackCourse
from lms.djangoapps.certificates.models import GeneratedCertificate

from futurex_openedx_extensions.helpers.querysets import check_staff_exist_queryset, get_base_queryset_courses


def annotate_courses_rating_queryset(
    base_queryset: QuerySet,
) -> QuerySet:
    """
    Annotate the given courses queryset with rating information.

    :param base_queryset: Base queryset of courses
    :type base_queryset: QuerySet
    :return: Annotated queryset of courses
    :rtype: QuerySet
    """
    queryset = base_queryset.annotate(
        rating_count=Coalesce(Subquery(
            FeedbackCourse.objects.filter(
                course_id=OuterRef('id'),
                rating_content__isnull=False,
                rating_content__gt=0,
            ).values('course_id').annotate(count=Count('id')).values('count'),
            output_field=IntegerField(),
        ), 0),
    ).annotate(
        rating_total=Coalesce(Subquery(
            FeedbackCourse.objects.filter(
                course_id=OuterRef('id'),
                rating_content__isnull=False,
                rating_content__gt=0,
            ).values('course_id').annotate(total=Sum('rating_content')).values('total'),
        ), 0),
    )

    return queryset


def get_courses_queryset(
    fx_permission_info: dict,
    search_text: str | None = None,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the courses queryset for the given tenant IDs and search text.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param search_text: Search text to filter the courses by
    :type search_text: str | None
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter
    :type active_filter: bool | None
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of courses
    :rtype: QuerySet
    """
    queryset = get_base_queryset_courses(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter,
    )

    search_text = (search_text or '').strip()
    if search_text:
        queryset = queryset.filter(
            Q(display_name__icontains=search_text) |
            Q(id__icontains=search_text),
        )

    queryset = annotate_courses_rating_queryset(queryset)

    if include_staff:
        is_staff_queryset = Q(Value(False, output_field=BooleanField()))
    else:
        is_staff_queryset = check_staff_exist_queryset('courseenrollment__user_id', 'org', 'id')

    queryset = queryset.annotate(
        enrolled_count=Count(
            'courseenrollment',
            filter=(
                Q(courseenrollment__is_active=True) &
                Q(courseenrollment__user__is_active=True) &
                Q(courseenrollment__user__is_staff=False) &
                Q(courseenrollment__user__is_superuser=False) &
                ~is_staff_queryset
            ),
        )
    ).annotate(
        active_count=Count(
            'courseenrollment',
            filter=(
                Q(courseenrollment__is_active=True) &
                Q(courseenrollment__user__is_active=True) &
                Q(courseenrollment__user__is_staff=False) &
                Q(courseenrollment__user__is_superuser=False) &
                ~is_staff_queryset
            ),
        )
    ).annotate(
        certificates_count=Coalesce(Subquery(
            GeneratedCertificate.objects.filter(
                course_id=OuterRef('id'),
                status='downloadable'
            ).values('course_id').annotate(count=Count('id')).values('count'),
            output_field=IntegerField(),
        ), 0),
    )

    return queryset


def get_learner_courses_info_queryset(
    fx_permission_info: dict, user_id: int, visible_filter: bool | None = True, active_filter: bool | None = None
) -> QuerySet:
    """
    Get the learner's courses queryset for the given user ID. This method assumes a valid user ID.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param user_id: The user ID to get the learner for
    :type user_id: int
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter
    :type active_filter: bool | None
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    queryset = get_base_queryset_courses(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter,
    ).filter(
        courseenrollment__user_id=user_id,
        courseenrollment__is_active=True,
    ).annotate(
        related_user_id=Value(user_id, output_field=IntegerField()),
    ).annotate(
        enrollment_date=Case(
            When(
                courseenrollment__user_id=user_id,
                then=F('courseenrollment__created'),
            ),
            default=None,
            output_field=DateTimeField(),
        )
    ).annotate(
        last_activity=Case(
            When(
                Exists(
                    BlockCompletion.objects.filter(
                        user_id=user_id,
                        context_key=OuterRef('id'),
                    ),
                ),
                then=Subquery(
                    BlockCompletion.objects.filter(
                        user_id=user_id,
                        context_key=OuterRef('id'),
                    ).values('context_key').annotate(
                        last_activity=Max('modified'),
                    ).values('last_activity'),
                    output_field=DateTimeField(),
                ),
            ),
            default=F('enrollment_date'),
            output_field=DateTimeField(),
        )
    )

    return queryset
