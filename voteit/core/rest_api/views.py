from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.messages import get_messages
from django.utils.translation import gettext as _
from django.db import models
from django.db import transaction
from rest_framework import filters
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from social_core.actions import do_disconnect
from social_core.exceptions import NotAllowedToDisconnect
from social_django.utils import load_backend
from social_django.utils import load_strategy
from statemachine import registry as sm_registry

from voteit.core import PERM
from voteit.core.loggers import log_auth
from voteit.core.rest_api import router
from voteit.core.rest_api.filters import ActionAnnotatedDjangoFilterBackend
from voteit.core.rest_api.mixins import ModelContextMixin
from voteit.core.rest_api.serializers import LogoutSerializer
from voteit.core.rest_api.serializers import MessageSerializer
from voteit.core.rest_api.serializers import ProviderSerializer
from voteit.core.rest_api.serializers import StateMachineSchemaSerializer
from voteit.core.rest_api.serializers import UserAndRolesSerializer
from voteit.core.rest_api.serializers import UserConnectionSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.core.rest_api.serializers import UserListSerializer
from voteit.core.sessions import end_tracked_sessions
from voteit.core.sessions import forget_session
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.close import close_session_connections
from voteit.messaging.close import close_user_connections
from voteit.messaging.models import LOGGED_OUT
from voteit.messaging.models import LOGGED_OUT_EVERYWHERE
from voteit.organisation.pipeline import _transfer_social_auths
from voteit.organisation import LOGIN_PROVIDER_SESSION_KEY
from voteit.organisation.pipeline import CONNECT_INTENT_SESSION_KEY
from voteit.organisation.utils import get_user_identity_data

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
        """
        The requesting user, plus the other accounts that are the same person.

        identity_id groups those, but it belongs to the id proxy alone -- anyone
        who only ever logged in with another provider has none, and must still
        reach their own row to read or edit it.
        """
        user = self.request.user
        if not user.is_authenticated:
            return User.objects.none()
        query = models.Q(pk=user.pk)
        if user.identity_id:
            query |= models.Q(identity_id=user.identity_id, is_active=True)
        return User.objects.filter(query)

    def list(self, request):
        # get_serializer, not the class: the payload carries session-derived
        # fields, which need the request in context.
        serializer = self.get_serializer(request.user)
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
        # No notice beside the close: the close code says "logged out" by
        # itself -- 4001 for every device, 4000 for this one -- and the client
        # is what knows how to word either.
        if everywhere:
            close_user_connections(
                user_pk,
                code=LOGGED_OUT_EVERYWHERE,
                # Sockets flush their own session on the way out, which is what
                # reaches a device end_tracked_sessions could not name.
                flush_session=True,
            )
        elif session_key:
            close_session_connections(session_key, code=LOGGED_OUT)
        return Response()

    @action(methods=["POST"], detail=True)
    @transaction.atomic(durable=True)
    def switch(self, request, pk):
        user = self.get_object()
        log_auth("Switch user", for_user=user, request=request)
        # Every credential follows, not just the id proxy's: the account being
        # switched to is the same person, and leaving a login method behind on
        # the old row would send the next login straight back to it.
        _transfer_social_auths(request.user, user)
        # login() flushes the session on the way to the other account, and this
        # is not a social login so nothing puts it back. Same person, same
        # provider -- and the client still needs it to log out of that provider.
        login_provider = request.session.get(LOGIN_PROVIDER_SESSION_KEY)
        login(request, user, backend="voteit.core.backends.PrefetchedModelBackend")
        if login_provider:
            request.session[LOGIN_PROVIDER_SESSION_KEY] = login_provider
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

    @action(methods=["GET"], detail=False, serializer_class=UserConnectionSerializer)
    def connections(self, request):
        """
        GET /api/user/connections/ -- the ways this account can be logged into.
        """
        serializer = self.get_serializer(
            request.user.social_auth.order_by("created"), many=True
        )
        return Response(serializer.data)

    @action(methods=["POST"], detail=False, serializer_class=ProviderSerializer)
    def connect(self, request):
        """
        POST /api/user/connect/ -- start attaching another login method.

        Records that the user asked for this, then hands back where to send
        them. Without that record ``require_connect_intent`` treats the
        returning credential as a different person sitting down at an open
        session, which is exactly what it is when nobody pressed this.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.validated_data["provider"]
        request.session[CONNECT_INTENT_SESSION_KEY] = provider.provider_id
        return Response(
            data={
                "provider": provider.provider_id,
                "login_url": provider.backend.get_login_url(provider),
            }
        )

    @action(methods=["POST"], detail=False, serializer_class=ProviderSerializer)
    @transaction.atomic(durable=True)
    def disconnect(self, request):
        """
        POST /api/user/disconnect/ -- remove a login method from this account.

        This is the undo for connecting one, so it has to be reachable by
        someone who never meant to connect it in the first place.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.validated_data["provider"]
        strategy = load_strategy(request)
        backend = load_backend(strategy, provider.provider_id, redirect_uri=None)
        try:
            do_disconnect(backend, request.user)
        except NotAllowedToDisconnect:
            # SOCIAL_AUTH_DISCONNECT_PIPELINE drops the step that raises this,
            # deliberately -- see the note there. Still answered properly in case
            # a deployment puts it back.
            raise ValidationError(
                {"provider": _("You can't remove your only way of signing in.")}
            )
        log_auth(
            "Login method disconnected",
            request=request,
            provider=provider.provider_id,
            context=provider.organisation,
        )
        return Response(status=204)

    @action(methods=["GET"], detail=False)
    def email_choices(self, request):
        emails = get_user_identity_data(request.user).get("email", [])
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
