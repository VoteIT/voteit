from django_filters.rest_framework import DjangoFilterBackend
from djangorestframework_fsm.viewset_mixins import get_drf_fsm_mixin
from rest_framework import viewsets
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.mixins import SerializerClassesMixin, CreateModelPermissionsMixin

from voteit.proposal.models import Proposal

from . import serializers


__all__ = ['ProposalViewSet']


class ProposalViewSet(
    SerializerClassesMixin,
    # TODO: Permissions for fsm mixin
    # get_drf_fsm_mixin(Proposal, fieldname='state'),
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
    filterset_fields = 'agenda_item', 'agenda_item__meeting',
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = 'agenda_item'

    def get_queryset(self):
        if self.request.user.is_anonymous:
            return self.queryset.none()
        if self.request.user.is_superuser:
            return self.queryset
        # TODO: Filter out private ai:s
        # FIXME: A fix for @schyffel :)
        return self.queryset
        return self.queryset.filter(agenda_item__meeting__participants=self.request.user)
