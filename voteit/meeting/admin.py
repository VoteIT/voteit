from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.db import models
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import NoReverseMatch
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from fsm_admin.mixins import FSMTransitionMixin

from voteit.meeting.dialects import dialect_registry
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.workflows import MeetingWf
from voteit.proposal.models import Proposal

if TYPE_CHECKING:
    from voteit.core.abcs import MeetingContext


class CloneMeetingForm(forms.ModelForm):
    include_discussions = forms.BooleanField(required=False, initial=True)
    include_proposals = forms.BooleanField(required=False, initial=True)
    include_buttons = forms.BooleanField(required=False, initial=True)
    include_reactions = forms.BooleanField(required=False)
    clear_group_authors = forms.BooleanField(required=False)
    clear_authors = forms.BooleanField(required=False)
    clear_ai_states = forms.BooleanField(required=False, initial=True)
    clear_proposal_states = forms.BooleanField(required=False, initial=True)
    clear_proposal_id = forms.BooleanField(required=False, initial=True)
    use_existing_groups = forms.BooleanField(required=False, initial=True)
    add_participants = forms.BooleanField(required=False)
    commit = forms.BooleanField(required=False)

    class Meta:
        model = Meeting
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target_meeting"] = forms.ModelChoiceField(
            label="Välj kommande möte att populera",
            queryset=self.instance.organisation.meetings.filter(
                state__in=[MeetingWf.UPCOMING]
            ).exclude(pk=self.instance.pk),
        )
        self.stats = None

    def save(self, commit=None):
        # We won't use this commit
        from voteit.export_import.utils import direct_clone

        if self.errors:
            raise ValueError(
                "The %s could not be %s because the data didn't validate."
                % (
                    self.instance._meta.object_name,
                    "created" if self.instance._state.adding else "changed",
                )
            )
        target = self.cleaned_data.pop("target_meeting")
        commit = self.cleaned_data.pop("commit")
        importer = direct_clone(
            target=target, source=self.instance, commit=commit, **self.cleaned_data
        )
        self.stats = importer.stats().dict(skip_defaults=True)
        self.commit = commit
        if commit:
            return target
        else:
            return self.instance


class MeetingDialectForm(forms.ModelForm):
    dialect = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = Meeting
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.installed_dialect:
            label = "Dialekt redan installerad"
            choices = [
                ("", "Uninstall dialect"),
                (
                    self.instance.installed_dialect,
                    f"Keep {self.instance.installed_dialect}",
                ),
            ]
        else:
            label = "Installera dialekt?"
            org_installable = dialect_registry.get_org_installable(
                organisation=self.instance.organisation
            )
            choices = [
                ("", "- Select dialect to install -"),
            ]
            choices.extend([(k, v["title"]) for k, v in org_installable.items()])
        self.fields["dialect"].choices = choices
        self.fields["dialect"].label = label
        self.fields["dialect"].initial = self.instance.installed_dialect

    def save(self, commit=True):
        if self.has_changed():
            dialect = self.cleaned_data.get("dialect")
            with transaction.atomic(durable=True):
                if self.instance.installed_dialect and not dialect:
                    handler = dialect_registry.get_merged_handler(
                        self.instance.installed_dialect
                    )
                    handler.remove(self.instance)
                elif dialect and not self.instance.installed_dialect:
                    handler = dialect_registry.get_merged_handler(dialect)
                    handler.install(self.instance)
        return super().save(commit=commit)


class DialectFilter(admin.SimpleListFilter):
    title = "Dialect"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "dialect"
    # Constants
    VANILLA = "0"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        items = [(self.VANILLA, "None (vanilla)")]
        dialect_registry.load()
        items.extend((k, v.data.title or k) for k, v in dialect_registry.items())
        return items

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # decide how to filter the queryset.
        v = self.value()
        if v == self.VANILLA:
            return queryset.filter(installed_dialect__isnull=True)
        elif v:
            return queryset.filter(installed_dialect=v)
        return queryset


@admin.register(Meeting)
class MeetingAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    autocomplete_fields = ("organisation",)
    list_display = (
        "title",
        "ai_count",
        "proposal_count",
        "state",
        "start_time",
        "end_time",
        "meeting_org",
    )
    list_filter = (
        "organisation",
        "state",
        "er_policy_name",
        DialectFilter,
    )
    search_fields = ("title",)
    exclude = ("mentions",)
    change_form_template = "admin/meeting/meeting_change_form.html"

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        context["extra_btns"] = []
        if obj:
            for urlname, title in [
                ("admin:meeting_meeting_clone_form", "Clone"),
                ("admin:meeting_meeting_dialect_form", "Hantera dialekter"),
            ]:
                context["extra_btns"].append(
                    format_html(
                        '<a class="button" href="{}">{}</a>',
                        reverse(urlname, args=[obj.pk]),
                        title,
                    )
                )

        return super().render_change_form(request, context, *args, **kwargs)

    @admin.display(description="Agenda items")
    def ai_count(self, obj: Meeting):
        return obj.agenda_items.count()

    @admin.display(description="Proposals")
    def proposal_count(self, obj: Meeting):
        return Proposal.objects.filter(agenda_item__meeting=obj).count()

    @admin.display(description="Organisation")
    def meeting_org(self, obj: Meeting):
        return obj.organisation

    def get_queryset(self, request):
        return super().get_queryset(request)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:object_id>/clone-meeting-form/",
                self.admin_site.admin_view(self.clone_meeting_form),
                name="meeting_meeting_clone_form",
            ),
            path(
                "<int:object_id>/meeting-dialect-form/",
                self.admin_site.admin_view(self.meeting_dialect_form),
                name="meeting_meeting_dialect_form",
            ),
        ]
        return custom_urls + urls

    def clone_meeting_form(self, request, object_id):
        obj = get_object_or_404(Meeting, pk=object_id)

        if request.method == "POST":
            form = CloneMeetingForm(data=request.POST, instance=obj)
            if form.is_valid():
                instance = form.save()
                out = "\n".join([f"{k}:\t{v}" for k, v in form.stats.items() if v])
                if form.cleaned_data.get("commit"):
                    self.message_user(
                        request, f"{instance.title} uppdaterades med:\n" + out
                    )
                else:
                    self.message_user(
                        request,
                        f"Testkörning, hade lagt till:\n" + out,
                        level=messages.INFO,
                    )
                # Nya
                return redirect("admin:meeting_meeting_change", instance.pk)
        else:
            form = CloneMeetingForm(instance=obj)
        context = dict(
            self.admin_site.each_context(request),
            title="Klona möte",
            form=form,
            instance=obj,
            orig_form_url=reverse(
                "admin:meeting_meeting_change", kwargs={"object_id": object_id}
            ),
        )
        return render(request, "admin/meeting/special_meeting_form.html", context)

    def meeting_dialect_form(self, request, object_id):
        obj = get_object_or_404(Meeting, pk=object_id)

        if request.method == "POST":
            form = MeetingDialectForm(data=request.POST, instance=obj)
            if form.is_valid():
                form.save()
                if form.has_changed():
                    if dialect := form.cleaned_data.get("dialect"):
                        self.message_user(
                            request,
                            f"Installerade dialekten {dialect}",
                            level=messages.INFO,
                        )
                    else:
                        self.message_user(
                            request,
                            f"Avinstallerade dialekten",
                            level=messages.INFO,
                        )
                return redirect("admin:meeting_meeting_change", object_id)
        else:
            form = MeetingDialectForm(instance=obj)
        context = dict(
            self.admin_site.each_context(request),
            title="Hantera mötesdialekt",
            form=form,
            instance=obj,
            orig_form_url=reverse(
                "admin:meeting_meeting_change", kwargs={"object_id": object_id}
            ),
        )
        return render(request, "admin/meeting/special_meeting_form.html", context)


class MeetingFilter(admin.SimpleListFilter):
    title = "Meeting"
    parameter_name = "meeting"
    search_param = "meeting"

    def lookups(self, request, model_admin):
        """
        URL query str + Human-readable
        """
        val = request.GET.get("meeting", None)
        if val:
            return ((val, "Specific meeting"),)

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        v = self.value()
        if v:
            with suppress(TypeError, ValueError):
                pk = int(v)
                return queryset.filter(**{self.search_param: pk})
            messages.add_message(request, messages.ERROR, "Not a valid meeting filter")
        return queryset


class MeetingViaAIFilter(MeetingFilter):
    search_param = "agenda_item__meeting"


class MeetingViaMeetingGroupFilter(MeetingFilter):
    search_param = "meeting_group__meeting"


class MeetingAsContextFilter(MeetingFilter):
    search_param = "context"


class MeetingAdminMixin:
    @admin.display(description="Meeting")
    def meeting_link(self, obj: MeetingContext):
        viewname = "admin:meeting_meeting_change"
        meeting_pk = getattr(obj, "meeting_id", obj.meeting.pk)
        if meeting_pk:
            try:
                link = reverse(viewname, args=[meeting_pk])
            except NoReverseMatch:
                return "%s" % meeting_pk
            return format_html(
                '<a href="{}">{}</a>',
                link,
                getattr(obj, "m_title", meeting_pk),
            )
        return "-"

    def annotate_meeting(
        self, qs: models.QuerySet, title_attr="meeting__title", pk_attr=None
    ):
        """
        Add meeting pk with same attr as other fields will have meeting relation to qs in case of no direct relation.

        """
        qs = qs.annotate(m_title=models.F(title_attr))
        if pk_attr:
            qs = qs.annotate(meeting_id=models.F(title_attr))
        return qs


@admin.register(MeetingRoles)
class MeetingRolesAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "get_assigned", "meeting_link"
    list_filter = (
        MeetingAsContextFilter,
        "user__organisation",
    )
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )

    def get_assigned(self, instance):
        return instance.assigned


@admin.register(MeetingGroup)
class MeetingGroupAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = (
        "meeting",
        "members",
        "delegate_to",
    )
    list_display = (
        "title",
        "meeting_link",
        "votes",
        "member_count",
    )
    list_filter = (
        MeetingFilter,
        "meeting__organisation",
    )
    search_fields = ("title", "meeting__title")
    exclude = ("mentions",)

    @admin.display(description="Members")
    def member_count(self, group: MeetingGroup):
        return group.members.count()


@admin.register(GroupRole)
class GroupRoleAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = ("meeting",)
    list_display = (
        "title",
        "meeting_link",
        "get_roles",
    )
    list_filter = (
        MeetingFilter,
        "meeting__organisation",
    )
    search_fields = ("title", "meeting__title")
    exclude = ("mentions",)

    def get_roles(self, instance: GroupRole):
        return instance.roles


@admin.register(GroupMembership)
class GroupMembershipAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = (
        "user",
        "meeting_group",
        "role",
    )
    list_display = (
        "__str__",
        "meeting_link",
    )
    list_filter = (
        MeetingViaMeetingGroupFilter,
        "meeting_group__meeting__organisation",
    )
    search_fields = ("title",)
    exclude = ("mentions",)
    readonly_fields = (
        "role",
        "meeting_group",
        "user",
    )
