import csv

from django.http import Http404
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.core.decorators import has_perm_drf
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.proposal.models import TextDocument
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api import serializers
from voteit.proposal.rest_api.serializers import GenericExportProposalSerializer

__all__ = [
    "ProposalViewSet",
    "TextDocumentViewSet",
    "ExportProposalsViewSet",
]


@router.register("proposals", basename="proposal")
class ProposalViewSet(DefaultModelViewSet):
    model = Proposal  # And ALL subtypes!
    queryset = Proposal.objects.all().select_subclasses()
    serializer_class = serializers.GenericProposalSerializer  # Morphic
    serializer_classes = {
        "create": serializers.GenericCreateProposalSerializer,
        "preview": serializers.GenericCreateProposalSerializer,
        "list": serializers.ProposalDetailSerializer,
    }
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "agenda_item",
        "agenda_item__meeting",
    )
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"
    permission_type_map = DefaultModelViewSet.permission_type_map.copy()
    permission_type_map["preview"] = None

    @action(methods=["post"], detail=False)
    def preview(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_representation(serializer.validated_data)
        return Response(data=data)

    def get_queryset(self):
        if self.action == "list":
            # This isn't really necessary for QS since we use websockets
            try:
                ai = self.get_context(self.request)
            except ValidationError:
                ai = None
            if ai and self.request.user.has_perm(AgendaPermissions.VIEW, ai):
                return self.queryset.filter(agenda_item=ai)
            return self.queryset.none()
        return self.queryset


@router.register("text-documents", basename="text-document")
class TextDocumentViewSet(DefaultModelViewSet):
    model = TextDocument
    queryset = TextDocument.objects.all()
    serializer_class = serializers.TextDocumentSerializer
    serializer_classes = {"create": serializers.CreateTextDocumentSerializer}
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "agenda_item",
        "agenda_item__meeting",
    )
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"

    def get_queryset(self):
        if self.action == "list":
            # This isn't really necessary for QS since we use websockets
            try:
                ai = self.get_context(self.request)
            except ValidationError:
                ai = None
            if ai and self.request.user.has_perm(AgendaPermissions.VIEW, ai):
                return self.queryset.filter(agenda_item=ai)
            return self.queryset.none()
        return self.queryset


@router.register("export-proposals", basename="export-proposals")
class ExportProposalsViewSet(viewsets.GenericViewSet):
    model = Proposal  # And subtypes
    permission_classes = [permissions.IsAuthenticated]
    queryset = Meeting.objects.all()
    serializer_class = serializers.GenericExportProposalSerializer  # Morphic

    def list(self, request):
        return Response(data=[])

    def get_export_qs(self, meeting: Meeting):
        return (
            Proposal.objects.all()
            .select_subclasses()
            .prefetch_related("author", "meeting_group", "agenda_item")
            .filter(agenda_item__in=meeting.agenda_items.all())
            .order_by("agenda_item__order", "created")
        )

    @action(
        methods=["get"],
        detail=True,
    )
    @has_perm_drf(MeetingPermissions.MODERATE)
    def csv(self, request, *args, **kwargs):
        meeting = self.get_object()
        export_qs = self.get_export_qs(meeting)
        if not export_qs.exists():
            raise Http404("No data yet")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="proposals_{meeting.pk}_export.csv"'
        )
        # FIXME:Get proper field headers
        fieldnames = GenericExportProposalSerializer.get_all_field_names()
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        for item in export_qs:
            serializer = GenericExportProposalSerializer(item)
            writer.writerow(serializer.data)
        return response

    @action(
        methods=["get"],
        detail=True,
        renderer_classes=[JSONRenderer],
    )
    @has_perm_drf(MeetingPermissions.MODERATE)
    def json(self, request, *args, **kwargs):
        meeting = self.get_object()
        export_qs = self.get_export_qs(meeting)
        data = [self.get_serializer(item).data for item in export_qs]
        return Response(
            data,
            headers={
                "Content-Disposition": f'attachment; filename="proposals_{meeting.pk}_export.json"'
            },
        )
