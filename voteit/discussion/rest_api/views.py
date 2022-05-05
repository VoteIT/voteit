from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api import serializers


__all__ = ["DiscussionPostViewSet"]


@router.register("discussion-posts", basename="discussion-posts")
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

    def get_queryset(self):
        if self.action == "list":
            try:
                ai = self.get_context(self.request)
            except ValidationError:
                ai = None
            if ai and self.request.user.has_perm(AgendaPermissions.VIEW, ai):
                return self.queryset.filter(agenda_item=ai)
            return self.queryset.none()
        return self.queryset
