from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api import serializers
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions


class AgendaViewSet(DefaultModelViewSet):
    serializer_class = serializers.AgendaItemSerializer
    serializer_classes = {"create": serializers.CreateAgendaItemSerializer}
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    queryset = AgendaItem.objects.all()
    model = AgendaItem

    def get_queryset(self):
        if self.detail == "list":
            meeting = self.get_context(self.request)
            if self.request.user.has_perm(meeting, MeetingPermissions.VIEW):
                queryset = self.queryset.filter(meeting=meeting)
                if not self.request.user.has_perm(meeting, MeetingPermissions.MODERATE):
                    return queryset.exclude(state=AgendaItemWf.PRIVATE)
                return queryset
            else:
                return self.queryset.none()
        return self.queryset
