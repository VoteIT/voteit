from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Max, F
from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting


class ListConfig(models.Model):
    pass


class ListHandler(models.Model):
    """ System responsible for setting order on speakers.
        There may be several of these per meeting, and they may even be the same type.
    """
    title = models.CharField(max_length=200, default="")
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE)
    moderators = models.ManyToManyField(
        User, related_name="%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True


class SpeakerList(models.Model):
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="speaker_lists"
    )
    agenda_item = models.ForeignKey(
        AgendaItem, on_delete=models.CASCADE, null=True, related_name="speaker_lists"
    )
    speakers = models.ManyToManyField(
        User, through="speaker.Speaker", related_name="speaker_lists"
    )


class SpeakerManager(models.Manager):
    def create(self, **kwargs) -> Speaker:
        speaker = self.model(**kwargs)

        with transaction.atomic():
            # Get our current max order number
            results = self.filter(list=speaker.list).aggregate(Max("order"))
            # Increment and use it for our new object
            current_order = results["order__max"]
            if current_order is not None:
                # Otherwise handled by default 1
                speaker.order = current_order + 1
            speaker.save()
            return speaker

    def move(self, speaker: Speaker, new_order: int):
        """ Move an object to a new order position """

        qs = self.get_queryset()

        with transaction.atomic():
            if speaker.order > int(new_order):
                qs.filter(
                    list=speaker.list, order__lt=speaker.order, order__gte=new_order
                ).exclude(pk=speaker.pk).update(order=F("order") + 1)
            else:
                qs.filter(
                    list=speaker.list, order__lte=new_order, order__gt=speaker.order
                ).exclude(pk=speaker.pk).update(order=F("order") - 1)

            speaker.order = new_order
            speaker.save()


class Speaker(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    list = models.ForeignKey(
        SpeakerList, on_delete=models.CASCADE, related_name="speakers"
    )
    created = models.DateTimeField(editable=False, auto_now_add=True)
    order = models.PositiveSmallIntegerField(default=1)
