from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib import admin
from django.db import models
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.html import format_html

from voteit.agenda.models import AgendaItem
from voteit.meeting.admin import MeetingAdminMixin
from voteit.meeting.admin import MeetingFilter

if TYPE_CHECKING:
    from voteit.core.abcs import AgendaItemContext


@admin.register(AgendaItem)
class AgendaAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "meeting_link",
        "proposal_count",
        "state",
    )
    list_filter = (
        "state",
        "meeting__organisation",
        MeetingFilter,
    )
    autocomplete_fields = (
        "meeting",
        "mentions",
    )
    search_fields = (
        "title",
        "body",
        "meeting__title",
    )
    readonly_fields = ("order",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_proposal_count=models.Count("proposals", distinct=True))
        )

    @admin.display(description="Proposals")
    def proposal_count(self, obj: AgendaItem):
        return obj._proposal_count


class AgendaItemAdminMixin:
    @admin.display(description="Agenda item")
    def agenda_item_link(self, obj: AgendaItemContext):
        viewname = "admin:agenda_agendaitem_change"
        ai_pk = getattr(obj, "agenda_item_id", obj.agenda_item.pk)
        if ai_pk:
            try:
                link = reverse(viewname, args=[ai_pk])
            except NoReverseMatch:
                return "%s" % ai_pk
            return format_html(
                '<a href="{}">{}</a>',
                link,
                getattr(obj, "ai_title", ai_pk),
            )
        return "-"

    def annotate_ai(
        self, qs: models.QuerySet, title_attr="agenda_item__title", pk_attr=None
    ):
        """
        Add ai pk with same attr as other fields will have ai relation to qs in case of no direct relation.

        """
        qs = qs.annotate(ai_title=models.F(title_attr))
        if pk_attr:
            qs = qs.annotate(agenda_item_id=models.F(pk_attr))
        return qs
