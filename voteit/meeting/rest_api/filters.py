from django_filters import rest_framework as filters
from voteit.meeting.models import MeetingRoles


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class UserPkFilter(filters.FilterSet):
    """Query filter including all objects where user_id is in list of primary keys
    GET parameters would be something like ?user_id_in=1,2,3,6"""

    user_id_in = NumberInFilter(field_name="user_id", lookup_expr="in")

    class Meta:
        model = MeetingRoles
        fields = ("user_id_in",)
