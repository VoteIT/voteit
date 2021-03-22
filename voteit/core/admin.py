from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from voteit.core.models import User

admin.site.register(User, UserAdmin)
