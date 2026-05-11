from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from voteit.core.rest_api import router
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.notes.models import Note
from voteit.notes.rest_api.serializers import CreateNoteSerializer
from voteit.notes.rest_api.serializers import NoteSerializer
from voteit.notes.rest_api.serializers import RelatedMeetingSerializer


@router.register("notes", basename="notes")
class NoteViewSet(ModelViewSet):
    serializer_class = NoteSerializer
    filterset_class = ForceMeetingWithRoleFilter
    expected_default_http_status = 400

    def get_serializer_class(self):
        if self.action == "create":
            return CreateNoteSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        return Note.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        headers = self.get_success_headers(serializer.data)
        created = getattr(serializer, "_created", True)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            headers=headers,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="delete-all",
        serializer_class=RelatedMeetingSerializer,
    )
    def delete_all(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meeting = serializer.validated_data["meeting"]
        request.user.notes.filter(meeting=meeting).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
