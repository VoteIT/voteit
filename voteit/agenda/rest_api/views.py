from rest_framework.exceptions import ValidationError

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api import serializers
from voteit.agenda.workflows import AgendaItemWf
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
