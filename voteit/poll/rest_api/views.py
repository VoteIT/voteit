from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.mixins import SerializerClassesMixin, CreateModelPermissionsMixin, TransitionsMixin
from voteit.poll.models import *

from . import serializers


__all__ = ['PollViewSet', 'ElectoralRegisterViewSet']


class PollViewSet(
    TransitionsMixin,
    SerializerClassesMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet
):
    model = Poll
    queryset = Poll.objects.all()
    serializer_class = serializers.PollDetailSerializer
    serializer_classes = {
        'list': serializers.PollListSerializer,
        'create': serializers.PollCreateSerializer,
    }
    filter_backends = DjangoFilterBackend,
    filterset_fields = 'agenda_item', 'agenda_item__meeting',
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = 'agenda_item'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        # TODO: Filter out private ai:s
        return self.queryset.filter(agenda_item__meeting__participants=self.request.user)


class ElectoralRegisterViewSet(viewsets.ReadOnlyModelViewSet):
    model = ElectoralRegister
    queryset = ElectoralRegister.objects.all()
    serializer_class = serializers.ElectoralRegisterSerializer

    def get_queryset(self):
        return ElectoralRegister.objects.for_user(self.request.user)
