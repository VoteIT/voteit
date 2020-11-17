from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.mixins import SerializerClassesMixin, CreateModelPermissionsMixin
from voteit.discussion.models import DiscussionPost

from . import serializers


__all__ = ['DiscussionPostViewSet']


class DiscussionPostViewSet(
    SerializerClassesMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet
):
    model = DiscussionPost
    queryset = DiscussionPost.objects.all()
    serializer_class = serializers.DiscussionPostSerializer
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
