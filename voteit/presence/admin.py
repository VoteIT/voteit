from django.contrib import admin

from voteit.meeting.admin import MeetingAdminMixin
from voteit.presence.models import PresenceCheck
from voteit.presence.models import Presence


@admin.register(PresenceCheck)
class PresenceCheckAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = "state", "meeting_link", "opened", "closed"
    list_filter = ("state", "meeting__organisation")
    exclude = ("state",)
    search_fields = ("meeting__title",)
    autocomplete_fields = ("meeting",)


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_filter = ("user__organisation", "presence_check__state")
    list_display = "user", "presence_check", "created", "meeting"
    autocomplete_fields = ("user", "presence_check")
    search_fields = (
        "user__last_name",
        "user__first_name",
        "user__userid",
    )
