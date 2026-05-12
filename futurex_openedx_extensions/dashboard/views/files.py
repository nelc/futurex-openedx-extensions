"""Views for serving stored files."""
from __future__ import annotations

import mimetypes
from typing import Any

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from futurex_openedx_extensions.helpers.constants import CONFIG_FILES_UPLOAD_DIR


class TenantAssetServeView(APIView):
    """Public endpoint that serves tenant asset files.

    Only files under `{FX_DASHBOARD_STORAGE_DIR}/{tenant_id}/{CONFIG_FILES_UPLOAD_DIR}/`
    are served. CSV exports and anything else are rejected. No authentication; meant
    to sit behind a CDN.
    """
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request: Any, tenant_id: str, filename: str) -> Any:  # pylint: disable=no-self-use
        """GET /api/fx/assets/v1/serve/<tenant_id>/<filename>"""
        # URL regex (\d+ / [^/]+) already blocks slashes and ensures non-empty values;
        # this guards against path travesal attacks.
        if filename in ('.', '..'):
            raise Http404

        storage_path = '/'.join([
            settings.FX_DASHBOARD_STORAGE_DIR.rstrip('/'),
            tenant_id,
            CONFIG_FILES_UPLOAD_DIR,
            filename,
        ])
        if not default_storage.exists(storage_path):
            raise Http404

        content_type, _ = mimetypes.guess_type(filename)
        response = FileResponse(
            default_storage.open(storage_path, 'rb'),
            content_type=content_type or 'application/octet-stream',
        )
        response['Cache-Control'] = 'public, max-age=86400'
        return response
