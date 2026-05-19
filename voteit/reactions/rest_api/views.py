from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.http import Http404
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.core.utils import get_model_shortname
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.reactions import PERM_LIST_REACTIONS
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton
from voteit.reactions.rest_api import serializers


@router.register("reaction-buttons", basename="reaction-buttons")
class ReactionButtonViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = serializers.ButtonDetailSerializer
    filterset_class = ForceMeetingWithRoleFilter
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "retrieve": None,
        "set": "set",
        "remove": "remove",
        "list_reactions": PERM_LIST_REACTIONS,
    }
    expected_default_http_status = 400

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.ButtonCreateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        return ReactionButton.objects.filter(meeting__participants=self.request.user)

    def _get_reactable(
        self, *, button: ReactionButton, object_id: int, content_type: ContentType
    ):
        model = content_type.model_class()
        if get_model_shortname(model) not in button.allowed_models:
            raise ValidationError(
                {
                    "content_type": "This reaction button does not support this content type."
                }
            )
        try:
            return model.objects.get(
                pk=object_id, agenda_item__meeting_id=button.meeting_id
            )
        except model.DoesNotExist:
            raise Http404

    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.ReactionTargetSerializer,
    )
    @transaction.atomic(durable=True)
    def set(self, request, *args, **kwargs):
        button: ReactionButton = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reactable = self._get_reactable(button=button, **serializer.validated_data)
        ai_pk = getattr(reactable, "agenda_item_id", None)
        set_data = {**serializer.validated_data, "agenda_item_id": ai_pk}
        if button.flag_mode:
            set_data["defaults"] = {"user": request.user}
        else:
            set_data["user"] = request.user
        reaction, created = button.reactions.get_or_create(**set_data)
        return Response(
            serializers.ReactionSerializer(reaction).data,
            status=201 if created else 200,
        )

    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.ReactionTargetSerializer,
    )
    @transaction.atomic(durable=True)
    def remove(self, request, *args, **kwargs):
        button: ReactionButton = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ct = serializer.validated_data["content_type"]
        oid = serializer.validated_data["object_id"]
        qs = Reaction.objects.filter(content_type=ct, object_id=oid, button=button)
        if not button.flag_mode:
            qs = qs.filter(user=request.user)
        qs.delete()
        return Response(status=204)

    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.ReactionTargetSerializer,
        url_path="list-reactions",
    )
    def list_reactions(self, request, *args, **kwargs):
        button: ReactionButton = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_ids = list(
            button.reactions.filter(**serializer.validated_data).values_list(
                "user_id", flat=True
            )
        )
        return Response({"users": user_ids})
