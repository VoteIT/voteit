from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.admin import AgendaItemAdminMixin
from voteit.meeting.admin import MeetingAdminMixin
from voteit.meeting.admin import MeetingViaAIFilter
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.models import TextParagraph


@admin.register(Proposal)
class ProposalAdmin(
    AgendaItemAdminMixin, MeetingAdminMixin, FSMTransitionMixin, admin.ModelAdmin
):
    fsm_field = ["state"]
    list_display = (
        "prop_id",
        "__str__",
        "state",
        "meeting_link",
        "agenda_item_link",
        "author",
        "meeting_group",
    )
    list_filter = (
        "state",
        MeetingViaAIFilter,
        "author__organisation",
    )
    search_fields = (
        "body",
        "prop_id",
        "agenda_item__title",
        "agenda_item__meeting__title",
        "author__first_name",
        "author__last_name",
        "author__userid",
        "meeting_group__groupid",
        "meeting_group__title",
    )
    autocomplete_fields = (
        "agenda_item",
        "author",
        "meeting_group",
        "mentions",
    )
    exclude = ("state",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = self.annotate_meeting(
            qs,
            title_attr="agenda_item__meeting__title",
            pk_attr="agenda_item__meeting_id",
        )
        qs = self.annotate_ai(qs)
        return qs.prefetch_related("author")


@admin.register(DiffProposal)
class DiffProposalAdmin(ProposalAdmin):
    fsm_field = ["state"]
    list_display = (
        "prop_id",
        "__str__",
        "state",
        "meeting_link",
        "agenda_item_link",
        "author",
        "meeting_group",
    )
    list_filter = (
        "state",
        MeetingViaAIFilter,
        "author__organisation",
    )
    search_fields = (
        "body",
        "prop_id",
        "agenda_item__title",
        "agenda_item__meeting__title",
        "author__first_name",
        "author__last_name",
        "author__userid",
        "meeting_group__groupid",
        "meeting_group__title",
    )
    autocomplete_fields = (
        "agenda_item",
        "author",
        "meeting_group",
        "mentions",
        "paragraph",
    )
    exclude = ("state",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = self.annotate_meeting(
            qs,
            title_attr="agenda_item__meeting__title",
            pk_attr="agenda_item__meeting_id",
        )
        qs = self.annotate_ai(qs)
        return qs.prefetch_related("author")


@admin.register(TextParagraph)
class TextParagraphAdmin(admin.ModelAdmin):
    search_fields = (
        "body",
        "agenda_item__title",
    )
    list_display = ("__str__", "agenda_item", "text_document")
    readonly_fields = ("agenda_item", "text_document")


@admin.register(TextDocument)
class TextDocumentAdmin(MeetingAdminMixin, AgendaItemAdminMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "meeting_link",
        "agenda_item_link",
        "base_tag",
    )
    list_filter = (
        MeetingViaAIFilter,
        "agenda_item__meeting__organisation",
    )
    search_fields = (
        "body",
        "base_tag",
        "agenda_item__title",
        "agenda_item__meeting__title",
    )
    autocomplete_fields = ("agenda_item",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = self.annotate_meeting(
            qs,
            title_attr="agenda_item__meeting__title",
            pk_attr="agenda_item__meeting_id",
        )
        return self.annotate_ai(qs)
