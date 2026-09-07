from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.messages import get_messages
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import filters
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from statemachine import registry as sm_registry

from voteit.core import PERM
from voteit.core.loggers import log_auth
from voteit.core.messages.notice import Notice
from voteit.core.rest_api import router
from voteit.core.rest_api.filters import ActionAnnotatedDjangoFilterBackend
from voteit.core.rest_api.mixins import ModelContextMixin
from voteit.core.rest_api.serializers import LogoutSerializer
from voteit.core.rest_api.serializers import MessageSerializer
from voteit.core.rest_api.serializers import StateMachineSchemaSerializer
from voteit.core.rest_api.serializers import UserAndRolesSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.core.rest_api.serializers import UserListSerializer
from voteit.core.sessions import end_tracked_sessions
from voteit.core.sessions import forget_session
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.close import close_session_connections
from voteit.messaging.close import close_user_connections
from voteit.organisation.pipeline import _transfer_social_auths
from voteit.organisation.utils import get_idproxy_user_data

__all__ = ()

User = get_user_model()


@router.register("users", "users")
class UserSearchViewSet(ModelContextMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    filter_backends = (
        ActionAnnotatedDjangoFilterBackend,
        filters.SearchFilter,
    )
    filterset_fields = ("meeting",)
    search_fields = "username", "email", "first_name", "last_name"
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"

    def get_serializer_class(self):
        if self.action == "list":
            return UserListSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """
        User search as follows:
        - superuser: all (basically only during development)
        - org managers: organisation members
        - moderators: all meeting participants
        """
        user = self.request.user
        if user.is_superuser or user.has_perm(
            user.organisation.get_perm(PERM.MANAGE), user.organisation
        ):
            return user.organisation.users.all()
        try:
            meeting = self.get_context(self.request)
        except ValidationError:
            meeting = None
        # FIXME: Public meeting is used in an odd way in frontend. This needs to be cleaned up.
        if meeting and meeting.has_roles(user, ROLE_PARTICIPANT):
            return meeting.participants.all()
        return User.objects.none()


@router.register("user", basename="user")
class UserView(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    A single view to get data for currently logged in user.
    """

    serializer_class = UserAndRolesSerializer

    def get_queryset(self):
        if identity_id := getattr(self.request.user, "identity_id", None):
            return User.objects.filter(identity_id=identity_id, is_active=True)
        return User.objects.none()

    def list(self, request):
        serializer = self.serializer_class(request.user)
        return Response(serializer.data)

    @action(methods=["POST"], detail=False, serializer_class=LogoutSerializer)
    def logout(self, request):
        """End this session, or -- with ``everywhere`` -- all of them.

        Either way the sockets that just lost their login are closed rather
        than left running with an identity that no longer exists: the socket
        scope's user is resolved once, at handshake, so nothing else would ever
        tell them.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        everywhere = serializer.validated_data["everywhere"]
        # Both are read before logout(): afterwards request.user is anonymous
        # and the session key is gone.
        user_pk = request.user.pk
        session_key = request.session.session_key
        log_auth("Logout everywhere" if everywhere else "Logout", request=request)
        if everywhere:
            # First, so no in-flight request can refresh a session that is
            # about to be killed.
            end_tracked_sessions(user_pk)
        elif session_key:
            forget_session(user_pk, session_key)
        logout(request)
        if everywhere:
            close_user_connections(
                user_pk,
                # Sockets flush their own session on the way out, which is what
                # reaches a device end_tracked_sessions could not name.
                flush_session=True,
                notice=Notice(
                    payload={
                        "type": "info",
                        "message": _("You have been logged out on all devices."),
                    }
                ),
            )
        elif session_key:
            close_session_connections(
                session_key,
                notice=Notice(
                    payload={
                        "type": "info",
                        "message": _("You have been logged out."),
                    }
                ),
            )
        return Response()

    @action(methods=["POST"], detail=True)
    @transaction.atomic(durable=True)
    def switch(self, request, pk):
        user = self.get_object()
        log_auth("Switch user", for_user=user, request=request)
        _transfer_social_auths(request.user, user, "idproxy")
        login(request, user, backend="voteit.core.backends.PrefetchedModelBackend")
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def alternate(self, request):
        if request.user.identity_id:
            qs = self.get_queryset().exclude(pk=request.user.pk)
        else:
            qs = User.objects.none()
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def email_choices(self, request):
        emails = get_idproxy_user_data(request.user).get("email", [])
        return Response(data={"emails": sorted(emails)})

    @action(
        ["get"],
        detail=False,
        serializer_class=MessageSerializer,
        permission_classes=[AllowAny],
    )
    def messages(self, request, *args, **kwargs):
        messages = get_messages(request)
        serializer = self.get_serializer(messages, many=True)
        return Response(data=serializer.data)


@router.register("health", basename="health")
class HealthCheckView(GenericViewSet):
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        return Response("OK!")


@router.register("state-machines", basename="state-machines")
class StateMachinesViewSet(GenericViewSet):
    """
    Read-only schema registry for all VoteIT state machines. No authentication required.

    Each entry describes the states, events, and transitions of one state machine class.
    The frontend uses this to render state labels, available action buttons, and transition
    graphs without needing per-resource requests.

    Response shape:

        {
          "<MachineName>": {
            "states": {
              "<state_id>": {"name": "...", "initial": true}   // initial/final only present when true
            },
            "events": {
              "<event_id>": {
                "name": "...",
                "transitions": [
                  {
                    "from": "<state_id>",
                    "to": "<state_id>",
                    "validators": ["<name>", ...],  // backend guards; mirrored in frontend checks
                    "cond": ["<name>", ...]          // conditional guards (evaluated server-side)
                  }
                ]
              }
            }
          }
        }

    List:    GET /api/state-machines/                    — all machines
    Detail:  GET /api/state-machines/<MachineName>/      — single machine, 404 if unknown
    """

    permission_classes = [permissions.AllowAny]

    def _voteit_machines(self):
        sm_registry.init_registry()
        return {
            cls.__name__: cls
            for qn, cls in sm_registry._REGISTRY.items()
            if qn.startswith("voteit.")
        }

    def list(self, request, *args, **kwargs):
        return Response(
            {
                name: StateMachineSchemaSerializer(cls).data
                for name, cls in self._voteit_machines().items()
            }
        )

    def retrieve(self, request, pk=None, *args, **kwargs):
        machines = self._voteit_machines()
        if pk not in machines:
            return Response(status=404)
        return Response(StateMachineSchemaSerializer(machines[pk]).data)
