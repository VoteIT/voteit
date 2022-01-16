from logging import getLogger

from django.conf import settings
from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission


logger = getLogger(__name__)


class HasInviteAPIKey(BasePermission):
    """
    Allows access with a specific header in the request.
    """

    def has_permission(self, request, view):
        try:
            api_key = settings.INVITE_API_KEY
        except AttributeError:
            raise AuthenticationFailed("INVITE_API_KEY not found in settings")
        if not api_key:
            raise AuthenticationFailed("INVITE_API_KEY not set")
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != b"api-key":
            return False
        if len(auth) != 2:
            raise AuthenticationFailed(
                "Invalid auth header, must have format 'api-key XXX'"
            )
        # We're not mucking about with encoding etc here... Bleh
        return auth[1] == api_key.encode()
