from rest_framework import serializers
from voteit.agenda.rest_api.serializers import AgendaListSerializer

from voteit.meeting import models


class MeetingSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Meeting
        fields = 'url', 'title', 'state', 'start_time', 'end_time', 'public'


class MeetingDetailSerializer(serializers.ModelSerializer):
    agenda_items = AgendaListSerializer(many=True, read_only=True)

    class Meta:
        model = models.Meeting
        fields = 'title', 'state', 'start_time', 'end_time', 'public', 'agenda_items',


class AgendaOrderSerializer(serializers.Serializer):
    order = serializers.CharField()
