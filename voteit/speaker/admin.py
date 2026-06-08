from django.contrib import admin

from voteit.core.admin import StateMachineAdminMixin
from voteit.meeting.admin import MeetingAdminMixin
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles


@admin.register(SpeakerListSystem)
class SLSystemAdmin(StateMachineAdminMixin, MeetingAdminMixin, admin.ModelAdmin):
    list_display = (
        "room",
        "meeting_link",
        "method_name",
        "state",
    )
    list_filter = (
        "meeting__organisation",
        "method_name",
        "state",
    )
    readonly_fields = (
        "active_list",
        "meeting",
        "room",
    )
    autocomplete_fields = (
        "meeting",
        "room",
    )
    search_fields = (
        "room__title",
        "meeting__title",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(qs)


@admin.register(SpeakerList)
class SLAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = (
        "agenda_item",
        "speaker_system",
    )
    list_display = (
        "__str__",
        "meeting_link",
        "speakers_count",
    )
    list_filter = ("speaker_system__meeting__organisation",)
    readonly_fields = ("order",)
    search_fields = (
        "title",
        "meeting__title",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(
            qs,
            title_attr="speaker_system__meeting__title",
        )

    @admin.display(description="Speakers")
    def speakers_count(self, sl: SpeakerList):
        return sl.speaker_items.count()


@admin.register(Speaker)
class SpeakerAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = (
        "speaker_list",
        "user",
    )
    list_display = (
        "__str__",
        "speaker_list",
        "user",
        "started",
        "seconds",
        "meeting_link",
    )
    list_filter = ("speaker_list__speaker_system__meeting__organisation",)
    # readonly_fields = ("order",)
    search_fields = (
        "user__first_name",
        "user__last_name",
        "speaker_list__title",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(
            qs,
            title_attr="speaker_list__speaker_system__meeting__title",
            pk_attr="speaker_list__speaker_system__meeting_id",
        )


@admin.register(SpeakerSystemRoles)
class SpeakerSystemRolesAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "meeting_link", "get_assigned"
    list_filter = ("user__organisation",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )

    def get_assigned(self, instance):
        return instance.assigned

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(
            qs, title_attr="context__meeting__title", pk_attr="context__meeting_id"
        )
