from __future__ import annotations
from typing import Union, TYPE_CHECKING

import rules
from django.contrib.auth.models import User
from django.db.models import Model

if TYPE_CHECKING:
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import Meeting


@rules.predicate
def is_author(user: User, instance: Model):
    return getattr(instance, "author", object()) == user


@rules.predicate
def is_not_archived(user: User, instance: Union[Meeting, AgendaItem]):
    """ Generic check for archived state.
        Keep this as a negated state since check for is not None will return a false positive otherwise!
    """
    return instance is not None and getattr(instance, "state", None) not in ("archived", "archiving", None)
