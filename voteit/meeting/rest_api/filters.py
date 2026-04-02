import functools
from operator import or_

import django_filters
from django.db.models import Q
from django.forms import MultipleChoiceField
from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES

from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles


def _meeting_with_role_qs(request):
    return Meeting.objects.filter(roles__user=request.user)


class ForceMeetingWithRoleFilter(filters.FilterSet):
    """
    Use with ActionAnnotatedDjangoFilterBackend
    """

    view_action: str
    view_detail: bool
    meeting = django_filters.ModelChoiceFilter(queryset=_meeting_with_role_qs)
    required_on: list[str] | set[str] = {"list"}

    def is_valid(self):
        if (
            self.view_action in self.required_on
            and self.is_bound
            and self.form.is_valid()
        ):
            if not isinstance(self.form.cleaned_data.get("meeting"), Meeting):
                self.form.add_error(
                    "meeting", f"Required argument for action '{self.view_action}'."
                )
        return super().is_valid()


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


# filters.BaseInFilter
class AnyRoleFilter(filters.Filter):
    field_class = MultipleChoiceField

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        if value:
            or_queries = functools.reduce(or_, [Q(assigned__contains=r) for r in value])
            qs = qs.filter(or_queries)
        if self.distinct:
            qs = qs.distinct()
        return qs


class MeetingRolesFilter(filters.FilterSet):
    """
    FilterSet for meeting roles viewset.
    GET parameters would be something like:
    user_id_in=1,2,3,6
    any_roles=["discusser", "proposer"]
    """

    user_id_in = NumberInFilter(field_name="user_id")
    any_roles = AnyRoleFilter(
        field_name="assigned", choices=tuple(MeetingRoles.valid_roles.items())
    )

    class Meta:
        model = MeetingRoles
        fields = ("user_id_in", "any_roles")
