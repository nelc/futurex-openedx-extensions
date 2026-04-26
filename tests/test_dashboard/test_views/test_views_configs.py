"""Test views for the dashboard app - configs"""
# pylint: disable=duplicate-code
import hashlib
import json
from unittest.mock import ANY, patch

import ddt
import pytest
from django.urls import reverse
from eox_tenant.models import Route, TenantConfig
from rest_framework import status as http_status
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.test import APITestCase

from futurex_openedx_extensions.dashboard.views.configs import ThemeConfigDraftView, ThemeConfigPublishView
from futurex_openedx_extensions.helpers.converters import dict_to_hash
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, DraftConfig
from tests.test_dashboard.test_mixins import BaseTestViewMixin


@pytest.mark.usefixtures('base_data')
class TestConfigEditableInfoView(BaseTestViewMixin):
    """Tests for ConfigEditableInfoView"""
    VIEW_NAME = 'fx_dashboard:config-editable-info'

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)

        ConfigAccessControl.objects.create(key_name='platform_name', path='platform_name', writable=True)
        ConfigAccessControl.objects.create(key_name='pages', path='theme_v2,sections,pages', writable=True)
        ConfigAccessControl.objects.create(key_name='primary_color', path='theme_v2,primary_color', writable=False)
        response = self.client.get(self.url, data={'tenant_ids': 1})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        expected_data = {
            'editable_fields': ['platform_name', 'pages'],
            'read_only_fields': ['primary_color']
        }
        self.assertEqual(response.json(), expected_data)

    def test_one_tenant(self):
        """Verify that ConfigEditableInfoView calls verify_one_tenant_id_provided."""
        self.login_user(self.staff_user)
        with patch(
            'futurex_openedx_extensions.dashboard.views.configs.ConfigEditableInfoView.verify_one_tenant_id_provided'
        ) as mock_verify_one_tenant:
            mock_verify_one_tenant.return_value = 1
            response = self.client.get(self.url, data={'tenant_ids': '1'})
            mock_verify_one_tenant.assert_called_once()
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)


class DraftConfigDataMixin:  # pylint: disable=too-few-public-methods
    """Mixin to create draft config data for tests"""
    def setUp(self):
        """Setup"""
        super().setUp()
        draft_config = DraftConfig.objects.create(
            tenant_id=1,
            config_path='theme_v2.links.facebook',
            config_value='draft.facebook.com',
            created_by_id=1,
            updated_by_id=1,
        )
        draft_config.revision_id = 88776655
        draft_config.save()


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestThemeConfigDraftView(DraftConfigDataMixin, BaseTestViewMixin):
    """Tests for ThemeConfigDraftView"""
    VIEW_NAME = 'fx_dashboard:theme-config-draft'

    def test_only_authorized_users_can_retrieve_draft_config(self):
        """Verify that only authourized users can retrieve draft"""
        ConfigAccessControl.objects.create(key_name='facebook_link', path='theme_v2.links.facebook')
        tenant_config = TenantConfig.objects.get(id=1)
        self.url_args = [tenant_config.id]

        self.login_user(3)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertIn('updated_fields', response.json())

        self.login_user(10)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['reason'], 'User does not have access to the tenant (1)')

    def test_draft_config_retrieve_success(self):
        """Verify that the view returns the correct response"""
        tenant_config = TenantConfig.objects.get(id=1)
        ConfigAccessControl.objects.create(key_name='facebook_link', path='theme_v2.links.facebook')
        self.login_user(self.staff_user)
        self.url_args = [tenant_config.id]
        expected_result = {
            'facebook_link': {
                'published_value': 'facebook.com',
                'draft_value': 'draft.facebook.com'
            }
        }
        expected_hash = hashlib.sha256(
            json.dumps(expected_result, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert response.json()['updated_fields'] == expected_result
        assert response.json()['draft_hash'] == expected_hash

    @ddt.data(
        (
            {},
            "Missing required parameter: 'key'"
        ),
        (
            {'key': 'not-exist'},
            'Invalid key, unable to find key: (not-exist) in config access control'
        ),
        (
            {'key': 'non-writable'},
            '(4001) Config Key: (non-writable) is not writable.'
        ),
        (
            {'key': 123},
            '(4001) Key name must be a string.'
        ),
        (
            {'key': 'platform_name'},
            '(4001) Provide either new_value or reset.'
        ),
        (
            {'key': 'platform_name', 'new_value': 'new updated name'},
            "Missing required parameter: 'current_revision_id'"
        ),
    )
    @ddt.unpack
    def test_put_payload_validation(self, data, expected_reason):
        """Verify that different validation cases return the correct error message."""
        tenant_config = TenantConfig.objects.create(
            external_key='test',
            lms_configs={
                'platform_name': 'my name',
                'theme_v2': {'pages': ['home_page']},
                'config_draft': {},
                'LMS_BASE': 'example.com',
                'non-writable': 'some data',
                'course_org_filter': 'example',
            }
        )
        Route.objects.create(
            domain='example.com',
            config=tenant_config
        )
        ConfigAccessControl.objects.create(
            key_name='platform_name', path='platform_name', writable=True, key_type='string'
        )
        ConfigAccessControl.objects.create(
            key_name='pages', path='theme_v2.pages', writable=True, key_type='list'
        )
        ConfigAccessControl.objects.create(
            key_name='non-writable', path='non-writable', writable=False, key_type='string'
        )

        self.login_user(self.staff_user)
        self.url_args = [tenant_config.id]
        response = self.client.put(self.url, data=data, format='json')

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.data['reason'] == expected_reason

    @staticmethod
    def _prepare_data(tenant_id, config_path):
        """Helper to prepare data for the test"""
        tenant_config = TenantConfig.objects.get(id=tenant_id)
        assert tenant_config.lms_configs['platform_name'] == 's1 platform name'
        assert DraftConfig.objects.filter(tenant_id=tenant_id).count() == 1, 'bad test data'

        ConfigAccessControl.objects.create(key_name='platform_name', path=config_path, writable=True)
        assert DraftConfig.objects.filter(tenant_id=tenant_id, config_path=config_path).count() == 0, 'bad test data'

    @patch('futurex_openedx_extensions.dashboard.views.configs.ThemeConfigDraftView.validate_input')
    @patch('futurex_openedx_extensions.dashboard.views.configs.update_draft_tenant_config')
    def test_draft_config_update(self, mock_update_draft, mocked_validate_input):
        """Verify that the view returns the correct response"""
        def _update_draft(**kwargs):
            """mock update_draft_tenant_config effect"""
            draft_config = DraftConfig.objects.create(
                tenant_id=1,
                config_path=config_path,
                config_value=new_value,
                created_by_id=1,
                updated_by_id=1,
            )
            draft_config.revision_id = 987
            draft_config.save()

        tenant_id = 1
        config_path = 'platform_name'
        self.login_user(self.staff_user)
        self.url_args = [tenant_id]

        self._prepare_data(tenant_id, config_path)

        new_value = 's1 new name'
        mock_update_draft.side_effect = _update_draft

        response = self.client.put(
            self.url,
            data={
                'key': 'platform_name',
                'new_value': new_value,
                'current_revision_id': '456',
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {
            'bad_keys': [],
            'not_permitted': [],
            'revision_ids': {
                'platform_name': '987',
            },
            'values': {
                'platform_name': new_value,
            },
        })
        mock_update_draft.assert_called_once_with(
            tenant_id=tenant_id,
            config_path='platform_name',
            current_revision_id=456,
            new_value=new_value,
            reset=False,
            user=ANY,
        )
        mocked_validate_input.assert_called_once_with('456')

    @patch('futurex_openedx_extensions.dashboard.views.configs.ThemeConfigDraftView.validate_input')
    @patch('futurex_openedx_extensions.dashboard.views.configs.update_draft_tenant_config')
    @ddt.data(
        (None, False),
        ('not boolean', False),
        ('1', False),
        (1, False),
        (False, False),
        (True, True),
    )
    @ddt.unpack
    def test_draft_config_update_reset(self, reset_value, expected_passed_value, mock_update_draft, _):
        """Verify that `reset` is passed to update_draft_tenant_config correctly."""
        tenant_id = 1
        config_path = 'platform_name'
        self._prepare_data(tenant_id, config_path)

        self.url_args = [1]
        self.login_user(self.staff_user)
        self.client.put(
            self.url,
            data={
                'key': 'platform_name',
                'new_value': 'anything',
                'current_revision_id': '0',
                'reset': reset_value,
            },
            format='json'
        )
        mock_update_draft.assert_called_once_with(
            tenant_id=1,
            config_path=config_path,
            current_revision_id=0,
            new_value='anything',
            reset=expected_passed_value,
            user=ANY,
        )

    def test_validate_input(self):
        """Verify the sad scenario when the validation is enabled."""
        with pytest.raises(FXCodedException) as exc_info:
            ThemeConfigDraftView.validate_input('not numeric')
        self.assertEqual(exc_info.value.code, FXExceptionCodes.INVALID_INPUT.value)
        self.assertEqual(str(exc_info.value), 'current_revision_id type must be numeric value.')

    def test_put_with_conflicted_revision_id(self):
        """Verify that the view returns 409 when the revision_id is conflicted."""
        tenant_config = TenantConfig.objects.get(id=1)
        self.login_user(self.staff_user)
        self.url_args = [tenant_config.id]

        assert DraftConfig.objects.filter(tenant_id=1).count() == 1, 'bad test data'
        draft_config = DraftConfig.objects.get(tenant_id=1)
        draft_config.revision_id = 456
        draft_config.save()
        ConfigAccessControl.objects.create(key_name='links', path=draft_config.config_path, writable=True)

        not_the_correct_revision_id = draft_config.revision_id + 1
        response = self.client.put(
            self.url,
            data={
                'key': 'links',
                'new_value': 'new value',
                'current_revision_id': not_the_correct_revision_id,
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT, response.data)
        self.assertEqual(
            response.data['reason'],
            '(13003) Failed to update all the specified draft config paths.',
        )

    @patch('futurex_openedx_extensions.dashboard.views.configs.update_draft_tenant_config')
    def test_draft_config_update_fails(self, mock_update_draft):
        """
        Verify that if the update_draft_tenant_config fails for any reason other than FXExceptionCodes.UPDATE_FAILED
        it'll return 400 with the error message.
        """
        self.login_user(self.staff_user)
        self.url_args = [1]
        ConfigAccessControl.objects.create(key_name='facebook', path='theme_v2.links.facebook', writable=True)

        mock_update_draft.side_effect = FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message='some error message',
        )

        response = self.client.put(
            self.url,
            data={
                'key': 'facebook',
                'new_value': 'any value',
                'current_revision_id': '456',
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data['reason'], '(4001) some error message')

    def test_draft_config_delete(self):
        """Verify that the view returns the correct response"""
        tenant_config = TenantConfig.objects.get(id=1)
        assert DraftConfig.objects.filter(tenant_id=1).count() != 0
        self.url_args = [tenant_config.id]

        self.login_user(23)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['reason'], 'User does not have access to the tenant (1)')
        tenant_config.refresh_from_db()
        assert DraftConfig.objects.filter(tenant_id=1).count() != 0

        self.login_user(8)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        tenant_config.refresh_from_db()
        assert DraftConfig.objects.filter(tenant_id=1).count() == 0


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestThemeConfigPublishView(DraftConfigDataMixin, BaseTestViewMixin):
    """Tests for ThemeConfigPublishView"""
    VIEW_NAME = 'fx_dashboard:theme-config-publish'

    @patch('futurex_openedx_extensions.dashboard.views.configs.publish_tenant_config')
    def test_success(self, mocked_publish_config):
        """Verify that the view returns the correct response"""
        ConfigAccessControl.objects.create(key_name='platform_name', path='platform_name', key_type='string')
        ConfigAccessControl.objects.create(key_name='pages', path='theme_v2.pages', key_type='list')
        ConfigAccessControl.objects.create(key_name='links', path='theme_v2.links.facebook', key_type='string')
        updated_fields = {'links': {'published_value': 'facebook.com', 'draft_value': 'draft.facebook.com'}}
        expected_return_value = {
            'updated_fields': {
                'links': {'old_value': 'facebook.com', 'new_value': 'draft.facebook.com'}
            }
        }
        payload = {
            'draft_hash': dict_to_hash(updated_fields),
            'tenant_id': 1
        }
        self.login_user(10)
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['reason'], 'User does not have required access for tenant (1)')

        self.login_user(self.staff_user)
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        mocked_publish_config.assert_called_once_with(1)
        self.assertEqual(response.json(), expected_return_value)

    @ddt.data(
        ('does-not-matter', None, 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', [], 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', '', 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', 'non-int', 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', '1', 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        (None, 1, 'Draft hash is required and must be a string.', http_status.HTTP_400_BAD_REQUEST),
        ('', 1, 'Draft hash is required and must be a string.', http_status.HTTP_400_BAD_REQUEST),
        (['not str'], 1, 'Draft hash is required and must be a string.', http_status.HTTP_400_BAD_REQUEST),
        ('invalid_hash', 1, 'Draft hash mismatched with current draft values hash.', http_status.HTTP_400_BAD_REQUEST),
        ('does-bot-matter', 12, 'User does not have required access for tenant (12)', http_status.HTTP_403_FORBIDDEN),
    )
    @ddt.unpack
    def test_validations(self, draft_hash, tenant_id, expected_error, expected_status):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data={
            'draft_hash': draft_hash,
            'tenant_id': tenant_id
        }, format='json')
        self.assertEqual(response.status_code, expected_status)
        self.assertEqual(response.data.get('reason'), expected_error)

    def test_dispatch_is_non_atomic(self):
        """Verify that the view has the correct dispatch method"""
        dispatch_method = ThemeConfigPublishView.dispatch
        is_non_atomic = getattr(dispatch_method, '_non_atomic_requests', False)
        self.assertTrue(
            is_non_atomic,
            'dispatch method should be decorated with non_atomic_requests. atomic is used internally when needed'
        )


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class ThemeConfigRetrieveViewTest(DraftConfigDataMixin, BaseTestViewMixin):
    """Tests for ThemeConfigRetrieveView"""
    VIEW_NAME = 'fx_dashboard:theme-config-values'

    def test_success(self):
        """Verify that the view returns the correct response"""
        ConfigAccessControl.objects.create(key_name='platform_name', path='platform_name', key_type='string')
        ConfigAccessControl.objects.create(key_name='pages', path='theme_v2.pages', key_type='list')
        ConfigAccessControl.objects.create(key_name='links', path='theme_v2.links.facebook', key_type='string')
        self.login_user(self.staff_user)
        params = {
            'tenant_ids': '1',
            'keys': 'platform_name,pages,color,links',
            'published_only': '0'
        }
        response = self.client.get(self.url, data=params)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.json()['values'], {
            'platform_name': 's1 platform name',
            'pages': ['home_page'],
            'links': 'draft.facebook.com',
        })
        self.assertEqual(response.json()['revision_ids'], {
            'links': '88776655',
            'pages': '0',
            'platform_name': '0',
        })

        params['published_only'] = '1'
        response = self.client.get(self.url, data=params)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.json()['values'], {
            'platform_name': 's1 platform name',
            'pages': ['home_page'],
            'links': 'facebook.com',
        })
        self.assertEqual(response.json()['revision_ids'], {})

    def test_one_tenant(self):
        """Verify that ThemeConfigRetrieveView calls verify_one_tenant_id_provided."""
        self.login_user(8)
        with patch(
            'futurex_openedx_extensions.dashboard.views.configs.ThemeConfigRetrieveView.verify_one_tenant_id_provided'
        ) as mock_verify_one_tenant:
            mock_verify_one_tenant.return_value = 1
            response = self.client.get(self.url, data={
                'tenant_ids': '1',
                'keys': '',
            })
            mock_verify_one_tenant.assert_called_once()
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class ThemeConfigTenantView(BaseTestViewMixin):
    """Tests for ThemeConfigTenantView"""
    VIEW_NAME = 'fx_dashboard:theme-config-tenant'

    @ddt.data(
        (
            {'owner_user_id': None},
            'Subdomain is required.'
        ),
        (
            {'sub_domain': ['non', 'string'], 'owner_user_id': 1},
            'Subdomain must be a string.'
        ),
        (
            {'sub_domain': 'invalid_domain$', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': '-startwithhyphen', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': '1startwithnumber', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': 'domain space', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': '$pecial_chars!', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': 'domain@domain', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': 'LongString17Chars'},
            'Subdomain cannot exceed 16 characters.'
        ),
        (
            {'sub_domain': 'validsubdomain'},
            'Platform name is required.'
        ),
        (
            {'sub_domain': 'validsubdomain', 'platform_name': 11},
            'Platform name must be a string.'
        ),
        (
            {'sub_domain': 'validsubdomain', 'platform_name': 'Valid name', 'owner_user_id': 999999},
            'User with ID 999999 does not exist.'
        ),
    )
    @ddt.unpack
    def test_payload_validation(self, data, expected_reason):
        """Verify that different sub_domain cases raise the correct reason"""
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, HTTP_400_BAD_REQUEST)
        assert response.data['reason'] == expected_reason

    @pytest.mark.django_db
    @patch('futurex_openedx_extensions.helpers.tenants.generate_tenant_config')
    @patch('futurex_openedx_extensions.dashboard.views.configs.add_course_access_roles')
    @ddt.data(True, False)
    def test_success(self, owner_id_passed, mock_add_course_access_roles, mock_generate_config):
        """Verify that the view returns the correct response"""
        mock_generate_config.return_value = {
            'LMS_BASE': 'testplatform.local.overhang.io:8000',
            'SITE_NAME': 'http://testplatform.local.overhang.io:8000/',
            'course_org_filter': ['testplatform_org'],
        }
        self.login_user(self.staff_user)
        data = {
            'sub_domain': 'testplatform',
            'platform_name': 'Test Platform'
        }
        if owner_id_passed:
            data['owner_user_id'] = self.staff_user
        response = self.client.post(self.url, data=data, format='json')
        if owner_id_passed:
            mock_add_course_access_roles.assert_called_once()
        else:
            mock_add_course_access_roles.assert_not_called()
        assert response.status_code == http_status.HTTP_200_OK
        result = response.json()
        assert result['tenant_id'] > 0
        result.pop('tenant_id')
        assert result == {
            'lms_root_url': 'https://testplatform.local.overhang.io',
            'logo_image_url': '',
            'platform_name': '',
            'studio_root_url': 'https://studio.example.com',
        }


@ddt.ddt
class TestSetThemePreviewCookieView(APITestCase):
    """Tests for SetThemePreviewCookieView"""
    def setUp(self):
        """Initialize the test case"""
        self.url = reverse('fx_dashboard:set-theme-preview')

    def test_redirect_when_cookie_present(self):
        """Verify that the view redirects if the theme-preview cookie is set to 'yes'."""
        self.client.cookies['theme-preview'] = 'yes'
        response = self.client.get(self.url)
        assert response.status_code == 302, 'Expected redirect when theme-preview cookie is set'

    def test_render_template_when_cookie_absent(self):
        """Verify that the view renders the set_theme_preview.html template if no theme-preview cookie is set."""
        response = self.client.get(self.url)
        assert response.status_code == 200, 'Expected status 200 when theme-preview cookie is not set'
        assert 'set_theme_preview.html' in [t.name for t in response.templates], 'Expected template to be rendered'

    @ddt.data(
        ('/custom-next-url/', '/custom-next-url/'),
        (None, f'http://testserver{reverse("fx_dashboard:set-theme-preview")}')
    )
    @ddt.unpack
    def test_redirect_url_resolves_correctly(self, next_param, expected_redirect):
        """Verify that the view correctly resolves the next URL parameter for redirection."""
        params = {'next': next_param} if next_param else {}
        self.client.cookies['theme-preview'] = 'yes'
        response = self.client.get(self.url, params)
        assert response.url == expected_redirect, f'Expected redirect to {expected_redirect}'
