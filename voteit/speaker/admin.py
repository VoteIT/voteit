from django.contrib import admin

from .models import *


@admin.register(SpeakerListSystem, SpeakerList)
class SLSystemAdmin(admin.ModelAdmin):
    pass
