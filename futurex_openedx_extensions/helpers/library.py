"""Library helpers."""
from xmodule.modulestore.django import modulestore

from futurex_openedx_extensions.helpers.extractors import get_partial_access_course_ids


def get_accessible_libraries(fx_permission_info: dict, search_text: str = None) -> list:
    """Get list of accessible libraries"""
    libraries = modulestore().get_libraries()
    course_ids_with_partial_access = get_partial_access_course_ids(fx_permission_info, include_libraries=True)
    return [
        library for library in libraries
        if (
            (library.location.library_key.org in fx_permission_info['view_allowed_full_access_orgs']) or
            (
                library.location.library_key.org in fx_permission_info['view_allowed_course_access_orgs'] and
                str(library.location.library_key) in course_ids_with_partial_access
            )
        ) and (not search_text or search_text.lower() in library.display_name.lower())
    ]
