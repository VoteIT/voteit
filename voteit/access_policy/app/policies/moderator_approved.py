from __future__ import annotations

from datetime import datetime
from logging import getLogger
from typing import List
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type
from typing import Union

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import transition
from voteit.access_policy.models import AccessPolicy
from voteit.access_policy.registries import access_policies
from voteit.core.abcs import MeetingContext
from voteit.core.role import Role
from voteit.core.workflows import AcceptanceWf
from voteit.meeting.rules import is_moderator

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from django.contrib.auth.models import AbstractUser

__all__ = ["ModeratorApprovedAccess"]

logger = getLogger(__name__)


@access_policies
class ModeratorApprovedAccess(AccessPolicy):
    name: str = "moderator_approved"
    title: str = _("Users apply for access, moderators approve manually")

    exporters = {"meeting": {"ignore_fields": ("access_requests",)}}

    def request_access(self, user: AbstractUser, message: str = "") -> AccessRequest:
        #  FIXME: Block subsequent requests etc
        if AccessRequest.objects.filter(
            user=user, state=AcceptanceWf.UNHANDLED
        ).exists():
            # FIXME Exception
            raise ValueError("Already requested")
        return AccessRequest.objects.create(
            access_policy=self, user=user, message=message
        )

    @property
    def unhandled_requests_qs(self):
        return self.access_requests.filter(
            access_policy=self, state=AcceptanceWf.UNHANDLED
        )


class AccessRequest(MeetingContext):
    state: str = FSMField(
        default=AcceptanceWf.initial,
        choices=AcceptanceWf.choices(),
        protected=True,
        editable=False,
    )
    access_policy: ModeratorApprovedAccess = models.ForeignKey(
        ModeratorApprovedAccess,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    message: Optional[str] = models.TextField(blank=True, null=True)
    moderator_message: Optional[str] = models.TextField(blank=True, null=True)
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    handled_ts: Optional[datetime] = models.DateTimeField(
        blank=True, null=True, editable=False
    )
    handled_by: Optional[AbstractUser] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        blank=True,
        null=True,
        editable=False,
    )
    roles_given: List = ArrayField(models.CharField(max_length=20), default=tuple)

    @property
    def meeting(self) -> Meeting:
        return self.access_policy.meeting

    @transition(
        field=state,
        source=AcceptanceWf.UNHANDLED,
        target=AcceptanceWf.ACCEPTED,
        on_error=AcceptanceWf.UNHANDLED,
        permission=is_moderator,
    )
    def accept(
        self,
        moderator_user: AbstractUser,
        give_roles: List[Union[str, Type[Role]]],
        message: str = "",
    ):
        """Moderator accepts a request and sets some roles to a user."""
        self.meeting.add_roles(self.user, *give_roles)
        self.roles_given = give_roles
        self._set_handled(moderator_user, message)

    @transition(
        field=state,
        source=AcceptanceWf.UNHANDLED,
        target=AcceptanceWf.REJECTED,
        on_error=AcceptanceWf.UNHANDLED,
        permission=is_moderator,
    )
    def reject(self, moderator_user: AbstractUser, message: str = ""):
        """Moderator rejects request."""
        self._set_handled(moderator_user, message)

    @transition(
        field=state,
        source=AcceptanceWf.REJECTED,
        target=AcceptanceWf.UNHANDLED,
        permission=is_moderator,
    )
    def reset(self):
        """In case reject was pressed wrongly, the moderator may reset the request back to unhandled."""
        self.handled_by = None
        self.handled_ts = None
        self.moderator_message = None

    def _set_handled(self, moderator_user: AbstractUser, message: str):
        self.handled_by = moderator_user
        self.handled_ts = now()
        self.moderator_message = message
