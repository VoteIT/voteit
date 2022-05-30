from __future__ import annotations
from logging import LoggerAdapter
from logging import getLogger
from typing import Optional
from typing import TYPE_CHECKING

from django.db.transaction import on_commit

from voteit.core.utils import get_model_shortname

if TYPE_CHECKING:
    from django.db.models import Model
    from voteit.core.models import User as UserType
    from voteit.core.role import Role


class OnCommitLoggerAdapter(LoggerAdapter):
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


class EventLoggerAdapter(OnCommitLoggerAdapter):
    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        if context := kwargs.pop("context"):
            context: Model
            kwargs["extra"]["context_name"] = get_model_shortname(context)
            kwargs["extra"]["context_pk"] = context.pk
        if actor := kwargs.pop("actor"):
            actor: UserType
            kwargs["extra"]["actor"] = actor.pk
        if for_user := kwargs.pop("for_user"):
            for_user: UserType
            kwargs["extra"]["for_user"] = for_user.pk
        for k in set(kwargs) - {"extra"}:
            # Move other things to extra domain
            kwargs["extra"][k] = kwargs.pop(k)
        return msg, kwargs


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


def getEventLogger(name=None, extra=None):
    """
    Logger with on_commit behaviour and some extra methods to extract user and context from kwargs.
    """
    logger = getLogger(name=name)
    if extra is None:
        # We need a dict here
        extra = {}
    logger = EventLoggerAdapter(logger, extra)
    return logger


# This is a special logger meant to catch notifications for ops.
notification_logger = getLogger("voteit.notification")
# This is the 'root' namespace for events. Create specific namespaces for each event type by adding
# names afterwards
events_logger = getEventLogger("voteit.event")
# A permission is changed by someone
roles_logger = getEventLogger("voteit.event.roles")


def log_roles_change(
    msg: str,
    *,
    actor: Optional[UserType],
    context: Model,
    for_user: UserType,
    roles: list[Role, str],
    extra: Optional[dict] = None,
) -> None:
    """
    Shorthand to log changes to roles

    :param msg: Describe origin
    :param actor: Who did this
    :param context: Where
    :param for_user: Who was changed
    :param roles: List of roles
    :param extra: extra log param
    """
    roles_logger.info(
        msg,
        actor=actor,
        context=context,
        for_user=for_user,
        roles=list(str(x) for x in roles),
    )
