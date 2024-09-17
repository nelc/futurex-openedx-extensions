"""Wrapper class for CourseCreator model."""
from __future__ import annotations

from typing import List

from cms.djangoapps.course_creators.models import CourseCreator
from django.contrib.auth import get_user_model
from django.db.models.functions import Lower
from organizations.models import Organization

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes


class CourseCreatorManager:
    """Wrapper class for CourseCreator model."""

    def __init__(self, user_id: int) -> None:
        """
        Initialize the course creator from user ID

        :param user_id: User ID of the user creating the course.
        :type user_id: int
        """
        self._user_id = user_id
        self._db_record = None
        self._user = None

        self.reload()

    @property
    def db_record(self) -> CourseCreator:
        """
        Get the CourseCreator object.

        :return: CourseCreator object.
        """
        if not self._db_record:
            self.reload()
        return self._db_record

    @property
    def user(self) -> get_user_model:
        """
        Get the user object of the course creator.

        :return: User object.
        """
        return self._user

    def reload(self) -> None:
        """Reload the user object from the database."""
        if not isinstance(self._user_id, int) or self._user_id <= 0:
            raise FXCodedException(
                FXExceptionCodes.USER_NOT_FOUND,
                'FXCourseCreator: invalid user_id!'
            )

        try:
            self._user = get_user_model().objects.get(id=self._user_id)
        except get_user_model().DoesNotExist as exc:
            raise FXCodedException(
                FXExceptionCodes.USER_NOT_FOUND,
                f'FXCourseCreator: User ({self._user_id}) not found!'
            ) from exc

        self._db_record = self.user.coursecreator if hasattr(self.user, 'coursecreator') else None

    def validate_creator(self) -> None:
        """Validate the course creator."""
        if not self.db_record:
            raise FXCodedException(
                FXExceptionCodes.COURSE_CREATOR_NOT_FOUND,
                f'FXCourseCreator: Course creator not found for user: {self.user.username}'
            )

    def is_granted(self) -> bool:
        """
        Check if the course creator is granted.

        :return: True if the course creator is granted.
        :rtype: bool
        """
        self.validate_creator()

        return self.db_record.state == self.db_record.GRANTED

    def is_orgs_empty(self) -> bool:
        """
        Check if the course creator has access to any organizations.

        :return: True if the course creator has access to any organizations.
        :rtype: bool
        """
        self.validate_creator()

        return not self.db_record.organizations.exists()

    def is_all_orgs(self) -> bool:
        """
        Check if the course creator has access to all organizations.

        :return: True if the course creator has access to all organizations.
        :rtype: bool
        """
        self.validate_creator()

        return self.db_record.all_organizations

    def get_orgs(self) -> List[str]:
        """
        Get the organizations the course creator has access to.

        :return: List of organizations the course creator has access to.
        :rtype: List[str]
        """
        return list(self.db_record.organizations.annotate(
            short_name_lower=Lower('short_name')
        ).values_list('short_name_lower', flat=True))

    def delete_creator(self) -> None:
        """Delete the course creator."""
        self.validate_creator()

        self.db_record.delete()
        self.reload()

    def add_orgs(self, orgs: list[str]) -> None:
        """
        Add the orgs to the course creator record. Doing that through the many-to-many relationship to avoid
        triggering signals of the CourseCreator model.

        :param orgs: The orgs to add
        :type orgs: list
        """
        try:
            is_all_orgs = self.is_all_orgs()
        except FXCodedException as exc:
            if exc.code != FXExceptionCodes.COURSE_CREATOR_NOT_FOUND.value:
                raise

            CourseCreator.objects.bulk_create([
                CourseCreator(user=self.user, all_organizations=False, state=CourseCreator.GRANTED),
            ])
            self.reload()
            is_all_orgs = False

        if is_all_orgs:
            return

        existing_orgs = set(self.get_orgs())
        orgs = list(set(orgs) - existing_orgs)
        if not orgs:
            return

        organizations_many_to_many = CourseCreator.organizations.through

        new_orgs = []
        for org in orgs:
            try:
                new_orgs.append(Organization.objects.get(short_name=org))
            except Organization.DoesNotExist as exc:
                raise FXCodedException(
                    FXExceptionCodes.INVALID_INPUT,
                    f'FXCourseCreator: organization not found: ({org})'
                ) from exc

        organizations_many_to_many.objects.bulk_create([
            organizations_many_to_many(
                coursecreator_id=self.db_record.id,
                organization_id=org.id,
            ) for org in new_orgs
        ])
        self.reload()

    def remove_orgs(self, orgs: list[str], delete_on_empty: bool = True) -> None:
        """
        Remove the orgs from the course creator record. Doing that through the many-to-many relationship to avoid
        triggering signals of the CourseCreator model.

        :param orgs: The orgs to remove
        :type orgs: list
        :param delete_on_empty: True to delete the record if empty, False otherwise
        :type delete_on_empty: bool
        """
        if not self.db_record:
            return

        organizations_many_to_many = CourseCreator.organizations.through
        organizations_many_to_many.objects.filter(
            coursecreator_id=self.db_record.id,
            organization__short_name__in=orgs,
        ).delete()
        self.reload()

        if delete_on_empty and self.is_orgs_empty():
            self.delete_creator()
