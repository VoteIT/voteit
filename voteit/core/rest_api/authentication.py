from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """
    DRF answers unauthenticated requests with 401 only if the first
    authentication class provides a WWW-Authenticate value, otherwise 403.
    The frontend relies on 401 to tell "not logged in" apart from 403
    "not allowed" (e.g. a pending removal request).
    """

    def authenticate_header(self, request):
        return "Session"
