from django_filters import rest_framework as filters
from voteit.organisation.models import OrganisationRoles


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class UserPkFilter(filters.FilterSet):
    """Query filter including all objects where user_id is in list of primary keys
    GET parameters would be something like ?context=1&user_id_in=1,2,3,6"""

    user_id_in = NumberInFilter(field_name="user_id", lookup_expr="in")

    class Meta:
        model = OrganisationRoles
        fields = ("user_id_in",)
