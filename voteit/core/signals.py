from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import class_prepared
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.core import models_to_register

if TYPE_CHECKING:
    from django.db.models import Model


roles_added = Signal(providing_args=["sender", "instance", "roles"])
roles_removed = Signal(providing_args=["sender", "instance", "roles"])


@receiver(class_prepared)
def deferred_register_model(sender: Model, **kw):
    """Prep register models in content registry.
    Done in apps ready()
    """

    models_to_register.add(sender)
