from abc import ABC, abstractmethod

from django.test import TestCase


class WorkflowTests(TestCase):

    def setUp(self):
        from voteit.core.component import FactoryRegistry
        self.registry = FactoryRegistry(self._cut)

    @property
    def _cut(self):
        from voteit.core.workflow import Workflow

        return Workflow
