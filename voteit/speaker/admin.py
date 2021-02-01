from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from .models import *


@admin.register(SpeakerListSystem)
class SLSystemAdmin(admin.ModelAdmin):
    list_display = ("title", "meeting", "method_name")
    list_filter = ("meeting", "method_name")
    autocomplete_fields = ("meeting",)
    search_fields = (
        "title",
        "meeting",
    )


@admin.register(SpeakerList)
class SLAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = "state"
