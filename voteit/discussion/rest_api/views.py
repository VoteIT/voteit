import csv

from django.http import Http404
from django.http import HttpResponse
from django.db import models
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet


from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api import serializers
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR


__all__ = [
    "DiscussionPostViewSet",
    "ExportDiscussionPostsViewSet",
]


@router.register("discussion-posts", basename="discussion-posts")
class DiscussionPostViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    model = DiscussionPost
    serializer_class = serializers.DiscussionPostDetailSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # Checked in serializer
        "retrieve": None,  # Filtered by queryset
    }

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.DiscussionPostCreateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if self.action == "list":
            return DiscussionPost.objects.none()
        user = self.request.user
        return DiscussionPost.objects.filter(
            models.Q(
                agenda_item__meeting__roles__user=user,
                agenda_item__meeting__roles__assigned__contains=ROLE_MODERATOR,
            )
            | models.Q(agenda_item__meeting__roles__user=user)
            & ~models.Q(agenda_item__state="private")
        ).select_related("agenda_item__meeting").distinct()


@router.register("export-discussion-posts", basename="export-discussion-posts")
class ExportDiscussionPostsViewSet(viewsets.GenericViewSet):
    model = DiscussionPost
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.DiscussionPostExportSerializer

    def get_queryset(self):
        return Meeting.objects.filter(
            models.Q(roles__user=self.request.user)
            & models.Q(roles__assigned__contains=ROLE_MODERATOR)
        )

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
    def json(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="discussion_m{meeting.pk}_export.json"'
            },
        )
