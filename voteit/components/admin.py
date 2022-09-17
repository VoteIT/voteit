# from django.contrib import admin
# from django.db import transaction
# from django.http import HttpResponse
# from django.http import HttpResponseRedirect
# from django.template import loader
# from django.urls import reverse
# from dolly.core import LiveCloner
# from fsm_admin.mixins import FSMTransitionMixin
#
# from voteit.agenda.models import AgendaItem
# from voteit.meeting.models import Meeting
# from voteit.meeting.models import MeetingGroup
# from voteit.meeting.models import MeetingRoles
# from voteit.meeting.utils import clone_meeting
# from voteit.meeting.utils import collect_meeting
# from voteit.meeting.utils import get_default_models_ignored_on_clone
# from voteit.proposal.models import Proposal
#
#
#
#
# @admin.register(MeetingGroup)
# class MeetingGroupAdmin(admin.ModelAdmin):
#     autocomplete_fields = ("meeting", "members")
#     list_display = ("title", "meeting", "member_count")
#     list_filter = ("meeting", "members")
#     search_fields = ("title",)
#     exclude = ("mentions",)
#
#     def member_count(self, group: MeetingGroup):
#         return group.members.count()
