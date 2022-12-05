from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.meeting.admin import MeetingAdminMixin
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles


@admin.register(SpeakerListSystem)
class SLSystemAdmin(MeetingAdminMixin, FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = "state"
    list_display = ("title", "meeting_link", "method_name", "state")
    list_filter = ("meeting__organisation", "method_name", "state")
    readonly_fields = ("active_list",)
    autocomplete_fields = ("meeting",)
    search_fields = (
        "title",
        "meeting",
    )


@admin.register(SpeakerList)
class SLAdmin(MeetingAdminMixin, FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = "state"
    autocomplete_fields = (
        "agenda_item",
        "speaker_system",
    )
    list_display = (
        "__str__",
        "meeting_link",
        "is_current",
        "speakers_count",
    )
    list_filter = ("speaker_system__meeting__organisation",)
    readonly_fields = ("current", "order")
    search_fields = (
        "title",
        "meeting__title",
    )

    @admin.display(description="Current", boolean=True)
    def is_current(self, sl: SpeakerList):
        return bool(sl.current)

    @admin.display(description="Speakers")
    def speakers_count(self, sl: SpeakerList):
        return sl.speaker_items.count()


@admin.register(SpeakerSystemRoles)
class SpeakerSystemRolesAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "meeting_link", "assigned"
    list_filter = ("user__organisation",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )
