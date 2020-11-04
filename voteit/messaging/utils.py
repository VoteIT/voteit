from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

# from channels.db import database_sync_to_async
# from django.db.models import Model

logger = getLogger(__name__)

if TYPE_CHECKING:
    # from django.contrib.auth.models import AbstractUser
    from voteit.core.component import Registry


# @database_sync_to_async
# def check_permission(model: Model, pk: int, permission: str, user: AbstractUser) -> bool:
#     instance = model.objects.filter(pk=pk).first()
#     if instance is None:
#         logger.debug("No %s found with pk %s", model, pk)
#         return False
#     return user.has_perm(permission, instance)


def get_channel_registry() -> Registry:
    from voteit.messaging.registries import channel_registry
    return channel_registry
