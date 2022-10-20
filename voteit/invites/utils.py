from __future__ import annotations

from datetime import timedelta
from logging import getLogger
from typing import Optional
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext as _

from voteit.invites.exceptions import InviteError
from voteit.core.workflows import SendWf
from voteit.invites.workflows import InviteWf
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.core.component import Registry
    from voteit.invites.registries import InviteDataRegistry
    from voteit.invites.messages import SendInvitesSchema
    from voteit.invites.models import InviteDispatch
    from voteit.invites.models import MeetingInvite


logger = getLogger(__name__)


def get_invite_data_registry() -> InviteDataRegistry:
    from .registries import invite_data

    return invite_data


def get_dispatchers_registry() -> Registry:
    from .registries import invite_dispatchers

    return invite_dispatchers


def create_invites(created_by: User = None, **kwargs):
    """
    Note, this method should run within an atomic block in case something goes wrong
    """

    from voteit.invites.messages import AddInvitesSchema

    assert created_by is not None
    add_data = AddInvitesSchema(**kwargs)
    meeting: Meeting = Meeting.objects.get(pk=add_data.meeting)
    added = []
    changed = []
    skipped_count = 0
    for i, row in enumerate(add_data.invite_data, 1):
        invite_qs = meeting.invites.find_invites(**{add_data.type: row})
        if invite_qs.exists():
            try:
                # First filter out excludable
                invite: MeetingInvite = invite_qs.exclude(
                    state__in=add_data.skip_states
                ).get()
            except ObjectDoesNotExist:
                skipped_count += 1
                continue
            # Do we hit multiple active invites?
            except MultipleObjectsReturned:
                raise InviteError(
                    f"Data on row {i} matched different invites that already exist. You need to clear them first."
                )

            # Update invite
            invite.invite_data = row
            invite.roles = add_data.roles
            invite.last_modified_by = created_by
            user: Optional[User] = invite.used_by
            if not user and invite.state not in {InviteWf.ACCEPTED, InviteWf.OPEN}:
                invite.state = InviteWf.OPEN
            invite.save()
            changed.append(invite.pk)
            #  Set permissions according to the new state
            if user:
                # Adjust existing roles
                requested_roles = set(invite.roles)
                current_roles = meeting.get_roles(user) or set()
                if remove_roles := current_roles - requested_roles:
                    meeting.remove_roles(user, *remove_roles)
                if add_roles := requested_roles - current_roles:
                    meeting.add_roles(user, *add_roles)
        else:
            # We need to create a new invite
            invite = meeting.invites.create(
                type=add_data.type,
                invite_data=row,
                created_by=created_by,
                roles=add_data.roles,
                last_modified_by=created_by,
            )
            added.append(invite.pk)
    return added, changed, skipped_count


def create_dispatch_and_schedule_invites(
    created_by: User = None, **kwargs
) -> InviteDispatch:
    from voteit.invites.messages import SendInvitesSchema

    send_data = SendInvitesSchema(**kwargs)
    meeting: Meeting = Meeting.objects.get(pk=send_data.meeting)
    send_exclude_ts = now() - timedelta(hours=send_data.resend_minimum)
    invites_qs = meeting.invites.filter(send_state__in=send_data.states).exclude(
        last_sent__gt=send_exclude_ts
    )
    with transaction.atomic(durable=True):
        invite_dispatch: InviteDispatch = meeting.invite_dispatches.create(
            subject=send_data.subject,
            body=send_data.body,
            dispatcher_name=send_data.dispatcher_name,
            created_by=created_by,
        )
        invite_dispatch.invites.set(invites_qs)
        invites_qs.update(send_state=SendWf.SCHEDULED)
    return invite_dispatch
