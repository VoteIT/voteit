from typing import Optional

from django.contrib.auth.models import User
from django.db import models
from voteit.meeting.models import Meeting


class ParticipantNumber(models.Model):
    """ A specific number for a specific user within a meeting.
        This works as an alias in situations where it would be impractical to use usernames,
        for instance a plenary debate with bad internet connections. Speakers (users)
        could then have signs with a number on that the moderator simply enters to queue them.
    """
    number = models.PositiveSmallIntegerField()
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    pns = models.ForeignKey("PNSystem", on_delete=models.CASCADE, related_name="numbers")
    created = models.DateTimeField(editable=False, auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "pns"],
                name="%(app_label)s_%(class)s_unique_check_for_user",
            ),
            models.UniqueConstraint(
                fields=["pns", "number"],
                name="%(app_label)s_%(class)s_unique_check_for_number",
            ),
        ]


class PNSystem(models.Model):
    """
    The Participant number system has a 1-1 relation to a meeting.

    Most of the permission checks for this system is delegated to the related meeting,
    so there's no separate role.
    """
    meeting: Optional[Meeting] = models.OneToOneField(
        Meeting, on_delete=models.CASCADE, null=True
    )

    def get_user(self, pn: int, default=None) -> Optional[User]:
        for pn_obj in self.numbers.filter(number=pn).all().prefetch_related('user'):
            return pn_obj.user
        return default
