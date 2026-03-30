import warnings
from abc import ABC

from rest_framework import viewsets

from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.mixins import CreateModelPermissionsMixin
from voteit.core.rest_api.mixins import DefaultQS
from voteit.core.rest_api.mixins import ModelContextMixin
from voteit.core.rest_api.mixins import TransitionsMixin


@warnings.deprecated(
    "Replace this model with generics from DRF + VerboseAutoPermissionViewSetMixin"
)
class DefaultModelViewSet(
    DefaultQS,
    CreateModelPermissionsMixin,
    TransitionsMixin,
    viewsets.ModelViewSet,
    ABC,
):
    """
    Checks permissions properly where applicable and enables all actions
    """


@warnings.deprecated(
    "Replace this model with generics from DRF + VerboseAutoPermissionViewSetMixin"
)
class ReadonlyModelViewSet(
    DefaultQS,
    AutoPermissionViewSetMixin,
    ModelContextMixin,
    viewsets.ReadOnlyModelViewSet,
    ABC,
):
    """
    Read-only version
    """

    @property
    def context_queryset(self):
        # This is since ModelContextMixin wasn't part of ReadonlyModelViewSet
        raise NotImplementedError("Implement in subclass if used")
