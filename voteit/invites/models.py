from __future__ import annotations

from collections import Collection
from datetime import datetime
from logging import getLogger
from typing import List
from typing import Optional
from typing import Set
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_fsm import FSMField
from django_fsm import transition

from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.utils import get_dispatchers_registry
from voteit.invites.utils import get_invite_data_registry
from voteit.invites.workflows import InviteWf
from voteit.core.abcs import MeetingContext
from voteit.core.fields import RichTextField
from voteit.core.permissions import NOT_ALLOWED
from voteit.core.workflows import SendWf

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.invites.abcs import InviteDispatcher


logger = getLogger(__name__)


class MeetingInviteManager(models.Manager):
    """
    Helper to find invites matching a specific users data.
    """

    @cached_property
    def invite_data_registry(self):
        return get_invite_data_registry()

    @cached_property
    def invite_reg_keys(self) -> Set:
        return set(self.invite_data_registry.keys())

    def check_query_keys(self, keys):
        no_such_data = set(keys) - self.invite_reg_keys
        if no_such_data:
            logger.warning(
                "Invite search with indexes that doesn't exist: %s", no_such_data
            )

    def find_open_invites(self, organisation=None, /, **kw) -> models.QuerySet:
        qs = self.find_invites(**kw).filter(
            state=InviteWf.OPEN
        )
        if organisation is None:
            return qs
        return qs.filter(meeting__organisation=organisation)

    def find_invites(self, **kw) -> models.QuerySet:
        """
        Return any invites matching data.
        This assumes that the data is from a trusted source and is validated somehow.
        """
        self.check_query_keys(kw.keys())
        base_qs = self.get_queryset()
        queries = None
        for (k, values) in kw.items():
            if values is None or k not in self.invite_data_registry:
                continue
            if isinstance(values, str) or not isinstance(values, Collection):
                values = {values}
            if queries is None:
                queries = models.Q(invite_data__in=values, type=k)
            else:
                queries |= models.Q(invite_data__in=values, type=k)
        if queries is None:
            return MeetingInvite.objects.none()
        else:
            return base_qs.filter(queries)


class MeetingInvite(MeetingContext):
    name = "meeting_invite"
    state: str = FSMField(
        default=InviteWf.initial, choices=InviteWf.choices(), editable=False
    )
    send_state: str = FSMField(
        default=SendWf.initial, choices=SendWf.choices(), editable=False
    )
    last_sent: Optional[datetime] = models.DateTimeField(blank=True, null=True)
    created: datetime = models.DateTimeField(auto_now_add=True, editable=False)
    created_by: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_invites",
    )
    modified: datetime = models.DateTimeField(auto_now=True, editable=False)
    last_modified_by: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        editable=False,
        null=True,
    )
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
    roles: List = ArrayField(models.CharField(max_length=20), default=tuple)
    type: str = models.CharField(
        verbose_name="Type of invite", default="email", max_length=20
    )
    # This must match real invite data
    invite_data: str = models.CharField(max_length=200)

    def validate(self):
        reg = get_invite_data_registry()
        if self.type not in reg:
            raise ValueError("No such invite data type")
        reg[self.type](**{self.type: self.invite_data})

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
        self.meeting.add_roles(user, *self.roles)

    @transition(
        field=state,
        source=InviteWf.OPEN,
        target=InviteWf.REJECTED,
        permission=NOT_ALLOWED,  # Special view, not a normal transition
    )
    def reject(self, user: Optional[AbstractUser]):
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

    # SEND STATE TRANSITIONS
    @transition(
        field=send_state,
        source=[x for x in SendWf.states.keys() if x != SendWf.SCHEDULED],
        target=SendWf.SCHEDULED,
        permission=NOT_ALLOWED,  # Special view, not a normal transition
    )
    def schedule(self):
        pass

    objects = MeetingInviteManager()

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self):
        return f"invite:{self.pk}"


class InviteDispatch(models.Model):
    name = "invite_dispatch"
    invites = models.ManyToManyField(MeetingInvite)
    subject: str = models.CharField(max_length=100, default="")
    body: str = RichTextField(verbose_name="Message body", default="")
    dispatcher_name: str = models.CharField(max_length=30, default="send_email")
    created: datetime = models.DateTimeField(auto_now_add=True)
    created_by: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    meeting: Meeting = models.ForeignKey(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="invite_dispatches",
    )

    @cached_property
    def dispatcher(self) -> InviteDispatcher:
        reg = get_dispatchers_registry()
        return reg[self.dispatcher_name](self)

    def send(self, invite: MeetingInvite) -> bool:
        if invite.type != self.dispatcher.type:
            raise TypeError(
                f"Dispatch {self.dispatcher.type} called with {invite} that requires {invite.type}"
            )
        return self.dispatcher.send(invite)

    def send_scheduled(self):
        sent = 0
        failed = 0
        skipped = self.invites.exclude(send_state=SendWf.SCHEDULED).count()
        for invite in self.invites.filter(send_state=SendWf.SCHEDULED):
            invite: MeetingInvite
            invite.send_state = SendWf.SENDING
            invite.save()
            try:
                invite.validate()
                self.send(invite)
            except Exception as exc:
                invite.send_state = SendWf.FAILED
                logger.exception("Invite %s failed while sending", invite.pk)
                failed += 1
            else:
                invite.send_state = SendWf.SENT
                invite.last_sent = now()
                sent += 1
            invite.save()
        return sent, failed, skipped

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self):
        v = getattr(self, "subject", None)
        if not v:
            v = f"Dispatch:{self.pk}"
        return v
