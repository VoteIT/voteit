"""
GDPR removal requests.

Requesting removal emails the account's address after a delay, with a link to
abort. That email is what protects against someone else requesting removal
from the user's unattended computer.

A user with nothing to review is instead removed when the delay is up, and the
email confirms the removal.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from logging import getLogger
from urllib.parse import urlencode

import django_rq
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import ProtectedError
from django.db.models import RestrictedError
from django.template import loader
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.timezone import now
from django.utils.translation import gettext as _
from redis.exceptions import ConnectionError
from redis.exceptions import TimeoutError
from rq.exceptions import NoSuchJobError
from rq.job import Job

from voteit.core import RQ_LONG_QUEUE
from voteit.core.sessions import end_user_access

logger = getLogger(__name__)

_TOKEN_SALT = "voteit.core.removal.abort"


def _job_id(user_pk: int) -> str:
    return f"user-removal-email-{user_pk}"


def _is_current(user, requested: str) -> bool:
    return (
        user.removal_requested is not None
        and user.removal_requested.isoformat() == requested
    )


def make_abort_token(user) -> str:
    """
    Bound to this particular request: once it's aborted or requested again,
    removal_requested changes and the token stops working.
    """
    assert user.removal_requested is not None
    return signing.dumps(
        {"u": user.pk, "t": user.removal_requested.isoformat()}, salt=_TOKEN_SALT
    )


def abort_removal_path(user) -> str:
    """The frontend page that aborts, with the token."""
    path = getattr(settings, "ABORT_REMOVAL_URL", "/abort-removal")
    return f"{path}?{urlencode({'token': make_abort_token(user)})}"


def get_user_from_abort_token(token: str):
    """The user whose current removal request the token belongs to, or None."""
    try:
        data = signing.loads(token, salt=_TOKEN_SALT)
        user = get_user_model().objects.get(pk=data["u"])
    except (signing.BadSignature, KeyError, TypeError, ObjectDoesNotExist):
        return None
    return user if _is_current(user, data["t"]) else None


def schedule_removal_email(user, language: str) -> None:
    """
    (Re)start the delay before the email. Call after commit, the job reads the
    user from the database.
    """
    queue = django_rq.get_queue(RQ_LONG_QUEUE)
    try:
        _cancel(_job_id(user.pk), queue.connection)
        queue.enqueue_in(
            timedelta(minutes=settings.REMOVAL_EMAIL_DELAY_MINUTES),
            email_removal_requested,
            user.pk,
            user.removal_requested.isoformat(),
            language,
            job_id=_job_id(user.pk),
        )
    except (ConnectionError, TimeoutError):
        # Sending now would skip the delay, so it isn't sent at all.
        logger.exception("Could not schedule removal email for user %s", user.pk)


def cancel_removal_email(user_pk: int) -> None:
    queue = django_rq.get_queue(RQ_LONG_QUEUE)
    try:
        _cancel(_job_id(user_pk), queue.connection)
    except (ConnectionError, TimeoutError):
        # The job checks the request is still current, so it does nothing.
        logger.warning("Could not cancel removal email for user %s", user_pk)


def _cancel(job_id: str, connection) -> None:
    try:
        Job.fetch(job_id, connection=connection).delete()
    except NoSuchJobError:
        pass


def email_removal_requested(user_pk: int, requested: str, language: str):
    """
    RQ job. Does nothing unless the request it was scheduled for still stands.

    A user with nothing to review is removed, everyone else gets the email with
    the abort link.
    """
    with transaction.atomic():
        try:
            # Locked so an abort can't land between the check and the delete.
            user = (
                get_user_model()
                .objects.select_for_update(of=("self",))
                .select_related("organisation")
                .get(pk=user_pk)
            )
        except ObjectDoesNotExist:
            return
        if not _is_current(user, requested):
            return
        organisation = user.organisation
        if organisation is None:
            raise ValueError(f"User {user_pk} has no organisation")
        email, context = user.email, _confirmation_context(user)
        if get_removal_report(user).classification == NO_ACTIVITY and _delete_user(
            user
        ):
            transaction.on_commit(lambda: end_user_access(user_pk))
            transaction.on_commit(
                lambda: send_removal_confirmation(email, context, language)
            )
            return f"Removed user {user_pk}"
    if not user.email:
        logger.info("User %s requested removal but has no email", user.pk)
        return
    abort_url = f"https://{organisation.host}{abort_removal_path(user)}"
    with translation.override(language):
        html_body = loader.render_to_string(
            "voteit/core/removal_requested.html",
            context={
                "full_name": user.get_full_name() or user.userid or user.username,
                "org_title": organisation.title,
                "abort_url": abort_url,
                "title": _("Your account is marked for removal"),
            },
        )
        subject = _("Your account is marked for removal")
    send_mail(
        subject=subject,
        message=strip_tags(html_body),
        html_message=html_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return f"Sent removal email to user {user.pk}"


def _delete_user(user) -> bool:
    try:
        with transaction.atomic():
            user.delete()
    except (ProtectedError, RestrictedError):
        # Something the report doesn't cover, e.g. a post without an agenda item.
        logger.warning("User %s has no activity but could not be deleted", user.pk)
        return False
    logger.info("Removed user %s on their own request", user.pk)
    return True


#: Postpone kinds. Both keep the user out of the managers' reminders, block also
#: tells managers not to remove yet -- advisory, removal still works.
POSTPONE_BLOCK = "block"
POSTPONE_REMIND = "remind"
POSTPONE_KINDS = (POSTPONE_BLOCK, POSTPONE_REMIND)


def _postpone_key(user_pk: int) -> str:
    return f"removal-postpone-{user_pk}"


def postpone_removal(user_pk: int, kind: str, until: datetime) -> None:
    """Kept in the cache, so losing it only means reminders come back early."""
    assert kind in POSTPONE_KINDS
    timeout = (until - now()).total_seconds()
    if timeout <= 0:
        clear_postponed_removal(user_pk)
        return
    cache.set(_postpone_key(user_pk), {"kind": kind, "until": until}, timeout)


def clear_postponed_removal(user_pk: int) -> None:
    cache.delete(_postpone_key(user_pk))


def get_postponed_removals(user_pks) -> dict[int, dict]:
    """``{user_pk: {"kind": ..., "until": ...}}`` for those postponed."""
    keys = {_postpone_key(pk): pk for pk in user_pks}
    if not keys:
        return {}
    return {keys[key]: value for key, value in cache.get_many(keys).items()}


DELETED = "deleted"
ANONYMISED = "anonymised"


def remove_user(user, language: str) -> str:
    """
    Remove a user who asked for it: deleted when nothing references them,
    anonymised otherwise. Returns DELETED or ANONYMISED.

    Run in a transaction with the row locked. The confirmation goes out after
    commit, in ``language``.
    """
    from voteit.core.anonymise import anonymise_user

    user_pk = user.pk
    email, context = user.email, _confirmation_context(user)
    if get_removal_report(user).classification == NO_ACTIVITY and _delete_user(user):
        transaction.on_commit(lambda: end_user_access(user_pk))
        result = DELETED
    else:
        anonymise_user(user)
        result = ANONYMISED
    transaction.on_commit(lambda: send_removal_confirmation(email, context, language))
    return result


def _confirmation_context(user) -> dict:
    return {
        "full_name": user.get_full_name() or user.userid or user.username,
        "org_title": user.organisation.title,
    }


def send_removal_confirmation(email: str, context: dict, language: str) -> None:
    if not email:
        return
    with translation.override(language):
        subject = _("Your account has been removed")
        html_body = loader.render_to_string(
            "voteit/core/removal_completed.html",
            context={**context, "title": subject},
        )
    send_mail(
        subject=subject,
        message=strip_tags(html_body),
        html_message=html_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )


#: Classifications, least to most in need of care.
NO_ACTIVITY = "no_activity"
INACTIVE_MEETINGS = "inactive_meetings"
ACTIVE_MEETING = "active_meeting"
ONGOING_POLL = "ongoing_poll"
#: Above the rest: removing them changes who runs the organisation.
ORGANISATION_ROLES = "organisation_roles"


@dataclass
class MeetingInvolvement:
    pk: int
    title: str
    state: str
    roles: list[str] = field(default_factory=list)
    used_invite: bool = False
    groups: list[str] = field(default_factory=list)
    ongoing_polls: int = 0
    votes: int = 0
    speaker_entries: int = 0
    proposals: int = 0
    discussion_posts: int = 0
    vote_transfers: int = 0
    reactions: int = 0


@dataclass
class RemovalReport:
    """What removing a user would affect, for a manager to judge."""

    user: object
    removable_after: datetime
    organisation_roles: list[str]
    meetings: list[MeetingInvolvement]
    classification: str
    postponed: dict | None = None


def removable_after(user) -> datetime:
    return user.removal_requested + timedelta(hours=settings.REMOVAL_WAIT_HOURS)


def _count_by(rows) -> dict[int, dict[int, int]]:
    """``{user_pk: {meeting_pk: count}}`` from ``(user_pk, meeting_pk)`` rows."""
    counts: dict[int, dict[int, int]] = {}
    for user_pk, meeting_pk in rows:
        per_user = counts.setdefault(user_pk, {})
        per_user[meeting_pk] = per_user.get(meeting_pk, 0) + 1
    return counts


def get_removal_report(user) -> RemovalReport:
    return get_removal_reports([user])[0]


def get_removal_reports(users) -> list[RemovalReport]:
    """
    Expects users with removal_requested set. A fixed number of queries,
    whatever the number of users.
    """
    from django.db.models import Q

    from voteit.discussion.models import DiscussionPost
    from voteit.invites.models import MeetingInvite
    from voteit.meeting.models import GroupMembership
    from voteit.meeting.models import Meeting
    from voteit.meeting.models import MeetingRoles
    from voteit.meeting.statemachines import MeetingStateMachine
    from voteit.organisation.models import OrganisationRoles
    from voteit.poll.models import Poll
    from voteit.poll.models import Vote
    from voteit.poll.models import VoteTransfer
    from voteit.poll.statemachines import PollStateMachine
    from voteit.proposal.models import Proposal
    from voteit.reactions.models import Reaction
    from voteit.speaker.models import Speaker

    users = list(users)
    if not users:
        return []
    user_pks = {user.pk for user in users}
    postponed = get_postponed_removals(user_pks)

    org_roles = {
        user_pk: list(assigned)
        for user_pk, assigned in OrganisationRoles.objects.filter(
            user__in=user_pks
        ).values_list("user_id", "assigned")
    }
    roles: dict[int, dict[int, list[str]]] = {}
    for user_pk, meeting_pk, assigned in MeetingRoles.objects.filter(
        user__in=user_pks
    ).values_list("user_id", "context_id", "assigned"):
        roles.setdefault(user_pk, {})[meeting_pk] = list(assigned)
    invited = _count_by(
        MeetingInvite.objects.filter(used_by__in=user_pks).values_list(
            "used_by_id", "meeting_id"
        )
    )
    groups: dict[int, dict[int, list[str]]] = {}
    for user_pk, meeting_pk, title in (
        GroupMembership.objects.filter(user__in=user_pks)
        .order_by("meeting_group__title")
        .values_list("user_id", "meeting_group__meeting_id", "meeting_group__title")
    ):
        groups.setdefault(user_pk, {}).setdefault(meeting_pk, []).append(title)
    # The key lookup can't use an index, the organisation keeps the scan small.
    voter_keys = {str(pk): pk for pk in user_pks}
    ongoing_rows = []
    for meeting_pk, voter_data in Poll.objects.filter(
        state=PollStateMachine.ongoing.value,
        meeting__organisation__in={user.organisation_id for user in users},
        electoral_register__voter_data__has_any_keys=list(voter_keys),
    ).values_list("meeting_id", "electoral_register__voter_data"):
        ongoing_rows.extend(
            (voter_keys[key], meeting_pk) for key in voter_keys if key in voter_data
        )
    ongoing_polls = _count_by(ongoing_rows)
    votes = _count_by(
        Vote.objects.filter(user__in=user_pks).values_list(
            "user_id", "poll__meeting_id"
        )
    )
    speaker_entries = _count_by(
        Speaker.objects.filter(user__in=user_pks).values_list(
            "user_id", "speaker_list__meeting_id"
        )
    )
    proposals = _count_by(
        Proposal.objects.filter(author__in=user_pks).values_list(
            "author_id", "agenda_item__meeting_id"
        )
    )
    discussion_posts = _count_by(
        DiscussionPost.objects.filter(author__in=user_pks).values_list(
            "author_id", "agenda_item__meeting_id"
        )
    )
    # Deleting the user cascades through these, so they must keep the user from
    # counting as no_activity.
    transfer_rows = []
    for meeting_pk, source_pk, target_pk in VoteTransfer.objects.filter(
        Q(source__in=user_pks) | Q(target__in=user_pks)
    ).values_list("meeting_id", "source_id", "target_id"):
        transfer_rows.extend(
            (pk, meeting_pk) for pk in {source_pk, target_pk} if pk in user_pks
        )
    vote_transfers = _count_by(transfer_rows)
    reactions = _count_by(
        Reaction.objects.filter(user__in=user_pks).values_list(
            "user_id", "button__meeting_id"
        )
    )

    per_user = {
        user_pk: set().union(
            *(
                source.get(user_pk, {})
                for source in (
                    roles,
                    invited,
                    groups,
                    ongoing_polls,
                    votes,
                    speaker_entries,
                    proposals,
                    discussion_posts,
                    vote_transfers,
                    reactions,
                )
            )
        )
        - {None}
        for user_pk in user_pks
    }
    meetings = Meeting.objects.filter(pk__in=set().union(*per_user.values()))
    meetings = {meeting.pk: meeting for meeting in meetings}
    active_states = {
        MeetingStateMachine.upcoming.value,
        MeetingStateMachine.ongoing.value,
    }

    reports = []
    for user in users:
        involvements = [
            MeetingInvolvement(
                pk=meeting.pk,
                title=meeting.title,
                state=meeting.state,
                roles=roles.get(user.pk, {}).get(meeting.pk, []),
                used_invite=meeting.pk in invited.get(user.pk, {}),
                groups=groups.get(user.pk, {}).get(meeting.pk, []),
                ongoing_polls=ongoing_polls.get(user.pk, {}).get(meeting.pk, 0),
                votes=votes.get(user.pk, {}).get(meeting.pk, 0),
                speaker_entries=speaker_entries.get(user.pk, {}).get(meeting.pk, 0),
                proposals=proposals.get(user.pk, {}).get(meeting.pk, 0),
                discussion_posts=discussion_posts.get(user.pk, {}).get(meeting.pk, 0),
                vote_transfers=vote_transfers.get(user.pk, {}).get(meeting.pk, 0),
                reactions=reactions.get(user.pk, {}).get(meeting.pk, 0),
            )
            for meeting in (meetings[pk] for pk in sorted(per_user[user.pk]))
        ]
        user_org_roles = org_roles.get(user.pk, [])
        if user_org_roles:
            classification = ORGANISATION_ROLES
        elif any(m.ongoing_polls for m in involvements):
            classification = ONGOING_POLL
        elif any(m.state in active_states for m in involvements):
            classification = ACTIVE_MEETING
        elif involvements:
            classification = INACTIVE_MEETINGS
        else:
            classification = NO_ACTIVITY
        reports.append(
            RemovalReport(
                user=user,
                removable_after=removable_after(user),
                organisation_roles=user_org_roles,
                meetings=involvements,
                classification=classification,
                postponed=postponed.get(user.pk),
            )
        )
    return reports
