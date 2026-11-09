"""
GDPR removal requests.

Requesting removal emails the account's address after a delay, with a link to
abort. That email is what protects against someone else requesting removal
from the user's unattended computer.
"""

from __future__ import annotations

from datetime import timedelta
from logging import getLogger
from urllib.parse import urlencode

import django_rq
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.template import loader
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.translation import gettext as _
from redis.exceptions import ConnectionError
from redis.exceptions import TimeoutError
from rq.exceptions import NoSuchJobError
from rq.job import Job

from voteit.core import RQ_LONG_QUEUE

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
    """RQ job. Does nothing unless the request it was scheduled for still stands."""
    try:
        user = get_user_model().objects.select_related("organisation").get(pk=user_pk)
    except ObjectDoesNotExist:
        return
    if not _is_current(user, requested):
        return
    organisation = user.organisation
    if organisation is None:
        return
    if not user.email:
        logger.info("User %s requested removal but has no email", user.pk)
        return
    abort_url = f"https://{organisation.host}{abort_removal_path(user)}"
    with translation.override(language):
        html_body = loader.render_to_string(
            "voteit/core/removal_requested.html",
            context={
                "full_name": user.get_full_name() or user.username,
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
