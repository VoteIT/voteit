from rest_framework import mixins

from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api.serializers import InviteCreateSerializer
from voteit.invites.rest_api.serializers import MeetingInviteSerializer
from voteit.token_api import register_meeting_api
from voteit.token_api.base import MeetingApiBaseViewSet


class InviteCreateViaTokenSerializer(InviteCreateSerializer):
    meeting = None  # removed from input; injected from API key in validate()

    def validate(self, attrs):
        attrs["meeting"] = self.context["request"].meeting_api_key.meeting
        return super().validate(attrs)


@register_meeting_api("invites")
class InvitesView(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    MeetingApiBaseViewSet,
):
    """
    Manage invites for the meeting associated with the API key.

    Authenticate with `Api-Key <key>` in the `Authorization` header.
    The `meeting` field is never accepted in the request body — it is always
    taken from the API key itself.

    **Scopes**

    | Action   | Required scope                    |
    |----------|-----------------------------------|
    | list     | `invites.list` or `invites.*`     |
    | retrieve | `invites.retrieve` or `invites.*` |
    | create   | `invites.create` or `invites.*`   |
    | destroy  | `invites.destroy` or `invites.*`  |

    **POST body (create)**

    - `roles` — list of role identifiers, e.g. `["pa"]`. At least one required.
    - `data` — list of user-data objects, e.g. `[{"email": "user@example.com"}]`.
    - `dryrun` — boolean (default `false`). If `true`, the operation is validated
      and the result returned but nothing is persisted.
    """
    token_api_scope = "invites"
    serializer_class = MeetingInviteSerializer

    def get_queryset(self):
        if api_key := getattr(self.request, "meeting_api_key", None):
            return MeetingInvite.objects.filter(meeting_id=api_key.meeting_id)
        return MeetingInvite.objects.none()

    def get_serializer_class(self):
        if self.action == "create":
            return InviteCreateViaTokenSerializer
        return super().get_serializer_class()
