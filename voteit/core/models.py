from abc import abstractmethod

from django.contrib.auth.models import User
from django.db import models
from django.utils.functional import cached_property
from voteit.core.workflow import workflows, Workflow, Transition
from django.utils.translation import gettext as _


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

    def __str__(self):
        return self.title


class WorkflowMixin(models.Model):
    wf_state = models.CharField(max_length=20, null=True)

    @property
    @abstractmethod
    def wf_name(self) -> str:
        pass

    class Meta:
        abstract = True

    @cached_property
    def workflow(self) -> Workflow:
        factory = workflows[self.wf_name]
        return factory(self)

    @property
    def wf_state_title(self) -> str:
        return self.workflow.states.get(self.wf_state, _("Unknown state: %(state)s") % {'state': self.wf_state})

    @property
    def do_transition(self) -> Transition:
        # Delegate
        return self.workflow.do_transition
