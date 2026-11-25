"""Tests for the learner theme views"""
from unittest.mock import patch

import ddt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from eox_tenant.models import TenantConfig
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.models import CourseLearnerMeta
from tests.test_dashboard.test_mixins import BaseTestViewMixin

SITE_MIDDLEWARE = settings.MIDDLEWARE + ('django.contrib.sites.middleware.CurrentSiteMiddleware',)
# Open edX signs in users whose account is not activated yet (its backend is an AllowAllUsersModelBackend)
ALLOW_INACTIVE_BACKENDS = ['django.contrib.auth.backends.AllowAllUsersModelBackend']


@override_settings(ALLOWED_HOSTS=['*'], MIDDLEWARE=SITE_MIDDLEWARE)
@pytest.mark.usefixtures('base_data')
class LearnerThemeViewMixin(BaseTestViewMixin):
    """Requests are served on a tenant's site, like the LMS does (CurrentSiteMiddleware)"""

    def get(self, host='s1.sample.com'):
        """GET the view on the given host"""
        return self.client.get(self.url, HTTP_HOST=host)

    def get_unknown_site(self):
        """GET the view on a site that exists but serves no tenant"""
        Site.objects.get_or_create(domain='unknown.sample.com', name='unknown')
        return self.get(host='unknown.sample.com')

    def login_inactive_user(self, user_id):
        """Sign in a user whose account is not activated"""
        get_user_model().objects.filter(id=user_id).update(is_active=False)
        self.login_user(user_id)


class TestLearnerThemeShellView(LearnerThemeViewMixin):
    """Tests for LearnerThemeShellView"""
    VIEW_NAME = 'fx_dashboard:learner-theme-shell'

    def test_anonymous_success(self):
        """Verify the shell is public and uses the tenant of the request's site"""
        tenant = TenantConfig.objects.get(id=3)
        tenant.lms_configs['theme_v2'] = {'entity_identity': {'short_name': {'ar': 'ث', 'en': 'Three'}}}
        tenant.save()

        response = self.get(host='s3.sample.com')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['short_name'], {'ar': 'ث', 'en': 'Three'})
        self.assertEqual(set(response.data), {
            'active', 'logo_url', 'brand_color', 'site_name', 'short_name', 'parent_org', 'nav', 'footer', 'help_url',
            'languages', 'default_language', 'urls',
        })
        default_shell = self.get().data
        self.assertEqual(default_shell['short_name'], default_shell['site_name'])
        self.assertTrue(all(default_shell['short_name'].values()))

    def test_unknown_site(self):
        """Verify a site that is not a tenant gets 404"""
        response = self.get_unknown_site()
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_tenant_without_config(self):
        """Verify a tenant whose config disappeared gets 404"""
        with patch('futurex_openedx_extensions.dashboard.views.learner_theme.get_learner_theme_shell', return_value={}):
            response = self.get()
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)


@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
class TestLearnerThemeCatalogView(LearnerThemeViewMixin):
    """Tests for LearnerThemeCatalogView"""
    VIEW_NAME = 'fx_dashboard:learner-theme-catalog'

    def test_anonymous_tenant_isolation(self, _):
        """Verify the catalogue is public and holds the request tenant's courses only"""
        response = self.get(host='s3.sample.com')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'results', 'categories'})
        self.assertEqual([item['id'] for item in response.data['results']], ['course-v1:ORG4+1+1'])
        self.assertFalse(response.data['results'][0]['enrolled'])

    def test_enrolled_flag_for_signed_in_user(self, _):
        """Verify `enrolled` reflects the signed-in user's own enrollments"""
        self.login_user(15)
        response = self.get(host='s3.sample.com')
        self.assertTrue(response.data['results'][0]['enrolled'])

    def test_about_only_course_not_listed(self, _):
        """Verify a course hidden from the catalogue (visibility `about`) is not returned to the public"""
        CourseOverview.objects.filter(id='course-v1:ORG4+1+1').update(catalog_visibility='about')
        response = self.get(host='s3.sample.com')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['results'], [])

    def test_unknown_site(self, _):
        """Verify a site that is not a tenant gets 404"""
        self.assertEqual(self.get_unknown_site().status_code, http_status.HTTP_404_NOT_FOUND)

    @pytest.mark.usefixtures('cache_testing')
    def test_cached_per_tenant_with_live_enrolled(self, _):
        """Verify the cached catalogue stays on its tenant's host and `enrolled` is the caller's own, never cached"""
        self.login_user(15)
        enrolled_response = self.get(host='s3.sample.com')
        self.client.logout()
        anonymous_response = self.get(host='s3.sample.com')
        other_tenant_response = self.get(host='s1.sample.com')

        self.assertEqual([item['id'] for item in enrolled_response.data['results']], ['course-v1:ORG4+1+1'])
        self.assertTrue(enrolled_response.data['results'][0]['enrolled'])
        self.assertEqual([item['id'] for item in anonymous_response.data['results']], ['course-v1:ORG4+1+1'])
        self.assertFalse(anonymous_response.data['results'][0]['enrolled'])
        self.assertNotIn('course-v1:ORG4+1+1', [item['id'] for item in other_tenant_response.data['results']])
        self.assertEqual(len(other_tenant_response.data['results']), 12)
        self.assertEqual(
            [key for key in anonymous_response.data['results'][0] if key != 'enrolled'],
            list(cache.get('fx_learner_theme_catalog_3')['data']['results'][0]),
        )

    @pytest.mark.usefixtures('cache_testing')
    def test_meta_write_clears_the_cached_catalogue(self, _):
        """Verify a level / learning mode written through courses/v1/meta shows in the catalogue at once"""
        def _level():
            return {item['id']: item['level'] for item in self.get().data['results']}['course-v1:ORG1+3+3']

        self.assertIsNone(_level())
        CourseOverview.objects.filter(id='course-v1:ORG1+3+3').update(display_name='Edited in Studio')
        self.assertNotIn('Edited in Studio', [item['title'] for item in self.get().data['results']])

        self.login_user(3)
        response = self.client.put(
            reverse('fx_dashboard:courses-course-meta', args=['course-v1:ORG1+3+3']),
            data={'level': 'advanced', 'learning_mode': 'self_paced'},
            format='json',
            HTTP_HOST='s1.sample.com',
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.client.logout()

        self.assertEqual(_level(), 'advanced')
        self.assertIn('Edited in Studio', [item['title'] for item in self.get().data['results']])


class TestLearnerThemeMyProgramsView(LearnerThemeViewMixin):
    """Tests for LearnerThemeMyProgramsView"""
    VIEW_NAME = 'fx_dashboard:learner-theme-programs'

    def test_anonymous(self):
        """Verify sign-in is required"""
        self.assertIn(self.get().status_code, [http_status.HTTP_401_UNAUTHORIZED, http_status.HTTP_403_FORBIDDEN])

    @patch('futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data', return_value={})
    def test_own_data_of_the_request_tenant_only(self, _):
        """Verify the user gets their own enrollments, limited to the request host's tenant"""
        self.login_user(15)

        tenant1 = self.get().data
        tenant3 = self.get(host='s3.sample.com').data

        self.assertEqual(set(tenant1), {'user', 'stats', 'resume', 'results'})
        self.assertEqual(set(tenant1['user']), {'full_name', 'first_name', 'arabic_name', 'masked_email'})
        self.assertNotIn('user15', str(tenant1['user']))
        self.assertEqual(
            sorted(item['course_id'] for item in tenant1['results']),
            ['course-v1:ORG1+5+5', 'course-v1:ORG2+7+7'],
        )
        self.assertEqual([item['course_id'] for item in tenant3['results']], ['course-v1:ORG4+1+1'])
        self.assertEqual(set(tenant1['results'][0]), {
            'course_id', 'title', 'image_url', 'progress_percent', 'next_step', 'pass_grade_percent', 'resume_url',
            'completed', 'certificate_url',
        })

    @override_settings(AUTHENTICATION_BACKENDS=ALLOW_INACTIVE_BACKENDS)
    @patch('futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data', return_value={})
    def test_inactive_user_gets_own_programs(self, _):
        """Verify a signed-in user whose account is not activated gets their programs, like the stock learner home"""
        self.login_inactive_user(15)

        response = self.get(host='s3.sample.com')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual([item['course_id'] for item in response.data['results']], ['course-v1:ORG4+1+1'])

    def test_unknown_site(self):
        """Verify a site that is not a tenant gets 404"""
        self.login_user(15)
        self.assertEqual(self.get_unknown_site().status_code, http_status.HTTP_404_NOT_FOUND)


class TestLearnerThemeMyCertificatesView(LearnerThemeViewMixin):
    """Tests for LearnerThemeMyCertificatesView"""
    VIEW_NAME = 'fx_dashboard:learner-theme-certificates'

    def test_anonymous(self):
        """Verify sign-in is required"""
        self.assertIn(self.get().status_code, [http_status.HTTP_401_UNAUTHORIZED, http_status.HTTP_403_FORBIDDEN])

    def test_own_certificates_of_the_request_tenant_only(self):
        """Verify the certificates API is asked for the signed-in user and the request tenant's courses only"""
        self.login_user(15)
        with patch(
            'futurex_openedx_extensions.helpers.learner_theme.get_certificates_for_user_by_course_keys',
            return_value={CourseKey.from_string('course-v1:ORG4+1+1'): {
                'status': 'downloadable', 'download_url': '/certificates/u1', 'uuid': 'u1', 'grade': '0.8',
                'created': None,
            }},
        ) as mock_api:
            response = self.get(host='s3.sample.com')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(mock_api.call_args.args[0].id, 15)
        self.assertEqual([str(key) for key in mock_api.call_args.args[1]], ['course-v1:ORG4+1+1'])
        self.assertEqual(response.data, [{
            'course_id': 'course-v1:ORG4+1+1',
            'title': 'Course 1 of ORG4',
            'issuer': '',
            'issued_at': None,
            'grade_percent': 80,
            'verify_code': 'u1',
            'preview_url': 'http://s3.sample.com/certificates/u1',
            'download_url': 'http://s3.sample.com/certificates/u1',
            'verify_url': 'http://s3.sample.com/certificates/u1',
        }])

    @override_settings(AUTHENTICATION_BACKENDS=ALLOW_INACTIVE_BACKENDS)
    def test_inactive_user_gets_own_certificates(self):
        """Verify a signed-in user whose account is not activated gets their certificates"""
        self.login_inactive_user(15)
        with patch(
            'futurex_openedx_extensions.helpers.learner_theme.get_certificates_for_user_by_course_keys',
            return_value={CourseKey.from_string('course-v1:ORG4+1+1'): {
                'status': 'downloadable', 'download_url': '/certificates/u1', 'uuid': 'u1', 'grade': '0.8',
                'created': None,
            }},
        ) as mock_api:
            response = self.get(host='s3.sample.com')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(mock_api.call_args.args[0].id, 15)
        self.assertEqual([item['course_id'] for item in response.data], ['course-v1:ORG4+1+1'])

    def test_unknown_site(self):
        """Verify a site that is not a tenant gets 404"""
        self.login_user(15)
        self.assertEqual(self.get_unknown_site().status_code, http_status.HTTP_404_NOT_FOUND)


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestCourseLearnerMetaView(BaseTestViewMixin):
    """Tests for CourseLearnerMetaView"""
    VIEW_NAME = 'fx_dashboard:courses-course-meta'

    def setUp(self):
        """Point the URL at a course of tenant 1"""
        super().setUp()
        self.url_args = ['course-v1:ORG1+3+3']

    def test_unauthorized(self):
        """Verify sign-in is required"""
        self.assertEqual(self.client.get(self.url).status_code, http_status.HTTP_403_FORBIDDEN)

    def test_get_and_put(self):
        """Verify a tenant staff user reads and sets the course meta"""
        self.login_user(3)
        self.assertEqual(self.client.get(self.url).data, {'level': None, 'learning_mode': None})

        response = self.client.put(self.url, data={'level': 'advanced', 'learning_mode': 'self_paced'}, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data, {'level': 'advanced', 'learning_mode': 'self_paced'})
        record = CourseLearnerMeta.objects.get(course_key=CourseKey.from_string('course-v1:ORG1+3+3'))
        self.assertEqual(record.updated_by_id, 3)
        self.assertEqual(self.client.get(self.url).data, {'level': 'advanced', 'learning_mode': 'self_paced'})

        response = self.client.put(self.url, data={'level': None, 'learning_mode': None}, format='json')
        self.assertEqual(response.data, {'level': None, 'learning_mode': None})

    @ddt.data(
        {'level': 'expert', 'learning_mode': None},
        {'level': 'basic', 'learning_mode': 'online'},
        {'level': 'basic'},
        {},
    )
    def test_put_invalid(self, payload):
        """Verify invalid values are rejected"""
        self.login_user(3)
        response = self.client.put(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CourseLearnerMeta.objects.exists())

    @ddt.data('get', 'put')
    def test_course_of_another_tenant(self, method):
        """Verify a course outside the caller's tenants can be neither read nor written"""
        self.login_user(3)
        self.url_args = ['course-v1:ORG4+1+1']
        CourseLearnerMeta.set_meta(
            CourseKey.from_string('course-v1:ORG4+1+1'), level='basic', learning_mode='blended', user=None,
        )

        if method == 'put':
            response = self.client.put(self.url, data={'level': 'advanced', 'learning_mode': None}, format='json')
        else:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertIn('Course not found or access denied', response.data['reason'])
        self.assertEqual(
            CourseLearnerMeta.get_meta(CourseKey.from_string('course-v1:ORG4+1+1')),
            {'level': 'basic', 'learning_mode': 'blended'},
        )

    def test_system_staff_any_tenant(self):
        """Verify system staff can set the meta of any tenant's course"""
        self.login_user(self.staff_user)
        self.url_args = ['course-v1:ORG4+1+1']
        response = self.client.put(self.url, data={'level': 'basic', 'learning_mode': 'blended'}, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
