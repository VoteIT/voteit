import csv

from django.http import Http404
from django.http import HttpResponse
from django.db import models
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
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api import serializers
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions


__all__ = ["DiscussionPostViewSet", "ExportDiscussionPostsViewSet"]


@router.register("discussion-posts", basename="discussion-posts")
class DiscussionPostViewSet(DefaultModelViewSet):
    model = DiscussionPost
    queryset = DiscussionPost.objects.all()
    serializer_class = serializers.DiscussionPostDetailSerializer
    serializer_classes = {
        "create": serializers.DiscussionPostCreateSerializer,
    }
    filterset_fields = (
        "agenda_item",
        "agenda_item__meeting",
    )
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"

    def get_queryset(self):
        if self.action == "list":
            try:
                ai = self.get_context(self.request)
            except ValidationError:
                ai = None
            if ai and self.request.user.has_perm(AgendaPermissions.VIEW, ai):
                return self.queryset.filter(agenda_item=ai)
            return self.queryset.none()
        return self.queryset


@router.register("export-discussion-posts", basename="export-discussion-posts")
class ExportDiscussionPostsViewSet(viewsets.GenericViewSet):
    model = DiscussionPost
    queryset = Meeting.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.DiscussionPostExportSerializer

    def list(self, request):
        return Response(data=[])

    def get_export_qs(self, meeting: Meeting) -> models.QuerySet[DiscussionPost]:
        return (
            DiscussionPost.objects.filter(agenda_item__in=meeting.agenda_items.all())
            .prefetch_related("meeting_group", "author", "agenda_item")
            .order_by("agenda_item__order", "created")
        )

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
            f'attachment; filename="discussion_m{meeting.pk}_export.csv"'
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
                "Content-Disposition": f'attachment; filename="discussion_m{meeting.pk}_export.json"'
            },
        )
