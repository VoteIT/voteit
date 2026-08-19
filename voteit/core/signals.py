from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db.models.signals import class_prepared
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from voteit.core import models_to_register

if TYPE_CHECKING:
    from django.db.models import Model


# The following signals will provide arguments "sender", "instance" and "roles"
roles_added = Signal()
roles_removed = Signal()
# Sends signals based on python-statemachine transitions. Use helper in utils to send signal
# sender    instance class
# instance  the wrapped model
# source    source state instance
# target    target state instance
# event     sm event instance
before_sm_transition = Signal()
after_sm_transition = Signal()


@receiver(class_prepared)
def deferred_register_model(sender: Model, **kw):
    """Prep register models in content registry.
    Done in apps ready()
    """

    models_to_register.add(sender)


def post_init_registrations():
    User = get_user_model()
    from voteit.core.messages.user import InvalidateUserCache
    from voteit.messaging.channels import OnlineChannel

    @receiver(pre_delete, sender=User)
    @receiver(post_save, sender=User)
    def invalidate_user_cache(*, instance: User, created=False, **kwargs):
        if not created:
            msg = InvalidateUserCache(payload={"pk": instance.pk})
            OnlineChannel().sync_publish(msg)
