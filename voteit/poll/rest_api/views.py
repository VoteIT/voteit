import csv

from django.contrib.auth import get_user_model
from django.db import models
from django.http import Http404
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.viewsets import ViewSet

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.base import ReadonlyModelViewSet
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.mixins import SerializerClassesMixin
from voteit.meeting.permissions import MeetingPermissions
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import VoteTransfer
from voteit.poll.rest_api import serializers
from voteit.poll.schemas import ElectoralRegistryPolicySchema
from voteit.poll.utils import get_electoral_policy_registry

__all__ = (
    "PollViewSet",
    "ElectoralRegisterViewSet",
    "ElectoralRegisterPoliciesViewSet",
    "ExportERViewSet",
)

User = get_user_model()


@router.register("polls")
class PollViewSet(DefaultModelViewSet):
    serializer_class = serializers.PollDetailSerializer
    serializer_classes = {
        "create": serializers.PollCreateSerializer,
        "list": serializers.PollListSerializer,
    }
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"
    model = Poll
    queryset = Poll.objects.all()
    filterset_fields = (
        "agenda_item",
        "meeting",
    )

    def get_queryset(self):
        if self.detail:
            return self.queryset
        # This isn't really necessary for QS since we use websockets
        try:
            ai = self.get_context(self.request)
        except ValidationError:
            ai = None
        if ai and self.request.user.has_perm(AgendaPermissions.VIEW, ai):
            return self.queryset.filter(agenda_item=ai)
        return self.queryset.none()


@router.register("electoral-registers", basename="electoral-registers")
class ElectoralRegisterViewSet(ReadonlyModelViewSet):
    model = ElectoralRegister
    serializer_class = serializers.ElectoralRegisterSerializer
    filterset_fields = ("meeting",)

    def get_queryset(self):
        return ElectoralRegister.objects.for_user(self.request.user)

    @method_decorator(cache_page(60 * 60 * 24 * 7))
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


@router.register("vote-transfer", basename="vote-transfer")
class VoteTransferViewSet(
    AutoPermissionViewSetMixin,
    SerializerClassesMixin,
    ModelViewSet,
):
    serializer_class = serializers.VoteTransferSerializer
    serializer_classes = {
        "update": serializers.VoteTransferReassignSerializer,
        "partial_update": serializers.VoteTransferReassignSerializer,
    }
    model = VoteTransfer
    queryset = VoteTransfer.objects.all()

    def get_queryset(self):
        if self.action == "list":
            return VoteTransfer.objects.filter(
                models.Q(source=self.request.user) | models.Q(target=self.request.user)
            )
        # Perms handle the rest
        return VoteTransfer.objects.select_related("source", "target", "meeting").all()


@router.register("electoral-register-policies", basename="electoral-register-policies")
class ElectoralRegisterPoliciesViewSet(ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        reg = get_electoral_policy_registry()
        results = []
        for er_policy in reg.values():
            data = ElectoralRegistryPolicySchema.from_orm(er_policy)
            results.append(data.dict())
        return Response(data=results)


@router.register("export-electoral-register", basename="export-electoral-register")
class ExportERViewSet(viewsets.GenericViewSet):
    model = ElectoralRegister
    permission_classes = [permissions.IsAuthenticated]
    queryset = ElectoralRegister.objects.all().prefetch_related("meeting")
    serializer_class = serializers.VoterExportSerializer

    def list(self, request):
        return Response(data=[])

    def get_export_qs(self, er: ElectoralRegister):
        return (
            er.voterweight_set.all()
            .prefetch_related("user")
            .order_by("user__first_name")
        )

    def get_er(self, request):
        er: ElectoralRegister = self.get_object()
        if not request.user.has_perm(MeetingPermissions.MODERATE, er.meeting):
            raise PermissionDenied(
                f"Missing required permission {MeetingPermissions.MODERATE}"
            )
        return er

    @action(
        methods=["get"],
        detail=True,
    )
    def csv(self, request, *args, **kwargs):
        er = self.get_er(request)
        if not er.voterweight_set.exists():
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
        er = self.get_er(request)
        serializer = self.get_serializer(self.get_export_qs(er), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="er_{er.pk}_export.json"'
            },
        )
