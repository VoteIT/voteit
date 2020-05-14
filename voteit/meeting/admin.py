from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.meeting.models import Meeting


@admin.register(Meeting)
class MeetingAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    # fields = ("title", )