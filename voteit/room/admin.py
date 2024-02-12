from django.contrib import admin

from voteit.meeting.admin import MeetingAdminMixin
from voteit.room.models import Room


@admin.register(Room)
class RoomAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "handler",
        "meeting_link",
        "created",
    )
    search_fields = (
        "meeting__title",
        "user__first_name",
        "user__last_nam",
        "user__userid",
    )
    autocomplete_fields = (
        "agenda_item",
        "handler",
        "poll",
    )
    list_filter = ("meeting__organisation",)
    readonly_fields = ("meeting",)
