import django_filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.filters import ActionAnnotatedDjangoFilterBackend
from voteit.meeting.models import Meeting
from voteit.notes.models import Note
from voteit.notes.rest_api.serializers import CreateNoteSerializer
from voteit.notes.rest_api.serializers import NoteSerializer
from voteit.notes.rest_api.serializers import RelatedMeetingSerializer


def get_meeting_queryset(request):
    return Meeting.objects.for_user(request.user)


class MeetingFilter(django_filters.FilterSet):
    meeting = django_filters.ModelChoiceFilter(
        queryset=get_meeting_queryset,
    )

    def is_valid(self) -> bool:
        if self.is_bound and self.form.is_valid():
            if self.view_action == "list":
                if not self.form.cleaned_data.get("meeting"):
                    self.form.add_error(
                        "meeting", "Required field 'meeting' is missing."
                    )
                    return False
        return super().is_valid()


@router.register("notes", basename="notes")
class NoteViewSet(ModelViewSet):
    serializer_class = NoteSerializer
    filterset_class = MeetingFilter
    filter_backends = (ActionAnnotatedDjangoFilterBackend,)
    expected_default_http_status = 400

    def get_serializer_class(self):
        if self.action == "create":
            return CreateNoteSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        return Note.objects.filter(user=self.request.user)

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
