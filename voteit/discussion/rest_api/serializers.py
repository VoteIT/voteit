from rest_framework import serializers
from voteit.discussion import models


__all__ = ("DiscussionPostSerializer",)


class DiscussionPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DiscussionPost
        fields = 'url', 'title', 'agenda_item'
