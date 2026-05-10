from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from envelope.models import Connection

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
    search_fields = ("title",)
    list_display = (
        "title",
        "meeting_count",
        "online_users",
        "users",
        "manager_count",
        "meeting_creator_count",
    )
    autocomplete_fields = ("mentions",)
    list_filter = (InactiveOrgFilter,)
    actions = [
        "mark_as_active",
        "mark_as_inactive",
    ]

    @cached_property
    def online_mapping(self):
        recent_connections_user_qs = Connection.objects.filter(
            online=True, last_action__gt=now() - timedelta(minutes=10)
        ).values_list("user_id", flat=True)
        user_qs = User.objects.filter(id__in=recent_connections_user_qs).distinct()
        return {
            x["organisation"]: x["id__count"]
            for x in user_qs.values("organisation")
            .order_by()
            .annotate(models.Count("id"))
        }

    @admin.display(description="Managers")
    def manager_count(self, obj: Organisation):
        return obj.managers__count

    @admin.display(description="Online", ordering="online_users")
    def online_users(self, obj: Organisation):
        return self.online_mapping.get(obj.pk, 0)

    @admin.display(description="Users", ordering="users")
    def users(self, obj: Organisation):
        return obj.users.count()

    @admin.display(description="Meeting Creators")
    def meeting_creator_count(self, obj: Organisation):
        return obj.meeting_creator__count

    @admin.display(description="Meetings")
    def meeting_count(self, obj: Organisation):
        return obj.meeting__count

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            meeting__count=models.Count("meetings", distinct=True),
            meeting_creator__count=models.Count(
                "roles",
                distinct=True,
                filter=models.Q(roles__assigned__contains=ROLE_MEETING_CREATOR),
            ),
            managers__count=models.Count(
                "roles",
                distinct=True,
                filter=models.Q(roles__assigned__contains=ROLE_ORG_MANAGER),
            ),
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

    @admin.display(description="Org active?", boolean=True)
    def organisation_active(self, instance):
        if org := instance.organisation:
            return org.active
