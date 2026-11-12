from django.contrib import admin

from .models import HistoryLog
from .models import MeetingStats
from .models import OrganisationPeriodStats


def _fmt_duration(td):
    if not td:
        return "—"
    total = int(td.total_seconds())
    h, m = divmod(total // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


@admin.register(HistoryLog)
class HistoryLogAdmin(admin.ModelAdmin):
    list_display = (
        "org",
        "date",
        "user_online_count",
        "action_count",
        "fmt_online",
        "speaker_count",
        "fmt_spoken",
    )
    list_filter = ("org",)
    date_hierarchy = "date"
    readonly_fields = (
        "mean_online_duration",
        "mean_spoken_duration",
        "action_types",
        "content_types",
        "proposal_outcomes",
    )

    @admin.display(description="Online")
    def fmt_online(self, obj):
        return _fmt_duration(obj.online_duration)

    @admin.display(description="Speaking")
    def fmt_spoken(self, obj):
        return _fmt_duration(obj.spoken_duration)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrganisationPeriodStats)
class OrganisationPeriodStatsAdmin(ReadOnlyAdmin):
    list_display = (
        "org",
        "period",
        "start",
        "unique_online_users",
        "unique_logins",
        "unique_actors",
        "active_meetings",
        "unique_participants",
    )
    list_filter = ("period", "org")
    date_hierarchy = "start"


@admin.register(MeetingStats)
class MeetingStatsAdmin(ReadOnlyAdmin):
    list_display = (
        "meeting_id",
        "title",
        "org",
        "first_activity",
        "last_activity",
        "unique_participants",
        "unique_voters",
        "poll_count",
    )
    list_filter = ("org",)
    search_fields = ("title",)
    date_hierarchy = "last_activity"
