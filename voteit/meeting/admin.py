from django.contrib import admin

from voteit.meeting.models import Meeting


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    pass