from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    search_fields = ("title",)
    list_display = (
        "title",
        "meeting_count",
    )

    def meeting_count(self, obj: Organisation):
        return obj.meetings.count()

    meeting_count.short_description = _("Meetings")


@admin.register(TermsOfService)
class TermsOfServiceAdmin(admin.ModelAdmin):
    pass


@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    pass


@admin.register(OAuth2Provider)
class OAuth2ProviderAdmin(admin.ModelAdmin):
    pass
