from __future__ import annotations

from abc import abstractmethod
from collections import Collection
from logging import getLogger
from typing import Dict
from typing import List
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django_fsm import FSMField
from django_fsm import transition

from voteit.access_policy.permissions import MeetingInvitePermissions
from voteit.access_policy.utils import get_invite_data_registry
from voteit.access_policy.workflows import InviteWf
from voteit.core.abcs import MeetingContext
from voteit.core.permissions import NOT_ALLOWED

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

    def find_invites(self, **kw) -> models.QuerySet:
        """
        Return any invites matching data.
        This assumes that the data is from a trusted source and is validated somehow.
        """
        reg = get_invite_data_registry()
        no_such_data = set(kw.keys()) - set(reg.keys())
        if no_such_data:
            logger.warning(
                "Invite search with indexes that doesn't exist: %s", no_such_data
            )
        base_qs = self.get_queryset().filter(state=InviteWf.OPEN)
        queries = None
        for (k, values) in kw.items():
            if values is None or k not in reg:
                continue
            schema = reg[k]
            if isinstance(values, str) or not isinstance(values, Collection):
                values = {values}
            for v in values:
                # Transform and validate
                data = schema(**{k: v})  # Might raise pydantics validation error
                v = getattr(data, k)
                if queries is None:
                    queries = models.Q(data__contains={k: v})
                else:
                    queries |= models.Q(data__contains={k: v})
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
    created_by: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_invites",
    )
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
    data: Dict[str, str] = models.JSONField(
        verbose_name="Data to match invite against", encoder=DjangoJSONEncoder
    )
    matched: List[Dict[str, str]] = models.JSONField(
        verbose_name="Data that matched",
        encoder=DjangoJSONEncoder,
        blank=True,
        null=True,
    )

    def validate_invite_data(self, data=_marker):
        """
        Make sure any data stored works with registered invite data types.
        Pass along data if you want to check something, otherwise the stored data is checked.
        """
        if data is _marker:
            data = self.data
        reg = get_invite_data_registry()
        reg.validate(data)

    def save(self, **kw):
        self.validate_invite_data()  # Crash and burn is better than corrupt db
        super().save(**kw)

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

    objects = MeetingInviteManager()
