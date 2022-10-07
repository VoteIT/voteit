from django.contrib import admin

from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton


@admin.register(ReactionButton)
class ReactionButtonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "meeting",
        "active",
        "pk",
    )
    list_filter = ("active", "meeting__organisation")
    search_fields = (
        "meeting__title",
        "title",
    )


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
    search_fields = ("meeting__title", "title", "user__userid")
