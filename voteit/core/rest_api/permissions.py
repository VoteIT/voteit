from logging import getLogger

from django.conf import settings
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission


logger = getLogger(__name__)


class HasIDProxyAPIKey(BasePermission):
    """
    Allows access with a specific header in the request.
    """

    def has_permission(self, request, view):
        if hasattr(request, "user") and request.user.is_superuser:
            return True
        try:
            api_key = settings.ID_PROXY_API_KEY
        except AttributeError:
            raise AuthenticationFailed("ID_PROXY_API_KEY not found in settings")
        if not api_key:
            raise AuthenticationFailed("ID_PROXY_API_KEY not set")
        auth = request.META.get("HTTP_API_KEY", None)
        if auth is None:
            raise AuthenticationFailed("Missing Api-Key header")
        if isinstance(auth, str):
            # Work around django test client oddness
            auth = auth.encode(HTTP_HEADER_ENCODING)
        if auth != api_key.encode(HTTP_HEADER_ENCODING):
            raise AuthenticationFailed("Bad Api-Key")
        return True
