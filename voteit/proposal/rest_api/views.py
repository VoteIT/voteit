from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.proposal.models import TextDocument
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api import serializers

__all__ = ["ProposalViewSet"]


@router.register("proposals", basename="proposal")
class ProposalViewSet(DefaultModelViewSet):
    model = Proposal  # And ALL subtypes!
    queryset = Proposal.objects.all().select_subclasses()
    serializer_class = serializers.GenericProposalSerializer  # Morphic
    serializer_classes = {
        "create": serializers.GenericCreateProposalSerializer,
        "preview": serializers.GenericCreateProposalSerializer,
    }
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "agenda_item",
        "agenda_item__meeting",
    )
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"
    permission_type_map = DefaultModelViewSet.permission_type_map.copy()
    permission_type_map["preview"] = None

    @action(methods=["post"], detail=False)
    def preview(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_representation(serializer.validated_data)
        return Response(data=data)

    def get_queryset(self):
        if self.action == "list":
            # This isn't really necessary for QS since we use websockets
            try:
                ai = self.get_context(self.request)
            except ValidationError:
                ai = None
            if ai and self.request.user.has_perm(AgendaPermissions.VIEW, ai):
                return self.queryset.filter(agenda_item=ai)
            return self.queryset.none()
        return self.queryset


@router.register("text-documents", basename="text-document")
class TextDocumentViewSet(DefaultModelViewSet):
    model = TextDocument
    queryset = TextDocument.objects.all()
    serializer_class = serializers.TextDocumentSerializer
    serializer_classes = {"create": serializers.CreateTextDocumentSerializer}
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "agenda_item",
        "agenda_item__meeting",
    )
    context_queryset = AgendaItem.objects.all()
    context_lookup_kwarg = "agenda_item"

    def get_queryset(self):
        if self.action == "list":
            # This isn't really necessary for QS since we use websockets
            try:
                ai = self.get_context(self.request)
            except ValidationError:
                ai = None
            if ai and self.request.user.has_perm(AgendaPermissions.VIEW, ai):
                return self.queryset.filter(agenda_item=ai)
            return self.queryset.none()
        return self.queryset
