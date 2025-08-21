from __future__ import annotations

from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import IntegrityError
from django.db import models

from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.fields import RolesField
from voteit.core.role import Role
from voteit.core.utils import get_model_by_shortname
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.core.models import BaseContent
    from voteit.agenda.models import AgendaItem


def _default_allowed_models():
    return ["proposal", "discussion_post"]


@auditlog.register(
    include_fields=[
        "title",
        "meeting",
        "target",
        "change_roles",
        "list_roles",
        "active",
        "allowed_models",
        "on_presentation",
        "on_vote",
        "vote_template",
        "flag_mode",
    ],
)
class ReactionButton(MeetingContext):
    name = "reaction_button"
    title: str = models.CharField(verbose_name="Display name", max_length=80)
    description: str = models.CharField(
        verbose_name="Description",
        max_length=100,
        blank=True,
        default="",
    )
    icon: str = models.CharField(
        verbose_name="Icon name",
        max_length=30,
        default="",
        blank=True,
    )
    color: str = models.CharField(verbose_name="Color", max_length=15)
    target: int | None = models.SmallIntegerField(
        verbose_name="Required target", null=True, blank=True
    )
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="reaction_buttons"
    )
    order: int = models.PositiveSmallIntegerField(default=0)
    change_roles: list[Role] = RolesField(
        role_choices=MeetingRoles.valid_roles.values(), max_length=60
    )
    list_roles: list[Role] = RolesField(
        role_choices=MeetingRoles.valid_roles.values(), max_length=60
    )
    active: bool = models.BooleanField(verbose_name="Is this activated?", default=True)
    allowed_models: list[str] = ArrayField(
        models.CharField(max_length=20),
        default=_default_allowed_models,
        blank=True,
    )
    on_presentation: bool = models.BooleanField(
        verbose_name="Show in presentation mode", default=False
    )
    on_vote: bool = models.BooleanField(verbose_name="Show during vote", default=False)
    vote_template: bool = models.BooleanField(
        verbose_name="As Vote template", default=False
    )
    flag_mode: bool = models.BooleanField(verbose_name="Flag mode?", default=False)

    class Meta:
        verbose_name = "Reaction button"
        verbose_name_plural = "Reaction buttons"
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
    meeting_id: int

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"ReactionButton: {self.title}"


class Reaction(AgendaItemContext, MeetingContext):
    """
    Works as a boolean true for a specific context, user and button.
    Essentially users never have reactions if they haven't marked something.
    """

    content_type: ContentType = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id: int = models.PositiveIntegerField()
    object: BaseContent = GenericForeignKey()
    button: ReactionButton = models.ForeignKey(
        ReactionButton, on_delete=models.CASCADE, related_name="reactions"
    )
    # Normally we don't want to delete user, but we should probably allow this later
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT
    )
    agenda_item: AgendaItem = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        related_name="reactions",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Reaction"
        verbose_name_plural = "Reactions"
        unique_together = [["content_type", "object_id", "button", "user"]]

    @property
    def meeting(self) -> Meeting | None:
        return self.button.meeting

    def __str__(self):
        return f"{self.button.title} from {self.user}"

    def __repr__(self):
        return f"{self.button.title} from {self.user}"
