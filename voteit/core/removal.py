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
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import ProtectedError
from django.db.models import RestrictedError
from django.template import loader
from django.utils import translation
from django.utils.html import strip_tags
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
            return
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


@dataclass
class RemovalReport:
    """What removing a user would affect, for a manager to judge."""

    user: object
    removable_after: datetime
    organisation_roles: list[str]
    meetings: list[MeetingInvolvement]
    classification: str


def removable_after(user) -> datetime:
    return user.removal_requested + timedelta(hours=settings.REMOVAL_WAIT_HOURS)


def _count_by(values) -> dict[int, int]:
    counts: dict[int, int] = {}
    for key in values:
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_removal_report(user) -> RemovalReport:
    """Expects a user with removal_requested set. A fixed number of queries."""
    from voteit.discussion.models import DiscussionPost
    from voteit.invites.models import MeetingInvite
    from voteit.meeting.models import GroupMembership
    from voteit.meeting.models import Meeting
    from voteit.meeting.statemachines import MeetingStateMachine
    from voteit.poll.models import Poll
    from voteit.poll.models import Vote
    from voteit.poll.statemachines import PollStateMachine
    from voteit.proposal.models import Proposal
    from voteit.speaker.models import Speaker

    org_roles = user.organisation_roles.first()
    org_roles = list(org_roles.assigned) if org_roles else []
    roles = {
        meeting_pk: list(assigned)
        for meeting_pk, assigned in user.meeting_roles.values_list(
            "context_id", "assigned"
        )
    }
    invited = set(
        MeetingInvite.objects.filter(used_by=user).values_list("meeting_id", flat=True)
    )
    groups: dict[int, list[str]] = {}
    for meeting_pk, title in (
        GroupMembership.objects.filter(user=user)
        .order_by("meeting_group__title")
        .values_list("meeting_group__meeting_id", "meeting_group__title")
    ):
        groups.setdefault(meeting_pk, []).append(title)
    ongoing_polls = _count_by(
        Poll.objects.filter(
            state=PollStateMachine.ongoing.value,
            electoral_register__voter_data__has_key=str(user.pk),
        ).values_list("meeting_id", flat=True)
    )
    votes = _count_by(
        Vote.objects.filter(user=user).values_list("poll__meeting_id", flat=True)
    )
    speaker_entries = _count_by(
        Speaker.objects.filter(user=user).values_list(
            "speaker_list__meeting_id", flat=True
        )
    )
    proposals = _count_by(
        Proposal.objects.filter(author=user).values_list(
            "agenda_item__meeting_id", flat=True
        )
    )
    discussion_posts = _count_by(
        DiscussionPost.objects.filter(author=user).values_list(
            "agenda_item__meeting_id", flat=True
        )
    )

    meeting_pks = set().union(
        roles,
        invited,
        groups,
        ongoing_polls,
        votes,
        speaker_entries,
        proposals,
        discussion_posts,
    )
    meeting_pks.discard(None)
    meetings = [
        MeetingInvolvement(
            pk=meeting.pk,
            title=meeting.title,
            state=meeting.state,
            roles=roles.get(meeting.pk, []),
            used_invite=meeting.pk in invited,
            groups=groups.get(meeting.pk, []),
            ongoing_polls=ongoing_polls.get(meeting.pk, 0),
            votes=votes.get(meeting.pk, 0),
            speaker_entries=speaker_entries.get(meeting.pk, 0),
            proposals=proposals.get(meeting.pk, 0),
            discussion_posts=discussion_posts.get(meeting.pk, 0),
        )
        for meeting in Meeting.objects.filter(pk__in=meeting_pks).order_by("pk")
    ]
    active_states = {
        MeetingStateMachine.upcoming.value,
        MeetingStateMachine.ongoing.value,
    }
    if org_roles:
        classification = ORGANISATION_ROLES
    elif any(m.ongoing_polls for m in meetings):
        classification = ONGOING_POLL
    elif any(m.state in active_states for m in meetings):
        classification = ACTIVE_MEETING
    elif meetings:
        classification = INACTIVE_MEETINGS
    else:
        classification = NO_ACTIVITY
    return RemovalReport(
        user=user,
        removable_after=removable_after(user),
        organisation_roles=org_roles,
        meetings=meetings,
        classification=classification,
    )
