from django_filters.rest_framework import DjangoFilterBackend
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.base import DefaultModelViewSet, ReadonlyModelViewSet
from voteit.poll.models import *

from . import serializers


__all__ = [
    "PollViewSet",
    "ElectoralRegisterViewSet",
]


class PollViewSet(DefaultModelViewSet):
    serializer_class = serializers.PollDetailSerializer
    serializer_classes = {
        "create": serializers.PollCreateSerializer,
        "list": serializers.PollListSerializer,
    }
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"
    model = Poll
    queryset = Poll.objects.all()
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "agenda_item",
        "meeting",
    )


class ElectoralRegisterViewSet(ReadonlyModelViewSet):
    model = ElectoralRegister
    queryset = ElectoralRegister.objects.all()
    serializer_class = serializers.ElectoralRegisterSerializer

    def get_queryset(self):
        return ElectoralRegister.objects.for_user(self.request.user)
