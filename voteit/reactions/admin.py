from django.contrib import admin

from voteit.meeting.admin import MeetingAdminMixin
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton


@admin.register(ReactionButton)
class ReactionButtonAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "meeting_link",
        "active",
        "pk",
    )
    list_filter = ("active", "meeting__organisation")
    search_fields = (
        "meeting__title",
        "title",
    )
    autocomplete_fields = ("meeting",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(qs)


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = (
        "button",
        "object_id",
        "content_type",
        "user",
        "agenda_item",
    )
    list_filter = ("user__organisation",)
    search_fields = (
        "meeting__title",
        "title",
        "user__userid",
    )
    autocomplete_fields = (
        "button",
        "user",
        "agenda_item",
    )
