from rest_framework import serializers

from voteit.speaker.models import *


class SpeakerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakerList
        fields = "url", "pk", "state"
