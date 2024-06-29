"""Courses details collectors"""
from __future__ import annotations

from common.djangoapps.student.models import CourseAccessRole
from completion.models import BlockCompletion
from django.db.models import (
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

from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses


def get_courses_queryset(
    fx_permission_info: dict,
    search_text: str = None,
    visible_filter: bool | None = True,
    active_filter: bool | None = None
) -> QuerySet:
    """
    Get the courses queryset for the given tenant IDs and search text.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param search_text: Search text to filter the courses by
    :type search_text: str
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter
    :type active_filter: bool | None
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
    queryset = queryset.annotate(
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
    ).annotate(
        enrolled_count=Count(
            'courseenrollment',
            filter=(
                Q(courseenrollment__is_active=True) &
                Q(courseenrollment__user__is_active=True) &
                Q(courseenrollment__user__is_staff=False) &
                Q(courseenrollment__user__is_superuser=False) &
                ~Exists(
                    CourseAccessRole.objects.filter(
                        user_id=OuterRef('courseenrollment__user_id'),
                        org=OuterRef('org'),
                    ),
                )
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
                ~Exists(
                    CourseAccessRole.objects.filter(
                        user_id=OuterRef('courseenrollment__user_id'),
                        org=OuterRef('org'),
                    ),
                )
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
