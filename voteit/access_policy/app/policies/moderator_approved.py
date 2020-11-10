from __future__ import annotations

from logging import getLogger
from typing import List, Type, Union

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.db import models
from django_fsm import FSMField, transition

from voteit.access_policy.models import AccessPolicy
from voteit.access_policy.registries import access_policies
from voteit.core.role import Role
from voteit.core.workflows import AcceptanceWf
from voteit.meeting.rules import is_moderator

__all__ = ["ModeratorApprovedAccess"]

logger = getLogger(__name__)


@access_policies
class ModeratorApprovedAccess(AccessPolicy):
    name = "moderator_approved"
    title = _("Users apply for access, moderators approve manually")

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


class AccessRequest(models.Model):
    state = FSMField(
        default=AcceptanceWf.initial,
        choices=AcceptanceWf.choices(),
        protected=True,
        editable=False,
    )
    access_policy = models.ForeignKey(
        ModeratorApprovedAccess,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    message = models.TextField(blank=True, null=True)
    moderator_message = models.TextField(blank=True, null=True)
    created = models.DateTimeField(editable=False, auto_now_add=True)
    handled_ts = models.DateTimeField(blank=True, null=True, editable=False)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        blank=True,
        null=True,
        editable=False,
    )
    roles_given: str = models.TextField(_("Roles given"), null=True, blank=True)

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
        """ Moderator accepts a request and sets some roles to a user.
        """
        roles_to_handle = self.access_policy.prep_roles(*give_roles)
        for role in roles_to_handle:
            role.add(self.user)
        self.roles_given = ",".join([x.name for x in roles_to_handle])
        self._set_handled(moderator_user, message)

    @transition(
        field=state,
        source=AcceptanceWf.UNHANDLED,
        target=AcceptanceWf.REJECTED,
        on_error=AcceptanceWf.UNHANDLED,
        permission=is_moderator,
    )
    def reject(self, moderator_user: AbstractUser, message: str = ""):
        """ Moderator rejects request.
        """
        self._set_handled(moderator_user, message)

    @transition(
        field=state,
        source=AcceptanceWf.REJECTED,
        target=AcceptanceWf.UNHANDLED,
        permission=is_moderator,
    )
    def reset(self):
        """ In case reject was pressed wrongly, the moderator may reset the request back to unhandled.
        """
        self.handled_by = None
        self.handled_ts = None
        self.moderator_message = None

    def _set_handled(self, moderator_user: AbstractUser, message: str):
        self.handled_by = moderator_user
        self.handled_ts = now()
        self.moderator_message = message
