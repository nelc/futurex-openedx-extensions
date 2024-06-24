"""PyTest fixtures for tests."""
import pytest
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment, UserSignupSource
from django.contrib.auth import get_user_model
from django.utils import timezone
from eox_tenant.models import Route, TenantConfig
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from tests.base_test_data import _base_data


@pytest.fixture(scope="session")
def base_data(django_db_setup, django_db_blocker):  # pylint: disable=unused-argument
    """Create base data for tests."""
    def _create_users():
        """Create users."""
        user = get_user_model()
        for i in range(1, _base_data["users_count"] + 1):
            user.objects.create(
                id=i,
                username=f"user{i}",
                email=f"user{i}@example.com",
            )
        for user_id in _base_data["super_users"]:
            user.objects.filter(id=user_id).update(is_superuser=True)
        for user_id in _base_data["staff_users"]:
            user.objects.filter(id=user_id).update(is_staff=True)
        for user_id in _base_data["inactive_users"]:
            user.objects.filter(id=user_id).update(is_active=False)

    def _create_tenants():
        """Create tenants."""
        for tenant_id, tenant_config in _base_data["tenant_config"].items():
            TenantConfig.objects.create(
                id=tenant_id,
                lms_configs=tenant_config["lms_configs"],
            )

    def _create_routes():
        """Create routes."""
        for route_id in _base_data["routes"]:
            Route.objects.create(
                id=route_id,
                domain=_base_data["routes"][route_id]["domain"],
                config_id=_base_data["routes"][route_id]["config_id"],
            )

    def _create_user_signup_sources():
        """Create user signup sources."""
        for site, users in _base_data["user_signup_source__users"].items():
            for user_id in users:
                UserSignupSource.objects.create(
                    site=site,
                    user_id=user_id,
                )

    def _create_course_access_roles():
        """Create course access roles."""
        for role, orgs in _base_data["course_access_roles"].items():
            for org, users in orgs.items():
                for user_id in users:
                    CourseAccessRole.objects.create(
                        user_id=user_id,
                        role=role,
                        org=org,
                    )

    def _create_ignored_course_access_roles():
        """Create course access roles for records that will be ignored by our APIs."""
        for reason, orgs in _base_data["ignored_course_access_roles"].items():
            for role, users in orgs.items():
                for user_id in users:
                    assert reason in ['no_org'], f"Unknown reason for (ignored_course_access_roles) test data: {reason}"
                    params = {
                        'user_id': user_id,
                        'role': role,
                        'org': '',
                    }
                    CourseAccessRole.objects.create(**params)

    def _create_course_overviews():
        """Create course overviews."""
        for org, count in _base_data["course_overviews"].items():
            for i in range(1, count + 1):
                CourseOverview.objects.create(
                    id=f"course-v1:{org}+{i}+{i}",
                    org=org,
                    catalog_visibility="both",
                    display_name=f"Course {i} of {org}",
                )

        now_time = timezone.now()
        for course_id, data in _base_data["course_attributes"].items():
            course = CourseOverview.objects.get(id=course_id)
            for field, value in data.items():
                if field in ("start", "end"):
                    assert value in ("F", "P"), f"Bad value for {field} in course_attributes testing data: {value}"
                if field == "start":
                    if value == "F":
                        course.start = now_time + timezone.timedelta(days=1)
                    else:
                        course.start = now_time - timezone.timedelta(days=10)
                    continue
                if field == "end":
                    if value == "F":
                        course.end = now_time + timezone.timedelta(days=10)
                    else:
                        course.end = now_time - timezone.timedelta(days=1)
                    continue
                setattr(course, field, value)
            course.save()

    def _create_course_enrollments():
        """Create course enrollments."""
        for org, enrollments in _base_data["course_enrollments"].items():
            for course_id, users in enrollments.items():
                for user_id in users:
                    assert 0 < course_id <= _base_data["course_overviews"][org], \
                        f"Bad course_id in enrollment testing data for org: {org}, course: {course_id}"
                    assert 0 < user_id <= _base_data["users_count"], \
                        f"Bad user_id in enrollment testing data for org: {org}, user: {user_id}, course: {course_id}"
                    CourseEnrollment.objects.create(
                        user_id=user_id,
                        course_id=f"course-v1:{org}+{course_id}+{course_id}",
                        is_active=True,
                    )

    def _create_certificates():
        """Create certificates."""
        for org, courses in _base_data["certificates"].items():
            for course_id, user_ids in courses.items():
                for user_id in user_ids:
                    GeneratedCertificate.objects.create(
                        user_id=user_id,
                        course_id=f"course-v1:{org}+{course_id}+{course_id}",
                        status='downloadable',
                    )

    with django_db_blocker.unblock():
        _create_users()
        _create_tenants()
        _create_routes()
        _create_user_signup_sources()
        _create_course_access_roles()
        _create_ignored_course_access_roles()
        _create_course_overviews()
        _create_course_enrollments()
        _create_certificates()
