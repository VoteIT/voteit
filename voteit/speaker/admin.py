from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles


@admin.register(SpeakerListSystem)
class SLSystemAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = "state"
    list_display = ("title", "meeting", "method_name", "state")
    list_filter = ("meeting", "method_name", "state")
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
    list_display = "assigned", "user", "context"
