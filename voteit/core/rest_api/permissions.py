from logging import getLogger

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
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


class IsAuthenticated(permissions.IsAuthenticated):
    """
    The default. Users who requested removal are locked out, except from the
    actions a view lists in ``removal_requested_actions``.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.removal_requested is not None and getattr(
            view, "action", None
        ) not in getattr(view, "removal_requested_actions", ()):
            # Raised rather than returned, so "code" ends up in the response
            # body and the frontend can tell this apart from other 403s.
            raise PermissionDenied(
                {
                    "detail": _("Removal of this account has been requested."),
                    "code": "removal_requested",
                }
            )
        return True
