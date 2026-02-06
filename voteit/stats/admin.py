from django.contrib import admin

from .models import HistoryLog


@admin.register(HistoryLog)
class HistoryLogAdmin(admin.ModelAdmin):
    list_display = (
        "org",
        "date",
        "user_online_count",
        "action_count",
        "online_duration",
        "speaker_count",
        "spoken_duration",
        "login_count",
    )
    list_filter = ("org", "date")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
