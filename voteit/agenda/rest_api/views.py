import csv

from django.db import models
from django.db.models import QuerySet
from django.http import Http404
from django.http import HttpResponse
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api import serializers
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.models import Meeting
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.meeting.roles import ROLE_MODERATOR


@router.register("agenda-items")
class AgendaViewSet(VerboseAutoPermissionViewSetMixin, TransitionsMixin, ModelViewSet):
    serializer_class = serializers.AgendaItemSerializer
    filterset_class = ForceMeetingWithRoleFilter
    queryset = AgendaItem.objects.all()
    model = AgendaItem
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # Checked in serializer
        "retrieve": None,  # Limited by queryset
        "update_last_read": None,  # Limited by queryset
    }
    expected_default_http_status = 400

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateAgendaItemSerializer
        return super().get_serializer_class()

    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.LastReadSerializer,
        url_path="update-last-read",
    )
    def update_last_read(self, request, *args, **kwargs):
        instance: AgendaItem = self.get_object()
        last_read = instance.mark_read(request.user)
        serializer = self.get_serializer(last_read)
        return Response(serializer.data)

    def get_queryset(self):
        user = self.request.user
        return (
            AgendaItem.objects.filter(
                # Moderators see all items in their meetings
                models.Q(
                    meeting__roles__user=user,
                    meeting__roles__assigned__contains=ROLE_MODERATOR,
                )
                # Participants see non-private items in their meetings
                | models.Q(meeting__roles__user=user)
                & ~models.Q(state=AgendaItemWf.PRIVATE)
            )
            .select_related("meeting")
            .distinct()
        )


@router.register("export-agenda-items", basename="export-agenda-items")
class ExportAgendaItemsViewSet(viewsets.GenericViewSet):
    model = Meeting
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.ExportAgendaItemSerializer

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.filter(
            roles__user=self.request.user, roles__assigned__contains=ROLE_MODERATOR
        )

    def list(self, request):
        return Response(data=[])

    def get_export_qs(self, meeting):
        return meeting.agenda_items.order_by("order")

    @action(
        methods=["get"],
        detail=True,
    )
    def csv(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        if not serializer.data:
            raise Http404("No data yet")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="agenda_items_m{meeting.pk}_export.csv"'
        )
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
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="agenda_items_m{meeting.pk}_export.json"'
            },
        )
