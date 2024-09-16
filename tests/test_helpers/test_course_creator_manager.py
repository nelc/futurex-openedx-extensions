"""Tests for the CourseCreatorManager class."""
from unittest.mock import MagicMock, patch

import pytest
from cms.djangoapps.course_creators.models import CourseCreator
from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed
from fake_models.models import m2m_changed_never_use_set_add_remove_or_clear as orgs_signal_handler
from organizations.models import Organization

from futurex_openedx_extensions.helpers.course_creator_manager import CourseCreatorManager
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes


def _add_clear_org_to_course_creator(course_creator, org_instance=None):
    """
    Helper to add orgs or clear all orgs to the course-creator record. When org_instance is None, all orgs are cleared.
    Otherwise, org_instance is added to the course-creator record.
    """
    m2m_changed.disconnect(receiver=orgs_signal_handler, sender=CourseCreator.organizations.through)
    if org_instance:
        course_creator.organizations.add(org_instance)
    else:
        course_creator.organizations.clear()
    m2m_changed.connect(receiver=orgs_signal_handler, sender=CourseCreator.organizations.through)


@pytest.fixture
def empty_course_creator():
    """Create a CourseCreator record for user 33 with no organizations."""
    CourseCreator.objects.bulk_create([CourseCreator(
        user_id=33, all_organizations=False, state=CourseCreator.GRANTED,
    )])
    for org_index in range(1, 5):
        org_name = f'org{org_index}'
        Organization.objects.create(short_name=org_name)
    return CourseCreator.objects.get(user_id=33)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_creator_manager.CourseCreatorManager.reload')
def test_course_creator_manager_init(mock_reload, base_data):  # pylint: disable=unused-argument
    """Verify that the CourseCreatorManager is initialized correctly."""
    creator = CourseCreatorManager(user_id=3)
    assert mock_reload.called_once()
    assert creator.user is None


@pytest.mark.django_db
def test_course_creator_manager_reload_no_creator(base_data):  # pylint: disable=unused-argument
    """Verify that the CourseCreatorManager reload method works when no creator exists."""
    user = get_user_model().objects.get(id=3)
    creator = CourseCreatorManager(user_id=3)

    assert creator.user == user
    assert creator.db_record is None


@pytest.mark.django_db
def test_course_creator_manager_reload_creator_exists(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the CourseCreatorManager reload method works when a creator exists."""
    user = get_user_model().objects.get(id=33)
    creator = CourseCreatorManager(user_id=33)

    assert creator.user == user
    assert creator.db_record == empty_course_creator
    assert creator.db_record.state == CourseCreator.GRANTED
    CourseCreator.objects.filter(id=empty_course_creator.id).update(state=CourseCreator.DENIED)
    assert creator.db_record.state == CourseCreator.GRANTED
    creator.reload()
    assert creator.db_record.state == CourseCreator.DENIED


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [0, -1, 'invalid'])
def test_course_creator_manager_reload_invalid_user_id(user_id):
    """Verify that the CourseCreatorManager raises an exception when an invalid user_id is provided."""
    with pytest.raises(FXCodedException) as exc_info:
        CourseCreatorManager(user_id=user_id)
    assert exc_info.value.code == FXExceptionCodes.USER_NOT_FOUND.value
    assert str(exc_info.value) == 'FXCourseCreator: invalid user_id!'


@pytest.mark.django_db
def test_course_creator_manager_reload_user_not_found(base_data):  # pylint: disable=unused-argument
    """Verify that the CourseCreatorManager raises an exception when the user is not found."""
    with pytest.raises(FXCodedException) as exc_info:
        CourseCreatorManager(user_id=999)
    assert exc_info.value.code == FXExceptionCodes.USER_NOT_FOUND.value
    assert str(exc_info.value) == 'FXCourseCreator: User (999) not found!'


@pytest.mark.django_db
def test_course_creator_manager_validate_creator(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the validate_creator method works correctly."""
    assert CourseCreatorManager(user_id=33).validate_creator() is None

    with pytest.raises(FXCodedException) as exc_info:
        CourseCreatorManager(user_id=4).validate_creator()
    assert exc_info.value.code == FXExceptionCodes.COURSE_CREATOR_NOT_FOUND.value
    assert str(exc_info.value) == 'FXCourseCreator: Course creator not found for user: user4'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_creator_manager.CourseCreatorManager.reload')
def test_course_creator_manager_db_record(mock_reload, base_data):  # pylint: disable=unused-argument
    """Verify that the CourseCreatorManager db_record property calls reload if the record is not set."""
    creator = CourseCreatorManager(user_id=3)
    assert mock_reload.called_once()
    assert creator._db_record is None  # pylint: disable=protected-access
    mock_reload.reset_mock()
    assert creator.db_record is None
    assert mock_reload.called_once()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_creator_manager.CourseCreatorManager.validate_creator')
def test_course_creator_manager_is_granted(
    mock_validate, base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that is_granted works correctly."""
    creator = CourseCreatorManager(user_id=33)
    record = creator.db_record
    assert record.state == CourseCreator.GRANTED
    assert creator.is_granted() is True

    CourseCreator.objects.filter(id=record.id).update(state=CourseCreator.DENIED)
    creator.reload()
    mock_validate.reset_mock()
    assert creator.is_granted() is False
    assert mock_validate.called_once()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_creator_manager.CourseCreatorManager.validate_creator')
def test_course_creator_manager_is_orgs_empty(
    mock_validate, base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that is_orgs_empty works correctly."""
    creator = CourseCreatorManager(user_id=33)
    record = creator.db_record
    assert not record.organizations.exists()
    assert creator.is_orgs_empty() is True

    mock_validate.reset_mock()
    with patch(
        'futurex_openedx_extensions.helpers.course_creator_manager.CourseCreator.organizations',
        return_value=MagicMock(exists=MagicMock(return_value=True)),
    ):
        assert creator.is_orgs_empty() is False
    assert mock_validate.called_once()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_creator_manager.CourseCreatorManager.validate_creator')
def test_course_creator_manager_is_all_orgs(
    mock_validate, base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that is_all_orgs works correctly."""
    creator = CourseCreatorManager(user_id=33)
    record = creator.db_record
    assert not record.organizations.exists()
    assert creator.is_all_orgs() is False

    mock_validate.reset_mock()
    with patch(
        'futurex_openedx_extensions.helpers.course_creator_manager.CourseCreator.all_organizations',
        return_value=False,
    ):
        assert creator.is_orgs_empty() is True
    assert mock_validate.called_once()


@pytest.mark.django_db
def test_course_creator_manager_get_orgs(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that get_orgs works correctly."""
    creator = CourseCreatorManager(user_id=33)
    assert isinstance(creator.get_orgs(), list)
    assert not creator.get_orgs()

    _add_clear_org_to_course_creator(empty_course_creator, Organization.objects.get(short_name='ORG1'))
    _add_clear_org_to_course_creator(empty_course_creator, Organization.objects.get(short_name='ORG2'))
    creator.reload()
    assert creator.get_orgs() == ['org1', 'org2']


@pytest.mark.django_db
def test_course_creator_manager_delete_creator(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that delete_creator works correctly."""
    creator = CourseCreatorManager(user_id=33)
    assert creator.db_record is not None
    _add_clear_org_to_course_creator(empty_course_creator, Organization.objects.get(short_name='ORG1'))
    _add_clear_org_to_course_creator(empty_course_creator, Organization.objects.get(short_name='ORG2'))
    creator.reload()

    creator.delete_creator()
    assert CourseCreator.objects.filter(user_id=33).exists() is False
    creator.reload()
    assert creator.db_record is None


@pytest.mark.django_db
def test_course_creator_manager_add_orgs(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that add_orgs adds the organizations to the course creator record."""
    creator = CourseCreatorManager(user_id=33)
    assert creator.is_all_orgs() is False
    creator.add_orgs(['org1', 'org2'])
    assert empty_course_creator.organizations.count() == 2
    assert set(empty_course_creator.organizations.values_list('short_name', flat=True)) == {'org1', 'org2'}

    creator.add_orgs(['org1', 'org3'])
    assert empty_course_creator.organizations.count() == 3
    assert set(empty_course_creator.organizations.values_list('short_name', flat=True)) == {'org1', 'org2', 'org3'}

    creator.add_orgs([])
    assert empty_course_creator.organizations.count() == 3
    assert set(empty_course_creator.organizations.values_list('short_name', flat=True)) == {'org1', 'org2', 'org3'}


@pytest.mark.django_db
def test_course_creator_manager_add_orgs_creates_creator(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that add_orgs creates a course creator record if it does not exist."""
    user_id = 4
    creator = CourseCreatorManager(user_id=user_id)
    assert creator.db_record is None

    creator.add_orgs(['org1', 'org2'])
    assert CourseCreator.objects.filter(user_id=user_id).exists()
    creator.reload()
    assert creator.db_record is not None


@pytest.mark.django_db
def test_course_creator_manager_add_orgs_global(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that add_orgs does not add organizations if the user has global creator access."""
    user_id = 33
    CourseCreator.objects.filter(user_id=user_id).update(all_organizations=True)
    creator = CourseCreatorManager(user_id=user_id)
    assert creator.is_orgs_empty()

    creator.add_orgs(['org1', 'org2'])
    assert creator.is_all_orgs() is True
    creator.reload()
    assert creator.is_all_orgs() is True


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_creator_manager.CourseCreatorManager.is_all_orgs')
def test_course_creator_manager_add_fail(
    mock_is_all_orgs, base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that add_orgs might fail ofr any reason."""
    mock_is_all_orgs.side_effect = FXCodedException(code=0, message='Some error for testing!')
    creator = CourseCreatorManager(user_id=33)
    with pytest.raises(type(mock_is_all_orgs.side_effect)) as exc_info:
        creator.add_orgs(['org1', 'org2'])
    assert str(exc_info.value) == mock_is_all_orgs.side_effect.args[0]


@pytest.mark.django_db
def test_course_creator_manager_add_no_org(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that add_orgs raises an exception when an organization does not exist."""
    creator = CourseCreatorManager(user_id=33)
    with pytest.raises(FXCodedException) as exc_info:
        creator.add_orgs(['org-not-exists'])
    assert str(exc_info.value) == 'FXCourseCreator: organization not found: (org-not-exists)'


@pytest.mark.django_db
def test_course_creator_manager_remove_orgs(
    base_data, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that remove_orgs removes the organizations from the course creator record."""
    for org_index in range(1, 5):
        _add_clear_org_to_course_creator(empty_course_creator, Organization.objects.get(short_name=f'ORG{org_index}'))

    creator = CourseCreatorManager(user_id=33)
    creator.remove_orgs(['org1', 'org2', 'invalid_org'])
    assert empty_course_creator.organizations.count() == 2
    assert set(empty_course_creator.organizations.values_list('short_name', flat=True)) == {'org3', 'org4'}

    creator.remove_orgs(['org1', 'org3'])
    assert empty_course_creator.organizations.count() == 1
    assert set(empty_course_creator.organizations.values_list('short_name', flat=True)) == {'org4'}

    creator.remove_orgs([])
    assert empty_course_creator.organizations.count() == 1
    assert set(empty_course_creator.organizations.values_list('short_name', flat=True)) == {'org4'}

    creator.remove_orgs(['org4'], delete_on_empty=False)
    assert CourseCreator.objects.filter(user_id=33).exists()
    assert empty_course_creator.organizations.count() == 0

    creator.remove_orgs([], delete_on_empty=False)
    assert CourseCreator.objects.filter(user_id=33).exists()
    assert empty_course_creator.organizations.count() == 0

    creator.remove_orgs([])
    assert not CourseCreator.objects.filter(user_id=33).exists()

    creator.remove_orgs(['org1'])
    assert not CourseCreator.objects.filter(user_id=33).exists()
