import csv

from django.contrib.auth import get_user_model
from django.db import models
from django.db import transaction
from django.http import Http404
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.viewsets import ViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import StateMachineMixin
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.models import VoteTransfer
from voteit.poll.rest_api import serializers
from voteit.poll.schemas import ElectoralRegistryPolicySchema
from voteit.poll.utils import get_electoral_policy_registry

__all__ = ()

User = get_user_model()


@router.register("polls", basename="poll")
class PollViewSet(VerboseAutoPermissionViewSetMixin, StateMachineMixin, ModelViewSet):
    serializer_class = serializers.PollDetailSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "retrieve": None,
        "create": None,  # In serializer
        "event": None,
        "state_machine": None,
    }
    filterset_fields = (
        "agenda_item",
        "meeting",
    )

    def get_queryset(self):
        return Poll.objects.filter(
            models.Q(meeting__roles__user=self.request.user)
            & (
                models.Q(meeting__roles__assigned__contains=ROLE_MODERATOR)
                | (~models.Q(state="private") & ~models.Q(agenda_item__state="private"))
            )
        ).distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.PollCreateSerializer
        elif self.action == "list":
            return serializers.PollListSerializer
        return super().get_serializer_class()


@router.register("electoral-registers", basename="electoral-registers")
class ElectoralRegisterViewSet(ReadOnlyModelViewSet):
    serializer_class = serializers.ElectoralRegisterSerializer
    filterset_class = ForceMeetingWithRoleFilter
    # filterset_fields = ("meeting",)
    expected_default_http_status = 400

    def get_queryset(self):
        return ElectoralRegister.objects.for_user(self.request.user)

    @method_decorator(cache_page(60 * 60 * 24 * 7))
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(
        detail=False,
        methods=["post"],
        serializer_class=serializers.TriggerCreateERSerializer,
        url_path="trigger-create",
    )
    @transaction.atomic
    def trigger_create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if serializer._created:
            return Response(
                serializers.ElectoralRegisterSerializer(
                    serializer._er, context={"request": request}
                ).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=["post"],
        serializer_class=serializers.ManualCreateERSerializer,
        url_path="manual-create",
    )
    @transaction.atomic
    def manual_create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if serializer._created:
            return Response(
                serializers.ElectoralRegisterSerializer(
                    serializer._er, context={"request": request}
                ).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


@router.register("vote-transfer", basename="vote-transfer")
class VoteTransferViewSet(
    VerboseAutoPermissionViewSetMixin,
    ModelViewSet,
):
    serializer_class = serializers.VoteTransferSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "retrieve": None,
        "create": None,  # Checked in serializer
    }

    def get_queryset(self):
        qs = VoteTransfer.objects.filter(
            models.Q(source=self.request.user)
            | models.Q(target=self.request.user)
            | models.Q(
                meeting__roles__user=self.request.user,
                meeting__roles__assigned__contains=ROLE_MODERATOR,
            )
        )
        if self.action == "retrieve":
            qs = qs.select_related("source", "target", "meeting")
        return qs.distinct()

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return serializers.VoteTransferReassignSerializer
        return super().get_serializer_class()


@router.register("votes", basename="vote")
class VoteViewSet(VerboseAutoPermissionViewSetMixin, viewsets.GenericViewSet):
    """Create-only - there's no list/retrieve, votes are fetched via WS on subscribe."""

    queryset = Vote.objects.none()
    serializer_class = serializers.VoteAddSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # Checked in serializer via poll field
    }
    expected_default_http_status = 405

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vote = serializer.save()
        response_status = (
            status.HTTP_201_CREATED if serializer._created else status.HTTP_200_OK
        )
        return Response(
            serializers.VoteSerializer(
                vote, context=self.get_serializer_context()
            ).data,
            status=response_status,
        )


@router.register("electoral-register-policies", basename="electoral-register-policies")
class ElectoralRegisterPoliciesViewSet(ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        reg = get_electoral_policy_registry()
        results = []
        for er_policy in reg.values():
            data = ElectoralRegistryPolicySchema.model_validate(er_policy)
            results.append(data.model_dump())
        return Response(data=results)


@router.register("export-electoral-register", basename="export-electoral-register")
class ExportERViewSet(viewsets.GenericViewSet):
    model = ElectoralRegister
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.VoterExportSerializer

    def get_queryset(self):
        return ElectoralRegister.objects.for_user(self.request.user).prefetch_related(
            "meeting"
        )

    def list(self, request):
        return Response(data=[])

    def get_export_qs(self, er: ElectoralRegister):
        User = get_user_model()
        voter_data = er.voter_data
        users = User.objects.filter(pk__in=voter_data.keys()).order_by("first_name")
        return [
            {
                "first_name": u.first_name,
                "last_name": u.last_name,
                "email": u.email,
                "userid": u.userid,
                "weight": voter_data[str(u.pk)],
            }
            for u in users
        ]

    @action(
        methods=["get"],
        detail=True,
    )
    def csv(self, request, *args, **kwargs):
        er = self.get_object()
        if not er.voter_data:
            raise Http404("No data yet")
        serializer = self.get_serializer(self.get_export_qs(er), many=True)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="er_{er.pk}_export.csv"'
        )
        # FIXME:Get proper field headers
        writer = csv.DictWriter(response, fieldnames=serializer.child.fields)
        writer.writeheader()
        for row in serializer.data:
            writer.writerow(row)
        return response

    @action(
        methods=["get"],
        detail=True,
        renderer_classes=[JSONRenderer],
    )
    def json(self, request, *args, **kwargs):
        er = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(er), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="er_{er.pk}_export.json"'
            },
        )
