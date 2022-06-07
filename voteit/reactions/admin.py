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
    list_filter = ("active", "meeting")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = (
        "button",
        "object_id",
        "content_type",
        "user",
        "agenda_item",
    )
    list_filter = (
        "agenda_item__meeting",
        "content_type",
        "button",
    )
