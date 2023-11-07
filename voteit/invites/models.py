from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
from logging import getLogger
from operator import or_
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError
from django.db import models
from django.utils.timezone import now
from django_fsm import FSMField
from django_fsm import transition

from voteit.core.abcs import MeetingContext
from voteit.core.decorators import ensure_atomic
from voteit.core.decorators import has_exact_filter
from voteit.core.fields import RolesField
from voteit.core.permissions import NOT_ALLOWED
from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.utils import get_invite_adapter_registry
from voteit.invites.workflows import InviteWf
from voteit.meeting.models import GroupRole
from voteit.meeting.models import MeetingRoles
from voteit.meeting.models import MeetingGroup

if TYPE_CHECKING:
    from voteit.core.models import User as UserType
    from voteit.meeting.models import Meeting
    from voteit.core.role import Role
    from voteit.organisation.models import Organisation

logger = getLogger(__name__)


@dataclass
class InviteResult:
    pks: set[str]
    added: int
    changed: int
    existed: int


class MeetingInviteManager(models.Manager):
    """
    Helper to find invites matching a specific user's data.
    """

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
        for k, values in kw.items():
            if not values:
                continue
            if k not in reg:
                logger.warning("Invite search with indexes that doesn't exist: %s", k)
                continue
            adapter = reg[k]
            if not adapter.is_user_data:
                logger.warning("Invite search with indexes that isn't user_data: %s", k)
                continue
            if isinstance(values, str) or not isinstance(values, Collection):
                values = [values]
            queries.append(adapter.query(*values))
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
            user_id: assigned
            for user_id, assigned in meeting.roles.filter(
                user_id__in=assigned_user_pks
            ).values_list("user_id", "assigned")
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
        meeting: Meeting,
    ) -> InviteResult:
        data = [{invite_type: x} for x in values]
        return self.create_or_update_mixed(data=data, roles=roles, meeting=meeting)

    def _build_user_data_query_dict(
        self, *items: dict[str, str]
    ) -> dict[str, set[str]]:
        result = defaultdict(set)
        for item in items:
            for k, v in item.items():
                result[k].add(v)
        return result

    @has_exact_filter("meeting")
    def find_mixed_user_data(
        self, *items: dict[str, str]
    ) -> Sequence[
        models.QuerySet[MeetingInvite],
        dict[str, models.QuerySet[MeetingInvite]],
    ]:
        """
        Queries db and checks for intersecting data between different types.
        It's only relevant for data that has several user_data types.

        Returns a sequence with exact matches first, and then the items that might match just one contained in a dict where key is the user data matched.
        """
        # Let's check exact matches first.
        if not items:
            return self.get_queryset().none(), {}
        or_queries = reduce(or_, [models.Q(user_data__contains=x) for x in items])
        exact_qs = self.get_queryset().filter(or_queries)
        # And any values reused in other invites, which could be problematic
        conflicting_single_match = {}
        user_data_query_dict = self._build_user_data_query_dict(*items)
        if len(user_data_query_dict) > 1:
            # No point in doing queries if there was only one query type
            for user_data_type, values in user_data_query_dict.items():
                single_type_qs = self.find_invites(**{user_data_type: values}).exclude(
                    pk__in=exact_qs
                )
                if single_type_qs.exists():
                    conflicting_single_match[user_data_type] = single_type_qs
        return exact_qs, conflicting_single_match

    @ensure_atomic
    def create_or_update_mixed(
        self,
        *,
        data: list[dict[str, str]],
        roles: list[str],
        meeting: Meeting,
    ) -> InviteResult:
        """
        Create invites with mixed data
        """
        exact_qs, conflicting_single_match = self.find_mixed_user_data(*data)
        if conflicting_single_match:
            # FIXME: How do we handle this?
            raise IntegrityError("Partial invites found")
        roles = sorted(str(x) for x in roles)
        total_existing = exact_qs.count()
        # This prefetch and the role update is very inefficient. It should be refactored when we have time.
        invite_pks = set(exact_qs.values_list("pk", flat=True))
        needs_role_update_qs = exact_qs.exclude(roles=roles).prefetch_related("used_by")
        for invite in needs_role_update_qs:
            invite.roles = roles
            # We've already excluded var exclude_states
            if invite.state not in (InviteWf.OPEN, InviteWf.ACCEPTED):
                invite.state = InviteWf.OPEN
            invite.save()
        # Change state of other invites that haven't been touched
        for invite in exact_qs.exclude(
            state__in={InviteWf.OPEN, InviteWf.ACCEPTED}
        ).exclude(pk__in=needs_role_update_qs):
            invite.state = InviteWf.OPEN
            invite.save()
        self._update_assigned_roles(meeting, needs_role_update_qs)
        already_correct_count = total_existing - needs_role_update_qs.count()
        already_handled_user_data = list(exact_qs.values_list("user_data", flat=True))
        # Filter any intersecting user_data,
        # ie {'email': 'boo@bees.com'} in {'email': 'boo@bees.com', 'something': 'blabla'} is a match
        add_data = []
        for item in data:
            items = item.items()
            # Is this a subset of any handled data?
            if any(items <= x.items() for x in already_handled_user_data):
                continue
            if item not in add_data:  # Avoid duplicate
                add_data.append(item)
        new_invites = []
        # Bulk create instead? We miss signals but that might not be a problem
        for value in add_data:
            new_invites.append(
                self.create(
                    roles=roles,
                    user_data=value,
                )
            )
        # New, updated, untouched (skipped - either existed and matched exactly or in exclude_states)
        invite_pks.update({x.pk for x in new_invites})
        return InviteResult(
            pks=invite_pks,
            added=len(new_invites),
            changed=needs_role_update_qs.count(),
            existed=already_correct_count,
        )


class MeetingInvite(MeetingContext):
    name = "meeting_invite"
    state: str = FSMField(
        default=InviteWf.initial, choices=InviteWf.choices(), editable=False
    )
    created: datetime = models.DateTimeField(default=now, editable=False)
    # Warning! We want to drop this later on!
    created_by: UserType | None = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_invites",
        blank=True,
        null=True,
    )
    # Warning! We want to drop this later on!
    last_modified_by: UserType | None = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        blank=True,
        null=True,
    )
    modified: datetime = models.DateTimeField(auto_now=True, editable=False)
    used_at: datetime = models.DateTimeField(null=True, blank=True)
    used_by: UserType = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="used_invites",
        null=True,
        blank=True,
    )
    meeting: Meeting = models.ForeignKey(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="invites",
    )
    roles: list[Role] = RolesField(
        max_length=60, role_choices=MeetingRoles.valid_roles.values()
    )
    user_data: dict = models.JSONField(
        encoder=DjangoJSONEncoder,
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["meeting", "user_data"],
                name="unique_meeting_invite_user_data",
            ),
        )

    @ensure_atomic
    @transition(
        field=state,
        source=InviteWf.OPEN,
        target=InviteWf.ACCEPTED,
        permission=NOT_ALLOWED,  # Special view, not a normal transition
    )
    def accept(self, user: UserType):
        """
        Important! Must always run within an atomic block!
        """
        self.used_by = user
        self.used_at = now()
        self.meeting.add_roles(user, *self.roles)
        reg = get_invite_adapter_registry()
        reg.run_accepted(self)

    @transition(
        field=state,
        source=InviteWf.OPEN,
        target=InviteWf.REJECTED,
        permission=NOT_ALLOWED,  # Special view, not a normal transition
    )
    def reject(self, user: UserType | None):
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

    # annotations
    group_annotations: models.QuerySet[MeetingGroupAnnotation]


class MeetingGroupAnnotation(models.Model):
    meeting_group: MeetingGroup = models.ForeignKey(
        MeetingGroup,
        on_delete=models.CASCADE,
        related_name="invite_annotations",
    )
    meeting_invite: MeetingInvite = models.ForeignKey(
        MeetingInvite,
        on_delete=models.CASCADE,
        related_name="group_annotations",
    )
    group_role: GroupRole = models.ForeignKey(
        GroupRole,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["meeting_group", "meeting_invite"],
                name="unique_invite_group_annotation",
            ),
        )

    objects: models.Manager
