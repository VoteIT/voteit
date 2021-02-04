from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from voteit.core.rest_api.mixins import CreateModelPermissionsMixin, TransitionsMixin

from voteit.meeting.models import *
from voteit.meeting.rest_api.filters import UserPkFilter

from . import serializers

__all__ = ('MeetingViewSet', 'MeetingRolesViewSet', )


class MeetingViewSet(
    TransitionsMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet,
):
    model = Meeting
    queryset = Meeting.objects.all()
    serializer_class = serializers.MeetingDetailSerializer
    serializer_classes = {
        'retrieve': serializers.MeetingDetailSerializer,
        'list': serializers.MeetingSerializer,
        'set_agenda_order': serializers.AgendaOrderSerializer,
    }
    filter_backends = DjangoFilterBackend, SearchFilter,
    search_fields = 'title',
    filterset_fields = 'public',

    @action(methods=['post'], detail=True)
    def set_agenda_order(self, request, pk):
        try:
            order = [int(o) for o in request.data.get('order', '').split(',')]
        except ValueError:
            return Response('Bad order', status=400)
        meeting: Meeting = self.get_object()
        agenda_items = meeting.agenda_items.filter(pk__in=order)
        for i, ai in enumerate(agenda_items):
            ai.order = order.index(ai.pk)
            ai.save()
        return Response(status=201)

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(participants=self.request.user)


class MeetingRolesViewSet(viewsets.ReadOnlyModelViewSet):
    model = MeetingRoles
    queryset = MeetingRoles.objects.all()
    serializer_class = serializers.MeetingRolesSerializer
    filter_backends = DjangoFilterBackend, SearchFilter,
    filter_class = UserPkFilter
    search_fields = '^user__first_name', '^user__last_name',
    permission_classes = permissions.IsAuthenticated,

    def get_queryset(self):
        # TODO who can see?
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(
            context__participants=self.request.user,
        )
