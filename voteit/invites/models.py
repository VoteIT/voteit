from __future__ import annotations

from collections.abc import Collection
from collections.abc import Sequence
from datetime import datetime
from functools import reduce
from logging import getLogger
from operator import or_
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_fsm import FSMField
from django_fsm import transition

from voteit.core.abcs import MeetingContext
from voteit.core.decorators import ensure_atomic
from voteit.core.permissions import NOT_ALLOWED
from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.registries import invite_adapter_registry
from voteit.invites.utils import get_invite_adapter_registry
from voteit.invites.workflows import InviteWf

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.organisation.models import Organisation

logger = getLogger(__name__)


class MeetingInviteManager(models.Manager):
    """
    Helper to find invites matching a specific user's data.
    """

    @cached_property
    def invite_adapter_registry(self):
        return invite_adapter_registry()

    def find_open_invites(
        self, *, organisation: Organisation | None = None, **kw
    ) -> models.QuerySet[MeetingInvite]:
        kw["organisation"] = organisation
        return self.find_invites(**kw).filter(state=InviteWf.OPEN)

    def find_invites(
        self, *, organisation: Organisation | None = None, **kw
    ) -> models.QuerySet:
        """
        Return any invites matching data.
        This assumes that the data is from a trusted source and is validated somehow.
        """
        reg = get_invite_adapter_registry()
        queries = []
        for (k, values) in kw.items():
            if not values:
                continue
            if k not in reg:
                logger.warning("Invite search with indexes that doesn't exist: %s", k)
                continue
            if isinstance(values, str) or not isinstance(values, Collection):
                values = [values]
            queries.append(reg[k].query(*values))
        if queries:
            or_queries = reduce(or_, queries)
            qs = self.get_queryset().filter(or_queries)
            if organisation:
                return qs.filter(meeting__organisation=organisation)
            return qs
        return MeetingInvite.objects.none()

    def _update_assigned_roles(
        self, meeting: Meeting, invites: Collection[MeetingInvite]
    ):
        invites = {x for x in invites if x.used_by_id}
        assigned_user_pks = {x.used_by_id for x in invites if x.used_by_id}
        meeting_roles_dict = {
            x.user_id: x.assigned
            for x in meeting.roles.filter(user_id__in=assigned_user_pks).values_list(
                "user_id", "assigned"
            )
        }
        for invite in invites:
            current_roles = set(meeting_roles_dict.get(invite.used_by_id, set()))
            set_roles = set(invite.roles)
            if remove_roles := current_roles - set_roles:
                meeting.remove_roles(invite.used_by, *remove_roles)
            if add_roles := set_roles - current_roles:
                meeting.add_roles(invite.used_by, *add_roles)

    @ensure_atomic
    def create_or_update_typed(
        self,
        *,
        invite_type,
        values: list[str],
        roles: list[str],
        exclude_states: set[str] = (InviteWf.REJECTED,),
        meeting: Meeting,
    ) -> Sequence[int, int, int]:
        """
        returns created, updated, existed
        """
        existing_qs = self.find_invites(**{invite_type: values}).filter(meeting=meeting)
        # skip_vals = existing_qs.exclude(state__in=exclude_states).values_list(
        #     f"user_data__{invite_type}", flat=True
        # )
        roles = sorted(str(x) for x in roles)
        total_existing = existing_qs.count()
        # This prefetch and the role update is very inefficient. It should be refactored when we have time.
        needs_role_update_qs = (
            existing_qs.exclude(roles=roles)
            .exclude(state__in=exclude_states)
            .prefetch_related("used_by")
        )
        # We may want to bulk this later on
        # needs_role_update_qs.update(roles=roles)
        for invite in needs_role_update_qs:
            invite.roles = roles
            # We've already excluded var exclude_states
            if invite.state not in (InviteWf.OPEN, InviteWf.ACCEPTED):
                invite.state = InviteWf.OPEN
            invite.save()
        self._update_assigned_roles(meeting, needs_role_update_qs)
        already_correct_count = total_existing - needs_role_update_qs.count()
        # Filter out values we've already touched
        needs_new = set(values) - set(
            existing_qs.values_list(f"user_data__{invite_type}", flat=True)
        )
        # As above, maybe bulk later on
        for value in needs_new:
            self.create(
                roles=roles,
                user_data={invite_type: value},
            )
        # New, updated, untouched (skipped - either existed and matched exactly or in exclude_states)
        return len(needs_new), needs_role_update_qs.count(), already_correct_count


class MeetingInvite(MeetingContext):
    name = "meeting_invite"
    state: str = FSMField(
        default=InviteWf.initial, choices=InviteWf.choices(), editable=False
    )
    created: datetime = models.DateTimeField(default=now, editable=False)
    modified: datetime = models.DateTimeField(auto_now=True, editable=False)
    used_at: datetime = models.DateTimeField(null=True, blank=True)
    used_by: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="used_invites",
        null=True,
        blank=True,
    )
    meeting: Meeting = models.ForeignKey(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="invites",
    )
    # FIXME: Validate roles - ValueError
    roles: list[str] = ArrayField(models.CharField(max_length=20), default=tuple)
    user_data: dict = models.JSONField(
        encoder=DjangoJSONEncoder,
    )

    # INVITE STATE TRANSITIONS
    @transition(
        field=state,
        source=InviteWf.OPEN,
        target=InviteWf.ACCEPTED,
        permission=NOT_ALLOWED,  # Special view, not a normal transition
    )
    def accept(self, user: AbstractUser):
        """
        Important! Must always run within an atomic block!
        """
        self.used_by = user
        self.used_at = now()
        self.meeting.add_roles(user, *self.roles)

    @transition(
        field=state,
        source=InviteWf.OPEN,
        target=InviteWf.REJECTED,
        permission=NOT_ALLOWED,  # Special view, not a normal transition
    )
    def reject(self, user: AbstractUser | None):
        if not user:
            return
        if user.pk is not None:
            self.used_by = user

    @transition(
        field=state,
        source=InviteWf.OPEN,
        target=InviteWf.REVOKED,
        permission=MeetingInvitePermissions.CHANGE,
    )
    def revoke(self):
        pass

    objects = MeetingInviteManager()

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self):
        return f"invite:{self.pk}"

    def save(self, **kwargs):
        # very basic don't shoot ourselves in the foot-validation
        if self.user_data:
            if not isinstance(self.user_data, dict):
                raise ValueError("user_data isn't a dict")
            for v in self.user_data.values():
                if not isinstance(v, str):
                    raise IntegrityError(
                        f"All user_data values must be strings. Found: {v}"
                    )
        if self.roles:
            # Make sure they're in the same order all the time
            self.roles = sorted(str(x) for x in self.roles)
        super().save(**kwargs)


# class InviteDispatch(models.Model):
#     name = "invite_dispatch"
#     invites = models.ManyToManyField(MeetingInvite)
#     subject: str = models.CharField(max_length=100, default="")
#     body: str = RichTextField(verbose_name="Message body", default="")
#     dispatcher_name: str = models.CharField(max_length=30, default="send_email")
#     created: datetime = models.DateTimeField(default=now, editable=False)
#     created_by: AbstractUser = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.CASCADE,
#     )
#     meeting: Meeting = models.ForeignKey(
#         "meeting.Meeting",
#         on_delete=models.CASCADE,
#         related_name="invite_dispatches",
#     )
#
#     @cached_property
#     def dispatcher(self) -> InviteDispatcher:
#         reg = get_dispatchers_registry()
#         return reg[self.dispatcher_name](self)
#
#     def send(self, invite: MeetingInvite) -> bool:
#         if invite.type != self.dispatcher.type:
#             raise TypeError(
#                 f"Dispatch {self.dispatcher.type} called with {invite} that requires {invite.type}"
#             )
#         return self.dispatcher.send(invite)
#
#     def send_scheduled(self):
#         sent = 0
#         failed = 0
#         skipped = self.invites.exclude(send_state=SendWf.SCHEDULED).count()
#         for invite in self.invites.filter(send_state=SendWf.SCHEDULED):
#             invite: MeetingInvite
#             invite.send_state = SendWf.SENDING
#             invite.save()
#             try:
#                 invite.validate()
#                 self.send(invite)
#             except Exception as exc:
#                 invite.send_state = SendWf.FAILED
#                 logger.exception("Invite %s failed while sending", invite.pk)
#                 failed += 1
#             else:
#                 invite.send_state = SendWf.SENT
#                 invite.last_sent = now()
#                 sent += 1
#             invite.save()
#         return sent, failed, skipped
#
#     def __repr__(self):
#         return f"<{self.__class__.__name__}: {self}>"
#
#     def __str__(self):
#         v = getattr(self, "subject", None)
#         if not v:
#             v = f"Dispatch:{self.pk}"
#         return v
