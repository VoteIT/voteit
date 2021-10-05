from django_filters.rest_framework import DjangoFilterBackend

from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api import serializers

__all__ = ["ProposalViewSet"]


class ProposalViewSet(DefaultModelViewSet):
    model = Proposal  # And ALL subtypes!
    queryset = Proposal.objects.all()
    serializer_class = serializers.GenericProposalSerializer  # Morphic
    serializer_classes = {"create": serializers.GenericCreateProposalSerializer}
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "agenda_item",
        "agenda_item__meeting",
    )
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"
