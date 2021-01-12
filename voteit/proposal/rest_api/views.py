from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.mixins import CreateModelPermissionsMixin, TransitionsMixin

from voteit.proposal.models import Proposal

from . import serializers


__all__ = ['ProposalViewSet']


class ProposalViewSet(
    TransitionsMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet
):
    model = Proposal
    queryset = Proposal.objects.all()
    serializer_class = serializers.ProposalDetailSerializer
    serializer_classes = {
        'list': serializers.ProposalListSerializer,
    }
    filter_backends = DjangoFilterBackend,
    filterset_fields = 'agenda_item', 'agenda_item__meeting', 'polls'
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = 'agenda_item'

    def get_queryset(self):
        if self.request.user.is_anonymous:
            return self.queryset.none()
        if self.request.user.is_superuser:
            return self.queryset
        # TODO: Filter out private ai:s
        # FIXME: A fix for @schyffel :)
        # return self.queryset
        return self.queryset.filter(agenda_item__meeting__participants=self.request.user)
