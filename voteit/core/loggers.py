from __future__ import annotations

from logging import LoggerAdapter
from logging import getLogger
from typing import TYPE_CHECKING

from django.core.handlers.wsgi import WSGIRequest
from django.db.models import Model
from django.db.transaction import on_commit
from rest_framework.request import Request

from voteit.core.abcs import MeetingContext
from voteit.core.abcs import OrganisationContext
from voteit.core.utils import get_model_shortname

if TYPE_CHECKING:
    from voteit.core.models import User as UserType
    from voteit.core.role import Role


class OnCommitAdapterMixin:
    """
    If there's an active transaction, delay the logging until after commit.
    Any exception will cause the log to be thrown away, but this is the point!
    (For instance only log actions that were performed correctly)
    """

    def log(self, level, msg, *args, **kwargs):
        """
        Delegate a log call to the underlying logger, but only after successful commit.
        """
        if self.isEnabledFor(level):
            msg, kwargs = self.process(msg, kwargs)
            # NOTE: Pass db arg to support several databases!
            on_commit(lambda: self.logger.log(level, msg, *args, **kwargs))


class EventAdapterMixin:
    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        if request := kwargs.pop("request", None):
            request: Request | WSGIRequest
            kwargs["extra"]["actor"] = getattr(request, "user", None)
            kwargs["extra"]["path"] = request.path
            kwargs["extra"]["method"] = request.method
        if context := kwargs.pop("context", None):
            context: Model
            kwargs["extra"]["context_name"] = get_model_shortname(context)
            kwargs["extra"]["context"] = context.pk
            organisation = None
            if isinstance(context, OrganisationContext):
                organisation = getattr(context.organisation, "pk", None)
            if isinstance(context, MeetingContext):
                kwargs["extra"]["meeting"] = context.meeting.pk
                if organisation is None:
                    organisation = getattr(context.meeting.organisation, "pk", None)
            if organisation:
                kwargs["extra"]["org"] = organisation
        for k in set(kwargs) - {"extra"}:
            # Move other things to extra domain
            val = kwargs.pop(k)
            if isinstance(val, Model):
                val = val.pk
            kwargs["extra"][k] = val
        return msg, kwargs


class OnCommitLoggerAdapter(OnCommitAdapterMixin, LoggerAdapter):
    ...


class OnCommitEventLoggerAdapter(
    OnCommitAdapterMixin, EventAdapterMixin, LoggerAdapter
):
    ...


class EventLoggerAdapter(EventAdapterMixin, LoggerAdapter):
    ...


def getOnCommitLogger(name=None, extra=None):
    """
    Return any logger but modify its behaviour to defer logging until on_commit.
    (Essentially this makes sure that the operation the log is about really happened!)

    Note that we won't force transactions here since it may cause logging messages to get lost or
    behave odd for critical levels.
    """
    logger = getLogger(name=name)
    logger = OnCommitLoggerAdapter(logger, extra)
    return logger


def getEventLogger(name=None, extra=None, on_commit=True):
    """
    Logger with on_commit behaviour and some extra methods to extract user and context from kwargs.
    """
    logger = getLogger(name=name)
    if extra is None:
        # We need a dict here
        extra = {}
    if on_commit:
        logger = OnCommitEventLoggerAdapter(logger, extra)
    else:
        logger = EventLoggerAdapter(logger, extra)
    return logger


# This is a special logger meant to catch notifications for ops.
notification_logger = getLogger("voteit.notification")
# This is the 'root' namespace for events. Create specific namespaces for each event type by adding
# names afterwards
events_logger = getEventLogger("voteit.event")
# A permission is changed by someone
roles_logger = getEventLogger("voteit.event.roles")
# Authentication logger
auth_logger = getEventLogger("voteit.event.auth", on_commit=False)


def log_roles_change(
    msg: str,
    *,
    actor: UserType | None,
    context: Model,
    for_user: UserType,
    roles: list[Role, str],
    **kwargs,
) -> None:
    """
    Shorthand to log changes to roles

    :param msg: Describe origin
    :param actor: Who did this
    :param context: Where
    :param for_user: Who was changed
    :param roles: List of roles
    """
    roles_logger.info(
        msg,
        actor=actor,
        context=context,
        for_user=for_user,
        roles=list(str(x) for x in roles),
        **kwargs,
    )


def log_auth(
    msg: str,
    *,
    request: Request | WSGIRequest,
    actor: UserType | None = None,
    context: Model = None,
    for_user: UserType = None,
    **kwargs,
):
    """
    Shorthand auth log

    :param msg: Describe action
    :param request:
    :param actor: Who did this, usually fetched from request
    :param context: Where the auth-event was. (Usually org)
    :param for_user: Is this for someone else than the actor?
    """
    if actor:
        kwargs["actor"] = actor
    if context:
        kwargs["context"] = context
    if for_user:
        kwargs["for_user"] = for_user
    ip = request.META.get("HTTP_X_FORWARDED_FOR", None)
    if not ip:
        ip = request.META.get("REMOTE_ADDR", None)
    if ip:
        kwargs["ip"] = ip
    auth_logger.info(
        msg,
        request=request,
        **kwargs,
    )
