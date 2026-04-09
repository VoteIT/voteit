from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import transition

from voteit.components.abcs import Component
from voteit.components.utils import get_meeting_component_adapters
from voteit.components.utils import get_organisation_component_adapters
from voteit.core import PERM
from voteit.core.abcs import MeetingContext
from voteit.core.abcs import OrganisationContext
from voteit.core.workflows import EnabledWf

if TYPE_CHECKING:
    from voteit.components.abcs import ComponentAdapter
    from voteit.organisation.models import Organisation
    from voteit.meeting.models import Meeting
    from voteit.core.component import Registry

__all__ = ("MeetingComponent", "OrganisationComponent")


logger = getLogger(__name__)


@auditlog.register(
    include_fields=[
        "component_name",
        "settings_data",
        "state",
        "meeting",
    ],
)
class MeetingComponent(Component, MeetingContext):
    name: str = "meeting_component"
    state: str = FSMField(
        default=EnabledWf.initial, choices=EnabledWf.choices(), editable=False
    )
    meeting: Meeting = models.ForeignKey(
        "meeting.Meeting", on_delete=models.CASCADE, related_name="components"
    )

    class Meta:
        verbose_name = "Meeting component"
        verbose_name_plural = "Meeting components"

    def get_registry(self) -> Registry[str, ComponentAdapter]:
        return get_meeting_component_adapters()

    @transition(
        field=state,
        source=EnabledWf.OFF,
        target=EnabledWf.ON,
        permission=f"components.{PERM.CHANGE}_meetingcomponent",
        custom={"title": _("Enable")},
        conditions=[Component.valid_component_name, Component.valid_settings],
    )
    def enable(self):
        pass

    @transition(
        field=state,
        source=EnabledWf.ON,
        target=EnabledWf.OFF,
        permission=f"components.{PERM.CHANGE}_meetingcomponent",
        custom={"title": _("Disable")},
    )
    def disable(self):
        pass


@auditlog.register(
    include_fields=[
        "component_name",
        "settings_data",
        "state",
        "organisation",
    ],
)
class OrganisationComponent(Component, OrganisationContext):
    name: str = "organisation_component"
    state: str = FSMField(
        default=EnabledWf.initial, choices=EnabledWf.choices(), editable=False
    )
    organisation: Organisation = models.ForeignKey(
        "organisation.Organisation", on_delete=models.CASCADE, related_name="components"
    )

    class Meta:
        verbose_name = "Organisation component"
        verbose_name_plural = "Organisation components"

    def get_registry(self) -> Registry[str, ComponentAdapter]:
        return get_organisation_component_adapters()

    @transition(
        field=state,
        source=EnabledWf.OFF,
        target=EnabledWf.ON,
        # permission=XXX,
        custom={"title": _("Enable")},
        conditions=[Component.valid_component_name, Component.valid_settings],
    )
    def enable(self):
        pass

    @transition(
        field=state,
        source=EnabledWf.ON,
        target=EnabledWf.OFF,
        # permission=XXX,
        custom={"title": _("Disable")},
    )
    def disable(self):
        pass
