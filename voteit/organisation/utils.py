from __future__ import annotations
from typing import Generator
from typing import TYPE_CHECKING

from django.db import models
from social_core.backends.base import BaseAuth
from social_core.backends.utils import load_backends
from social_django.models import UserSocialAuth
from social_django.utils import load_strategy

from voteit.organisation import IDPROXY_PROVIDER

if TYPE_CHECKING:
    from voteit.core.models import User


def get_provider_response_adapters():
    from .registries import provider_response_adapters

    return provider_response_adapters


# def annotate_org_from_actor():
#     qs = (
#         LogEntry.objects.exclude(actor__isnull=True)
#         .exclude(additional_data__has_key="o")
#         .exclude(
#             actor__organisation__isnull=True,
#         )
#     )
#     for log in qs:
#         if log.additional_data is None:
#             log.additional_data = {"o": log.actor.organisation_id}
#         else:
#             log.additional_data["o"] = log.actor.organisation_id
#         log.save()


def get_psa_backends() -> Generator[BaseAuth, None, None]:
    """
    This returns dummy versions of backends.
    """
    strategy = load_strategy()
    backend_class_names = strategy.get_backends()
    for backend in load_backends(backend_class_names).values():
        yield backend()


def get_idproxy_user_data(user: User) -> dict:
    """
    Fetch user_data from attached idproxy provider. But since for historic reasons,
    there might be duplicate users that we need to handle.
    """
    if user.is_anonymous:
        return {}
    # Fetch users social auth or related linked user
    if (
        usa := UserSocialAuth.objects.filter(
            provider=IDPROXY_PROVIDER,
        )
        .filter(models.Q(uid=user.identity_id) | models.Q(user=user))
        .first()
    ):
        return usa.extra_data.get("user_data", {})
    return {}
