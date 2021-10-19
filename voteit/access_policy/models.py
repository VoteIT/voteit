from __future__ import annotations

from abc import abstractmethod
from collections import Collection
from datetime import datetime
from logging import getLogger
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.functional import cached_property
from django_fsm import FSMField
from django_fsm import transition

from voteit.access_policy.permissions import MeetingInvitePermissions
from voteit.access_policy.utils import get_invite_data_registry
from voteit.access_policy.workflows import InviteWf
from voteit.core.abcs import MeetingContext
from voteit.core.fields import RichTextField
from voteit.core.permissions import NOT_ALLOWED
from voteit.core.workflows import SendWf

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting

logger = getLogger(__name__)


class AccessPolicy(MeetingContext):
    """
    Subclass this to create an access policy.

    The tests for this class are in voteit.access_policy.app.automatic
    """

    active: bool = models.BooleanField(default=False)
    meeting: Meeting = models.OneToOneField(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of access policy, used as ID."""

    @property
    @abstractmethod
    def title(self) -> str:
        """Human readable name"""

    def __str__(self):
        return f"{self.__class__.__name__} for meeting {self.meeting.pk}"


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

    def filter_on_any(
        self,
        data: Dict,
    ):
        self.check_query_keys(data.keys())
        items = set(data.items())
        k, v = items.pop()
        queries = models.Q(invite_data__contains={k: v})
        while items:
            k, v = items.pop()
            queries |= models.Q(invite_data__contains={k: v})
        return self.get_queryset().filter(queries)

    def find_invites(self, **kw) -> models.QuerySet:
        """
        Return any invites matching data.
        This assumes that the data is from a trusted source and is validated somehow.
        """
        self.check_query_keys(kw.keys())
        base_qs = self.get_queryset().filter(state=InviteWf.OPEN)
        queries = None
        for (k, values) in kw.items():
            if values is None or k not in self.invite_data_registry:
                continue
            schema = self.invite_data_registry[k]
            if isinstance(values, str) or not isinstance(values, Collection):
                values = {values}
            for v in values:
                # Transform and validate
                data = schema(**{k: v})  # Might raise pydantics validation error
                v = getattr(data, k)
                if queries is None:
                    queries = models.Q(invite_data__contains={k: v})
                else:
                    queries |= models.Q(invite_data__contains={k: v})
        if queries is None:
            return MeetingInvite.objects.none()
        else:
            return base_qs.filter(queries)


_marker = object()


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
    # This must match real invite data
    invite_data: Dict[str, str] = models.JSONField(
        verbose_name="Data to match invite against", encoder=DjangoJSONEncoder
    )
    matched: List[Dict[str, str]] = models.JSONField(
        verbose_name="Data that matched",
        encoder=DjangoJSONEncoder,
        blank=True,
        null=True,
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
        self.meeting.add_roles(user, *self.roles)

    @transition(
        field=state,
        source=InviteWf.OPEN,
        target=InviteWf.REJECTED,
        permission=NOT_ALLOWED,  # Special view, not a normal transition
    )
    def reject(self, user: AbstractUser):
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
    # FIXME

    objects = MeetingInviteManager()


class InviteDispatch(models.Model):
    name = "invite_dispatch"
    invites = models.ManyToManyField(MeetingInvite)
    body: str = RichTextField(verbose_name="Message body", default="")
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
