from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from voteit.agenda.models import *
from voteit.agenda.rest_api import serializers
from voteit.core.rest_api.mixins import TransitionsMixin, CreateModelPermissionsMixin
from voteit.meeting.models import Meeting


class AgendaViewSet(
    TransitionsMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet,
):
    queryset = AgendaItem.objects.all()
    serializer_class = serializers.AgendaItemSerializer
    serializer_classes = {
        'list': serializers.AgendaListSerializer,
    }
    filter_backends = DjangoFilterBackend,
    filterset_fields = 'meeting',
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = 'meeting'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        # TODO: Filter out private ai:s
        return self.queryset.filter(meeting__participants=self.request.user)
