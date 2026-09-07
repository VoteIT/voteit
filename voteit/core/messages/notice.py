"""s.msg -- an arbitrary notice from the server to connected clients.

Deliberately unrelated to anything else. It is not part of the connection
lifecycle -- that is ``s.close`` / ``s.closing``, which carry only a close code
-- and not an object update, so it has no pk and no owning model. It exists so
an operator can say something to whoever is connected: a maintenance warning
before a restart, or anything worth putting in the console.

``type`` is a closed set so the frontend can switch on it exhaustively and a
typo fails here rather than rendering as nothing in a browser.
"""

from typing import Literal
from typing import get_args

from chanx.messages.base import BaseMessage
from pydantic import BaseModel

from voteit.messaging.decorators import outgoing

NoticeType = Literal["info", "warning", "error"]

#: The same values as a tuple, for the management commands' argparse
#: ``choices=``. Derived rather than repeated so a command cannot offer a type
#: the wire contract does not have, or miss one it gains.
NOTICE_TYPES = get_args(NoticeType)


class NoticeSchema(BaseModel):
    type: NoticeType = "info"
    #: Shown to the user as-is, so it is already translated when it is sent.
    message: str


@outgoing
class Notice(BaseMessage):
    action: Literal["s.msg"] = "s.msg"
    payload: NoticeSchema
