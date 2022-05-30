from logging import LoggerAdapter
from logging import getLogger

from django.db.transaction import on_commit


# This is a special logger meant to catch notifications for ops.
notification_logger = getLogger("voteit.notifications")


class OnCommitLoggerAdapter(LoggerAdapter):
    """
    If there's an active transaction, delay the logging until after commit.
    Any exception will cause the log to be thrown away, but this is the point!
    (For instance only log actions that were performed correctly)
    """

    def log(self, level, msg, *args, **kwargs):
        """
        Delegate a log call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        if self.isEnabledFor(level):
            msg, kwargs = self.process(msg, kwargs)
            # NOTE: Pass db arg to support several databases!
            on_commit(lambda: self.logger.log(level, msg, *args, **kwargs))


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
