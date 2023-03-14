from django.contrib import admin

from voteit.active.models import ActiveUser
from voteit.meeting.admin import MeetingAdminMixin


@admin.register(ActiveUser)
class ActiveUserAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "user",
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
        "meeting",
        "user",
    )
    list_filter = ("meeting__organisation",)
