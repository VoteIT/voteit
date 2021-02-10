from __future__ import annotations
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from voteit.core.component import Registry
    from voteit.meeting.models import Meeting


def get_policies(meeting: Meeting, only_active=True) -> List:
    """Return meeting access policies

    >>> from voteit.meeting.models import Meeting
    >>> from voteit.access_policy.app.policies import AutomaticAccess, ModeratorApprovedAccess
    >>> meeting = Meeting.objects.create()
    >>> auto_ap = AutomaticAccess.objects.create(meeting=meeting)
    >>> mod_ap = ModeratorApprovedAccess.objects.create(meeting=meeting, active=True)
    >>> [x.name for x in get_policies(meeting)]
    ['moderator_approved']

    >>> [x.name for x in get_policies(meeting, only_active=False)]
    ['automatic', 'moderator_approved']
    """
    query = {"meeting": meeting}
    if only_active:
        query["active"] = True
    results = []

    reg = get_access_policy_registry()
    for ap_klass in reg.values():
        ap = ap_klass.objects.filter(**query).first()
        if ap is not None:
            results.append(ap)
    return results
    # return [ap for ap_class in reg.values() if ap := ap_class.objects.filter(**query).first()]


def get_access_policy_registry() -> Registry:
    from .registries import access_policies

    return access_policies
