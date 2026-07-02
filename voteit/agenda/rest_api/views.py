import csv
from logging import getLogger

from django.db import models
from django.db import transaction
from django.db.models import QuerySet
from django.http import Http404
from django.http import HttpResponse
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from statemachine.exceptions import TransitionNotAllowed

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api import serializers
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import StateMachineMixin
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.models import Meeting
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.meeting.roles import ROLE_MODERATOR

logger = getLogger(__name__)


@router.register("agenda-items")
class AgendaViewSet(VerboseAutoPermissionViewSetMixin, StateMachineMixin, ModelViewSet):
    serializer_class = serializers.AgendaItemSerializer
    filterset_class = ForceMeetingWithRoleFilter
    queryset = AgendaItem.objects.all()
    model = AgendaItem
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # Checked in serializer
        "retrieve": None,  # Limited by queryset
        "update_last_read": None,  # Limited by queryset
        "event": None,  # Permission checked inside SM validators
        "state_machine": None,
        "bulk_change": None,  # Meeting field restricts to moderators
        "bulk_delete": None,  # Meeting field restricts to moderators
    }
    expected_default_http_status = 400

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateAgendaItemSerializer
        return super().get_serializer_class()

    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.LastReadSerializer,
        url_path="update-last-read",
    )
    def update_last_read(self, request, *args, **kwargs):
        instance: AgendaItem = self.get_object()
        last_read = instance.mark_read(request.user)
        serializer = self.get_serializer(last_read)
        return Response(serializer.data)

    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.BulkAgendaItemChangeSerializer,
        url_path="bulk-change",
    )
    def bulk_change(self, request, *args, **kwargs):
        """
        POST /api/agenda-items/bulk-change/

        Request:  {"meeting": 1, "agenda_items": [1, 2, 3], "state": "ongoing"}
        Response: {"changed": 2}

        `state`, `block_discussion` and/or `block_proposals` may be combined
        in one request; at least one is required. State changes go through
        the state machine (`ai.sm.send`), so items where the transition isn't
        allowed (e.g. wrong source state, ongoing polls) are silently skipped
        rather than raising - mirrors the single-item /event/ endpoint's guards.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        agenda_items: list[AgendaItem] = vd["agenda_items"]
        must_save = set()
        target_state = vd.get("state")
        # Remember! We can't reload or change queryset when we touch several attributes.
        if target_state:
            for ai in agenda_items:
                if ai.state == target_state:
                    continue
                for event in ai.sm.allowed_events:
                    transitions = [
                        t
                        for state in ai.sm.configuration
                        for t in state.transitions
                        if event in t.events
                    ]
                    for trans in transitions:
                        if trans.target.value == target_state:
                            try:
                                ai.sm.send(event.id, user=request.user)
                                if ai.state == target_state:
                                    must_save.add(ai)
                            except (ValidationError, TransitionNotAllowed):
                                logger.debug("Transition failed", exc_info=True)
                            break
        block_proposals = vd.get("block_proposals")
        if block_proposals is not None:
            for ai in agenda_items:
                if ai.block_proposals != block_proposals:
                    ai.block_proposals = block_proposals
                    must_save.add(ai)
        block_discussion = vd.get("block_discussion")
        if block_discussion is not None:
            for ai in agenda_items:
                if ai.block_discussion != block_discussion:
                    ai.block_discussion = block_discussion
                    must_save.add(ai)
        with transaction.atomic(durable=True):
            for ai in must_save:
                ai.save()
        return Response({"changed": len(must_save)})

    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.BulkAgendaItemDeleteSerializer,
        url_path="bulk-delete",
    )
    def bulk_delete(self, request, *args, **kwargs):
        """
        POST /api/agenda-items/bulk-delete/

        Request:  {"meeting": 1, "agenda_items": [1, 2, 3]}
        Response: {"deleted": 3}

        Raises 400 if the meeting is ongoing.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agenda_items: list[AgendaItem] = serializer.validated_data["agenda_items"]
        pks = [ai.pk for ai in agenda_items]
        with transaction.atomic(durable=True):
            AgendaItem.objects.filter(pk__in=pks).delete()
        return Response({"deleted": len(pks)})

    def get_queryset(self):
        user = self.request.user
        return (
            AgendaItem.objects.filter(
                # Moderators see all items in their meetings
                models.Q(
                    meeting__roles__user=user,
                    meeting__roles__assigned__contains=ROLE_MODERATOR,
                )
                # Participants see non-private items in their meetings
                | models.Q(meeting__roles__user=user)
                & ~models.Q(state=AgendaItemStateMachine.private.value)
            )
            .select_related("meeting")
            .distinct()
        )


@router.register("export-agenda-items", basename="export-agenda-items")
class ExportAgendaItemsViewSet(viewsets.GenericViewSet):
    model = Meeting
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.ExportAgendaItemSerializer

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.filter(
            roles__user=self.request.user, roles__assigned__contains=ROLE_MODERATOR
        )

    def list(self, request):
        return Response(data=[])

    def get_export_qs(self, meeting):
        return meeting.agenda_items.order_by("order")

    @action(
        methods=["get"],
        detail=True,
    )
    def csv(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        if not serializer.data:
            raise Http404("No data yet")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="agenda_items_m{meeting.pk}_export.csv"'
        )
        writer = csv.DictWriter(response, fieldnames=serializer.child.fields)
        writer.writeheader()
        for row in serializer.data:
            writer.writerow(row)
        return response

    @action(
        methods=["get"],
        detail=True,
        renderer_classes=[JSONRenderer],
    )
    def json(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="agenda_items_m{meeting.pk}_export.json"'
            },
        )
