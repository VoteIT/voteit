from django_filters.rest_framework import DjangoFilterBackend
from djangorestframework_fsm.viewset_mixins import get_drf_fsm_mixin
from rest_framework import viewsets

from voteit.agenda.models import *
from voteit.agenda.rest_api import serializers
from voteit.core.rest_api.mixins import SerializerClassesMixin, CreateModelPermissionsMixin
from voteit.meeting.models import Meeting


class AgendaViewSet(
    SerializerClassesMixin,
    # TODO: Permissions for fsm mixin
    # get_drf_fsm_mixin(AgendaItem, fieldname='state'),
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
        if self.request.user.is_anonymous:
            return self.queryset.none()
        if self.request.user.is_superuser:
            return self.queryset
        # TODO: Filter out private ai:s
        return self.queryset.filter(meeting__participants=self.request.user)
