from django_filters.rest_framework import DjangoFilterBackend
from djangorestframework_fsm.viewset_mixins import get_drf_fsm_mixin
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from voteit.core.rest_api.mixins import SerializerClassesMixin

from voteit.meeting.models import *
from . import serializers

__all__ = ('MeetingViewSet',)


class MeetingViewSet(
    SerializerClassesMixin,
    # TODO: Permissions for fsm mixin
    # get_drf_fsm_mixin(Meeting, fieldname='state'),
    viewsets.ModelViewSet,
):
    permission_classes = [permissions.AllowAny]  # FIXME No, ofc not!
    model = Meeting
    queryset = Meeting.objects.all()
    serializer_class = serializers.MeetingSerializer
    serializer_classes = {
        'retrieve': serializers.MeetingDetailSerializer,
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

    # FIXME Uncomment this!
    # def get_queryset(self):
    #     if self.request.user.is_anonymous:
    #         return self.queryset.none()
    #     if self.request.user.is_superuser:
    #         return self.queryset
    #     return self.queryset.filter(participants=self.request.user)
