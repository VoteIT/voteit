from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles


@admin.register(SpeakerListSystem)
class SLSystemAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = "state"
    list_display = ("title", "meeting", "method_name", "state")
    list_filter = ("meeting__organisation", "method_name", "state")
    autocomplete_fields = ("meeting",)
    search_fields = (
        "title",
        "meeting",
    )


@admin.register(SpeakerList)
class SLAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = "state"


@admin.register(SpeakerSystemRoles)
class SpeakerSystemRolesAdmin(admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "assigned", "context"
    list_filter = ("user__organisation",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )
