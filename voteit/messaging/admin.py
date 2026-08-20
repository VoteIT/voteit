"""Admin for the websocket Connection log.

Connection rows are written by the consumer and never edited by hand, so this
is a read-only admin plus one repair action. The only real awkwardness is that
Connection has no foreign key to User (see the model docstring), so every
user-facing column and filter has to go through an explicit subquery -- the
same trick voteit.core.admin.OnlineFilter already uses.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.views.main import ChangeList
from django.db import models
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timezone import now

from voteit.core.models import User
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import NORMAL_CLOSE_CODES
from voteit.messaging.models import Connection
from voteit.organisation.models import Organisation

# Windows offered by the "Online now" page, in minutes.
WINDOW_CHOICES = (5, 15, 60)
DEFAULT_WINDOW = 15

# How long a connection has been open, for the "Online now" histogram. Ordered
# smallest first; the last entry is the catch-all and needs no bound.
CONNECTED_FOR_BUCKETS = (
    ("< 5 min", timedelta(minutes=5)),
    ("5-30 min", timedelta(minutes=30)),
    ("30 min - 2 h", timedelta(hours=2)),
    ("2-8 h", timedelta(hours=8)),
    ("> 8 h", None),
)


def stale_after() -> timedelta:
    """Read the window at call time so override_settings works in tests."""
    return timedelta(seconds=settings.VOTEIT_CONNECTION_STALE_AFTER)


def fmt_duration(td: timedelta | None) -> str:
    if not td:
        return "—"
    total = int(td.total_seconds())
    if total < 60:
        return f"{total}s"
    h, m = divmod(total // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def bucket_case(reference):
    """Case expression labelling each row by how long it has been connected."""
    whens = [
        models.When(
            connected_at__gt=reference - upper,
            then=models.Value(label),
        )
        for label, upper in CONNECTED_FOR_BUCKETS
        if upper is not None
    ]
    return models.Case(
        *whens,
        default=models.Value(CONNECTED_FOR_BUCKETS[-1][0]),
        output_field=models.CharField(),
    )


def user_admin_link(user: User | None, user_id: int) -> str:
    if user is None:
        return format_html("<em>#{} (deleted)</em>", user_id)
    try:
        link = reverse("admin:core_user_change", args=[user.pk])
    except NoReverseMatch:
        return str(user)
    return format_html('<a href="{}">{}</a>', link, user)


def attach_users(connections: list[Connection]) -> list[Connection]:
    """Resolve ``user_id`` to a User in one query, since there is no FK."""
    users = User.objects.select_related("organisation").in_bulk(
        {c.user_id for c in connections}
    )
    for conn in connections:
        conn.user = users.get(conn.user_id)
    return connections


class ConnectionChangeList(ChangeList):
    """Attaches the User to every row on the page in a single extra query."""

    def get_results(self, request):
        super().get_results(request)
        self.result_list = attach_users(list(self.result_list))


class ConnectionStateFilter(admin.SimpleListFilter):
    title = "State"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "state"
    # Constants
    ONLINE = "online"
    STALE = "stale"
    CLOSED = "closed"
    CLOSED_ABNORMALLY = "abnormal"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            (self.ONLINE, "Online"),
            (self.STALE, "Stale (open but silent)"),
            (self.CLOSED, "Closed normally"),
            (self.CLOSED_ABNORMALLY, "Closed abnormally"),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        window = stale_after()
        if self.value() == self.ONLINE:
            return queryset.online(window)
        elif self.value() == self.STALE:
            return queryset.stale(window)
        elif self.value() == self.CLOSED:
            return queryset.filter(code__in=NORMAL_CLOSE_CODES)
        elif self.value() == self.CLOSED_ABNORMALLY:
            return queryset.filter(code__isnull=False).exclude(
                code__in=NORMAL_CLOSE_CODES
            )
        return queryset


class ConnectionOrganisationFilter(admin.SimpleListFilter):
    title = "Organisation"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "org"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return Organisation.objects.order_by("title").values_list("pk", "title")

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if value := self.value():
            return queryset.filter(
                user_id__in=User.objects.filter(organisation=value).values("pk")
            )
        return queryset


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    change_list_template = "admin/voteit_messaging/connection/change_list.html"
    list_display = (
        "user_link",
        "organisation",
        "state",
        "connected_at",
        "last_action",
        "duration_display",
        "code",
        "channel_name",
    )
    # Nothing here is editable, so no column links to the change view -- that
    # would also nest an anchor inside the user link below.
    list_display_links = None
    list_filter = (
        ConnectionStateFilter,
        ConnectionOrganisationFilter,
        ("connected_at", admin.DateFieldListFilter),
    )
    # Users are matched via subquery in get_search_results; this only makes the
    # search box render.
    search_fields = ("channel_name",)
    list_per_page = 50
    # The table has hundreds of thousands of rows and is never reaped, so skip
    # the unfiltered COUNT that the changelist would otherwise run.
    show_full_result_count = False
    # date_hierarchy is deliberately absent for the same reason.
    actions = ["close_stale_connections"]

    def get_changelist(self, request, **kwargs):
        return ConnectionChangeList

    def get_queryset(self, request):
        return super().get_queryset(request).with_duration()

    def get_search_results(self, request, queryset, search_term):
        term = search_term.strip()
        if not term:
            return queryset, False
        query = models.Q(channel_name__icontains=term)
        if term.isdigit():
            query |= models.Q(user_id=int(term))
        query |= models.Q(
            user_id__in=User.objects.filter(
                models.Q(email__icontains=term)
                | models.Q(first_name__icontains=term)
                | models.Q(last_name__icontains=term)
                | models.Q(userid__icontains=term)
                | models.Q(username__icontains=term)
            ).values("pk")
        )
        return queryset.filter(query), False

    @admin.display(description="User")
    def user_link(self, obj: Connection):
        return user_admin_link(getattr(obj, "user", None), obj.user_id)

    @admin.display(description="Organisation")
    def organisation(self, obj: Connection):
        user = getattr(obj, "user", None)
        # None renders as the admin's empty_value_display.
        return user.organisation if user else None

    @admin.display(description="State")
    def state(self, obj: Connection):
        if obj.code is not None:
            return f"Closed ({obj.code})"
        if obj.last_action > now() - stale_after():
            return "Online"
        return "Stale"

    @admin.display(description="Duration", ordering="duration")
    def duration_display(self, obj: Connection):
        return fmt_duration(getattr(obj, "duration", None))

    @admin.action(description="Mark selected stale connections as closed")
    def close_stale_connections(self, request, queryset):
        """Write a close code onto rows whose socket vanished without one.

        This only touches the database -- it does not close a live socket, and
        it cannot make anyone look offline who did not already: a stale row is
        outside the window that ``ConnectionQuerySet.online()`` uses, so it was
        already excluded from every "currently online" count. If the socket
        does turn out to be alive, its next inbound message resets code to NULL
        via ConnectionMixin.update_connection.
        """
        selected = queryset.count()
        stale_pks = list(queryset.stale(stale_after()).values_list("pk", flat=True))
        updated = Connection.objects.filter(pk__in=stale_pks).update(
            code=ABNORMAL_CLOSURE
        )
        if updated:
            self.message_user(
                request,
                f"Closed {updated} stale connection(s) with code {ABNORMAL_CLOSURE}.",
                messages.SUCCESS,
            )
        if skipped := selected - updated:
            self.message_user(
                request,
                f"{skipped} selection(s) skipped — already closed, or still active.",
                messages.WARNING,
            )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [
            path(
                "online/",
                self.admin_site.admin_view(self.online_view),
                name="voteit_messaging_connection_online",
            ),
        ] + super().get_urls()

    def online_view(self, request):
        minutes = DEFAULT_WINDOW
        raw = request.GET.get("window", "")
        if raw.isdigit() and int(raw) in WINDOW_CHOICES:
            minutes = int(raw)
        window = timedelta(minutes=minutes)
        reference = now()
        online = Connection.objects.online(window)
        changelist_url = reverse("admin:voteit_messaging_connection_changelist")

        socket_count = online.count()
        user_count = online.values("user_id").distinct().count()

        context = {
            **self.admin_site.each_context(request),
            "title": "Online now",
            "minutes": minutes,
            "window_choices": WINDOW_CHOICES,
            "socket_count": socket_count,
            "user_count": user_count,
            "sockets_per_user": (
                round(socket_count / user_count, 2) if user_count else 0
            ),
            "organisations": self._online_per_organisation(online, changelist_url),
            "longest": self._longest_sessions(online),
            "buckets": self._connected_for_buckets(online, reference),
            "stale_count": Connection.objects.stale(window).count(),
            "stale_url": f"{changelist_url}?state={ConnectionStateFilter.STALE}",
            "changelist_url": changelist_url,
        }
        return TemplateResponse(
            request, "admin/voteit_messaging/connection/online.html", context
        )

    @staticmethod
    def _online_per_organisation(online, changelist_url: str) -> list[dict]:
        """Group open sockets by org -- via User, since Connection has no FK."""
        counts = (
            User.objects.filter(pk__in=online.user_ids(), organisation__isnull=False)
            .values("organisation")
            .annotate(users=models.Count("pk", distinct=True))
            .order_by("-users")
        )
        counts = list(counts)
        orgs_by_id = Organisation.objects.in_bulk(
            [row["organisation"] for row in counts]
        )
        rows = []
        for row in counts:
            if org := orgs_by_id.get(row["organisation"]):
                rows.append(
                    {
                        "organisation": org,
                        "users": row["users"],
                        "url": f"{changelist_url}?org={org.pk}",
                    }
                )
        return rows

    @staticmethod
    def _longest_sessions(online, limit: int = 10) -> list[dict]:
        connections = attach_users(
            list(online.with_duration().order_by("-duration")[:limit])
        )
        return [
            {
                "user": user_admin_link(getattr(conn, "user", None), conn.user_id),
                "organisation": (
                    conn.user.organisation if getattr(conn, "user", None) else "—"
                ),
                "connected_at": conn.connected_at,
                "duration": fmt_duration(conn.duration),
            }
            for conn in connections
        ]

    @staticmethod
    def _connected_for_buckets(online, reference) -> list[dict]:
        counts = dict(
            online.annotate(bucket=bucket_case(reference))
            # order_by() clears Meta.ordering, which would otherwise join
            # last_action into the GROUP BY and give one row per connection.
            .order_by()
            .values_list("bucket")
            .annotate(count=models.Count("pk"))
        )
        return [
            {"label": label, "count": counts.get(label, 0)}
            for label, _ in CONNECTED_FOR_BUCKETS
        ]
