from django_filters.rest_framework import DjangoFilterBackend


class ActionAnnotatedDjangoFilterBackend(DjangoFilterBackend):
    def get_filterset(self, request, queryset, view):
        fset = super().get_filterset(request, queryset, view)
        fset.view_action = view.action
        return fset
