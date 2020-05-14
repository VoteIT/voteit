from django.contrib import admin

from voteit.discussion.models import DiscussionPost


@admin.register(DiscussionPost)
class DiscussionPostAdmin(admin.ModelAdmin):
    pass
