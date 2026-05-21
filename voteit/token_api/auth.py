from datetime import timedelta

from django.http import HttpRequest
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework_api_key.permissions import BaseHasAPIKey

from voteit.token_api.models import MeetingAPIKey

LAST_USED_UPDATE_THRESHOLD = timedelta(minutes=1)


class MeetingAPIKeyAuthentication(BaseAuthentication, BaseHasAPIKey):
    model = MeetingAPIKey

    def authenticate(self, request):
        if key := self.key_parser.get(request):
            try:
                meeting_api_key = self.model.objects.get_from_key(key)
            except MeetingAPIKey.DoesNotExist:
                raise AuthenticationFailed("Not a valid meeting API key")
            setattr(request, "meeting_api_key", meeting_api_key)
            now = timezone.now()
            if (
                not meeting_api_key.last_used
                or (now - meeting_api_key.last_used) > LAST_USED_UPDATE_THRESHOLD
            ):
                MeetingAPIKey.objects.filter(pk=meeting_api_key.pk).update(
                    last_used=now
                )
            return meeting_api_key.user, None


def _scope_matches(scope: str, resource: str, action: str) -> bool:
    try:
        res_part, act_part = scope.split(".", 1)
    except ValueError:
        return False
    return res_part == resource and (act_part == "*" or act_part == action)


_READ_ONLY_ACTIONS = frozenset({"list", "retrieve", "metadata"})


class MeetingAPIKeyScope(BasePermission):
    def has_permission(self, request: HttpRequest, view) -> bool:
        key = getattr(request, "meeting_api_key", None)
        if key is None:
            # Authenticated session users may access read-only actions; the
            # queryset will be empty so no data is exposed.
            return (
                request.user
                and request.user.is_authenticated
                and getattr(view, "action", None) in _READ_ONLY_ACTIONS
            )
        resource = getattr(view, "token_api_scope", getattr(view, "basename", None))
        action = getattr(view, "action", None)
        if resource is None or action is None:
            return False
        if not any(_scope_matches(s, resource, action) for s in key.scopes):
            raise PermissionDenied(
                f"Scope '{resource}.{action}' or '{resource}.*' is required."
            )
        return True

    def has_object_permission(self, request: HttpRequest, view, obj) -> bool:
        if hasattr(obj, "meeting_id"):
            return request.meeting_api_key.meeting_id == obj.meeting_id
        else:
            return request.meeting_api_key.meeting == obj.meeting
