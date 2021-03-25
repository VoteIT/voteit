from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from voteit.core.models import OAuth2Provider
from voteit.core.models import User

admin.site.register(User, UserAdmin)


@admin.register(OAuth2Provider)
class OAuth2ProviderAdmin(admin.ModelAdmin):
    pass
