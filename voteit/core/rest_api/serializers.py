from django.contrib.auth import get_user_model
from rest_framework import serializers


UserModel = get_user_model()


class BaseModelSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        ModelClass = self.Meta.model
        return ModelClass.objects.create(
            author=self.context['request'].user,
            **validated_data
        )


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, instance: UserModel):
        return instance.get_full_name()

    class Meta:
        model = UserModel
        fields = 'pk', 'username', 'full_name', 'first_name', 'last_name',
