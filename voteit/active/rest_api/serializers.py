from __future__ import annotations

from rest_framework import serializers


__all__ = ("ActiveUserSerializer",)


class ActiveUserSerializer(serializers.Serializer):
    active = serializers.BooleanField()


class PurgeInactiveUsersSerializer(serializers.Serializer):
    hours = serializers.IntegerField(default=1, min_value=0, max_value=72)
