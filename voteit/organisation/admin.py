from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.timezone import now
from envelope.models import Connection

from voteit.meeting.models import Meeting
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
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
        recent_threshold = now() - timedelta(minutes=10)
        counts = list(
            Connection.objects.filter(
                online=True,
                last_action__gt=recent_threshold,
                user__organisation__isnull=False,
            )
            .values("user__organisation")
            .annotate(cnt=models.Count("user_id", distinct=True))
            .order_by("-cnt")
        )
        org_ids = [row["user__organisation"] for row in counts]
        count_map = {row["user__organisation"]: row["cnt"] for row in counts}
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


@admin.register(TermsOfService)
class TermsOfServiceAdmin(admin.ModelAdmin):
    pass


@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    pass


@admin.register(OAuth2Provider)
class OAuth2ProviderAdmin(admin.ModelAdmin):
    list_display = ["__str__", "organisation_active", "scope"]
    list_filter = ["scope", "organisation__active"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("organisation")

    @admin.display(description="Org active?", boolean=True)
    def organisation_active(self, instance):
        if org := instance.organisation:
            return org.active
