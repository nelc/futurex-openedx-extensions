"""Tests for the course certificates view"""
from unittest.mock import patch

import ddt
from opaque_keys.edx.keys import CourseKey
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from tests.test_dashboard.test_mixins import BaseTestViewMixin

COURSE_ID = 'course-v1:ORG1+3+3'


@ddt.ddt
class TestCourseCertificatesView(BaseTestViewMixin):
    """Tests for CourseCertificatesView"""
    VIEW_NAME = 'fx_dashboard:courses-course-certificates'

    def setUp(self):
        """Ensure URL points to a specific course"""
        super().setUp()
        self.url_args = [COURSE_ID]

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.put(self.url, data={'enabled': 1}, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @ddt.data((1, True), (0, False))
    @ddt.unpack
    def test_put_success(self, payload_value, expected_enabled):
        """Verify that PUT enables or disables the course certificates"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.courses.enable_course_certificates') as mock_enable, \
                patch('futurex_openedx_extensions.dashboard.views.courses.disable_course_certificates') as mock_disable:
            response = self.client.put(self.url, data={'enabled': payload_value}, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data, {'course_id': COURSE_ID, 'enabled': expected_enabled})
        called, not_called = (mock_enable, mock_disable) if expected_enabled else (mock_disable, mock_enable)
        called.assert_called_once()
        self.assertEqual(called.call_args.args[0], CourseKey.from_string(COURSE_ID))
        self.assertEqual(called.call_args.args[1].id, self.staff_user)
        not_called.assert_not_called()

    @ddt.data({}, {'enabled': 'maybe'})
    def test_put_invalid_payload(self, payload):
        """Verify that PUT returns 400 for a missing or invalid enabled value"""
        self.login_user(self.staff_user)
        response = self.client.put(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('enabled', response.data)

    def test_put_course_not_found(self):
        """Verify that PUT returns 404 when course is not found or not accessible"""
        self.login_user(self.staff_user)
        self.url_args = ['course-v1:INVALID+999+999']
        response = self.client.put(self.url, data={'enabled': 1}, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        assert 'Course not found or access denied' in str(response.data.get('reason'))

    @ddt.data(
        (FXExceptionCodes.COURSE_CERTIFICATE_TEMPLATE_NOT_FOUND, http_status.HTTP_409_CONFLICT),
        (FXExceptionCodes.COURSE_CERTIFICATE_COURSE_NOT_FOUND, http_status.HTTP_400_BAD_REQUEST),
    )
    @ddt.unpack
    def test_put_enable_failure(self, error_code, expected_status):
        """Verify that PUT maps enabling failures to the right status code"""
        self.login_user(self.staff_user)
        with patch(
            'futurex_openedx_extensions.dashboard.views.courses.enable_course_certificates',
            side_effect=FXCodedException(code=error_code, message='failure details'),
        ):
            response = self.client.put(self.url, data={'enabled': 1}, format='json')

        self.assertEqual(response.status_code, expected_status)
        self.assertEqual(response.data['reason'], f'({error_code.value}) failure details')
