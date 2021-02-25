from rest_framework import viewsets
from voteit.core.rest_api.mixins import (
    DefaultQS,
    CreateModelPermissionsMixin,
    TransitionsMixin,
    AutoPermissionViewSetMixin,
)


class DefaultModelViewSet(
    DefaultQS, CreateModelPermissionsMixin, TransitionsMixin, viewsets.ModelViewSet
):
    """ Checks permissions properly where applicable and enables all actions"""


class ReadonlyModelViewSet(
    DefaultQS, AutoPermissionViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """ Read-only version"""
