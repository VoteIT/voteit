from abc import ABC

from auditlog.context import auditlog_value
from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.renderers import JSONRenderer

from voteit.token_api.auth import MeetingAPIKeyAuthentication
from voteit.token_api.auth import MeetingAPIKeyScope


class MeetingApiBaseViewSet(viewsets.GenericViewSet, ABC):
    # Override token_api_scope to set the resource name used in scope matching.
    # Defaults to view.basename (set by the DRF router). Scopes are stored as
    # "<resource>.<action>" strings, e.g. "invites.list" or "invites.*".
    token_api_scope: str | None = None
    authentication_classes = [MeetingAPIKeyAuthentication, SessionAuthentication]
    permission_classes = [MeetingAPIKeyScope]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    filter_backends = []

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # AuditlogMiddleware captures request.user before DRF authentication runs,
        # leaving the actor as None. Mutate the existing context dict in-place now
        # that DRF has resolved the real user, so all writes in this request are
        # attributed correctly without disturbing the middleware's signal setup.
        try:
            auditlog_value.get()["actor"] = request.user
        except LookupError:
            pass

    def get_queryset(self):
        if not getattr(self.request, "meeting_api_key", None):
            return super().get_queryset().none()
        return super().get_queryset()
