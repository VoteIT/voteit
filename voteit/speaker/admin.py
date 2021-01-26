from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from .models import *


@admin.register(SpeakerListSystem)
class SLSystemAdmin(admin.ModelAdmin):
    pass


@admin.register(SpeakerList)
class SLAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = 'state'
