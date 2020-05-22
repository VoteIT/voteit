from django.contrib import admin

from voteit.organisation.models import Organisation


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    pass
