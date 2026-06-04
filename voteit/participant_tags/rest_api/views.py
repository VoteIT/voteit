from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from voteit.core.rest_api import router
from voteit.meeting.models import Meeting
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.participant_tags.rest_api.serializers import DeleteNamespaceSerializer
from voteit.participant_tags.rest_api.serializers import SetTagsSerializer
from voteit.participant_tags.rest_api.serializers import TagsSerializer

if TYPE_CHECKING:
    pass


@router.register("ptags", basename="ptags")
class ParticipantTagsViewSet(
    mixins.ListModelMixin,
    GenericViewSet,
):
    """
    We'll except this from permissions since queryset already narrows down the usage.
    """

    # model = Meeting
    serializer_class = TagsSerializer

    def get_queryset(self):
        return Meeting.objects.filter(
            state__in=[
                MeetingStateMachine.upcoming.value,
                MeetingStateMachine.ongoing.value,
            ],
            participants=self.request.user,
        )

    def list(self, request, *args, **kwargs):  # pragma: no coverage
        return Response(data=[])

    def retrieve(self, request, *args, **kwargs):
        """Mostly for testing"""
        meeting: Meeting = self.get_object()
        ptags = get_object_or_404(meeting.participant_tags, user=self.request.user)
        serializer = self.get_serializer(ptags)
        return Response(serializer.data)

    @action(detail=True, methods=["POST"], serializer_class=SetTagsSerializer)
    def set(self, request, *args, **kwargs):
        meeting: Meeting = self.get_object()
        ptags, created = meeting.participant_tags.get_or_create(user=self.request.user)
        serializer = self.get_serializer(
            ptags,
            data=request.data,
            context={**self.get_serializer_context(), "meeting": meeting},
        )
        serializer.is_valid(raise_exception=True)
        serializer.update(ptags, serializer.validated_data)
        return Response(
            status=created and status.HTTP_201_CREATED or status.HTTP_200_OK,
            data=TagsSerializer(ptags).data,
        )

    @action(
        detail=True,
        url_path="remove-ns",
        methods=["POST"],
        serializer_class=DeleteNamespaceSerializer,
    )
    def remove_ns(self, request, *args, **kwargs):
        meeting: Meeting = self.get_object()
        ptags = get_object_or_404(meeting.participant_tags, user=self.request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = False
        for ns in serializer.validated_data["ns"]:
            if ns in ptags.tags:
                del ptags.tags[ns]
                changed = True
        if changed:
            if ptags.tags:
                ptags.save()
            else:
                ptags.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_200_OK, data=TagsSerializer(ptags).data)

    def destroy(self, request, *args, **kwargs):
        meeting: Meeting = self.get_object()
        deleted = meeting.participant_tags.filter(user=self.request.user).delete()[0]
        return Response(
            status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND
        )
