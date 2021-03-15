from django_filters.rest_framework import DjangoFilterBackend

from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api import serializers


__all__ = ["DiscussionPostViewSet"]


class DiscussionPostViewSet(DefaultModelViewSet):
    model = DiscussionPost
    queryset = DiscussionPost.objects.all()
    serializer_class = serializers.DiscussionPostDetailSerializer
    serializer_classes = {
        "create": serializers.DiscussionPostCreateSerializer,
    }
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "agenda_item",
        "agenda_item__meeting",
    )
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"
