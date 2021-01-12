from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from voteit.core.rest_api.mixins import SerializerClassesMixin, CreateModelPermissionsMixin

from voteit.meeting.models import *
from voteit.meeting.rest_api.filters import UserPkFilter

from . import serializers

__all__ = ('MeetingViewSet', 'MeetingRolesViewSet', )


class MeetingViewSet(
    SerializerClassesMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet,
):
    model = Meeting
    queryset = Meeting.objects.all()
    serializer_class = serializers.MeetingSerializer
    serializer_classes = {
        'retrieve': serializers.MeetingDetailSerializer,
        'set_agenda_order': serializers.AgendaOrderSerializer,
    }
    filter_backends = DjangoFilterBackend, SearchFilter,
    search_fields = 'title',
    filterset_fields = 'public',

    @action(methods=['post'], detail=True)
    def set_agenda_order(self, request, pk):
        try:
            order = [int(o) for o in request.data.get('order', '').split(',')]
        except ValueError:
            return Response('Bad order', status=400)
        meeting: Meeting = self.get_object()
        agenda_items = meeting.agenda_items.filter(pk__in=order)
        for i, ai in enumerate(agenda_items):
            ai.order = order.index(ai.pk)
            ai.save()
        return Response(status=201)

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(participants=self.request.user)


class MeetingRolesViewSet(
        SerializerClassesMixin,
        viewsets.ModelViewSet,
):
    model = MeetingRoles
    queryset = MeetingRoles.objects.all()
    serializer_classes = {
        'add_role': serializers.RoleSerializer,
        'remove_role': serializers.RoleSerializer,
        'create': serializers.MeetingAddParticipantSerializer,
    }
    serializer_class = serializers.MeetingRolesSerializer
    filter_backends = DjangoFilterBackend,
    filter_class = UserPkFilter
    permission_classes = permissions.IsAuthenticated,

    def get_queryset(self):
        # TODO who can see?
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(
            context__participants=self.request.user,
        )

    def create(self, request):
        """ Gets or creates role using meeting_id and user_id
            Returns using MeetingRolesSerializer()
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        roles, created = MeetingRoles.objects.get_or_create(
            context_id = serializer.data.get('meeting_id'),
            user_id = serializer.data.get('user_id'),
        )
        serializer = serializers.MeetingRolesSerializer(roles)
        headers = self.get_success_headers(serializer.data)
        if created:
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        return Response(serializer.data, headers=headers)

    # TODO Permissions
    @action(methods=['post'], detail=True, url_path='add-role')
    def add_role(self, request, pk):
        instance: MeetingRoles = self.get_object()
        role_serializer = self.get_serializer(data=request.data)
        role_serializer.is_valid(raise_exception=True)
        role_name = role_serializer.data['role']
        instance.add(role_name)
        return Response(serializers.MeetingRolesSerializer(instance=instance).data)

    # TODO Permissions
    @action(methods=['post'], detail=True, url_path='remove-role')
    def remove_role(self, request, pk):
        instance: MeetingRoles = self.get_object()
        role_serializer = self.get_serializer(data=request.data)
        role_serializer.is_valid(raise_exception=True)
        role_name = role_serializer.data['role']
        if instance.user == request.user and role_name == 'moderator':
            return Response({
                'role': ['Removing yourself as moderator is not allowed.']
            }, status=400)
        instance.remove(role_name)
        return Response(serializers.MeetingRolesSerializer(instance=instance).data)
