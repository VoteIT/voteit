from __future__ import annotations

from logging import getLogger
from typing import List
from typing import TYPE_CHECKING

from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.component import Registry
    from voteit.access_policy.models import AccessPolicy

logger = getLogger(__name__)


def get_policies(meeting: Meeting, only_active=True) -> List[AccessPolicy]:
    """
    Return meeting access policies
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
