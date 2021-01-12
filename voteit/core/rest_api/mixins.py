from typing import Dict

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.query import QuerySet
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response
from rest_framework.serializers import Serializer

from .serializers import TransitionSerializer


class SerializerClassesMixin:
    serializer_classes: Dict[str, Serializer] = {}

    def get_serializer_class(self):
        """ Use serializer_classes and fall back to serializer_class.
        Return empty serializer for transition actions. """
        if self.name == 'Transition action':
            return Serializer
        return self.serializer_classes.get(self.action, self.serializer_class)


class CreateModelPermissionsMixin(CreateModelMixin):
    context_queryset: QuerySet
    context_lookup_kwarg: str = 'context'
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


class TransitionsMixin(SerializerClassesMixin):
    # TODO Figure out permission class (could be IsAuthenticated)
    # TODO Tests
    @action(methods=['post', 'get'], detail=True, permission_classes=[permissions.IsAuthenticated])
    def transitions(self, request, pk):
        """ Generic transitions action for 'state' field.
            Checks against available transitions for current user before calling.
        """
        instance = self.get_object()
        available_transitions = [t.name for t in instance.get_available_user_state_transitions(request.user)]
        if request.method == 'GET':
            return Response({
                'available_transitions': available_transitions
            })
        else:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            name = serializer.data['transition']
            if name not in available_transitions:
                return Response({
                    'error': f'Invalid transition: {name}',
                    'available_transitions': available_transitions
                }, status=400)

            getattr(instance, name)()
            instance.save()
            # TODO Possibly return serialized object, but strictly speaking not necessary.
            return Response(status=201)

    def get_serializer_class(self):
        if self.action == 'transitions':
            return TransitionSerializer
        return super().get_serializer_class()
