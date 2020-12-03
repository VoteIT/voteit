from contextlib import suppress
from typing import Type, Optional, List

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from voteit.agenda.rest_api.serializers import AgendaListSerializer
from voteit.core.models import Roles

from voteit.meeting import models


UserModel = get_user_model()


class UserRolesMixin(serializers.Serializer):
    current_user_roles = serializers.SerializerMethodField()

    def get_current_user_roles(self, instance) -> Optional[List[str]]:
        """ Return current user roles, if available, for a meeting. """
        if self.context:
            user = self.context['request'].user
            with suppress(ObjectDoesNotExist):
                return instance.roles.get(user=user).assigned


class MeetingSerializer(UserRolesMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Meeting
        fields = 'url', 'pk', 'title', 'state', 'start_time', 'end_time', 'public', 'current_user_roles'


class MeetingDetailSerializer(UserRolesMixin, serializers.ModelSerializer):
    agenda_items = AgendaListSerializer(many=True, read_only=True)

    class Meta:
        model = models.Meeting
        fields = 'title', 'pk', 'state', 'start_time', 'end_time', 'public', 'current_user_roles', 'agenda_items',


class AgendaOrderSerializer(serializers.Serializer):
    order = serializers.CharField()


class ParticipantSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, instance: UserModel):
        return instance.get_full_name()

    class Meta:
        model = UserModel
        fields = 'pk', 'full_name',


class MeetingRolesSerializer(serializers.ModelSerializer):
    meeting = serializers.IntegerField(source='context_id')
    user = ParticipantSerializer()

    class Meta:
        model = models.MeetingRoles
        fields = 'pk', 'user', 'meeting', 'assigned'


class RoleValidator:
    """ Ensures that role name is valid for roles class provided on class instantiation. """
    roles_cls: Type[Roles]

    def __init__(self, roles_cls: Type[Roles]):
        self.roles_cls = roles_cls

    def __call__(self, value):
        if value not in self.roles_cls.valid_roles:
            raise serializers.ValidationError(f'The role "{value}" is not valid for this context.')


class RoleSerializer(serializers.Serializer):
    role = serializers.CharField(max_length=20, validators=[RoleValidator(roles_cls=models.MeetingRoles)])
