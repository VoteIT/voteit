from django.contrib import admin
from voteit.participant_number.models import PNSystem
from voteit.participant_number.models import ParticipantNumber


@admin.register(ParticipantNumber)
class ParticipantNumberAdmin(admin.ModelAdmin):
    autocomplete_fields = ("user",)
    list_display = (
        "user",
        "pns",
        "number",
    )
    # list_display_links = ("pns",)
    list_filter = (
        "pns",
        "user",
        "user__organisation",
    )
    search_fields = (
        "user__last_name",
        "user__first_name",
        "user__userid",
    )


@admin.register(PNSystem)
class PNSystemAdmin(admin.ModelAdmin):
    autocomplete_fields = ("meeting",)
    list_display = ("meeting",)
    list_filter = ("meeting",)
    search_fields = ("meeting__title",)
