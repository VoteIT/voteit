from typing import Iterator

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, IntegrityError
from django.utils.translation import gettext_lazy as _

from voteit.core.fields import RoleField
from voteit.core.models import BaseContent
from voteit.core.role import Role
from voteit.meeting.models import Meeting


class ReactionButton(models.Model):
    role_set: models.QuerySet
    ICON_CHOICES = (  # TODO, maybe use material icons? https://material.io/resources/icons/?style=baseline
        ('thumb_up', _('Thumb up')),
        ('thumb_down', _('Thumb down')),
        ('check', _('Checkmark')),
        ('block', _('Block')),
        ('star', _('Star')),
        ('accessible', _('Accessible')),
    )
    COLOR_CHOICES = (  # TODO, don't know how to define these. Using BS4 standard names 4 now. Should follow theme.
        ('primary', _('Primary')),
        ('secondary', _('Secondary')),
        ('success', _('Success')),
        ('danger', _('Danger')),
        ('warning', _('Warning')),
        ('info', _('Info')),
    )

    title: str = models.CharField(_('Name'), max_length=80)
    icon: str = models.CharField(_('Icon name'), max_length=80, choices=ICON_CHOICES)
    color: str = models.CharField(_('Color'), max_length=80, choices=COLOR_CHOICES)
    meeting: Meeting = models.ForeignKey(Meeting, models.CASCADE)
    order: int = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _('Reaction button')
        verbose_name_plural = _('Reaction buttons')
        ordering = ['order']

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.order == 0:
            self.order = self.meeting.reactionbutton_set.count()
        super().save(force_insert, force_update, using, update_fields)

    def get_valid_roles(self, ct: ContentType, mode: str = 'view') -> Iterator[Role]:
        if mode not in ReactionRoles.MODES:
            raise ValueError(f'Invalid permission mode. Must be one of {ReactionRoles.MODES}')
        for reaction_role in self.role_set.filter(content_type=ct, **{mode: True}):
            yield reaction_role.role(self.meeting)

    class Manager(models.Manager):
        def counts_for_object(self, obj):
            obj_ct = ContentType.objects.get_for_model(obj)
            return self.get_queryset().annotate(
                count=models.Count('reaction', filter=models.Q(
                    reaction__content_type=obj_ct,
                    reaction__object_id=obj.pk,
                ))
            )

    objects = Manager()


class ReactionRoles(models.Model):
    """ Handles roles and their permissions for a specific button. """
    MODES = ('view', 'change', 'list')
    button = models.ForeignKey(ReactionButton, models.CASCADE, related_name='role_set')
    content_type = models.ForeignKey(ContentType, models.CASCADE)
    role = RoleField(Meeting, null=False, blank=False)
    view = models.BooleanField(default=True)
    change = models.BooleanField(default=True)
    list = models.BooleanField(default=False)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """ View is always on if there are other permissions. """
        if self.change or self.list:
            self.view = True
        super().save(force_insert, force_update, using, update_fields)


class Reaction(models.Model):
    """ """
    content_type: ContentType = models.ForeignKey(ContentType, models.CASCADE)
    object_id: int = models.PositiveIntegerField()
    object: BaseContent = GenericForeignKey()
    button: ReactionButton = models.ForeignKey(ReactionButton, models.CASCADE)
    user: User = models.ForeignKey(User, models.CASCADE)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        valid_roles = self.button.get_valid_roles(self.content_type, 'change')
        if not any(self.user in role for role in valid_roles):
            raise IntegrityError()
        super().save(force_insert, force_update, using, update_fields)

    class Meta:
        verbose_name = _('Reaction')
        verbose_name_plural = _('Reactions')
        unique_together = [['content_type', 'object_id', 'button', 'user']]
