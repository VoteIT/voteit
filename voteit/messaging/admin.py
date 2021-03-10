from django.contrib import admin

from voteit.messaging.models import Connection


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = "user", "online", "channel_name", "first_seen", "last_action"
    list_filter = "online", "user", "first_seen", "last_action"
    readonly_fields = "online", "first_seen", "last_action"
    search_fields = ("user",)
