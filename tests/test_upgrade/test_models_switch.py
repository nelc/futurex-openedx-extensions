"""Tests for models_switch module"""


def test_models_switch():
    """Test that the models switch is correct"""
    from futurex_openedx_extensions.upgrade.models_switch import ( \
        # pylint: disable=unused-import, import-outside-toplevel
        CourseAccessRole,
    )
    assert True, 'just verifying that the import works with no problems within the test environment'
