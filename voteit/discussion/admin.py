from django.contrib import admin

from voteit.discussion.models import DiscussionPost


@admin.register(DiscussionPost)
class DiscussionPostAdmin(admin.ModelAdmin):
    list_filter = (
        "agenda_item__meeting",
        "agenda_item",
        "author",
    )  # "group"
    list_display = (
        "__str__",
        "meeting",
        "agenda_item",
        "author",
    )  # "group"
    search_fields = "body", "agenda_item__title", "agenda_item__meeting__title"
