import django_filters
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import DjangoFilterBackend


class ActionAnnotatedDjangoFilterBackend(DjangoFilterBackend):
    def get_filterset(self, request, queryset, view):
        if fset := super().get_filterset(request, queryset, view):
            fset.view_action = view.action
            fset.view_detail = view.detail
            return fset


class RequiredModelChoiceFilter(django_filters.ModelChoiceFilter):
    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs.none()
        return super().filter(qs, value)
