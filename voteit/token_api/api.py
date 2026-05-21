from datetime import timedelta

from django.utils import timezone
from rest_framework import mixins
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.core.rest_api.utils import validate_model_add
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.token_api.models import MeetingAPIKey
from voteit.token_api.models import create_api_key_user


class MeetingAPIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingAPIKey
        read_only_fields = fields = [
            "prefix",
            "meeting",
            "created",
            "last_used",
            "revoked",
            "expiry_date",
            "name",
            "scopes",
        ]


class MeetingAPIKeyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingAPIKey
        read_only_fields = [
            "prefix",
            "created",
            "last_used",
            "revoked",
            "expiry_date",
        ]
        fields = [
            "name",
            "scopes",
            "meeting",
        ] + read_only_fields

    def validate_meeting(self, value):
        validate_model_add(self, MeetingAPIKey, value)
        return value


@router.register("meeting-api-token", basename="meeting-api-token")
class MeetingApiTokenViewSet(
    VerboseAutoPermissionViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """API-view for the tokens themselves"""

    lookup_field = "prefix"
    lookup_value_regex = r"[A-Za-z0-9]+"
    serializer_class = MeetingAPIKeySerializer
    filterset_class = ForceMeetingWithRoleFilter
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # Checked inside MeetingAPIKeyCreateSerializer.validate_meeting
        "cycle": "change",
    }

    def get_serializer_class(self):
        if self.action == "create":
            return MeetingAPIKeyCreateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        return MeetingAPIKey.objects.filter(
            meeting__roles__user=self.request.user,
            meeting__roles__assigned__contains=ROLE_MODERATOR,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meeting = serializer.validated_data["meeting"]
        api_user = create_api_key_user(meeting)
        expiry_date = timezone.now() + timedelta(days=120)
        obj, key = MeetingAPIKey.objects.create_key(
            **serializer.validated_data, user=api_user, expiry_date=expiry_date
        )
        return Response({**self.get_serializer(obj).data, "key": key}, status=201)

    def perform_destroy(self, instance):
        instance.revoked = True
        instance.save(update_fields=["revoked"])

    @action(methods=["POST"], detail=True)
    def cycle(self, request, prefix=None):
        instance = self.get_object()
        api_user = create_api_key_user(instance.meeting)
        obj, key = MeetingAPIKey.objects.create_key(
            name=instance.name,
            scopes=instance.scopes,
            meeting=instance.meeting,
            user=api_user,
        )
        MeetingAPIKey.objects.filter(pk=instance.pk).delete()
        return Response({**self.get_serializer(obj).data, "key": key}, status=201)
