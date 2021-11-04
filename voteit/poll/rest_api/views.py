from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.response import Response
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.base import DefaultModelViewSet, ReadonlyModelViewSet
from voteit.poll.models import *
from voteit.poll.registries import er_policy

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
    permission_type_map = {
        **ReadonlyModelViewSet.permission_type_map,
        "methods": None,
    }
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = "meeting",

    def get_queryset(self):
        return ElectoralRegister.objects.for_user(self.request.user)

    @action(detail=False, methods=['GET'])
    def methods(self, request):
        return Response([{
            "name": p.title,            # TODO Translate
            "value": p.name
        } for p in er_policy.values()])
