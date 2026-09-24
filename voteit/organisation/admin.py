from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from django.template.response import TemplateResponse
from django.urls import path
from social_core.backends.utils import load_backends
from voteit.messaging.models import Connection

from voteit.meeting.models import Meeting
from voteit.organisation.models import GlobalTermsOfService
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserAccept
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER

User = get_user_model()


class InactiveOrgFilter(admin.SimpleListFilter):
    title = "Inactive"
    parameter_name = "inactive"
    search_param = "active"

    def lookups(self, request, model_admin):
        """
        URL query str + Human-readable
        """
        return (
            ("inc", "Include inactive"),
            ("only", "Only inactive"),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        v = self.value()
        if v == "inc":
            return queryset
        elif v == "only":
            return queryset.filter(**{self.search_param: False})
        return queryset.filter(**{self.search_param: True})

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": "Hide",
        }
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == str(lookup),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    change_list_template = "admin/organisation/change_list.html"
    search_fields = ("title",)
    list_display = (
        "title",
        "host",
        "meeting_count",
        "users",
        "manager_count",
        "meeting_creator_count",
    )
    autocomplete_fields = ("mentions",)
    list_filter = (InactiveOrgFilter,)
    show_full_result_count = False
    actions = [
        "mark_as_active",
        "mark_as_inactive",
    ]

    @admin.display(description="Managers")
    def manager_count(self, obj: Organisation):
        return obj.managers__count

    @admin.display(description="Users", ordering="users__count")
    def users(self, obj: Organisation):
        return obj.users__count

    @admin.display(description="Meeting Creators", ordering="meeting_creator__count")
    def meeting_creator_count(self, obj: Organisation):
        return obj.meeting_creator__count

    @admin.display(description="Meetings", ordering="meeting__count")
    def meeting_count(self, obj: Organisation):
        return obj.meeting__count

    def get_urls(self):
        return [
            path(
                "online/",
                self.admin_site.admin_view(self.online_view),
                name="organisation_organisation_online",
            ),
        ] + super().get_urls()

    def online_view(self, request):
        # Connection no longer has an FK to user, so group through User rather
        # than following user__organisation off the connection itself.
        online_user_ids = Connection.objects.online(timedelta(minutes=10)).user_ids()
        counts = list(
            User.objects.filter(pk__in=online_user_ids, organisation__isnull=False)
            .values("organisation")
            .annotate(cnt=models.Count("pk", distinct=True))
            .order_by("-cnt")
        )
        org_ids = [row["organisation"] for row in counts]
        count_map = {row["organisation"]: row["cnt"] for row in counts}
        orgs_by_id = Organisation.objects.in_bulk(org_ids)
        organisations = []
        for org_id in org_ids:
            if org := orgs_by_id.get(org_id):
                org.online_users__count = count_map[org_id]
                organisations.append(org)
        context = {
            **self.admin_site.each_context(request),
            "title": "Online organisations",
            "organisations": organisations,
        }
        return TemplateResponse(request, "admin/organisation/online.html", context)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                meeting__count=Coalesce(
                    Subquery(
                        Meeting.objects.filter(organisation=OuterRef("pk"))
                        .values("organisation")
                        .annotate(cnt=models.Count("pk"))
                        .values("cnt")[:1]
                    ),
                    0,
                ),
                meeting_creator__count=Coalesce(
                    Subquery(
                        OrganisationRoles.objects.filter(
                            context=OuterRef("pk"),
                            assigned__contains=ROLE_MEETING_CREATOR,
                        )
                        .values("context")
                        .annotate(cnt=models.Count("pk"))
                        .values("cnt")[:1]
                    ),
                    0,
                ),
                managers__count=Coalesce(
                    Subquery(
                        OrganisationRoles.objects.filter(
                            context=OuterRef("pk"),
                            assigned__contains=ROLE_ORG_MANAGER,
                        )
                        .values("context")
                        .annotate(cnt=models.Count("pk"))
                        .values("cnt")[:1]
                    ),
                    0,
                ),
                users__count=Coalesce(
                    Subquery(
                        User.objects.filter(organisation=OuterRef("pk"))
                        .values("organisation")
                        .annotate(cnt=models.Count("pk"))
                        .values("cnt")[:1]
                    ),
                    0,
                ),
            )
        )

    @admin.display(description="Mark as active")
    def mark_as_active(self, request, queryset):
        queryset = queryset.filter(active=False)
        changed = queryset.update(active=True)
        self.message_user(
            request,
            f"Marked {changed} active",
            messages.SUCCESS,
        )

    @admin.action(description="Mark as inactive")
    def mark_as_inactive(self, request, queryset):
        queryset = queryset.filter(active=True)
        changed = queryset.update(active=False)
        self.message_user(
            request,
            f"Marked {changed} inactive",
            messages.SUCCESS,
        )


@admin.register(OrganisationRoles)
class OrganisationRolesAdmin(admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "get_assigned", "context"
    list_filter = ("context",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )

    def get_assigned(self, instance):
        return instance.assigned


@admin.register(GlobalTermsOfService)
class GlobalTermsOfServiceAdmin(admin.ModelAdmin):
    list_display = ("__str__", "version", "tos_count")
    fields = ("body", "version")
    actions = ["create_org_tos"]

    def get_queryset(self, request):
        return (
            super().get_queryset(request).annotate(tos__count=models.Count("org_tos"))
        )

    @admin.display(description="Organisation ToS", ordering="tos__count")
    def tos_count(self, obj: GlobalTermsOfService):
        return obj.tos__count

    @admin.action(description="Create organisation ToS from this version")
    def create_org_tos(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one version", messages.ERROR)
            return
        obj = queryset.get()
        # An older version would become the newest ToS of every organisation
        if GlobalTermsOfService.objects.filter(version__gt=obj.version).exists():
            self.message_user(
                request, "Only the latest version can be used", messages.ERROR
            )
            return
        created = obj.create_org_tos()
        self.message_user(
            request,
            f"Created ToS for {len(created)} organisation(s)",
            messages.SUCCESS,
        )


@admin.register(TermsOfService)
class TermsOfServiceAdmin(admin.ModelAdmin):
    list_display = ("__str__", "organisation", "version", "based_on", "accepts_count")
    list_select_related = ("organisation", "based_on")
    search_fields = ("organisation__title",)
    autocomplete_fields = ("organisation",)
    fields = ("organisation", "based_on", "body", "version")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(accepts__count=models.Count("accepts"))
        )

    @admin.display(description="Accepts", ordering="accepts__count")
    def accepts_count(self, obj: TermsOfService):
        return obj.accepts__count


@admin.register(UserAccept)
class UserAcceptAdmin(admin.ModelAdmin):
    list_display = ("user", "tos", "organisation", "accepted")
    list_select_related = ("user", "tos__organisation")
    search_fields = (
        "user__userid",
        "user__first_name",
        "user__last_name",
        "tos__organisation__title",
    )
    autocomplete_fields = ("user", "tos")


@admin.register(OAuth2Provider)
class OAuth2ProviderAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "provider_id",
        "primary",
        "hidden",
        "organisation_active",
        "scope",
    ]
    list_filter = [
        "provider_id",
        "primary",
        "hidden",
        "scope",
        "organisation__active",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("organisation")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "provider_id":
            # Only enabled backends: a typo here means no credentials at login.
            backends = load_backends(settings.AUTHENTICATION_BACKENDS)
            kwargs["widget"] = forms.Select(
                choices=sorted(
                    (name, f"{getattr(cls, 'TITLE', '') or name} ({name})")
                    for name, cls in backends.items()
                )
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Org active?", boolean=True)
    def organisation_active(self, instance):
        if org := instance.organisation:
            return org.active
