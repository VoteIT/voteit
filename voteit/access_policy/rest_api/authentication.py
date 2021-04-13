from django.conf import settings
from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed


class InviteBasicAuthentication(BasicAuthentication):
    """
    Check if username exists in settings.INVITE_SERVICE_USERS
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            user = result[0]
            try:
                service_users = settings.INVITE_SERVICE_USERS
            except AttributeError:
                raise AuthenticationFailed("INVITE_SERVICE_USERS not specified")
            if user.username in service_users:
                return result
            else:
                raise AuthenticationFailed("Not an allowed invite service user")
        return result
