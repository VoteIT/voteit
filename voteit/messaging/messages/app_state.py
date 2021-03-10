from collections import UserList
from typing import Type

from django.db.models import Model
from django.db.models import QuerySet
from rest_framework.serializers import ModelSerializer
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.envelopes import BaseEnvelope


class AppState(UserList):
    def append(self, item: BaseOutgoingMessage) -> None:
        """ Insert outgoing message into envelope 👅 """
        if not isinstance(item, BaseOutgoingMessage):
            raise ValueError(
                f"AppState can only contain BaseOutgoingMessage, got {type(item)}"
            )
        super().append(
            BaseEnvelope(
                t=item.name,
                p=item.data,
            )
        )

    def append_from(
        self,
        instance: Model,
        serializer_class: Type[ModelSerializer],
        message_class: Type[BaseOutgoingMessage],
    ):
        """ Insert outgoing message from instance, using DRF serializer and message_class """
        data = serializer_class(instance).data
        self.append(message_class(**data))

    def append_from_queryset(
        self,
        queryset: QuerySet,
        serializer_class: Type[ModelSerializer],
        message_class: Type[BaseOutgoingMessage],
    ):
        """ Insert outgoing messages from queryset, using DRF serializer and message class """
        for instance in queryset:
            self.append_from(instance, serializer_class, message_class)
