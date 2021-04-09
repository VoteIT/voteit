from abc import ABC, abstractmethod
from typing import Dict

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.query import QuerySet
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework import exceptions
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from voteit.core.utils import get_permission_registry

from .serializers import TransitionSerializer

from django.core.exceptions import ImproperlyConfigured


class AutoPermissionViewSetMixin:
    """
    Modified from rules.contrib.rest_framework

    Enforces object-level permissions in ``rest_framework.viewsets.ViewSet``,
    deriving the permission type from the particular action to be performed.

    Permissions are figured out as follows:
    <app_label>.<perm>_<model_name>

    where permission is any of the values in the permission_type_map
    """

    allow_unauthenticated = False
    permission_type_map = {
        "create": "add",
        "destroy": "delete",
        "list": None,
        "partial_update": "change",
        "retrieve": "view",
        "update": "change",
        "metadata": None,
        "transitions": None,
    }

    def get_model_perm(self, obj, perm_type: str):
        assert perm_type in self.permission_type_map.values()
        ct: ContentType = ContentType.objects.get_for_model(obj)
        app_name, model_name = ct.natural_key()
        perm_name = f"{app_name}.{perm_type}_{model_name}"
        reg = get_permission_registry()
        try:
            # This is to make debugging easier since permission instances have contexts etc
            return reg[perm_name]
        except KeyError:
            return perm_name

    def initial(self, *args, **kwargs):
        """Ensures user has permission to perform the requested action."""
        super().initial(*args, **kwargs)

        if not self.request.user:
            # No user, don't check permission
            if self.allow_unauthenticated:
                return
            else:
                raise self.permission_denied(self.request, f"Unauthenticated")

        # Get the handler for the HTTP method in use
        try:
            if self.request.method.lower() not in self.http_method_names:
                raise AttributeError
            handler = getattr(self, self.request.method.lower())
        except AttributeError:
            # method not supported, will be denied anyway
            return

        try:
            perm_type = self.permission_type_map[self.action]
        except KeyError:
            raise ImproperlyConfigured(
                "AutoPermissionViewSetMixin tried to authorize a request with the "
                "{!r} action, but permission_type_map only contains: {!r}".format(
                    self.action, self.permission_type_map
                )
            )
        if perm_type is None:
            # Skip permission checking for this action
            return

        # Determine whether we've to check object permissions (for detail actions)
        obj = None
        extra_actions = self.get_extra_actions()
        # We have to access the unbound function via __func__
        if handler.__func__ in extra_actions:
            if handler.detail:
                obj = self.get_object()
        # The context mixin handles checks for create permission, should be skip it here?
        elif self.action not in ("create", "list"):
            obj = self.get_object()

        # Finally, check permission
        if obj:
            perm = self.get_model_perm(obj, perm_type)
            if not self.request.user.has_perm(perm, obj):
                raise self.permission_denied(
                    self.request,
                    f"{perm} not allowed for user {self.request.user} on {obj}",
                )


class SerializerClassesMixin:
    serializer_classes: Dict[str, Serializer] = {}

    def get_serializer_class(self):
        """Use serializer_classes and fall back to serializer_class.
        Return empty serializer for transition actions."""
        if self.name == "Transition action":
            return Serializer
        return self.serializer_classes.get(self.action, self.serializer_class)


class ModelContextMixin(ABC):
    context_lookup_kwarg: str = "context"
    context_lookup_field: str = "pk"

    @property
    @abstractmethod
    def context_queryset(self) -> QuerySet:
        """ Specify this as a base for lookups. Something like Meeting.objects.all()"""

    def get_context(self, request):
        # FIXME: Request is probably present here already, right?
        lookup_val = request.data.get(self.context_lookup_kwarg)
        # FIXME: Maybe fallback to GET?
        if lookup_val is None:
            lookup_val = request.GET.get(self.context_lookup_kwarg)
        if lookup_val is None:
            raise exceptions.ValidationError(
                detail=f"{self.context_lookup_kwarg} not specified"
            )
        try:
            return self.context_queryset.get(**{self.context_lookup_field: lookup_val})
        except ObjectDoesNotExist:
            raise exceptions.NotFound(
                detail=f"No item found where {self.context_lookup_field}=={lookup_val}"
            )


class CreateModelPermissionsMixin(
    AutoPermissionViewSetMixin, CreateModelMixin, ModelContextMixin, ABC
):
    create_permission_denied_message: str = "Permission denied"
    _ignore_model_permissions = True

    @property
    @abstractmethod
    def model(self):
        """ Override me"""

    def create(self, request, *args, **kwargs):
        context = self.get_context(request)
        perm = self.get_model_perm(self.model, "add")
        if not request.user.has_perm(perm, context):
            raise self.permission_denied(
                request,
                f"{perm} not allowed for user {request.user} on {context}",
            )
        self.check_object_permissions(request, context)
        return super().create(request, *args, **kwargs)


class TransitionsMixin(SerializerClassesMixin):
    """ Since this is a mixin, it's tested in voteit.agenda.rest_api.tests.test_views"""

    @action(
        methods=["post", "get"],
        detail=True,
        permission_classes=[permissions.IsAuthenticated],
    )
    def transitions(self, request, pk):
        """Generic transitions action for 'state' field.
        Checks against available transitions for current user before calling.
        """
        instance = self.get_object()
        available_transitions = dict(
            (x.name, x)
            for x in instance.get_available_user_state_transitions(request.user)
        )
        if request.method == "GET":
            return Response(
                {"available_transitions": list(available_transitions.keys())}
            )
        else:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            name = serializer.data["transition"]
            if name not in available_transitions:
                return Response(
                    {
                        "error": f"Invalid transition: {name}",
                        "available_transitions": list(available_transitions.keys()),
                    },
                    status=400,
                )
            transition = available_transitions[name]
            if transition.has_perm(instance, request.user):
                getattr(instance, name)()
                instance.save()
                # TODO Possibly return serialized object, but strictly speaking not necessary.
                return Response(status=201)
            else:
                return self.permission_denied(
                    request, f"You need the permission {transition.permission}"
                )

    def get_serializer_class(self):
        if self.action == "transitions":
            return TransitionSerializer
        return super().get_serializer_class()


class DefaultQS:
    def get_queryset(self):
        if self.action in ("list",):  # Permission checks will never work
            if self.request.user.is_superuser:
                return self.queryset
            else:
                return self.queryset.none()
        return self.queryset
