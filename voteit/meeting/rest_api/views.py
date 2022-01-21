from django.db import transaction
from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting import roles
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api.filters import UserPkFilter
from voteit.organisation.models import Organisation

from . import serializers

__all__ = (
    "MeetingViewSet",
    "MeetingRolesViewSet",
    "MeetingGroupViewSet",
)


class MeetingViewSet(DefaultModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingDetailSerializer
    serializer_classes = {
        "list": serializers.MeetingSerializer,
        "set_agenda_order": serializers.AgendaOrderSerializer,
    }
    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
    )
    search_fields = ("title",)
    filterset_fields = ("public",)
    context_queryset = (
        Organisation.objects.none()
    )  # We've overridden get_context instead

    def get_context(self, request):
        """Override to fetch organisation from the user directly"""
        organisation = request.user.organisation
        if organisation is None:
            raise ValidationError(detail=f"User has no related organisation")
        return organisation

    @property
    def permission_type_map(self):
        data = super().permission_type_map.copy()
        data["set_agenda_order"] = "change"
        return data

    @action(methods=["post"], detail=True)
    def set_agenda_order(self, request, pk):
        serializer = serializers.AgendaOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]
        meeting: Meeting = self.get_object()
        agenda_items = meeting.agenda_items.filter(pk__in=order)
        with transaction.atomic():
            for ai in agenda_items:
                ai.order = order.index(ai.pk) + 1
                ai.save()
        return Response(status=201)

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    def perform_create(self, serializer):
        instance: Meeting = serializer.save()
        instance.add_roles(self.request.user, roles.ROLE_MODERATOR)


class MeetingRolesViewSet(viewsets.ReadOnlyModelViewSet):
    model = MeetingRoles
    queryset = MeetingRoles.objects.all()
    serializer_class = serializers.MeetingRolesSerializer
    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
    )
    filter_class = UserPkFilter
    search_fields = (
        "^user__first_name",
        "^user__last_name",
    )
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # TODO who can see?
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(
            context__participants=self.request.user,
        )


class MeetingGroupViewSet(DefaultModelViewSet):
    model = MeetingGroup
    serializer_class = serializers.MeetingGroupSerializer
    context_lookup_kwarg: str = "meeting"
    queryset = MeetingGroup.objects.all()

    @property
    def context_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)
