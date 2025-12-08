"""Courses details collectors"""
from __future__ import annotations

from datetime import date
from typing import List

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
from zeitlabs_payments.querysets import get_orders_queryset

from futurex_openedx_extensions.helpers.querysets import (
    check_staff_exist_queryset,
    get_accessible_users_and_courses,
    get_base_queryset_courses,
    get_course_search_queryset,
    get_one_user_queryset,
    get_search_query,
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
            get_search_query(['display_name', 'id'], [], search_text)
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


def get_courses_feedback_queryset(  # pylint: disable=too-many-arguments
    fx_permission_info: dict,
    course_ids: List[str] | None = None,
    public_only: bool = False,
    recommended_only: bool = False,
    feedback_search: str | None = None,
    rating_content_filter: List[int] | None = None,
    rating_instructors_filter: List[int] | None = None,
) -> QuerySet:
    """
    Returns a filtered queryset of FeedbackCourse based on provided criteria.

    :param fx_permission_info: Dictionary containing tenant or user permission info used to filter accessible courses.
    :param course_ids: Optional list of course ID strings to filter feedback by specific courses.
    :param public_only: If True, only include feedback marked as public.
    :param recommended_only: If True, only include feedback marked as recommended.
    :param feedback_search: Optional string to search within the feedback text (case-insensitive, partial match).
    :param rating_content_filter: Optional list of integers (1–5) to filter by content rating values.
    :param rating_instructors_filter: Optional list of integers (1–5) to filter by instructor rating values.
    :return: A Django QuerySet of FeedbackCourse objects matching the specified filters.
    """
    course_qs = get_course_search_queryset(
        fx_permission_info=fx_permission_info,
        search_text=None,
        course_ids=course_ids,
    )

    queryset = FeedbackCourse.objects.filter(
        course_id__in=Subquery(course_qs.values('id'))
    )

    if public_only:
        queryset = queryset.filter(public=True)

    if recommended_only:
        queryset = queryset.filter(recommended=True)

    if rating_content_filter:
        queryset = queryset.filter(rating_content__in=rating_content_filter)

    if rating_instructors_filter:
        queryset = queryset.filter(rating_instructors__in=rating_instructors_filter)

    if feedback_search := (feedback_search or '').strip():
        queryset = queryset.filter(feedback__icontains=feedback_search)

    queryset = queryset.select_related('author__profile')
    return queryset


def get_courses_orders_queryset(  # pylint: disable=too-many-arguments, too-many-locals
    fx_permission_info: dict,
    user_ids: list = None,
    course_ids: list = None,
    usernames: list = None,
    learner_search: str | None = None,
    course_search: str | None = None,
    sku_search: str | None = None,
    include_staff: bool = False,
    include_invoice: bool = False,
    include_user_details: bool = False,
    status: str | None = None,
    item_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet:
    """
    Returns a filtered queryset of Cart Orders based on provided criteria.

    :param fx_permission_info: Dictionary containing tenant or user permission info used to filter accessible courses.
    :type fx_permission_info: dict
    :param user_ids: List of user IDs to filter by (optional).
    :type user_ids: list | None
    :param course_ids: List of course IDs to filter by (optional).
    :type course_ids: list | None
    :param usernames: List of usernames to filter by (optional).
    :type usernames: list | None
    :param sku_search: Text to search enrollments by SKU (optional).
    :type sku_search: str | None
    :param include_staff: Flag to include staff users (default: False).
    :type include_staff: bool
    :param include_invoice: Flag to include invoice details (default: False).
    :type include_invoice: bool
    :param include_user_details: Flag to include user details (default: False).
    :type include_user_details: bool
    :param item_type: Item type to filter by (optional).
    :type item_type: str | None
    :return: A Django QuerySet of Cart objects matching the specified filters.
    :rtype: QuerySet
    """

    # pylint: disable=duplicate-code
    accessible_users, accessible_courses = get_accessible_users_and_courses(
        fx_permission_info=fx_permission_info,
        user_ids=user_ids,
        course_ids=course_ids,
        usernames=usernames,
        learner_search=learner_search,
        course_search=course_search,
        include_staff=include_staff,
    )

    return get_orders_queryset(
        filtered_courses_qs=accessible_courses,
        filtered_users_qs=accessible_users,
        sku_search=sku_search,
        status=status,
        item_type=item_type,
        include_invoice=include_invoice,
        include_user_details=include_user_details,
        date_from=date_from,
        date_to=date_to,
    )
