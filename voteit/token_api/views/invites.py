from django.db import transaction
from rest_framework import mixins
from rest_framework import serializers

from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api.serializers import InviteCreateSerializer
from voteit.invites.rest_api.serializers import MeetingInviteSerializer
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.token_api import register_meeting_api
from voteit.token_api.base import MeetingApiBaseViewSet


class InviteCreateViaTokenSerializer(InviteCreateSerializer):
    """
    Moderators can't be managed via the token API. The role can't be granted and
    invites carrying it can't be changed. Removing it from existing moderators is
    stopped by the inherited moderator lockout check, which always runs here since
    roles never contain moderator.
    """

    meeting = None  # removed from input; injected from API key in validate()

    def validate_roles(self, v):
        v = super().validate_roles(v)
        if ROLE_MODERATOR in v:
            raise serializers.ValidationError(
                "The moderator role can't be assigned via the API."
            )
        return v

    def validate(self, attrs):
        meeting = attrs["meeting"] = self.context["request"].meeting_api_key.meeting
        reg = get_invite_adapter_registry()
        ud_items = [
            {k: v for k, v in item.items() if k in reg.user_data_keys}
            for item in attrs["data"]
        ]
        existing_qs, _conflicting = meeting.invites.find_mixed_user_data(*ud_items)
        if existing_qs.filter(roles__contains=ROLE_MODERATOR).exists():
            raise serializers.ValidationError(
                {
                    "roles": "Invites with the moderator role can't be changed via the API."
                }
            )
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
      The moderator role (`mo`) is not accepted.
    - `data` — list of user-data objects, e.g. `[{"email": "user@example.com"}]`.
    - `dryrun` — boolean (default `false`). If `true`, the operation is validated
      and the result returned but nothing is persisted.

    Moderators can't be managed via this API: a request fails validation if it
    would change an invite with the moderator role, or remove the role from an
    existing moderator.
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

    def perform_destroy(self, instance):
        with transaction.atomic(durable=True):
            instance.delete()
