from django.db import models

from voteit.core.models import BaseContent
from voteit.reactions.mixins import Reactable


class DiscussionPost(BaseContent, Reactable):
    agenda_item = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        null=True,
        related_name="discussions",
    )
