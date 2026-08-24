from datetime import timedelta

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import NoReverseMatch
from django.utils.module_loading import import_string
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timezone import now

from auditlog.admin import LogEntryAdmin
from auditlog.models import LogEntry
from voteit.core.models import User
from voteit.messaging.admin import stale_after
from voteit.messaging.models import Connection
from voteit.core.user_merger import UserMerger
from voteit.discussion.models import DiscussionPost
from voteit.meeting.models import Meeting
from voteit.proposal.models import Proposal

_user_fieldsets = list(DefaultUserAdmin.fieldsets)
_user_fieldsets[0][1]["fields"] = list(_user_fieldsets[0][1]["fields"])
_user_fieldsets[0][1]["fields"].append("userid")
_user_fieldsets[0][1]["fields"].append("identity_id")
_user_fieldsets.insert(
    1,
    (
        "Organisation",
        {"fields": ("organisation",)},
    ),
)
_user_fieldsets.append(
    (
        "Profile image",
        {"fields": ("img_url", "image")},
    )
)


class OnlineFilter(admin.SimpleListFilter):
    title = "Online"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "online"
    # Constants
    ONLINE = "o"
    DISCONNECTED = "d"
    WITHIN_LAST_MONTH = "l"

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
            (self.DISCONNECTED, "Disconnected"),
            (self.WITHIN_LAST_MONTH, "Within last 30 days"),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Connection has no FK to user any more, so these go through a subquery
        # rather than a reverse relation -- which also drops the .distinct()
        # that the join previously made necessary.
        if self.value():
            # Same window as the Connection admin and the "Online now" page --
            # VOTEIT_CONNECTION_STALE_AFTER -- read at call time so it stays one
            # number rather than two that happen to agree.
            window = stale_after()
            if self.value() == self.ONLINE:
                return queryset.filter(
                    pk__in=Connection.objects.online(window).user_ids()
                )
            elif self.value() == self.DISCONNECTED:
                return queryset.exclude(
                    pk__in=Connection.objects.online(window).user_ids()
                )
            elif self.value() == self.WITHIN_LAST_MONTH:
                return queryset.filter(
                    pk__in=Connection.objects.active_since(
                        now() - timedelta(days=30)
                    ).user_ids()
                )


class LinkedFilter(admin.SimpleListFilter):
    title = "ID-links"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "linked"
    # Constants
    YES = "y"
    NO = "n"
    DUPLICATES = "d"
    MAYBE_CLEARABLE = "c"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            (self.YES, "Yes"),
            (self.NO, "No"),
            (self.DUPLICATES, "Duplicates"),
            (self.MAYBE_CLEARABLE, "Maybe clearable"),
        )

    def _dupes_qs(self) -> models.QuerySet:
        return (
            User.objects.values("identity_id")
            .annotate(ident_count=models.Count("identity_id"))
            .filter(ident_count__gt=1)
            .values_list("identity_id", flat=True)
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # decide how to filter the queryset.
        if self.value():
            if self.value() == self.YES:
                return queryset.filter(
                    identity_id__isnull=False,
                ).distinct()
            elif self.value() == self.NO:
                return queryset.filter(
                    identity_id__isnull=True,
                ).distinct()
            elif self.value() == self.DUPLICATES:
                return queryset.filter(identity_id__in=self._dupes_qs())
            elif self.value() == self.MAYBE_CLEARABLE:
                return queryset.filter(
                    identity_id__in=self._dupes_qs(), meeting_roles__isnull=True
                )


def _pick_source_target(user_a, user_b):
    """Return (source, target) — least active user becomes source."""
    from voteit.meeting.models import MeetingRoles
    from voteit.poll.models import Vote

    def score(user):
        return (
            MeetingRoles.objects.filter(user=user).count()
            + Vote.objects.filter(user=user).count()
            + Proposal.objects.filter(author=user).count()
            + DiscussionPost.objects.filter(author=user).count()
        )

    score_a, score_b = score(user_a), score(user_b)
    if score_a <= score_b:
        return user_a, user_b, score_a, score_b
    return user_b, user_a, score_b, score_a


class MergeUsersForm(forms.Form):
    source_pk = forms.IntegerField(widget=forms.HiddenInput)
    target_pk = forms.IntegerField(widget=forms.HiddenInput)
    score_src = forms.CharField(widget=forms.HiddenInput, required=False)
    score_tgt = forms.CharField(widget=forms.HiddenInput, required=False)
    confirm = forms.BooleanField(label="Yes, I confirm the merge", required=True)


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    fieldsets = _user_fieldsets
    list_display = (
        "__str__",
        "organisation",
        "email",
        "first_name",
        "last_name",
        "date_joined",
        "is_linked",
    )
    search_fields = (
        "first_name",
        "last_name",
        "email",
        "userid",
        "username",
    )
    list_filter = (
        "organisation",
        OnlineFilter,
        LinkedFilter,
        "is_active",
        "is_superuser",
        "is_staff",
        "date_joined",
        "last_login",
    )
    actions = ["merge_users_action"]

    @admin.display(description="ID-linked", boolean=True)
    def is_linked(self, user):
        return user.identity_id is not None

    @admin.action(description="Merge two users (select exactly two)")
    def merge_users_action(self, request, queryset):
        if queryset.count() != 2:
            self.message_user(
                request, "Select exactly 2 users to merge.", messages.ERROR
            )
            return
        users = list(queryset.order_by("pk"))
        if users[0].organisation_id != users[1].organisation_id:
            self.message_user(
                request,
                "Both users must belong to the same organisation.",
                messages.ERROR,
            )
            return
        source, target, score_src, score_tgt = _pick_source_target(*users)
        url = reverse("admin:core_user_merge_confirm")
        return HttpResponseRedirect(
            f"{url}?source={source.pk}&target={target.pk}"
            f"&score_src={score_src}&score_tgt={score_tgt}"
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "merge-confirm/",
                self.admin_site.admin_view(self.merge_confirm_view),
                name="core_user_merge_confirm",
            ),
        ]
        return custom_urls + urls

    def merge_confirm_view(self, request):
        source_pk = request.GET.get("source") or request.POST.get("source_pk")
        target_pk = request.GET.get("target") or request.POST.get("target_pk")
        score_src = request.GET.get("score_src") or request.POST.get("score_src")
        score_tgt = request.GET.get("score_tgt") or request.POST.get("score_tgt")
        try:
            source = User.objects.select_related("organisation").get(pk=int(source_pk))
            target = User.objects.select_related("organisation").get(pk=int(target_pk))
        except (User.DoesNotExist, TypeError, ValueError):
            self.message_user(request, "Invalid user selection.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:core_user_changelist"))

        merger = UserMerger(source=source, target=target, dry_run=True)
        try:
            preview_log = merger.run()
        except ValueError as e:
            self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(reverse("admin:core_user_changelist"))

        swap_url = (
            reverse("admin:core_user_merge_confirm")
            + f"?source={target.pk}&target={source.pk}"
            + (
                f"&score_src={score_tgt}&score_tgt={score_src}"
                if score_src is not None
                else ""
            )
        )

        if request.method == "POST":
            form = MergeUsersForm(request.POST)
            if form.is_valid():
                real_merger = UserMerger(source=source, target=target, dry_run=False)
                try:
                    log = real_merger.run()
                except ValueError as e:
                    self.message_user(request, str(e), messages.ERROR)
                    return HttpResponseRedirect(reverse("admin:core_user_changelist"))
                self.message_user(
                    request,
                    f"Merge complete: {len(log.moved)} moved, "
                    f"{len(log.merged_roles)} role merges, "
                    f"{len(log.skipped)} skipped.",
                    messages.SUCCESS,
                )
                return HttpResponseRedirect(
                    reverse("admin:core_user_change", args=[target.pk])
                )
        else:
            form = MergeUsersForm(
                initial={
                    "source_pk": source.pk,
                    "target_pk": target.pk,
                    "score_src": score_src,
                    "score_tgt": score_tgt,
                }
            )

        context = dict(
            self.admin_site.each_context(request),
            title="Confirm user merge",
            source=source,
            target=target,
            score_src=score_src,
            score_tgt=score_tgt,
            swap_url=swap_url,
            preview_log=preview_log,
            form=form,
        )
        return render(request, "admin/core/user_merge_confirm.html", context)


def _sm_event_action(modeladmin, request, queryset):
    """
    Two-step admin action for sending a state machine event to selected objects.

    Step 1: show event selector with from-state hints + list of selected objects.
    Step 2: show eligible/ineligible split and require confirmation.
    Execute: send event to eligible objects, report results.
    """
    sm_class = import_string(queryset.model.state_machine_name)

    selected_event_id = request.POST.get("sm_event")
    confirm = request.POST.get("confirm")

    if selected_event_id and confirm:
        succeeded, skipped, errors = [], [], []
        for obj in queryset:
            if any(e.id == selected_event_id for e in obj.sm.allowed_events):
                try:
                    obj.sm.send(selected_event_id, user=request.user)
                    obj.save()
                    succeeded.append(obj)
                except Exception as exc:
                    errors.append((obj, str(exc)))
            else:
                skipped.append(obj)
        if succeeded:
            modeladmin.message_user(
                request,
                f"Sent '{selected_event_id}' to {len(succeeded)} object(s).",
                messages.SUCCESS,
            )
        if skipped:
            modeladmin.message_user(
                request,
                f"{len(skipped)} object(s) skipped — event not valid from their current state.",
                messages.WARNING,
            )
        for obj, err in errors:
            modeladmin.message_user(request, f"{obj}: {err}", messages.ERROR)
        return

    # Build event metadata for the selection step: id, name, valid source states.
    event_info = []
    for event in sm_class.events:
        sources = sorted(
            {
                state.id
                for state in sm_class.states
                for t in state.transitions
                if event in t.events
            }
        )
        event_info.append({"id": event.id, "name": str(event.name), "sources": sources})

    if selected_event_id:
        # Step 2: split into eligible vs ineligible and ask for confirmation.
        eligible, ineligible = [], []
        for obj in queryset:
            (
                eligible
                if any(e.id == selected_event_id for e in obj.sm.allowed_events)
                else ineligible
            ).append(obj)
        context = dict(
            modeladmin.admin_site.each_context(request),
            title=f"Confirm: send '{selected_event_id}'",
            opts=queryset.model._meta,
            queryset=queryset,
            action_checkbox_name=ACTION_CHECKBOX_NAME,
            selected_event=selected_event_id,
            eligible=eligible,
            ineligible=ineligible,
        )
    else:
        # Step 1: event selection form.
        context = dict(
            modeladmin.admin_site.each_context(request),
            title="Send state machine event",
            opts=queryset.model._meta,
            queryset=queryset,
            action_checkbox_name=ACTION_CHECKBOX_NAME,
            event_info=event_info,
        )

    return render(request, "admin/sm_event_action.html", context)


_sm_event_action.short_description = "Send state machine event..."


class StateMachineAdminMixin:
    """Add to any ModelAdmin whose model uses StateMachineModelMixin for the SM event action."""

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions["send_sm_event"] = (
            _sm_event_action,
            "send_sm_event",
            _sm_event_action.short_description,
        )
        return actions


# Replace existing
admin.site.unregister(LogEntry)


@admin.register(LogEntry)
class VoteITLogEntryAdmin(LogEntryAdmin):
    list_display = LogEntryAdmin.list_display + ["meeting"]
    list_filter = ["actor__organisation"] + LogEntryAdmin.list_filter

    @admin.display(description="Meeting")
    def meeting(self, obj: LogEntry):
        if meeting_pk := obj.additional_data and obj.additional_data.get("m", None):
            try:
                meeting = Meeting.objects.get(pk=meeting_pk)
            except Meeting.DoesNotExist:
                return f"Deleted: {meeting_pk}"
            viewname = "admin:meeting_meeting_change"
            try:
                link = reverse(viewname, args=[meeting.pk])
            except NoReverseMatch:
                return "%s" % meeting
            return format_html(
                '<a href="{link}">{meeting}</a>', link=link, meeting=meeting
            )
        return "-"
