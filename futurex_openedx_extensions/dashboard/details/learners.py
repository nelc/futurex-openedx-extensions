"""Learners details collectors"""
from __future__ import annotations

from datetime import timedelta

from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.db.models import BooleanField, Case, Count, Exists, OuterRef, Q, Subquery, Value, When
from django.db.models.query import QuerySet
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.grades.models import PersistentCourseGrade

from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses, get_has_site_login_queryset
from futurex_openedx_extensions.helpers.tenants import get_tenants_sites


def get_courses_count_for_learner_queryset(
    fx_permission_info: dict,
    visible_courses_filter: bool = True,
    active_courses_filter: bool = None,
) -> QuerySet:
    """
    Annotate the given queryset with the courses count for the learner.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    return Count(
        'courseenrollment',
        filter=(
            Q(courseenrollment__course_id__in=get_base_queryset_courses(
                fx_permission_info,
                visible_filter=visible_courses_filter,
                active_filter=active_courses_filter,
            )) &
            ~Exists(
                CourseAccessRole.objects.filter(
                    user_id=OuterRef('id'),
                    org=OuterRef('courseenrollment__course__org')
                )
            )
        ),
        distinct=True
    )


def get_certificates_count_for_learner_queryset(
    fx_permission_info: dict,
    visible_courses_filter: bool = True,
    active_courses_filter: bool = None,
) -> QuerySet:
    """
    Annotate the given queryset with the certificate counts.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    return Count(
        'generatedcertificate',
        filter=(
            Q(generatedcertificate__course_id__in=Subquery(
                get_base_queryset_courses(
                    fx_permission_info,
                    visible_filter=visible_courses_filter,
                    active_filter=active_courses_filter
                ).values_list('id', flat=True)
            )) &
            Q(generatedcertificate__status='downloadable')
        ),
        distinct=True
    )


def get_learners_search_queryset(
    search_text: str = None,
    superuser_filter: bool | None = False,
    staff_filter: bool | None = False,
    active_filter: bool | None = True
) -> QuerySet:
    """
    Get the learners queryset for the given search text.

    :param search_text: Search text to filter the learners by
    :type search_text: str
    :param superuser_filter: Value to filter superusers. None means no filter
    :type superuser_filter: bool
    :param staff_filter: Value to filter staff users. None means no filter
    :type staff_filter: bool
    :param active_filter: Value to filter active users. None means no filter
    :type active_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    queryset = get_user_model().objects.all()

    if superuser_filter is not None:
        queryset = queryset.filter(is_superuser=superuser_filter)
    if staff_filter is not None:
        queryset = queryset.filter(is_staff=staff_filter)
    if active_filter is not None:
        queryset = queryset.filter(is_active=active_filter)

    search_text = (search_text or '').strip()
    if search_text:
        queryset = queryset.filter(
            Q(username__icontains=search_text) |
            Q(email__icontains=search_text) |
            Q(profile__name__icontains=search_text)
        )

    return queryset


def get_learners_queryset(
    fx_permission_info: dict,
    search_text: str = None,
    visible_courses_filter: bool = True,
    active_courses_filter: bool = None
) -> QuerySet:
    """
    Get the learners queryset for the given tenant IDs and search text.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param search_text: Search text to filter the learners by
    :type search_text: str
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    tenant_sites = get_tenants_sites(fx_permission_info['permitted_tenant_ids'])

    queryset = get_learners_search_queryset(search_text)

    queryset = queryset.annotate(
        courses_count=get_courses_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).annotate(
        certificates_count=get_certificates_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).annotate(
        has_site_login=get_has_site_login_queryset(tenant_sites)
    ).filter(
        Q(courses_count__gt=0) | Q(has_site_login=True)
    ).select_related('profile').order_by('id')

    return queryset


def get_learners_by_course_queryset(course_id: str, search_text: str = None) -> QuerySet:
    """
    Get the learners queryset for the given course ID.

    :param course_id: The course ID to get the learners for
    :type course_id: str
    :param search_text: Search text to filter the learners by
    :type search_text: str
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    queryset = get_learners_search_queryset(search_text)
    queryset = queryset.filter(
        courseenrollment__course_id=course_id
    ).filter(
        ~Exists(
            CourseAccessRole.objects.filter(
                user_id=OuterRef('id'),
                org=OuterRef('courseenrollment__course__org')
            )
        )
    ).annotate(
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

    return queryset


def get_learner_info_queryset(
    fx_permission_info: dict, user_id: int, visible_courses_filter: bool = True, active_courses_filter: bool = None
) -> QuerySet:
    """
    Get the learner queryset for the given user ID. This method assumes a valid user ID.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param user_id: The user ID to get the learner for
    :type user_id: int
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    queryset = get_user_model().objects.filter(id=user_id).annotate(
        courses_count=get_courses_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).annotate(
        certificates_count=get_certificates_count_for_learner_queryset(
            fx_permission_info,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).select_related('profile')

    return queryset
