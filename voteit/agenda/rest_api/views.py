import csv

from django.db.models import QuerySet
from django.http import Http404
from django.http import HttpResponse
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api import serializers
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.decorators import has_perm_drf
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions


@router.register("agenda-items")
class AgendaViewSet(DefaultModelViewSet):
    serializer_class = serializers.AgendaItemSerializer
    serializer_classes = {"create": serializers.CreateAgendaItemSerializer}
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    queryset = AgendaItem.objects.all()
    model = AgendaItem

    def get_queryset(self):
        if self.action == "list":
            try:
                meeting = self.get_context(self.request)
            except ValidationError:
                meeting = None
            if meeting and self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
                queryset = self.queryset.filter(meeting=meeting)
                if self.request.user.has_perm(MeetingPermissions.MODERATE, meeting):
                    return queryset
                return queryset.exclude(state=AgendaItemWf.PRIVATE)
            else:
                return self.queryset.none()
        return self.queryset


@router.register("export-agenda-items", basename="export-agenda-items")
class ExportAgendaItemsViewSet(viewsets.GenericViewSet):
    model = Meeting
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.ExportAgendaItemSerializer

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    def list(self, request):
        return Response(data=[])

    def get_export_qs(self, meeting):
        return meeting.agenda_items.order_by("order")

    @action(
        methods=["get"],
        detail=True,
    )
    @has_perm_drf(MeetingPermissions.MODERATE)
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
    @has_perm_drf(MeetingPermissions.MODERATE)
    def json(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="agenda_items_m{meeting.pk}_export.json"'
            },
        )
