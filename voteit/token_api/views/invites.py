from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from voteit.core.role import Role
from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api.serializers import InviteCreateSerializer
from voteit.invites.rest_api.serializers import MeetingInviteSerializer
from voteit.invites.statemachines import InviteStateMachine
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.token_api import register_meeting_api
from voteit.token_api.base import MeetingApiBaseViewSet
from voteit.token_api.filters import get_invite_filterset_class


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


class InviteRolesSerializer(serializers.Serializer):
    """
    Change roles on the invite passed as instance. Required roles follow along,
    like for meeting roles: adding proposer adds participant, removing participant
    removes proposer. The result is always kept complete, since syncing an accepted
    invite diffs the user's roles against it -- a missing participant role would
    take the user's other roles with it.

    Moderators are off limits, like on create. Besides the moderator role itself,
    an invite accepted by a moderator can't be changed: syncing it to the user
    would remove the moderator role, which the invite never carries.
    """

    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(MeetingRoles.valid_roles)),
        min_length=1,
    )

    def change(self, current: set[Role], roles: set[Role]) -> set[Role]:
        raise NotImplementedError  # pragma: no cover

    def validate_roles(self, v):
        if ROLE_MODERATOR in v:
            raise serializers.ValidationError(
                "The moderator role can't be changed via the API."
            )
        return v

    def validate(self, attrs):
        invite: MeetingInvite = self.instance
        if ROLE_MODERATOR in invite.roles:
            raise serializers.ValidationError(
                {
                    "roles": "Invites with the moderator role can't be changed via the API."
                }
            )
        if invite.state == InviteStateMachine.accepted.id and invite.meeting.has_roles(
            invite.used_by, ROLE_MODERATOR
        ):
            raise serializers.ValidationError(
                {
                    "roles": "The invite was accepted by a moderator. "
                    "Changing it would downgrade their permissions."
                }
            )
        valid_roles = MeetingRoles.valid_roles
        new_roles = self.change(
            {valid_roles[x] for x in invite.roles},
            {valid_roles[x] for x in attrs["roles"]},
        )
        if not new_roles:
            raise serializers.ValidationError(
                {"roles": "An invite must keep at least one role."}
            )
        attrs["roles"] = sorted(MeetingRoles().get_required_roles(*new_roles))
        return attrs

    def update(self, instance: MeetingInvite, validated_data):
        if validated_data["roles"] != instance.roles:
            instance.change_roles(validated_data["roles"])
        return instance


class InviteAddRolesSerializer(InviteRolesSerializer):
    def change(self, current, roles):
        return current | roles


class InviteRemoveRolesSerializer(InviteRolesSerializer):
    def change(self, current, roles):
        return current - MeetingRoles().get_reverse_required_roles(*roles)


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

    | Action       | Required scope                        |
    |--------------|---------------------------------------|
    | list         | `invites.list` or `invites.*`         |
    | retrieve     | `invites.retrieve` or `invites.*`     |
    | create       | `invites.create` or `invites.*`       |
    | destroy      | `invites.destroy` or `invites.*`      |
    | add_roles    | `invites.add_roles` or `invites.*`    |
    | remove_roles | `invites.remove_roles` or `invites.*` |

    **Query params (list)**

    - Any registered user data key, e.g. `?email=user@example.com`. Values are
      normalised like on create, so email matching isn't case sensitive.
    - `roles` — invites carrying the role, e.g. `?roles=pa`.
    - `state` — e.g. `?state=open`. One of `open`, `accepted`, `rejected`,
      `revoked` or `expired`.

    Separate values with commas to match any of them (`?roles=pa,pr`); different
    params must all match. Invalid values return 400.

    **POST body (create)**

    - `roles` — list of role identifiers, e.g. `["pa"]`. At least one required.
      The moderator role (`mo`) is not accepted.
    - `data` — list of user-data objects, e.g. `[{"email": "user@example.com"}]`.
    - `dryrun` — boolean (default `false`). If `true`, the operation is validated
      and the result returned but nothing is persisted.

    **Changing roles on an invite**

    `POST /{pk}/add-roles/` and `POST /{pk}/remove-roles/` with a body like
    `{"roles": ["pr"]}`. Required roles follow along: adding `pr` also adds `pa`,
    removing `pa` removes every role that requires it. An invite must keep at
    least one role. If the invite was accepted, the user's roles in the meeting
    are updated to match. Returns the invite.

    Moderators can't be managed via this API: a request fails validation if it
    would change an invite with the moderator role, or remove the role from an
    existing moderator. Invites accepted by a moderator can't have their roles
    changed.
    """

    token_api_scope = "invites"
    serializer_class = MeetingInviteSerializer
    action_serializers = {
        "create": InviteCreateViaTokenSerializer,
        "add_roles": InviteAddRolesSerializer,
        "remove_roles": InviteRemoveRolesSerializer,
    }
    filter_backends = [DjangoFilterBackend]

    @property
    def filterset_class(self):
        return get_invite_filterset_class()

    def get_queryset(self):
        if api_key := getattr(self.request, "meeting_api_key", None):
            qs = MeetingInvite.objects.filter(meeting_id=api_key.meeting_id)
            if self.action in ("add_roles", "remove_roles"):
                return qs.select_for_update()
            return qs
        return MeetingInvite.objects.none()

    def get_serializer_class(self):
        return (
            self.action_serializers.get(self.action) or super().get_serializer_class()
        )

    def perform_destroy(self, instance):
        with transaction.atomic(durable=True):
            instance.delete()

    @action(detail=True, methods=["post"], url_path="add-roles")
    def add_roles(self, request, pk=None):
        """
        Add roles to the invite, e.g. `{"roles": ["pr"]}`. Required roles are added too.
        """
        return self._change_roles(request)

    @action(detail=True, methods=["post"], url_path="remove-roles")
    def remove_roles(self, request, pk=None):
        """
        Remove roles from the invite, e.g. `{"roles": ["pr"]}`. Roles that require
        a removed role are removed too.
        """
        return self._change_roles(request)

    def _change_roles(self, request):
        with transaction.atomic(durable=True):
            invite = self.get_object()
            serializer = self.get_serializer(invite, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(
            MeetingInviteSerializer(invite, context=self.get_serializer_context()).data
        )
