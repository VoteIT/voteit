from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.motion.models import MotionProcess
from voteit.motion.models import Motion
from voteit.motion.models import MotionProposal


@admin.register(MotionProcess)
class MotionProcessAdmin(FSMTransitionMixin, admin.ModelAdmin):
    list_display = "title", "state"
    list_filter = "state", "organisation"
    search_fields = "title", "body"
    exclude = ("state",)


@admin.register(Motion)
class MotionAdmin(FSMTransitionMixin, admin.ModelAdmin):
    list_display = "title", "state", "author", "motion_process"
    list_filter = "state", # "motion_process", "author"
    search_fields = ("text",)
    exclude = ("state",)


@admin.register(MotionProposal)
class MotionProposalAdmin(admin.ModelAdmin):
    list_display = ("text", "motion")
   # list_filter = ("motion",)
    search_fields = ("text",)
