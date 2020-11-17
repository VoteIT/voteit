from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.mixins import SerializerClassesMixin, CreateModelPermissionsMixin
from voteit.poll.models import Poll

from . import serializers


__all__ = ['PollViewSet']


class PollViewSet(
    SerializerClassesMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet
):
    model = Poll
    queryset = Poll.objects.all()
    serializer_class = serializers.PollDetailSerializer
    serializer_classes = {
        'list': serializers.PollListSerializer,
    }
    filter_backends = DjangoFilterBackend,
    filterset_fields = 'agenda_item', 'agenda_item__meeting',
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = 'agenda_item'

    def get_queryset(self):
        if self.request.user.is_anonymous:
            return self.queryset.none()
        if self.request.user.is_superuser:
            return self.queryset
        # TODO: Filter out private ai:s
        return self.queryset.filter(agenda_item__meeting__participants=self.request.user)
