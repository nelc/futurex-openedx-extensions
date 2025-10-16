"""Helpers for generating Swagger documentation for the FutureX Open edX Extensions API."""
# pylint: disable=too-many-lines
from __future__ import annotations

from typing import Any, Dict, List

from django.conf import settings
from drf_yasg import openapi
from edx_api_doc_tools import ParameterLocation, path_parameter, query_parameter

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.helpers.extractors import (
    get_available_optional_field_tags,
    get_available_optional_field_tags_docs_table,
)

default_responses = {
    200: 'Success.',
    400: openapi.Response(
        description='Bad request. Details in the response body.',
        schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'detail': openapi.Schema(type=openapi.TYPE_OBJECT),
                'reason': openapi.Schema(type=openapi.TYPE_STRING),
            },
            example={
                'reason': 'Invalid course ID format: aaa-v1:course1',
                'detail': {},
            }
        ),
    ),
    404: openapi.Response(
        description='Resource not found, or not accessible to the user.',
        schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'detail': openapi.Schema(type=openapi.TYPE_OBJECT),
                'reason': openapi.Schema(type=openapi.TYPE_STRING),
            },
            example={
                'detail': 'Not found',
            }
        ),
    ),
    403: openapi.Response(
        description='Forbidden access. Details in the response body.',
        schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'detail': openapi.Schema(type=openapi.TYPE_OBJECT),
                'reason': openapi.Schema(type=openapi.TYPE_STRING),
            },
            example={
                'reason': 'Invalid tenant IDs provided',
                'detail': {
                    'tenant_ids': [
                        '10000'
                    ]
                },
            }
        ),
    ),
}


def responses(
    overrides: Dict[int, str] | None = None,
    remove: List[int] | None = None,
    success_description: str = None,
    success_schema: Any = None,
    success_examples: Any = None,
) -> Dict[int, str]:
    """
    Generate responses for the API endpoint.

    :param overrides: Optional overrides for the default responses.
    :type overrides: dict
    :param remove: Optional list of status codes to remove from the default responses.
    :type remove: list
    :param success_description: Optional success description to add to the 200 response.
    :type success_description: str
    :param success_schema: Optional success schema to add to the 200 response.
    :type success_schema: any
    :param success_examples: Optional success examples to add to the 200 response.
    :type success_examples: any
    :return: Responses for the API endpoint.
    :rtype: dict
    """
    result = {**default_responses, **(overrides or {})}
    if remove:
        for status_code in remove:
            result.pop(status_code, None)
    if success_description or success_schema or success_examples:
        result[200] = openapi.Response(
            description=f'Success. {success_description or ""}',
            schema=success_schema,
            examples=success_examples,
        )
    return result


def get_optional_parameter(path: str) -> Any:
    """
    Get optional_field_tags parameter with given path
    """
    return openapi.Parameter(
        'optional_field_tags',
        ParameterLocation.QUERY,
        required=False,
        type=openapi.TYPE_STRING,
        enum=list(get_available_optional_field_tags(path).keys()),
        description=repeated_descriptions['optional_field_tags'] + get_available_optional_field_tags_docs_table(path)
    )


common_parameters = {
    'include_staff': openapi.Parameter(
        'include_staff',
        ParameterLocation.QUERY,
        required=False,
        type=openapi.TYPE_INTEGER,
        enum=[1, 0],
        description=(
            'include staff users in the result `1` or `0`. Default is `0`. Any value other than `1` is considered'
            ' as `0`. A staff user is any user who has a role within the tenant.'
        )
    ),
    'download': openapi.Parameter(
        'download',
        ParameterLocation.QUERY,
        required=False,
        type=openapi.TYPE_STRING,
        enum=['csv'],
        description=(
            'Trigger a data export task for the results. Currently only `download=csv` is supported. The response'
            ' will no longer be a list of objects, but a JSON object with `export_task_id` field. Then the'
            ' `export_task_id` can be used with the `/fx/export/v1/tasks/` endpoints.\n'
            '\n**Note:** this parameter will disable pagination options `page` and `page_size`. Therefore, the'
            ' exported CSV will contain all the result\'s records.'
        )
    ),
    'tenant_ids': query_parameter(
        'tenant_ids',
        str,
        'a comma separated list of tenant ids to filter the results by. If not provided, the system will assume all'
        ' tenants that are accessible to the user.',
    ),
    'omit_subsection_name': openapi.Parameter(
        'omit_subsection_name',
        ParameterLocation.QUERY,
        required=False,
        type=openapi.TYPE_INTEGER,
        enum=['1', '0'],
        description=(
            'Omit the subsection name from the response. Can be `0` or `1`. This is useful when `exam_scores`'
            ' optional fields are requested; it\'ll omit the subsection names for cleaner representation of the'
            ' data. Default is `0`. Any value other than `1` is considered as `0`.'
        )
    ),
}

common_path_parameters = {
    'username-learner': path_parameter(
        'username',
        str,
        'The username of the learner to retrieve information for.',
    ),
    'username-staff': path_parameter(
        'username',
        str,
        'The username of the staff user to retrieve information for.',
    ),
    'tenant_id': path_parameter(
        'tenant_id',
        int,
        'The id of the tenant to retrieve or update config for.',
    ),
}

repeated_descriptions = {
    'roles_overview': '\nCategories of roles:\n'
    '-----------------------------------------------------\n'
    '| Role ID | Available in GET | Can be edited | Role level |\n'
    '|---------|------------------|---------------|------|\n'
    '| course_creator_group     | Yes | No  | global role |\n'
    '| support                  | Yes | No  | global role |\n'
    '| org_course_creator_group | Yes | Yes | tenant-wide only |\n'
    '| beta_testers             | Yes | Yes | course-specific only |\n'
    '| ccx_coach                | Yes | Yes | course-specific only |\n'
    '| finance_admin            | Yes | Yes | course-specific only |\n'
    '| staff                    | Yes | Yes | tenant-wide or course-specific |\n'
    '| data_researcher          | Yes | Yes | tenant-wide or course-specific |\n'
    '| instructor               | Yes | Yes | tenant-wide or course-specific |\n'
    '-----------------------------------------------------\n'
    '\nThe above table shows the available roles, their availability in the GET response, if they can be edited,'
    ' and the role level.\n'
    '\n**Security note**: having access to this endpoint does not mean the caller can assign any role to any user.'
    ' When using edit-role APIs; caller must be a `staff` or `org_course_creator_group` on the tenant:\n'
    '* System-staff/Superuser can do all operations (obviously!)\n'
    '* Tenant `staff` can do all operations except removing **tenant-wide** `staff` role from a user (including self)\n'
    '* `org_course_creator_group` can do all operations on the **course-level**, not the **tenant-level**. For'
    ' example, she can add `staff` role for another user on one course, but cannot add it as **tenant-wide**.'
    ' She can also remove **course-specific** roles from users, but cannot remove **tenant-wide** roles from any'
    ' user (including self)',

    'visible_course_definition': '\n**Note:** A *visible course* is the course with `Course Visibility In Catalog`'
    ' value set to `about` or `both`; and `visible_to_staff_only` is set to `False`. Courses are visible by default'
    ' when created.',

    'optional_field_tags': 'Optional fields are not included in the response by default. Caller can request them by'
    ' using the `optional_field_tags` parameter. It accepts a comma-separated list of optional field tags. The'
    ' following are the available tags along with the fields they include:\n'
    '| tag | mapped fields |\n'
    '|-----|---------------|\n'
}

common_schemas = {
    'role': openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'user_id': openapi.Schema(
                type=openapi.TYPE_INTEGER,
            ),
            'email': openapi.Schema(
                type=openapi.TYPE_STRING,
            ),
            'username': openapi.Schema(
                type=openapi.TYPE_STRING,
            ),
            'national_id': openapi.Schema(
                type=openapi.TYPE_STRING,
            ),
            'full_name': openapi.Schema(
                type=openapi.TYPE_STRING,
            ),
            'alternative_full_name': openapi.Schema(
                type=openapi.TYPE_STRING,
            ),
            'global_roles': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_STRING,
                ),
                example=['support', 'staff']
            ),
            'tenants': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                additional_properties=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'tenant_roles': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_STRING,
                            ),
                            example=['support']
                        ),
                        'course_roles': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            additional_properties=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                ),
                            ),
                            example={
                                'course-v1:nelp_org+222+22': ['staff']
                            }
                        ),
                    }
                )
            ),
            'is_system_staff': openapi.Schema(
                type=openapi.TYPE_BOOLEAN,
                example=False
            ),
        },
        example={
            'user_id': 13,
            'email': 'user1@example.com',
            'username': 'user1',
            'national_id': '12345',
            'full_name': 'user1',
            'alternative_full_name': 'عالي',
            'global_roles': [],
            'tenants': {
                '4': {
                    'tenant_roles': ['support'],
                    'course_roles': {
                        'course-v1:nelp_org+222+22': ['staff']
                    }
                }
            },
            'is_system_staff': False
        }
    )
}

docs_src = {
    'AccessibleTenantsInfoView.get': {
        'summary': 'Get information about accessible tenants for a user',
        'description': 'Get information about accessible tenants for a user. The caller must be a staff user or an'
        ' anonymous user. \n**Note:** This API will be deprecated and removed in version: v0.11.0.1.\n',
        'parameters': [
            query_parameter(
                'username_or_email',
                str,
                '(**required**) The username or email of the user to retrieve the accessible tenants for.'
            ),
        ],
        'responses': responses(
            success_description='The response is a JSON of the accessible tenant IDs as keys, and the tenant\'s'
            ' information as values.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='The tenant ID',
                additional_properties=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'lms_root_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The LMS root URL of the tenant',
                        ),
                        'studio_root_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The Studio root URL of the tenant',
                        ),
                        'platform_name': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The platform name of the tenant',
                        ),
                        'logo_image_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The logo image URL of the tenant',
                        )
                    },
                ),
            ),
            success_examples={
                'application/json': {
                    '1': {
                        'lms_root_url': 'https://heroes.lms.com',
                        'studio_root_url': 'https://studio.lms.com',
                        'platform_name': 'Heroes Academy',
                        'logo_image_url': 'https://www.s3.com/logo.png',
                    },
                    '4': {
                        'lms_root_url': 'https://monsters.lms.com',
                        'studio_root_url': 'https://studio.lms.com',
                        'platform_name': 'Monsters Academy',
                        'logo_image_url': 'https://www.s3.com/logo.png',
                    },
                },
            },
            remove=[404]
        ),
    },

    'AccessibleTenantsInfoViewV2.get': {
        'summary': 'Get information about accessible tenants for a user (version-2)',
        'description': 'Get information about accessible tenants for a user. The caller must have system-staff access,'
        ' but this API is essentially used in Server-to-Server communication',
        'parameters': [
            query_parameter(
                'username_or_email',
                str,
                '(**required**) The username or email of the user to retrieve the accessible tenants for.'
            ),
        ],
        'responses': responses(
            success_description='The response is a JSON of the accessible tenant IDs as keys, and the tenant\'s'
            ' information as values.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='The tenant ID',
                additional_properties=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'lms_root_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The LMS root URL of the tenant',
                        ),
                        'studio_root_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The Studio root URL of the tenant',
                        ),
                        'platform_name': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The platform name of the tenant',
                        ),
                        'logo_image_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='The logo image URL of the tenant',
                        )
                    },
                ),
            ),
            success_examples={
                'application/json': {
                    '1': {
                        'lms_root_url': 'https://heroes.lms.com',
                        'studio_root_url': 'https://studio.lms.com',
                        'platform_name': 'Heroes Academy',
                        'logo_image_url': 'https://www.s3.com/logo.png',
                    },
                    '4': {
                        'lms_root_url': 'https://monsters.lms.com',
                        'studio_root_url': 'https://studio.lms.com',
                        'platform_name': 'Monsters Academy',
                        'logo_image_url': 'https://www.s3.com/logo.png',
                    },
                },
            },
            remove=[404]
        ),
    },

    'CourseStatusesView.get': {
        'summary': 'Get number of courses of each status in the tenants',
        'description': 'The response will include the number of courses in the selected tenants for each status. See'
        ' details in the 200 response description below.\n'
        '\n**Note:** the count includes only visible courses.\n'
        f'{repeated_descriptions["visible_course_definition"]}',
        'parameters': [
            common_parameters['tenant_ids'],
        ],
        'responses': responses(
            success_description='The response is a JSON object with the status as the key, and the count as the value.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'self_active': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Number of self-paced active courses',
                    ),
                    'self_archived': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Number of self-paced archived courses',
                    ),
                    'self_upcoming': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Number of self-paced upcoming courses',
                    ),
                    'active': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Number of instructor-paced active courses',
                    ),
                    'archived': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Number of instructor-paced archived courses',
                    ),
                    'upcoming': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Number of instructor-paced upcoming courses',
                    ),
                },
            ),
            success_examples={
                'application/json': {
                    'self_active': 5,
                    'self_archived': 3,
                    'self_upcoming': 1,
                    'active': 2,
                    'archived': 0,
                    'upcoming': 0,
                },
            },
        ),
    },

    'CoursesView.get': {
        'summary': 'Get the list of courses in the tenants',
        'description': 'Get the list of courses in the tenants. Which is the list of all courses available in the'
        ' selected tenants regardless of their visibility.\n'
        f'{repeated_descriptions["visible_course_definition"]}',
        'parameters': [
            common_parameters['tenant_ids'],
            query_parameter(
                'search_text',
                str,
                'a search text to filter the results by. The search text will be matched against the course\'s ID and'
                ' display name.',
            ),
            openapi.Parameter(
                'sort',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_STRING,
                enum=[
                    'display_name', 'id', 'self_paced', 'org', 'enrolled_count', 'certificates_count',
                    'completeion_rate', '-display_name', '-id', '-self_paced', '-org', '-enrolled_count',
                    '-certificates_count', '-completeion_rate',
                ],
                description=(
                    'Which field to use when ordering the results. Available fields are:\n'
                    '- `display_name`: (**default**) course display name.\n'
                    '- `id`: course ID.\n'
                    '- `self_paced`: course self-paced status.\n'
                    '- `org`: course organization.\n'
                    '- `enrolled_count`: course enrolled learners count.\n'
                    '- `certificates_count`: course issued certificates count.\n'
                    '- `completion_rate`: course completion rate.\n'
                    '\nAdding a dash before the field name will reverse the order. For example, `-display_name`'
                    ' will sort the results by the course display name in descending order.'
                )
            ),
            common_parameters['include_staff'],
            common_parameters['download'],
        ],
        'responses': responses(
            overrides={
                200: serializers.CourseDetailsSerializer(read_only=True, required=False),

            },
            remove=[400]
        ),
    },

    'CoursesView.post': {
        'summary': 'Create a new course',
        'description': 'Create new Course. This API will use default org of given tenant as library org '
        'and will raise errors if default org is invalid or unset',
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'tenant_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Tenant id',
                    example=1,
                ),
                'number': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Number',
                    example='class1',
                ),
                'run': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Run',
                    example='summer2025',
                ),
                'display_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Name of the course',
                    example='my test course',
                ),
                'start': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Course start date',
                    example='2025-02-05T00:00:00Z',
                ),
                'end': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Course end date',
                    example='2028-02-05T23:59:59Z',
                ),
                'enrollment_start': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Enrollment start date',
                    example='2025-02-05T23:59:59Z',
                ),
                'enrollment_end': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Enrollment end date',
                    example='2025-02-05T23:59:59Z',
                ),
                'instructor_paced': openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description='True means the course is instructor-paced, False means it is self-paced',
                    example=True,
                ),
                'invitation_only': openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description='True means the course enrollment is invitation-only, False means it is open for all',
                    example=True,
                ),
                'language': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Language code of the course, e.g., "en" for English',
                    example='ar',
                ),
            },
            required=['tenant_id', 'number', 'run']
        ),
        'responses': responses(
            overrides={
                201: openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'course_key': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='Created course id',
                        ),
                    },
                ),
                400: 'Unable to create course. The response will include a JSON object with the error message.',
            },
            remove=[200, 404],
        ),
    },

    'LibraryView.get': {
        'summary': 'Get the list of libraries in the tenants',
        'description': 'Get the list of libraries in the tenants.',
        'parameters': [
            common_parameters['tenant_ids'],
            query_parameter(
                'search_text',
                str,
                'a search text to filter the results by. The search text will be matched against the library\'s'
                ' display name.',
            )
        ],
        'responses': responses(
            overrides={
                200: serializers.LibrarySerializer(read_only=True, required=False),
            },
            remove=[400]
        ),
    },

    'LibraryView.post': {
        'summary': 'Create a new library',
        'description': 'Create new library. This API will use default org of given tenant as library org '
        'and will raise errors if default org is invalid or unset',
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'tenant_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Tenant id',
                    example=1,
                ),
                'number': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Number',
                    example='class_1',
                ),
                'display_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Name to be used for library',
                    example='my test library',
                ),
            },
            required=['org', 'number', 'display_name']
        ),
        'responses': responses(
            overrides={
                201: openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'library_key': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='Created library id',
                        ),
                    },
                ),
                400: 'Unable to create library. The response will include a JSON object with the error message.',
            },
            remove=[200, 404],
        ),
    },

    'CoursesFeedbackView.get': {
        'summary': 'Get the list of feedback of courses in the tenants',
        'description': 'Get the list of feedbacks for accessible courses.',
        'parameters': [
            common_parameters['tenant_ids'],
            query_parameter(
                'search_text',
                str,
                'A search text to filter the results by. The search text will be matched against the feedback comment.',
            ),
            query_parameter(
                'course_ids',
                str,
                'A comma-separated list of course IDs to filter the results by. If not provided, the system will '
                'assume all courses that are accessible to the caller.',
            ),
            query_parameter(
                'rating_instructors',
                str,
                'A comma-separated list of integers from 0 to 5 (inclusive), e.g., `2,3`, to filter the results by.',
            ),
            query_parameter(
                'rating_content',
                str,
                'A comma-separated list of integers from 0 to 5 (inclusive), e.g., `2,3`, to filter the results by.',
            ),
            openapi.Parameter(
                'public_only',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_INTEGER,
                enum=[1, 0],
                description=(
                    'When set to `1`, returns only public feedbacks. Defaults to `0`. '
                    'Any value other than `1` is treated as `0`.'
                )
            ),
            openapi.Parameter(
                'recommended_only',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_INTEGER,
                enum=[1, 0],
                description=(
                    'When set to `1`, returns only feedbacks where the user recommended the course. Defaults to `0`. '
                    'Any value other than `1` is treated as `0`.'
                )
            ),
            common_parameters['download'],
        ],
        'responses': responses(
            overrides={
                200: serializers.CoursesFeedbackSerializer(read_only=True, required=False),
            },
        ),
    },

    'DataExportManagementView.list': {
        'summary': 'Get the list of data export tasks for the caller',
        'description': 'Get the list of data export tasks for the caller.',
        'parameters': [
            query_parameter(
                'view_name',
                str,
                'The name of the view to filter the results by. The view name is the name of the endpoint that'
                ' generated the data export task. ',
            ),
            query_parameter(
                'related_id',
                str,
                'The related ID to filter the results by. The related ID is the ID of the object that the data export',
            ),
            openapi.Parameter(
                'sort',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_STRING,
                enum=['-id'],
                description=(
                    'Which field to use when ordering the results according to any of the result fields. The default is'
                    ' `-id` (sorting descending by the task ID).'
                )
            ),
            query_parameter(
                'search_text',
                str,
                'a search text to filter the results by. The search text will be matched against the `filename` and the'
                ' `notes`.',
            ),
            get_optional_parameter('futurex_openedx_extensions.dashboard.serializers::DataExportTaskSerializer'),
        ],
        'responses': responses(
            overrides={
                200: serializers.DataExportTaskSerializer(read_only=True, required=False),
            },
            remove=[400]
        ),
    },

    'DataExportManagementView.partial_update': {
        'summary': 'Set the note of the task',
        'description': 'Set an optional note for the task. The note is a free text field that can be used to describe'
        ' the task so the user can remember the purpose of the task later.',
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'notes': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='A text note to set for the task',
                    example='Weekly report as requested by boss!',
                ),
            },
        ),
        'parameters': [
            path_parameter(
                'id',
                int,
                'The task ID to retrieve.',
            ),
        ],
        'responses': responses(
            overrides={
                200: serializers.DataExportTaskSerializer(read_only=True, required=False),
            },
            remove=[400]
        ),
    },

    'DataExportManagementView.retrieve': {
        'summary': 'Get details of a single task',
        'description': 'Get details of a single task by ID. The task must be owned by the caller.',
        'parameters': [
            path_parameter(
                'id',
                int,
                'The task ID to retrieve.',
            ),
            get_optional_parameter('futurex_openedx_extensions.dashboard.serializers::DataExportTaskSerializer')
        ],
        'responses': responses(
            overrides={
                200: serializers.DataExportTaskSerializer(read_only=True, required=False),
            },
            remove=[400]
        ),
    },

    'GlobalRatingView.get': {
        'summary': 'Get global rating statistics for the tenants',
        'description': 'Get global rating statistics for the tenants. The response will include the average rating and'
        ' the total number of ratings for the selected tenants, plus the number of ratings for each rating value from'
        ' 0 to 5 (inclusive).\n'
        '\n**Note:** the count includes only visible courses.\n'
        f'{repeated_descriptions["visible_course_definition"]}',
        'parameters': [
            common_parameters['tenant_ids'],
        ],
        'responses': responses(
            overrides={
                200: openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'total_rating': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'total_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'courses_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'rating_counts': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                '1': openapi.Schema(type=openapi.TYPE_INTEGER),
                                '2': openapi.Schema(type=openapi.TYPE_INTEGER),
                                '3': openapi.Schema(type=openapi.TYPE_INTEGER),
                                '4': openapi.Schema(type=openapi.TYPE_INTEGER),
                                '5': openapi.Schema(type=openapi.TYPE_INTEGER),
                            }
                        ),
                    },
                    example={
                        'total_rating': 10,
                        'total_count': 10,
                        'courses_count': 3,
                        'rating_counts': {
                            '1': 0,
                            '2': 5,
                            '3': 2,
                            '4': 2,
                            '5': 1,
                        }
                    }
                ),
            },
            remove=[400]
        ),
    },

    'ExcludedTenantsView.get': {
        'summary': 'Get the list of tenants that are excluded from the dashboard APIs',
        'description': 'Get the list of tenants that are excluded from the dashboard APIs. The response will include'
        ' the tenant IDs and the reason for exclusion.\n'
        '\n**Only system staff users can access this API.**\n\n'
        'The following are the possible reason codes:\n\n'
        '-----------------------------------------------------\n'
        '| Code | Description |\n'
        '|------|-------------|\n'
        '| 10002 | the tenant is not being used by any site route |\n'
        '| 10003 | the tenant is being used by more than one site route |\n'
        '| 10004 | `LMS_BASE` is missing the tenant\'s `lms_config` settings |\n'
        '| 10005 | the value of `LMS_BASE` in the tenant\'s `lms_config` settings does not match the `domain` value'
        ' of the related site route |\n'
        '| 10006 | the dashboard is explicitly disabled for this tenant ('
        '`lms_config["IS_FX_DASHBOARD_ENABLED"]` is explicitly to `False`) |\n'
        '| 10007 | `course_config_filter` is missing or not valid the tenant\'s `lms_config` settings |\n'
        '-----------------------------------------------------\n',
    },

    'LearnerCoursesView.get': {
        'summary': 'Get the list of courses for a specific learner',
        'description': 'Get the list of courses (regardless of course visibility) for a specific learner using the'
        ' `username`. The caller must have access to the learner\'s tenant through a tenant-role, or access to a course'
        ' where the learner is enrolled.\n'
        '\n**Note:** this endpoint will return `404` when inquiring for a staff user; unless `include_staff` is set to'
        f' `1`.\n{repeated_descriptions["visible_course_definition"]}',
        'parameters': [
            common_path_parameters['username-learner'],
            common_parameters['tenant_ids'],
            common_parameters['include_staff'],
        ],
        'responses': responses(
            overrides={
                200: serializers.LearnerCoursesDetailsSerializer(read_only=True, required=False),
            },
        ),
    },

    'LearnersDetailsForCourseView.get': {
        'summary': 'Get the list of learners for a specific course',
        'description': 'Get the list of learners for a specific course using the `course_id`. The caller must have'
        ' access to the course.',
        'parameters': [
            path_parameter(
                'course_id',
                str,
                'The course ID to retrieve the learners for.',
            ),
            common_parameters['tenant_ids'],
            query_parameter(
                'search_text',
                str,
                'a search text to filter the results by. The search text will be matched against the user\'s full name,'
                ' username, national ID, and email address.',
            ),
            common_parameters['include_staff'],
            get_optional_parameter(
                'futurex_openedx_extensions.dashboard.serializers::LearnerDetailsForCourseSerializer'
            ),
            common_parameters['download'],
            common_parameters['omit_subsection_name']
        ],
        'responses': responses(
            overrides={
                200: serializers.LearnerDetailsForCourseSerializer(read_only=True, required=False),
            },
            remove=[400]
        ),
    },

    'LearnersEnrollmentView.get': {
        'summary': 'Get the list of enrollments',
        'description': 'Get the list of enrollments in the tenants, which is the list of all learners having at '
        ' least one enrollment in any course.',
        'parameters': [
            common_parameters['tenant_ids'],
            query_parameter(
                'course_ids',
                str,
                'a comma separated list of course ids to filter the results by. If not provided, the system will '
                'assume all courses that are accessible to the caller.',
            ),
            query_parameter(
                'user_ids',
                str,
                'a comma separated list of learner user ids to filter the results by. If not provided, the system '
                'will assume all users that are accessible to the caller.',
            ),
            query_parameter(
                'usernames',
                str,
                'a comma separated list of learner usernames to filter the results by. If not provided, the system '
                ' will assume all users that are accessible to the caller.',
            ),
            query_parameter(
                'learner_search',
                str,
                'A search text to filter results, matched against the user\'s full name, username, national ID, and '
                ' email address.',
            ),
            query_parameter(
                'course_search',
                str,
                'A search text to filter results, matched against the course\'s ID and display name.',
            ),
            common_parameters['include_staff'],
            get_optional_parameter('futurex_openedx_extensions.dashboard.serializers::LearnerEnrollmentSerializer'),
            common_parameters['download'],
            common_parameters['omit_subsection_name'],
        ],
        'responses': responses(
            overrides={
                200: serializers.LearnerEnrollmentSerializer(read_only=True, required=False),
            }
        ),
    },

    'LearnerUnenrollView.post': {
        'summary': 'Unenroll a learner from a course',
        'description': 'Unenroll a learner from a specified course. The caller must have staff or instructor'
        ' permissions for the course. Provide one of: user_id, username, or email to identify the learner.',
        'parameters': [],
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['course_id'],
            properties={
                'user_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='User ID of the learner (optional, use one of: user_id, username, or email)'
                ),
                'username': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Username of the learner (optional, use one of: user_id, username, or email)'
                ),
                'email': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Email of the learner (optional, use one of: user_id, username, or email)'
                ),
                'course_id': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Course ID from which to unenroll the learner (required)'
                ),
                'reason': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Optional reason for unenrollment'
                ),
            },
        ),
        'responses': responses(
            overrides={
                200: openapi.Response(
                    description='Successfully unenrolled the learner',
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'message': openapi.Schema(type=openapi.TYPE_STRING),
                            'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'username': openapi.Schema(type=openapi.TYPE_STRING),
                            'course_id': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                    )
                ),
            }
        ),
    },

    'LearnerInfoView.get': {
        'summary': 'Get learner\'s information',
        'description': 'Get full information for a specific learner using the `username`. The caller must have access'
        ' to the learner\'s tenant through a tenant-role, or access to a course where the learner is enrolled.',
        'parameters': [
            common_path_parameters['username-learner'],
            common_parameters['tenant_ids'],
            common_parameters['include_staff'],
        ],
        'responses': responses(
            overrides={
                200: serializers.LearnerDetailsExtendedSerializer(read_only=True, required=False),
            },
        ),
    },

    'LearnersView.get': {
        'summary': 'Get the list of learners in the tenants',
        'description': 'Get the list of learners in the tenants. Which is the list of all learners having at least one'
        ' enrollment in any course in the selected tenants, or had their user registered for the first time within'
        ' the selected tenants. When using the `include_staff` parameter, the response will also include staff'
        ' users who have a role within the tenant regardless of enrollments or user registration.',
        'parameters': [
            common_parameters['tenant_ids'],
            query_parameter(
                'search_text',
                str,
                'a search text to filter the results by. The search text will be matched against the user\'s full name,'
                ' username, national ID, and email address.',
            ),
            query_parameter(
                'min_enrollments_count',
                int,
                'filter learners to include only those who have at least this number of enrollments. A'
                ' negative value will disable this filter as if it was not provided.',
            ),
            query_parameter(
                'max_enrollments_count',
                int,
                'filter learners to include only those who have at most this number of enrollments. A'
                ' negative value will disable this filter as if it was not provided.',
            ),
            common_parameters['include_staff'],
            common_parameters['download'],
        ],
        'responses': responses(
            overrides={
                200: serializers.LearnerDetailsSerializer(read_only=True, required=False),
            },
            remove=[400]
        ),
    },

    'MyRolesView.get': {
        'summary': 'Get the roles of the caller',
        'description': 'Get details of the caller\'s roles.',
        'parameters': [
            common_parameters['tenant_ids'],
        ],
        'responses': responses(
            overrides={
                200: common_schemas['role'],
            },
            remove=[400]
        ),
    },

    'TotalCountsView.get': {
        'summary': 'Get total counts statistics',
        'description': 'Get total counts for certificates, courses, hidden_courses, learners, and enrollments. The'
        ' `include_staff` parameter does not affect the counts of **course** and **hidden-courses**.',
        'parameters': [
            common_parameters['tenant_ids'],
            query_parameter(
                'stats',
                str,
                'a comma-separated list of the types of count statistics to include in the response. Available count'
                ' statistics are:\n'
                '- `certificates`: total number of issued certificates in the selected tenants. Only visible courses'
                ' are included in th count.\n'
                '- `courses`: total number of visible courses in the selected tenants.\n'
                '- `hidden_courses`: total number of hidden courses in the selected tenants.\n'
                '- `learners`: total number of learners in the selected tenants. The same learner might'
                ' be accessing multiple tenants, and will be counted on every related tenant.\n'
                '- `unique_learners`: unlike `learners` statistics; this one will not repeat the count of a learner'
                ' related to multiple tenants.\n'
                '- `enrollments`: total number of enrollments in visible courses in the selected tenants.\n'
                '- `learning_hours`: total learning hours for visible courses in the selected tenants.\n'
                '\n**Note:** Be ware of the deference between `learners` and `unique_learners`. The first will count'
                ' the learner on every related tenant, while the second will count the learner once. Therefore, the'
                ' returned JSON will **not** include `unique_learners_count` field per tenant. It\'ll only include'
                ' `total_unique_learners`.\n'
                '\n**Note:** The learning hours value of a course is calculated by multiplying the number of'
                ' certificates earned by all enrolled learners in that course by the course-effort value. The '
                'course-effort value is set in the course settings in hours:minutes format. For example, `15:30` means'
                ' 15 hour and 30 minutes. If the course-effort is not set, or set to less than 30 minutes, then it\'ll'
                ' be considered as 12 hours.\n'
                f'{repeated_descriptions["visible_course_definition"]}',
            ),
            common_parameters['include_staff'],
        ],
        'responses': responses(
            success_description='The response is a JSON object with the requested statistics.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='The tenant ID',
                additional_properties=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'certificates_count': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description='Total number of issued certificates in the tenant',
                        ),
                        'courses_count': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description='Total number of visible courses in the tenant',
                        ),
                        'hidden_courses_count': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description='Total number of hidden courses in the tenant',
                        ),
                        'learners_count': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description='Total number of learners in the tenant',
                        ),
                        'enrollments_count': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description='Total number of enrollments in visible courses in the tenant',
                        ),
                        'learning_hours': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description='Total learning hours for visible courses in the tenant',
                        ),
                    },
                ),
                properties={
                    'total_certificates_count': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Total number of issued certificates across all tenants',
                    ),
                    'total_courses_count': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Total number of visible courses across all tenants',
                    ),
                    'total_hidden_courses_count': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Total number of hidden courses across all tenants',
                    ),
                    'total_learners_count': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Total number of learners across all tenants',
                    ),
                    'total_enrollments_count': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Total number of enrollments across all tenants',
                    ),
                    'total_learning_hours': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Total learning hours across all tenants',
                    ),
                    'total_unique_learners': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='Total number of unique learners across all tenants',
                    ),
                    'limited_access': openapi.Schema(
                        type=openapi.TYPE_BOOLEAN,
                        description='`true` if the caller has limited access to any of the selected tenants.',
                    ),
                },
            ),
            success_examples={
                'application/json': {
                    '1': {
                        'certificates_count': 14,
                        'courses_count': 12,
                        'enrollments_count': 26,
                        'hidden_courses_count': 1,
                        'learners_count': 16,
                        'learning_hours_count': 230,
                    },
                    '2': {
                        'certificates_count': 32,
                        'courses_count': 5,
                        'enrollments_count': 45,
                        'hidden_courses_count': 0,
                        'learners_count': 46,
                        'learning_hours_count': 192,
                    },
                    'total_certificates_count': 46,
                    'total_courses_count': 17,
                    'total_enrollments_count': 71,
                    'total_hidden_courses_count': 1,
                    'total_learners_count': 62,
                    'total_learning_hours_count': 422,
                    'total_unique_learners': 55,
                    'limited_access': False,
                },
            },
        ),
    },

    'AggregatedCountsView.get': {
        'summary': 'Get aggregated total counts statistics',
        'description': 'Get aggregated total counts for enrollments.',
        'parameters': [
            common_parameters['tenant_ids'],
            openapi.Parameter(
                'stats',
                ParameterLocation.QUERY,
                required=True,
                type=openapi.TYPE_STRING,
                enum=['enrollments'],
                description=(
                    'A comma-separated list of the types of count statistics to include in the response.'
                    ' Available count statistics are:\n'
                    '- `enrollments`: total number of enrollments in visible courses in the selected tenants.\n'
                ),
            ),
            openapi.Parameter(
                'aggregate_period',
                ParameterLocation.QUERY,
                required=True,
                type=openapi.TYPE_STRING,
                enum=['day', 'month', 'quarter', 'year'],
                description=(
                    'The criteria to be used in the aggregation. Available periods are:\n'
                    '- `day`: daily aggregation. labels will be generated in the format `YYYY-MM-DD`\n'
                    '- `month`: monthly aggregation. labels will be generated in the format `YYYY-MM`\n'
                    '- `quarter`: quarterly aggregation. labels will be generated in the format `YYYY-Qn`\n'
                    '- `year`: yearly aggregation. labels will be generated in the format `YYYY`\n'
                ),
            ),
            query_parameter(
                'date_from',
                str,
                description=(
                    'The date to start the aggregation from. The date format must be `YYYY-MM-DD`. See the'
                    ' details `favors_backward` parameter that describes the behavior of `date_from`, `date_to`, and'
                    ' `favors_backward` parameters.'
                ),
            ),
            query_parameter(
                'date_to',
                str,
                description=(
                    'The date to end the aggregation from. The date format must be `YYYY-MM-DD`. See the'
                    ' details `favors_backward` parameter that describes the behavior of `date_from`, `date_to`, and'
                    ' `favors_backward` parameters.'
                ),
            ),
            openapi.Parameter(
                'favors_backward',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_INTEGER,
                enum=[0, 1],
                description=(
                    'This parameter is used when both `date_from` and `date_to` are not provided, or both'
                    ' are provided. Otherwise it\'ll be ignored.\n'
                    'The following describes the behavior of this parameter:\n'
                    '- **Case 1:**'
                    ' `date_to` is set, and `date_from` is not set: the system will calculate the `date_from` by going'
                    ' backward from `date_to` by the number of periods specified in `max_period_chunks`.\n'
                    '- **Case 2:**'
                    ' `date_from` is set, and `date_to` is not set: the system will calculate the `date_to` by going'
                    ' forward from `date_from` by the number of periods specified in `max_period_chunks`.\n'
                    '- **Case 3:**'
                    ' `date_from` and `date_to` are both not set:\n'
                    '  - if `favors_backward` is set to `1`; the system will set `date_to` to the current date, and'
                    ' calculate the `date_from` by going backward from `date_to` by the number of periods specified in'
                    ' `max_period_chunks`.\n'
                    '  - if `favors_backward` is set to `0`; the system will set `date_from` to the current date, and'
                    ' calculate the `date_to` by going forward from `date_from` by the number of periods specified in'
                    ' `max_period_chunks`.\n'
                    '- **Case 4:**'
                    ' `date_from` and `date_to` are both set: the system will switch the values if `date_from` is'
                    ' greater than `date_to`. Then:\n'
                    '  - if `favors_backward` is set to `1`; the system will calculate the minimum allowed date by'
                    ' going backward from `date_to` by the number of periods specified in `max_period_chunks`. Then'
                    ' it\'ll set that value to `date_from` if-and-only-if `date_from` is less than the allowed date.\n'
                    '  - if `favors_backward` is set to `0`; the system will calculate the maximum allowed date by'
                    ' going forward from `date_from` by the number of periods specified in `max_period_chunks`. Then'
                    ' it\'ll set that value to `date_to` if-and-only-if `date_to` is less than the allowed date.\n'
                    '\n**Note:** for any period other than `day`; the calculated `date_from` will be set to the first'
                    ' day of the period. And the calculated `date_to` will be set to the last day of the period.'
                ),
            ),
            query_parameter(
                'max_period_chunks',
                int,
                description=(
                    'The maximum number of periods to include in the response. Any value less than 1 will be'
                    ' converted use the default as in system configuration' +
                    f':\n\n**`{settings.FX_MAX_PERIOD_CHUNKS_MAP}`**\n' if hasattr(
                        settings, 'FX_MAX_PERIOD_CHUNKS_MAP',
                    ) else '' +
                    '\nThe default value is `0`.\n'
                    '\n**Note:** Any value exceeding the maximum allowed will be truncated to default.'
                ),
            ),
            openapi.Parameter(
                'fill_missing_periods',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_INTEGER,
                enum=[0, 1],
                description=(
                    'Fill the missing periods from data with zeros. Default is `1` (fill). This default'
                    ' ensures the repose never returns an empty period. If set to `0`, then the response will'
                    ' include only the periods with data.'
                ),
            ),
            common_parameters['include_staff'],
        ],
        'responses': responses(
            success_description='The response is a JSON object with the requested statistics.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='aggregated statistics',
            ),
            success_examples={
                'application/json': {
                    'query_settings': {
                        'aggregate_period': 'quarter',
                        'date_from': '2024-04-01T00:00:00Z',
                        'date_to': '2025-02-05T23:59:59Z',
                    },
                    'all_tenants': {
                        'enrollments_count': [
                            {
                                'label': '2024-Q2',
                                'value': 8,
                            },
                            {
                                'label': '2024-Q3',
                                'value': 2,
                            },
                            {
                                'label': '2024-Q4',
                                'value': 8,
                            },
                            {
                                'label': '2025-Q1',
                                'value': 0,
                            }
                        ],
                        'totals': {
                            'enrollments_count': 18,
                        }
                    },
                    'by_tenant': [
                        {
                            'enrollments_count': [
                                {
                                    'label': '2024-Q2',
                                    'value': 5,
                                },
                                {
                                    'label': '2024-Q3',
                                    'value': 0,
                                },
                                {
                                    'label': '2024-Q4',
                                    'value': 8,
                                },
                                {
                                    'label': '2025-Q1',
                                    'value': 0,
                                }
                            ],
                            'totals': {
                                'enrollments_count': 13,
                            },
                            'tenant_id': 1,
                        },
                        {
                            'enrollments_count': [
                                {
                                    'label': '2024-Q2',
                                    'value': 3,
                                },
                                {
                                    'label': '2024-Q3',
                                    'value': 2,
                                },
                                {
                                    'label': '2024-Q4',
                                    'value': 0,
                                },
                                {
                                    'label': '2025-Q1',
                                    'value': 0,
                                }
                            ],
                            'totals': {
                                'enrollments_count': 5,
                            },
                            'tenant_id': 2,
                        }
                    ],
                    'limited_access': False,
                },
            },
            overrides={
                400: 'Bad request. The response will include a JSON object with the error message.',
                401: 'Unauthorized. The response will include a JSON object with the error message.',
                403: 'Forbidden. The response will include a JSON object with the error message.',
                404: 'Not found. The response will include a JSON object with the error message.',
            },
        ),
    },

    'UserRolesManagementView.create': {
        'summary': 'Add a role to one or more users in the tenants',
        'description': f'Add a role to one or more users in the tenants.\n{repeated_descriptions["roles_overview"]}',
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'tenant_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                    description='The tenants we\'re adding these user-roles to. If more than one tenant is provided,'
                    ' then tenant_wide must be set `1`',
                    example=[1, 2],
                ),
                'users': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING),
                    description='List of user identifiers (username, email, or ID). Mixing the identifier types is'
                    ' allowed. Only one of any of the three identifiers is required for each user',
                    example=['user1', 'user2@example.com', 99],
                ),
                'role': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Role name to assign',
                    example='staff',
                ),
                'tenant_wide': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='`0` or `1` to specify if the role is tenant-wide or not. If set to `1`, then'
                    ' `courses_ids` must be `Null`, empty array, or omitted. Otherwise; `courses_ids` must be'
                    ' filled with at least one course ID',
                    example=0,
                ),
                'course_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING),
                    description='Course IDs for affected courses. See `tenant_wide` note above',
                    example=['course-v1:org+course+001', 'course-v1:org+course+002'],
                ),
            },
            required=['tenant_ids', 'users', 'role', 'tenant_wide']
        ),
        'parameters': [
        ],
        'responses': responses(
            overrides={
                201: 'Operation processed. The returned JSON contains more details:\n'
                '- `added`: the list of users successfully added to the role. The identifier is the same as the one'
                ' sent, ID, username, or email\n'
                '- `updated`: the list of users who had their role updated according to the request because they had'
                ' that role already but with different configuration\n'
                '- `not_updated`: users who already have the exact requested amendment\n'
                '- `failed`: for every failing user: the structure contain the user information + reason code (numeric)'
                ' + reason message\n'
                '\nPossible reason codes:\n'
                '------------------------------\n'
                '| Code | Description |\n'
                '|------|-------------|\n'
                '| 1001 | The given user does not exist within the query. For example, it might exist in the database'
                ' but not available within the request tenants  |\n'
                '| 1002 | The given user is not active (`is_active` = `False`) |\n'
                '| 1003 | The given email is used as a username for another user. Conflict data to be resolved by the'
                ' superuser |\n'
                '| 1004 | The given user is not accessible by the caller |\n'
                '| 2001 | Error while deleting role |\n'
                '| 2002 | Error while adding role to a user |\n'
                '| 2003 | Dirty data found for user which prevents the requested operation. For example, adding'
                ' `org_course_creator_group` to a user who has that role already exist without the required'
                ' `CourseCreator` record in the database (caused by old bad entry) |\n'
                '| 2004 | The given role is unsupported |\n'
                '| 2005 | Bad request entry for the requested roles operation |\n'
                '| 2006 | Course creator role is not granted or not present (caused by old bad entry) |\n'
                '| 2007 | Error while updating roles for user |\n'
                '| 5001 | Course creator record not found (caused by old bad entry) |\n'
                '------------------------------\n'
            },
            remove=[200],
        ),
    },

    'UserRolesManagementView.destroy': {
        'summary': 'Delete all roles of one user in all given tenants',
        'description': f'Delete all roles of one user in all given tenants.\n{repeated_descriptions["roles_overview"]}',
        'parameters': [
            common_path_parameters['username-staff'],
            openapi.Parameter(
                name='tenant_ids',
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description='Comma-separated list of tenant IDs to delete the user-roles from',
                required=True,
            ),
        ],
        'responses': responses(
            overrides={204: 'The user-roles have been deleted successfully.'},
            remove=[200],
        ),
    },

    'UserRolesManagementView.list': {
        'summary': 'Get the list of roles of users in the tenants',
        'description': 'Get the list of roles of users in the tenants',
        'parameters': [
            common_parameters['tenant_ids'],
        ],
        'responses': responses(
            overrides={
                200: common_schemas['role'],
            },
            remove=[400]
        ),
    },

    'UserRolesManagementView.retrieve': {
        'summary': 'Get the roles of a single users in the tenants',
        'description': 'Get the roles of a single users in the tenants',
        'parameters': [
            common_path_parameters['username-staff'],
            common_parameters['tenant_ids'],
        ],
        'responses': responses(
            overrides={
                200: common_schemas['role'],
            },
            remove=[400]
        ),
    },

    'UserRolesManagementView.update': {
        'summary': 'Change the roles of one user in one tenant',
        'description': 'Change the roles of one user in one tenant. The updated roles will replace all the existing.\n'
        f'{repeated_descriptions["roles_overview"]}'
        ' roles of the user in the tenant.',
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'tenant_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='The tenant ID to update the user roles in',
                    example=1,
                ),
                'tenant_roles': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING),
                    description='List of role names to assign to the user as tenant-wide roles',
                    example=['staff', 'org_course_creator_group'],
                ),
                'course_roles': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    additional_properties=openapi.Schema(type=openapi.TYPE_STRING),
                    description='Dictionary of course IDs and their roles. The course ID is the key, and the value is'
                    ' a list of role names to assign to the user for that course',
                    example={
                        'course-v1:org+course+001': ['instructor', 'ccx_coach'],
                        'course-v1:org+course+002': ['data_researcher', 'ccx_coach'],
                    },
                ),
            },
            required=['tenant_id', 'tenant_roles', 'course_roles']
        ),
        'parameters': [
            common_path_parameters['username-staff'],
        ],
        'responses': responses(
            overrides={
                200: common_schemas['role'],
            },
        ),
    },

    'VersionInfoView.get': {
        'summary': 'Get fx-openedx-extentions running version',
        'description': 'Get fx-openedx-extentions running version. The caller must be a system staff.',
        'parameters': [
        ],
        'responses': responses(
            remove=[400, 404],
            overrides={
                200: openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'version': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='Runnining version i.e 3.4.11',
                        ),
                    },
                ),
            },
        ),
    },

    'ConfigEditableInfoView.get': {
        'summary': 'Get information about editable settings of the theme config',
        'description': 'Get information about editable settings of the theme designer config.',
        'parameters': [
            query_parameter(
                'tenant_ids',
                str,
                'Tenant ids to retrieve the configuration for. \n '
                '**Note:** The caller must provide single tenant id to access the configuration.',
            ),
        ],
        'responses': responses(
            success_description='The response is a list of editable settings of the config',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'editable_fields': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description='list of strings where each value represents an editable settings key',
                        items=openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        example=['platform_name', 'primary_color', 'homepage_sections']
                    ),
                    'read_only_fields': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description='list of strings where each value represents a read-only settings key',
                        items=openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        example=['lms_base']
                    ),
                },
            ),
            success_examples={
                'application/json': {
                    'editable_fields': ['platform_name', 'primary_color', 'homepage_sections'],
                    'read_only_fields': ['lms_base']
                },
            },
            overrides={
                400: openapi.Response(
                    description='Bad request. Details in the response body.',
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'detail': openapi.Schema(type=openapi.TYPE_STRING),
                            'reason': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        example={
                            'detail': 'API can only be used for single tenant id.',
                        }
                    ),
                ),
            },
            remove=[404]
        ),
    },

    'ThemeConfigDraftView.get': {
        'summary': 'Get current draft theme configuration of given tenant.',
        'description': 'Get the current draft of theme configuration for a given tenant. The caller must have '
        'staff access.',
        'parameters': [
            common_path_parameters['tenant_id']
        ],
        'responses': responses(
            success_description='The response is list of updated fields with published and draft values along with '
            'draft hash. \n The `draft_hash` is important and will be required later for publish config API, to prevent'
            ' publishing unreviewed config.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'updated_fields': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'key1': openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'published_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Last Published value of the key1.',
                                    ),
                                    'draft_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Draft value of the key1',
                                    )
                                }
                            ),
                            'key2': openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'published_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Last Published value of the key2.',
                                    ),
                                    'draft_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Draft value of the key2',
                                    )
                                }
                            )
                        }
                    ),
                    'draft_hash': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Draft hash code, will be used later to publish config.',
                        example='ajsd90a8su9a8u9a8sdyf0a9sdhy0asdjgasdgkjdsfgj',
                    ),
                },
            ),
            success_examples={
                'application/json': {
                    'updated_fields': {
                        'platform_name': {
                            'published_value': 'my platform name',
                            'draft_value': 'My new Platform'
                        },
                        'primary_color': {
                            'published_value': '#ff0000',
                            'draft_value': '#ffffff'
                        },
                    },
                    'draft_hash': 'ajsd90a8su9a8u9a8sdyf0a9sdhy0asdjgasdgkjdsfgj'
                },
            },
            overrides={
                400: openapi.Response(
                    description='Bad request. Details in the response body.',
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'detail': openapi.Schema(type=openapi.TYPE_STRING),
                            'reason': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        example={
                            'detail': 'API can only be used for single tenant id.',
                        }
                    ),
                ),
                403: 'Forbidden access. Details in the response body.',
                404: 'No Draft found. The response will include a JSON object with the error message.',
            },
        ),
    },

    'ThemeConfigDraftView.put': {
        'summary': 'Update draft theme configuration of given tenant.',
        'description': 'Update draft of theme configuration for a given tenant otherwise create new draft with '
        'updated values if draft does not exist. The API can also be used to reset a key to its published value.',
        'parameters': [
            common_path_parameters['tenant_id'],
        ],
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'key': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Config field name value is updated for.',
                    example='platform_name',
                ),
                'current_revision_id': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Last fetched value of `revision_id` for the key. It is used to prevent'
                    ' concurrent updates. The API will return `409` if the value is outdated.',
                    example='My Platform Name',
                ),
                'new_value': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Update value.',
                    example='My new awesome Platform Name',
                ),
                'reset': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Reset is optional (default is `"0"`). If `"reset": "1"` is sent, then `new_value` will'
                    ' be ignored, and the draft record of this particular key will be deleted/discarded. Any value'
                    ' other than `"1"` will be considered as `"0"`.',
                    example='1',
                ),
            },
            required=['key', 'current_value']
        ),
        'responses': responses(
            success_description='See /draft/values API for details, the response is exactly the same as that one,'
            ' except that it\'ll always contain one key.'
            '\n\n**Note:** If the `new_value` is identical to the current value, the API will still succeed and it\'ll'
            ' return the same revision ID (indicating that the value has not changed).',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'values': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'key1': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description='Value of key1',
                            ),
                        },
                    ),
                    'not_permitted': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description='always empty in this API.',
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                    'bad_keys': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description='always empty in this API.',
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                    'revision_ids': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'key1': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description='revision_id of key1.',
                            ),
                        },
                    ),
                },
            ),
            success_examples={
                'application/json': {
                    'values': {
                        'secondary_colors': '#ff0000',
                    },
                    'not_permitted': [],
                    'bad_keys': [],
                    'revision_ids': {
                        'secondary_colors': '654987344',
                    },
                },
            },
            overrides={
                400: openapi.Response(
                    description='Bad request. Details in the response body.',
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'detail': openapi.Schema(type=openapi.TYPE_STRING),
                            'reason': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        example={
                            'detail': 'API can only be used for single tenant id.',
                        },
                    ),
                ),
                409: openapi.Response(
                    description='Unable to save changes due to conflicts.',
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'detail': openapi.Schema(type=openapi.TYPE_STRING),
                            'reason': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        example={
                            'detail': 'Current value is outdated.',
                        },
                    ),
                ),
            },
            remove=[404],
        ),
    },

    'ThemeConfigDraftView.delete': {
        'summary': 'Delete draft config (Discard draft changes)',
        'description': 'Delete/discard draft changes of theme config for a given tenant.',
        'parameters': [
            common_path_parameters['tenant_id'],
        ],
        'responses': responses(
            overrides={
                204: 'Draft is deleted successfully.',
                400: openapi.Response(
                    description='Bad request. Details in the response body.',
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'detail': openapi.Schema(type=openapi.TYPE_STRING),
                            'reason': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        example={
                            'detail': 'API can only be used for single tenant id.',
                        }
                    ),
                ),
                404: 'No Draft found. The response will include a JSON object with the error message.',
            },
            remove=[200],
        ),
    },

    'ThemeConfigPublishView.post': {
        'summary': 'Publish draft theme configuration of given tenant.',
        'description': 'Publish draft theme configuration for a given tenant.',
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'tenant_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='The tenant ID to publish the config for.',
                    example=1,
                ),
                'draft_hash': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='The draft_hash code is important and required to prevent publishing unreviewed '
                    'config. Caller can get its value using the API: GET /api/fx/config/v1/draft/',
                    example='ajsd90a8su9a8u9a8sdyf0a9sdhy0asdjgasdgkjdsfgj',
                ),
            },
            required=['tenant_id', 'draft_hash']
        ),
        'responses': responses(
            success_description='The response is list of published fields with old and new values.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'updated_fields': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'key1': openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'old_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Last Published value of the key1.',
                                    ),
                                    'new_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Draft value of the key1',
                                    )
                                }
                            ),
                            'key2': openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'old_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Last Published value of the key2.',
                                    ),
                                    'new_value': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description='Draft value of the key2',
                                    )
                                }
                            )
                        }
                    ),
                },
            ),
            success_examples={
                'application/json': {
                    'updated_fields': {
                        'platform_name': {
                            'old_value': 'my platform name',
                            'new_value': 'My new Platform'
                        },
                        'primary_color': {
                            'old_value': '#ff0000',
                            'new_value': '#ffffff'
                        },
                    },
                },
            },
            overrides={
                400: openapi.Response(
                    description='Bad request. Details in the response body.',
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'detail': openapi.Schema(type=openapi.TYPE_STRING),
                            'reason': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        example={
                            'reason': 'Invalid draft hash.',
                            'detail': {},
                        }
                    ),
                ),
            },
            remove=[404]
        ),
    },

    'ThemeConfigRetrieveView.get': {
        'summary': 'Get the theme config values for a given tenant.',
        'description': 'Get the values of theme configuration for a given tenant.',
        'parameters': [
            query_parameter(
                'tenant_ids',
                str,
                'Tenant IDs to retrieve the configuration for.\n'
                '**Note:** The caller must provide a single tenant ID to access the configuration.',
            ),
            query_parameter(
                'keys',
                str,
                'A comma-separated list of keys to get the values for. If not provided, the system will return all '
                'settings in response that are accessible to the user.',
            ),
            openapi.Parameter(
                'published_only',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_STRING,
                enum=['1', '0'],
                description=(
                    '- `published_only=0`: (**default**) The API will look for the draft value first; if not found, '
                    'then return the published value.\n'
                    '- `published_only=1`: The API will ignore drafts and will only return the last published value. '
                    'It will be useful to render live pages. Default is `0`. Any value other than `1` will be'
                    ' considered as `0`.'
                )
            ),
        ],
        'responses': responses(
            success_description='The response is a list of values, along with `not_permitted` and `bad_keys` info.'
            '\n`not_permitted` will contain a list of keys that are not accessible to the user.'
            '\n`bad_keys` will contain a list of keys that do not exist.'
            '\n`revision_ids` will contain a dictionary of requested keys with the current `revision_id`. The revision'
            ' ID is a unique identifier for the current draft value of the key across the tenant. It can be used to'
            ' check if the value has changed since the last time it was fetched.'
            '\n\n**Note:** the value `"0"` in the `revision_ids` means that the key does not have a draft value. This'
            ' is useful when `published_only=0` to check if the value returned for the key has been published or not.',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'values': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'key1': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description='Value of key1',
                            ),
                            'key2': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description='Value of key2.',
                            )
                        }
                    ),
                    'not_permitted': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description='List of keys that the user tried to access but are not permitted.',
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                    'bad_keys': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description='List of keys that the user tried to access but do not exist.',
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                    'revision_ids': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'key1': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description='revision_id of key1.',
                            ),
                            'key2': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description='revision_id of key2.',
                            )
                        }
                    ),
                },
            ),
            success_examples={
                'application/json': {
                    'values': {
                        'primary_colors': '#ff00ff',
                        'secondary_colors': '#ff0000',
                    },
                    'not_permitted': ['platform_name'],
                    'bad_keys': ['something'],
                    'revision_ids': {
                        'primary_colors': '0',
                        'secondary_colors': '654987321',
                    },
                },
            },
            remove=[404]
        ),
    },

    'ThemeConfigTenantView.post': {
        'summary': 'Create new tenant along with default theme config.',
        'description': 'Create new tenant along with default theme config. This API is allowed for system staff users'
        ' only.',
        'body': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'sub_domain': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Tenant sub domain.',
                    example='hero',
                ),
                'platform_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Tenant platform name',
                    example='My Platform',
                ),
                'owner_user_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Tenant owner if',
                    example=11,
                ),
            },
            required=['sub_domain', 'platform_name']
        ),
        'responses': responses(
            success_description='Returns the basic information about the created tenant',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'tenant_id': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='The tenant_id for the newly created tenant',
                    ),
                    'lms_root_url': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The LMS root URL of the tenant',
                    ),
                    'studio_root_url': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The Studio root URL of the tenant',
                    ),
                    'platform_name': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The platform name of the tenant',
                    ),
                    'logo_image_url': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The logo image URL of the tenant',
                    )
                },
            ),
            success_examples={
                'application/json': {
                    'tenant_id': 99,
                    'lms_root_url': 'https://heroes.lms.com',
                    'studio_root_url': 'https://studio.lms.com',
                    'platform_name': 'Heroes Academy',
                    'logo_image_url': 'https://www.s3.com/logo.png',
                },
            },
            overrides={
                200: 'Changes saved successfully.',
                400: 'Unable to create tenant. The response will include a JSON object with the error message.',
            },
            remove=[404],
        ),
    },

    'TenantInfoView.get': {
        'summary': 'Get basic information about the tenant.',
        'description': 'Return the basic information about the tenant. The caller must have any access role to the '
                       'tenant.',
        'responses': responses(
            success_description='Returns the basic information about the tenant',
            success_schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'tenant_id': openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description='The tenant_id for the tenant',
                    ),
                    'lms_root_url': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The LMS root URL of the tenant',
                    ),
                    'studio_root_url': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The Studio root URL of the tenant',
                    ),
                    'platform_name': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The platform name of the tenant',
                    ),
                    'logo_image_url': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='The logo image URL of the tenant',
                    )
                },
            ),
            success_examples={
                'application/json': {
                    'tenant_id': 99,
                    'lms_root_url': 'https://heroes.lms.com',
                    'studio_root_url': 'https://studio.lms.com',
                    'platform_name': 'Heroes Academy',
                    'logo_image_url': 'https://www.s3.com/logo.png',
                },
            },
            overrides={
                200: 'Changes saved successfully.',
            },
            remove=[404],
        ),
    },

    'TenantAssetsManagementView.create': {
        'summary': 'Add new asset to the tenant',
        'description': 'Add new asset to the tenant. \n `Note:` If an asset with the same slug already exists, the '
        'existing record will be updated with the new file instead of creating a duplicate entry. The old file will '
        '**not** be deleted from the storage.\n\n'
        '**Note:** only superusers can add assets with slugs starting with an underscore (`_`). These assets are '
        'considered private and will not be visible to other users. This is about the record in the database, not '
        'the asset file itself. The asset file will have it\'s own permissions according to the host that serves it',
        'body': serializers.TenantAssetSerializer(),
        'responses': responses(
            overrides={
                200: serializers.TenantAssetSerializer(include_write_only=False),
            },
            remove=[400]
        ),
    },

    'TenantAssetsManagementView.list': {
        'summary': 'List all asset',
        'description': 'Retrieve a list of all assets. System admins can view all assets, while other users can only '
        'view assets associated with their accessible tenant. Use the Tenant ID filter to narrow down the results to a '
        'specific tenant.\n\n'
        '**Note:** assets with slugs starting with an underscore (`_`) are considered private and will be visible only '
        'to system admins. This is about the record in the database, not the asset file itself. The asset file will '
        'have it\'s own permissions according to the host that serves it',
        'parameters': [
            query_parameter(
                'tenant_id',
                int,
                'The tenant id to filter the results by.',
            ),
            query_parameter(
                'updated_by',
                int,
                'The id of user to filter the results by.',
            ),
            openapi.Parameter(
                'sort',
                ParameterLocation.QUERY,
                required=False,
                type=openapi.TYPE_STRING,
                enum=['-id'],
                description=(
                    'Which field to use when ordering the results according to any of the result fields. The default is'
                    ' `-id` (sorting descending by the ID).'
                )
            ),
            query_parameter(
                'search_text',
                str,
                'a search text to filter the results by. The search text will be matched against the `slug`',
            ),
        ],
        'responses': responses(
            overrides={
                200: serializers.TenantAssetSerializer(include_write_only=False),
            },
            remove=[400, 404]
        ),
    },
}
