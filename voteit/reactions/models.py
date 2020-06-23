from django.db import models
from voteit.meeting.models import Meeting


class Reaction(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE)
    name = models.CharField(max_length=40)
