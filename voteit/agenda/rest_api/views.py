from django_filters.rest_framework import DjangoFilterBackend
from django_fsm import Transition
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from voteit.agenda.models import *
from voteit.agenda.rest_api import serializers
from voteit.core.rest_api.mixins import SerializerClassesMixin, CreateModelPermissionsMixin
from voteit.meeting.models import Meeting


class AgendaViewSet(
    SerializerClassesMixin,
    CreateModelPermissionsMixin,
    viewsets.ModelViewSet,
):
    queryset = AgendaItem.objects.all()
    serializer_class = serializers.AgendaItemSerializer
    serializer_classes = {
        'list': serializers.AgendaListSerializer,
    }
    filter_backends = DjangoFilterBackend,
    filterset_fields = 'meeting',
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = 'meeting'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        # TODO: Filter out private ai:s
        return self.queryset.filter(meeting__participants=self.request.user)

    # TODO Figure out permission class (could be IsAuthenticated)
    # TODO Tests
    # TODO Move to mixin
    @action(methods=['post', 'get'], detail=True, permission_classes=[permissions.IsAdminUser])
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
            name = request.data.get('name')
            if name not in available_transitions:
                return Response({
                    'error': f'Invalid transition: {name}',
                    'available_transitions': available_transitions
                }, status=400)

            getattr(instance, name)()
            instance.save()
            # TODO Possibly return serialized object, but strictly speaking not necessary.
            return Response(status=201)
