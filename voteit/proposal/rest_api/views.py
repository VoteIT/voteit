import csv

from django.db import models
from django.http import Http404
from django.http import HttpResponse
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from voteit.core.decorators import has_perm_drf
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.rest_api import serializers
from voteit.proposal.rest_api.serializers import GenericExportProposalSerializer

__all__ = [
    "ProposalViewSet",
    "TextDocumentViewSet",
    "ExportProposalsViewSet",
]


@router.register("proposals", basename="proposal")
class ProposalViewSet(
    VerboseAutoPermissionViewSetMixin, TransitionsMixin, ModelViewSet
):
    serializer_class = serializers.GenericProposalSerializer  # Morphic
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,
        "preview": None,
        "retract": "retract",
    }

    def get_serializer_class(self):
        if self.action in ("preview", "create"):
            return serializers.GenericCreateProposalSerializer
        elif self.action == "list":
            return serializers.ProposalDetailSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        # Proposal and subtypes!
        if self.action == "list":
            return Proposal.objects.none()
        return (
            Proposal.objects.filter(
                models.Q(agenda_item__meeting__roles__user=self.request.user)
                & models.Q(
                    agenda_item__meeting__roles__assigned__contains=ROLE_MODERATOR
                )
                | ~models.Q(agenda_item__state="private")
            )
            .select_subclasses()
            .distinct()
        )

    @action(methods=["post"], detail=False)
    def preview(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_representation(serializer.validated_data)
        return Response(data=data)


@router.register("text-documents", basename="text-document")
class TextDocumentViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = serializers.TextDocumentSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # Handled by qs
        "retrieve": None,
    }

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateTextDocumentSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if self.action == "list":
            return TextDocument.objects.none()
        return TextDocument.objects.filter(
            models.Q(agenda_item__meeting__roles__user=self.request.user)
            & models.Q(agenda_item__meeting__roles__assigned__contains=ROLE_MODERATOR)
            | ~models.Q(agenda_item__state="private")
        ).distinct()


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
