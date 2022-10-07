from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from envelope.models import Connection

from voteit.organisation.models import AccessToken
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
from voteit.organisation.roles import ROLE_ORG_MANAGER


User = get_user_model()


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    search_fields = ("title",)
    list_display = (
        "title",
        "meeting_count",
        "users_count",
        "manager_count",
    )
    autocomplete_fields = ("mentions",)

    @admin.display(description="Managers")
    def manager_count(self, obj: Organisation):
        return obj.roles.filter(assigned__contains=[ROLE_ORG_MANAGER]).count()

    @admin.display(description="Online users")
    def users_count(self, obj: Organisation):
        minutes = 10
        recent_connections_qs = Connection.objects.filter(
            online=True, last_action__gt=now() - timedelta(minutes=minutes)
        )
        online_users_qs = obj.users.filter(
            connections__in=recent_connections_qs
        ).distinct()
        return f"{online_users_qs.count()} / {obj.users.count()}"

    @admin.display(description="Meetings")
    def meeting_count(self, obj: Organisation):
        return obj.meetings.count()


@admin.register(OrganisationRoles)
class OrganisationRolesAdmin(admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "assigned", "context"
    list_filter = ("context",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    autocomplete_fields = ("user",)
    list_display = "user", "updated"
    list_filter = ("user__organisation",)


@admin.register(TermsOfService)
class TermsOfServiceAdmin(admin.ModelAdmin):
    pass


@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    pass


@admin.register(OAuth2Provider)
class OAuth2ProviderAdmin(admin.ModelAdmin):
    pass
