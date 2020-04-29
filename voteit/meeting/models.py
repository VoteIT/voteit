from django.contrib.auth.models import User
from django.db import models

# Create your models here.
from voteit.core.models import BaseContent, WorkflowMixin
from voteit.meeting.workflow import MeetingWorkflow


class Meeting(BaseContent, WorkflowMixin):
    wf_name = MeetingWorkflow.name
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    participants = models.ManyToManyField(User, blank=True, related_name="participant_in_meetings")
    potential_voters = models.ManyToManyField(User, blank=True, related_name="potential_voter_in_meetings")
