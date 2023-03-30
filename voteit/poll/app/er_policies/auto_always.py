from __future__ import annotations

from logging import getLogger

from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.models import ElectoralRegister
from voteit.poll.registries import er_policy
from voteit.poll.signals import new_er_created
from voteit.poll.workflows import PollWf

__all__ = ("AutoAlways",)
logger = getLogger(__name__)


@er_policy
class AutoAlways(ElectoralRegisterPolicy):
    """
    As soon as the potential voter role changes, create a new electoral register and attach it
    even to ongoing polls. This is only meant for demo meetings
    """

    name = "auto_always"
    title = _("Automatic always")
    description = _(
        "This method will always create a new electoral register when potential voters change. "
        "It will even change electoral register for ongoing polls, so use this with caution!"
    )
    group_votes_active = False

    logger = logger

    def get_voters(self, **kwargs) -> dict[int, int]:
        return {x: 1 for x in self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)}


def _maybe_create_and_update(instance: MeetingRoles, roles=()):
    if ROLE_POTENTIAL_VOTER in roles:
        meeting: Meeting = instance.context
        if meeting.er_policy_name == AutoAlways.name:
            current_er = meeting.latest_er
            # Possibly create a new electoral register
            new_er = meeting.er_policy.create_er()
            if new_er and current_er != new_er:
                for poll in meeting.polls.filter(state=PollWf.ONGOING):
                    # This will duplicate searches and checks over polls,
                    # but since this is only a demo we don't need to optimize for speed
                    meeting.er_policy.apply(poll)


@receiver(roles_added, sender=MeetingRoles)
def new_er_voter_added(instance: MeetingRoles, roles=(), **kw):
    _maybe_create_and_update(instance, roles=roles)


@receiver(roles_removed, sender=MeetingRoles)
def new_er_voter_removed(instance: MeetingRoles, roles=(), **kw):
    _maybe_create_and_update(instance, roles=roles)


@receiver(new_er_created)
def cleanup_unused_ers(instance: ElectoralRegister, **kwargs):
    """
    Auto always creates a lot of clutter. Remove unused ERs
    """
    if instance.source == AutoAlways.name:
        er_qs = ElectoralRegister.objects.filter(
            meeting=instance.meeting,
            source=instance.source,
            polls__isnull=True,
            polls_initial__isnull=True,
        ).exclude(pk=instance.pk)
        for er in er_qs:
            # Delete this way to trigger push
            er.delete()
