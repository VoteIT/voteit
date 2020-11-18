from typing import Dict

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.query import QuerySet
from rest_framework.mixins import CreateModelMixin
from rest_framework.permissions import DjangoObjectPermissions, IsAuthenticated
from rest_framework.serializers import Serializer


class SerializerClassesMixin:
    serializer_classes: Dict[str, Serializer] = {}

    def get_serializer_class(self):
        """ Use serializer_classes and fall back to serializer_class.
        Return empty serializer for transition actions. """
        if self.name == 'Transition action':
            return Serializer
        return self.serializer_classes.get(self.action, self.serializer_class)


class CreateModelPermissionsMixin(CreateModelMixin):
    permission_classes = IsAuthenticated, DjangoObjectPermissions
    context_queryset: QuerySet
    context_lookup_kwarg: str
    context_lookup_field: str = 'pk'
    _ignore_model_permissions = True

    def create(self, request, *args, **kwargs):
        try:
            context = self.context_queryset.get(
                **{self.context_lookup_field: request.data.get(self.context_lookup_kwarg)}
            )
        except ObjectDoesNotExist:
            self.permission_denied(request, 'Agenda item not found')
        else:
            self.check_object_permissions(request, context)
            return super().create(request, *args, **kwargs)
