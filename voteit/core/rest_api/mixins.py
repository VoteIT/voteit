from abc import ABC
from abc import abstractmethod
from logging import getLogger
from typing import Dict

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.query import QuerySet
from rest_framework import exceptions
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rules.contrib.rest_framework import (
    AutoPermissionViewSetMixin as RulesAutoPermissionViewSetMixin,
)

from voteit.core.rest_api.serializers import FSMTransitionSerializer
from voteit.core.rest_api.serializers import TransitionSerializer
from voteit.core.rest_api.utils import drf_do_transition
from voteit.core.rest_api.utils import get_valid_transitions
from voteit.core.rest_api.utils import get_valid_transitions_dict
from voteit.core.rest_api.utils import perm_denied_msg

logger = getLogger(__name__)


class VerboseAutoPermissionViewSetMixin(RulesAutoPermissionViewSetMixin):
    permission_type_map = {
        **RulesAutoPermissionViewSetMixin.permission_type_map,
        "metadata": None,
        "transitions": None,
    }

    def initial(self, *args, **kwargs):
        try:
            return super().initial(*args, **kwargs)
        except PermissionDenied as exc:
            if self.detail and getattr(settings, "VERBOSE_PERMISSIONS", False):
                obj = self.get_object()
                perm_type = self.permission_type_map[self.action]
                perm = self.get_queryset().model.get_perm(perm_type)
                raise exceptions.PermissionDenied(perm_denied_msg(perm, obj)) from exc
            else:
                raise


class SerializerClassesMixin:
    serializer_classes: Dict[str, Serializer] = {}

    def get_serializer_class(self):
        """
        Use serializer_classes and fall back to serializer_class.
        Return empty serializer for transition actions.
        """
        if self.name == "Transition action":
            return Serializer
        return self.serializer_classes.get(self.action, self.serializer_class)

    def __init_subclass__(cls, **kwargs):
        """
        Make sure subclasses that have 'update' specified also have 'partial_update'
        """
        if (
            "update" in cls.serializer_classes
            and "partial_update" not in cls.serializer_classes
        ):
            logger.warning(
                "%s has 'update' in serializer_classes, but not 'partial_update'. "
                "Adding serializer to partial update too.",
                cls,
            )
            cls.serializer_classes["partial_update"] = cls.serializer_classes["update"]


class ModelContextMixin(ABC):
    context_lookup_kwarg: str = "context"
    context_lookup_field: str = "pk"

    @property
    @abstractmethod
    def context_queryset(self) -> QuerySet:
        """Specify this as a base for lookups. Something like Meeting.objects.all()"""

    def get_context(self, request):
        # FIXME: Request is probably present here already, right?
        lookup_val = request.data.get(self.context_lookup_kwarg)
        # FIXME: Maybe fallback to GET?
        if lookup_val is None:
            lookup_val = request.GET.get(self.context_lookup_kwarg)
        if lookup_val is None:
            raise exceptions.ValidationError(
                detail="%(lookup_kw)s not specified"
                % {"lookup_kw": self.context_lookup_kwarg}
            )
        try:
            return self.context_queryset.get(**{self.context_lookup_field: lookup_val})
        except ObjectDoesNotExist:
            raise exceptions.NotFound(
                "No item found where %(lookup_field)s==%(lookup_val)s"
                % {
                    "lookup_field": self.context_lookup_field,
                    "lookup_val": lookup_val,
                }
            )


class TransitionsMixin(SerializerClassesMixin):
    """
    Note that it only works if the FSM field is called 'state'.
    """

    fsm_field_name: str = "state"

    @action(
        methods=["post", "get"],
        detail=True,
        permission_classes=[permissions.IsAuthenticated],
    )
    def transitions(self, request, pk):
        """
        Generic transitions action for field.
        Checks against available transitions for current user before calling.
        """
        instance = self.get_object()
        if request.method == "GET":
            transitions = sorted(
                get_valid_transitions(instance, attr=self.fsm_field_name),
                key=lambda x: x.name,
            )
            transition_serializer = FSMTransitionSerializer(
                transitions,
                many=True,
                context={"request": request, "instance": instance},
            )
            return Response(transition_serializer.data)
        else:
            transition_name = request.data.get("transition", None)
            valid_transitions = get_valid_transitions_dict(instance)
            with transaction.atomic(durable=True):
                drf_do_transition(
                    instance=instance,
                    field_name=self.fsm_field_name,
                    transition_name=transition_name,
                    valid_transitions=valid_transitions,
                    user=request.user,
                )
                instance.save()
            # TODO Possibly return serialized object, but strictly speaking not necessary.
            new_state = getattr(instance, self.fsm_field_name)
            return Response(status=201, data={self.fsm_field_name: new_state})

    def get_serializer_class(self):
        if self.action == "transitions":
            return TransitionSerializer
        return super().get_serializer_class()
