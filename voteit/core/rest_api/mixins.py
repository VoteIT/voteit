from abc import ABC
from abc import abstractmethod

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.query import QuerySet
from django.utils.encoding import smart_str
from django.utils.module_loading import import_string
from rest_framework import exceptions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.utils import formatting
from rules.contrib.rest_framework import (
    AutoPermissionViewSetMixin as RulesAutoPermissionViewSetMixin,
)
from voteit.core.statemachines import StateMachineModelMixin

from voteit.core.rest_api.serializers import SMEventSerializer
from voteit.core.rest_api.utils import perm_denied_msg


def _sm_to_mermaid(sm_class) -> str:
    lines = ["stateDiagram-v2", f"    [*] --> {sm_class.initial_state.id}"]
    for state in sm_class.states:
        for trans in state.transitions:
            for event in trans.events:
                lines.append(f"    {trans.source.id} --> {trans.target.id}: {event.id}")
        if state.final:
            lines.append(f"    {state.id} --> [*]")
    return "\n".join(lines)


class VerboseAutoPermissionViewSetMixin(RulesAutoPermissionViewSetMixin):
    permission_type_map = {
        **RulesAutoPermissionViewSetMixin.permission_type_map,
        "metadata": None,
        "transitions": None,
    }

    def get_object(self):
        # Cache the fetched object for the lifetime of the request so that
        # AutoPermissionViewSetMixin.initial() and the action handler don't
        # each issue a separate DB query for the same row.
        if not hasattr(self, "_cached_object"):
            self._cached_object = super().get_object()
        return self._cached_object

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


class StateMachineMixin:
    instance: StateMachineModelMixin

    def get_view_description(self, html=False):
        if getattr(self, "action", None) == "event":
            sm_name = getattr(self.model, "state_machine_name", None)
            if sm_name:
                mermaid = _sm_to_mermaid(import_string(sm_name))
                description = (
                    f"Sends an event to the state machine.\n\n```\n{mermaid}\n```"
                )
                description = formatting.dedent(smart_str(description))
                return (
                    formatting.markup_description(description) if html else description
                )
        return super().get_view_description(html=html)

    def get_serializer(self, *args, **kwargs):
        if (
            getattr(self, "action", None) == "event"
            and not args
            and "instance" not in kwargs
        ):
            try:
                kwargs["instance"] = self.get_object()
            except Exception:
                pass
        return super().get_serializer(*args, **kwargs)

    @action(
        detail=True,
        methods=["POST", "GET", "PATCH"],
        serializer_class=SMEventSerializer,
    )
    @transaction.atomic(durable=True)
    def event(self, request, *args, **kwargs):
        """
        Sends an event to the state machine. Events trigger transitions to new states.
        """
        obj = self.get_object()
        if request.method != "GET":
            serializer = self.get_serializer(obj, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(
            data={
                "state": obj.state,
                "events": [e.id for e in obj.sm.allowed_events],
            }
        )
