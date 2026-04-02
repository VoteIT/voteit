from django_filters.rest_framework import DjangoFilterBackend


class ActionAnnotatedDjangoFilterBackend(DjangoFilterBackend):
    def get_filterset(self, request, queryset, view):
        if fset := super().get_filterset(request, queryset, view):
            fset.view_action = view.action
            fset.view_detail = view.detail
            return fset
