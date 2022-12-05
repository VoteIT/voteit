from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.meeting.admin import MeetingAdminMixin
from voteit.presence.models import PresenceSystem
from voteit.presence.models import PresenceCheck
from voteit.presence.models import Presence


@admin.register(PresenceSystem)
class PresenceSystemAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = ("meeting_link",)
    search_fields = ("meeting__title",)
    list_filter = ("meeting__organisation",)


@admin.register(PresenceCheck)
class PresenceCheckAdmin(MeetingAdminMixin, FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = "state", "meeting_link", "presence_system", "opened", "closed"
    list_filter = ("state", "meeting__organisation")
    exclude = ("state",)
    search_fields = ("meeting__title",)


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
