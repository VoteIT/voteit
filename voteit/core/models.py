from __future__ import annotations

from abc import ABCMeta
from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext as _


class _AbstractModelMeta(ABCMeta, type(models.Model)):
    pass


class ABCModel(models.Model, metaclass=_AbstractModelMeta):
    """ Abstract classes based on ABCMeta don't work in django -
        this is a workaround to make them behave correctly.
        Remove this as soon as it's fixed in django.
    """

    class Meta:
        abstract = True


class BaseContent(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    created = models.DateTimeField(editable=False, auto_now_add=True)
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="author_%(app_label)s_%(class)s",
    )
    modified = models.DateTimeField(editable=False, auto_now=True)
    last_modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="last_modified_%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.title[:50]}>"

    def __str__(self):
        return self.title[:50]
