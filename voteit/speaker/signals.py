from __future__ import annotations

from typing import TYPE_CHECKING, Type

from django.db import models
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import Signal
from django.dispatch import receiver
from voteit.speaker.models import Speaker

if TYPE_CHECKING:
    pass


list_updated = Signal(providing_args=["sender", "instance", "queue"])


@receiver(post_save, sender=Speaker)
def set_initial_order(
    sender: Type[Speaker], instance: Speaker, created: bool, **kwargs
):
    """
    :param sender: Model
    :param instance: Speaker instance
    :param created: Is this a new db records? We only care about the newly created for this method.
    :param kwargs:
    """
    if created:
        sl = instance.list
        results = sl.speaker_items.filter(order__isnull=False).aggregate(
            models.Max("order")
        )
        current_order = results["order__max"]
        if current_order is None:
            order = 1
        else:
            order = current_order + 1
        instance.order = order
        instance.save()
        sl.reorder()


@receiver(post_delete, sender=Speaker)
def reorder_after_delete(sender: Type[Speaker], instance: Speaker, **kwargs):
    instance.list.reorder(force_signal=True)
