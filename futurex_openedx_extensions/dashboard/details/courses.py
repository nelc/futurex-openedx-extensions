"""Courses details collectors"""
from __future__ import annotations

from common.djangoapps.student.models import CourseEnrollment
from completion.models import BlockCompletion
from django.contrib.auth import get_user_model
from django.db.models import (
    BooleanField,
    Case,
    Count,
    DateTimeField,
    Exists,
    F,
    FloatField,
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
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.querysets import (
    check_staff_exist_queryset,
    get_base_queryset_courses,
    get_one_user_queryset,
    update_removable_annotations,
)


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

    update_removable_annotations(queryset, removable=['rating_count', 'rating_total'])

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
        is_staff_queryset = check_staff_exist_queryset(
            ref_user_id='user_id', ref_org='course__org', ref_course_id='course_id',
        )

    queryset = queryset.annotate(
        enrolled_count=Coalesce(Subquery(
            CourseEnrollment.objects.filter(
                course_id=OuterRef('id'),
                is_active=True,
                user__is_active=True,
                user__is_staff=False,
                user__is_superuser=False,
            ).filter(
                ~is_staff_queryset,
            ).values('course_id').annotate(count=Count('id')).values('count'),
            output_field=IntegerField(),
        ), 0)
    ).annotate(
        active_count=Coalesce(Subquery(
            CourseEnrollment.objects.filter(
                course_id=OuterRef('id'),
                is_active=True,
                user__is_active=True,
                user__is_staff=False,
                user__is_superuser=False,
            ).filter(
                ~is_staff_queryset,
            ).values('course_id').annotate(count=Count('id')).values('count'),
            output_field=IntegerField(),
        ), 0)
    ).annotate(
        certificates_count=Coalesce(Subquery(
            GeneratedCertificate.objects.filter(
                course_id=OuterRef('id'),
                status='downloadable',
                user__is_active=True,
            ).annotate(
                course__org=Subquery(
                    CourseOverview.objects.filter(id=OuterRef('course_id')).values('org')
                )
            ).filter(
                ~is_staff_queryset
            ).values('course_id').annotate(count=Count('id')).values('count'),
            output_field=IntegerField(),
        ), 0),
    ).annotate(
        completion_rate=Case(
            When(enrolled_count=0, then=Value(0.0)),
            default=F('certificates_count') * 1.0 / F('enrolled_count'),
            output_field=FloatField(),
        )
    )

    update_removable_annotations(queryset, removable=[
        'enrolled_count', 'active_count', 'certificates_count', 'completion_rate',
    ])

    return queryset


def get_learner_courses_info_queryset(
    fx_permission_info: dict,
    user_key: get_user_model | int | str,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the learner's courses queryset for the given user ID. This method assumes a valid user ID.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param user_key: The user key to get the learner for
    :type user_key: get_user_model | int | str
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter
    :type active_filter: bool | None
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    user = get_one_user_queryset(
        fx_permission_info=fx_permission_info,
        user_key=user_key,
        include_staff=include_staff
    ).first()

    queryset = get_base_queryset_courses(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter,
    ).filter(
        courseenrollment__user_id=user.id,
        courseenrollment__is_active=True,
    ).annotate(
        related_user_id=Value(user.id, output_field=IntegerField()),
    ).annotate(
        enrollment_date=Case(
            When(
                courseenrollment__user_id=user.id,
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
                        user_id=user.id,
                        context_key=OuterRef('id'),
                    ),
                ),
                then=Subquery(
                    BlockCompletion.objects.filter(
                        user_id=user.id,
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

    update_removable_annotations(queryset, removable=['related_user_id', 'enrollment_date', 'last_activity'])

    return queryset
