from __future__ import annotations

from typing import List
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import IntegrityError
from django.db import models
from django.utils.translation import gettext_lazy as _
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.utils import get_model_by_shortname
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.core.models import BaseContent
    from voteit.agenda.models import AgendaItem


def _default_allowed_models():
    return ["proposal", "discussion_post"]


class ReactionButton(MeetingContext):
    name = "reaction_button"
    # role_set: models.QuerySet
    ICON_CHOICES = (  # TODO, maybe use material icons? https://material.io/resources/icons/?style=baseline
        ("mdi-thumb-up", _("Thumb up")),
        ("mdi-thumb-down", _("Thumb down")),
        ("mdi-check", _("Checkmark")),
        ("mdi-cancel", _("Block")),
        ("mdi-star", _("Star")),
        ("mdi-wheelchair-accessibility", _("Accessible")),
        ("mdi-heart", _("Heart")),
        ("mdi-forum", _("Forum")),
        ("mdi-alert", _("Alert")),
        ("mdi-attachment", _("Attachment")),
        ("mdi-pencil", _("Pencil")),
        ("mdi-currency-eur", _("Currency")),
    )
    COLOR_CHOICES = (  # TODO, don't know how to define these. Using BS4 standard names 4 now. Should follow theme.
        ("accent", _("Accent")),
        ("primary", _("Primary")),
        ("secondary", _("Secondary")),
        ("error", _("Error")),
        ("info", _("Info")),
        ("success", _("Success")),
        ("warning", _("Warning")),
    )

    title: str = models.CharField(_("Display name"), max_length=80)
    icon: str = models.CharField(_("Icon name"), max_length=80, choices=ICON_CHOICES)
    color: str = models.CharField(_("Color"), max_length=80, choices=COLOR_CHOICES)
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="reaction_buttons"
    )
    order: int = models.PositiveSmallIntegerField(default=0)
    change_roles: List[str] = ArrayField(models.CharField(max_length=20), default=tuple)
    list_roles: List[str] = ArrayField(models.CharField(max_length=20), default=tuple)
    active: bool = models.BooleanField(_("Is this activated?"), default=True)
    allowed_models: List[str] = ArrayField(
        models.CharField(max_length=20),
        default=_default_allowed_models,
        blank=True,
    )

    exporters = {"meeting": {}}
    importers = {"meeting": {}, "organisation": {}}

    class Meta:
        verbose_name = _("Reaction button")
        verbose_name_plural = _("Reaction buttons")
        ordering = ["order"]

    def save(self, **kw):
        if self.order == 0:
            self.order = self.meeting.reaction_buttons.count()
        for role in set(self.change_roles) | set(self.list_roles):
            if role not in MeetingRoles.valid_roles:
                raise ValueError(f"{role} is not a valid meeting role")
        if self.meeting.is_archived:
            raise IntegrityError("This is part of an archived meeting")
        for k in self.allowed_models:
            model = get_model_by_shortname(k)
            if model is None:
                raise IntegrityError(
                    f"'allowed_models' contains the value {k} which isn't a valid model."
                )
        super().save(**kw)

    class Manager(models.Manager):
        def counts_for_object(self, obj):
            obj_ct = ContentType.objects.get_for_model(obj)
            return self.get_queryset().annotate(
                count=models.Count(
                    "reactions",
                    filter=models.Q(
                        reactions__content_type=obj_ct,
                        reactions__object_id=obj.pk,
                    ),
                )
            )

    objects = Manager()
    reactions: models.QuerySet

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"ReactionButton: {self.title}"


class Reaction(AgendaItemContext):
    """Works as a boolean true for a specific context, user and button.
    Essentially users never have reactions if the haven't marked something.
    """

    content_type: ContentType = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id: int = models.PositiveIntegerField()
    object: BaseContent = GenericForeignKey()
    button: ReactionButton = models.ForeignKey(
        ReactionButton, on_delete=models.CASCADE, related_name="reactions"
    )
    # Normally we don't want to delete user, but we should probably allow this later
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    agenda_item: AgendaItem = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        related_name="reactions",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Reaction")
        verbose_name_plural = _("Reactions")
        unique_together = [["content_type", "object_id", "button", "user"]]

    # class Manager(models.Manager):
    #     def reactions_for_ai(self, ai: AgendaItem):
    #         from voteit.discussion.models import DiscussionPost
    #         from voteit.proposal.models import Proposal
    #
    #         ctypes = ContentType.objects.get_for_models(Proposal, DiscussionPost)
    #         ai.proposals.all() | ai.discussions.all()
    #
    #         return self.get_queryset().filter(
    #             content_type__in=ctypes,
    #             object_id__in=ai.proposals.all() | ai.discussions.all(),
    #         )

    # objects = Manager()

    def __str__(self):
        return f"{self.button.title} from {self.user}"

    def __repr__(self):
        return f"{self.button.title} from {self.user}"
