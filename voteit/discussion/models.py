from django.db import models

from voteit.core.models import BaseContent


class DiscussionPost(BaseContent):
    agenda_item = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        null=True,
        related_name="discussions",
    )
