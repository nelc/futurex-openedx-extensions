"""Config views for the dashboard app"""
from __future__ import annotations

import json
import re
from typing import Any

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from rest_framework import status as http_status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import (
    COURSE_ACCESS_ROLES_STAFF_EDITOR,
    FX_VIEW_DEFAULT_AUTH_CLASSES,
)
from futurex_openedx_extensions.helpers.converters import dict_to_hash, error_details_to_dictionary
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ConfigAccessControl
from futurex_openedx_extensions.helpers.permissions import FXHasTenantAllCoursesAccess
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin, add_course_access_roles
from futurex_openedx_extensions.helpers.tenants import (
    create_new_tenant_config,
    delete_draft_tenant_config,
    get_accessible_config_keys,
    get_all_tenants_info,
    get_draft_tenant_config,
    get_tenant_config,
    publish_tenant_config,
    update_draft_tenant_config,
)

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


@docs('ConfigEditableInfoView.get')
class ConfigEditableInfoView(FXViewRoleInfoMixin, APIView):
    """View to get the list of editable keys of the theme designer config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'fx_config_editable_fields'
    fx_view_description = 'api/fx/config/v1/editable: Get editable settings of config'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/config/v1/editable/
        """
        tenant_id = self.verify_one_tenant_id_provided(request)

        return JsonResponse({
            'editable_fields': get_accessible_config_keys(
                user_id=request.user.id,
                tenant_id=tenant_id,
                writable_fields_filter=True,
            ),
            'read_only_fields': get_accessible_config_keys(
                user_id=request.user.id,
                tenant_id=tenant_id,
                writable_fields_filter=False,
            ),
        })


@docs('ThemeConfigDraftView.get')
@docs('ThemeConfigDraftView.put')
@docs('ThemeConfigDraftView.delete')
class ThemeConfigDraftView(FXViewRoleInfoMixin, APIView):
    """View to manage draft theme config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_draft'
    fx_allowed_write_methods = ['PUT', 'DELETE']
    fx_view_description = 'api/fx/config/v1/draft/<tenant_id>: draft theme config APIs'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']
    fx_tenant_id_url_arg_name: str = 'tenant_id'

    def get(self, request: Any, tenant_id: int) -> Response | JsonResponse:  # pylint: disable=no-self-use
        """Get draft config"""
        updated_fields = get_draft_tenant_config(tenant_id=int(tenant_id))
        return JsonResponse({
            'updated_fields': updated_fields,
            'draft_hash': dict_to_hash(updated_fields)
        })

    @staticmethod
    def validate_input(current_revision_id: int) -> None:
        """Validate the input"""
        if current_revision_id is None:
            raise KeyError('current_revision_id')

        try:
            _ = int(current_revision_id)
        except ValueError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='current_revision_id type must be numeric value.'
            ) from exc

    def put(self, request: Any, tenant_id: int) -> Response:
        """Update draft config"""
        data = request.data
        try:
            key = data['key']
            if not isinstance(key, str):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT, message='Key name must be a string.'
                )

            key_access_info = ConfigAccessControl.objects.get(key_name=key)
            if not key_access_info.writable:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT, message=f'Config Key: ({data["key"]}) is not writable.'
                )

            if 'reset' not in data and 'new_value' not in data:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT, message='Provide either new_value or reset.'
                )

            new_value = data.get('new_value')
            current_revision_id = data.get('current_revision_id')
            reset = data.get('reset', False) is True
            self.validate_input(current_revision_id)

            update_draft_tenant_config(
                tenant_id=int(tenant_id),
                config_path=key_access_info.path,
                current_revision_id=int(current_revision_id),
                new_value=new_value,
                reset=reset,
                user=request.user,
            )

            data = get_tenant_config(tenant_id=int(tenant_id), keys=[key], published_only=False)
            return Response(
                status=http_status.HTTP_200_OK,
                data=serializers.TenantConfigSerializer(data, context={'request': request}).data,
            )

        except KeyError as exc:
            return Response(
                error_details_to_dictionary(reason=f'Missing required parameter: {exc}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except FXCodedException as exc:
            if exc.code in [
                FXExceptionCodes.DRAFT_CONFIG_CREATE_MISMATCH.value,
                FXExceptionCodes.DRAFT_CONFIG_UPDATE_MISMATCH.value,
                FXExceptionCodes.DRAFT_CONFIG_DELETE_MISMATCH.value,
            ]:
                return Response(
                    error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                    status=http_status.HTTP_409_CONFLICT
                )
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except ConfigAccessControl.DoesNotExist:
            return Response(
                error_details_to_dictionary(
                    reason=f'Invalid key, unable to find key: ({data["key"]}) in config access control'
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request: Any, tenant_id: int) -> Response:  # pylint: disable=no-self-use
        """Delete draft config"""
        delete_draft_tenant_config(tenant_id=int(tenant_id))
        return Response(status=http_status.HTTP_204_NO_CONTENT)


@docs('ThemeConfigPublishView.post')
class ThemeConfigPublishView(FXViewRoleInfoMixin, APIView):
    """View to publish theme config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_publish'
    fx_view_description = 'api/fx/config/v1/publish/: Get editable settings of config'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    @staticmethod
    def validate_payload(data: dict, fx_permission_info: dict) -> dict:
        """
        Validates the payload.

        :param data: The payload data from the request
        :param fx_permission_info: The permission info
        :raises FXCodedException: If the payload data is invalid
        """
        tenant_id = data.get('tenant_id')
        if not tenant_id or not isinstance(tenant_id, int):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Tenant id is required and must be an int.'
            )

        if tenant_id not in fx_permission_info['view_allowed_tenant_ids_full_access']:
            raise PermissionDenied(detail=json.dumps(
                {'reason': f'User does not have required access for tenant ({tenant_id})'}
            ))

        draft_hash = data.get('draft_hash')
        if not draft_hash or not isinstance(draft_hash, str):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Draft hash is required and must be a string.'
            )
        current_draft = get_draft_tenant_config(tenant_id=tenant_id)
        current_draft_hash = dict_to_hash(current_draft)
        if current_draft_hash != draft_hash:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Draft hash mismatched with current draft values hash.'
            )
        return current_draft

    @staticmethod
    def rename_keys(updated_fields: dict) -> dict:
        """
        Rename 'published_value' to 'old_value' and 'draft_value' to 'new_value
        """
        renamed_data = {}
        for key, value in updated_fields.items():
            renamed_data[key] = {
                'old_value': value.get('published_value', None),
                'new_value': value.get('draft_value', None)
            }
        return renamed_data

    def post(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        POST /api/fx/config/v1/publish/
        """
        data = request.data
        updated_fields = self.validate_payload(data, self.request.fx_permission_info)
        publish_tenant_config(data['tenant_id'])
        return JsonResponse({'updated_fields': self.rename_keys(updated_fields)})


@docs('ThemeConfigRetrieveView.get')
class ThemeConfigRetrieveView(FXViewRoleInfoMixin, APIView):
    """View to get theme config values"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_values'
    fx_view_description = 'api/fx/config/v1/values/: Get theme config values'
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    def validate_keys(self, tenant_id: int) -> list:
        """Validate keys"""
        keys = self.request.query_params.get('keys', '')
        if keys:
            return keys.split(',')

        return get_accessible_config_keys(user_id=self.request.user.id, tenant_id=tenant_id)

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        GET /api/fx/config/v1/values/
        """
        tenant_id = self.verify_one_tenant_id_provided(request)

        data = get_tenant_config(
            tenant_id,
            self.validate_keys(tenant_id=tenant_id),
            request.query_params.get('published_only', '0') == '1'
        )
        return Response(serializers.TenantConfigSerializer(data, context={'request': request}).data)


@docs('ThemeConfigTenantView.post')
class ThemeConfigTenantView(FXViewRoleInfoMixin, APIView):
    """View to create new Tenant and theme config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_tenant'
    fx_view_description = 'api/fx/config/v1/tenant/: Create new Tenant'

    @staticmethod
    def validate_payload(data: dict) -> None:
        """
        Validates the payload.

        :param data: The payload data from the request
        :raises FXCodedException: If the payload data is invalid
        """
        sub_domain = data.get('sub_domain')
        if not sub_domain:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Subdomain is required.'
            )
        if not isinstance(sub_domain, str):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Subdomain must be a string.'
            )
        if len(sub_domain) > 16:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Subdomain cannot exceed 16 characters.'
            )
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', sub_domain):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=(
                    'Subdomain can only contain letters and numbers and cannot start with a number.'
                )
            )

        platform_name = data.get('platform_name')
        if not platform_name:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Platform name is required.'
            )
        if not isinstance(platform_name, str):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Platform name must be a string.'
            )

        owner_user_id = data.get('owner_user_id')
        if owner_user_id and not get_user_model().objects.filter(id=owner_user_id).exists():
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f'User with ID {owner_user_id} does not exist.'
            )

    def post(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        POST /api/fx/config/v1/tenant/
        """
        data = request.data
        self.validate_payload(data)
        tenant_config = create_new_tenant_config(data['sub_domain'], data['platform_name'])
        owner_user_id = data.get('owner_user_id')
        if owner_user_id:
            add_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=[tenant_config.id],
                user_keys=[data['owner_user_id']],
                role=COURSE_ACCESS_ROLES_STAFF_EDITOR,
                tenant_wide=True,
                course_ids=[],
            )

        result = {'tenant_id': tenant_config.id}
        result.update(get_all_tenants_info()['info'].get(tenant_config.id))
        return JsonResponse(result)
