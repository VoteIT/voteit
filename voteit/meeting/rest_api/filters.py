from django_filters import rest_framework as filters
from voteit.meeting.models import MeetingRoles


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class RoleInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class MeetingRolesFilter(filters.FilterSet):
    """
    FilterSet for meeting roles viewset.
    GET parameters would be something like:
    user_id_in=1,2,3,6
    any_roles=discusser,proposer
    """

    user_id_in = NumberInFilter(field_name="user_id")
    any_roles = RoleInFilter(field_name="assigned", lookup_expr="overlap")

    class Meta:
        model = MeetingRoles
        fields = ("user_id_in", "any_roles")
