from rest_framework import serializers


class BaseModelSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        ModelClass = self.Meta.model
        return ModelClass.objects.create(
            author=self.context['request'].user,
            **validated_data
        )
