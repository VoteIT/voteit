from django.contrib.auth import get_user_model
from django_filters import rest_framework as filters
from voteit.organisation.models import OrganisationRoles


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class TextInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class UserPkFilter(filters.FilterSet):
    """Query filter including all objects where user_id is in list of primary keys
    GET parameters would be something like ?context=1&user_id_in=1,2,3,6"""

    user_id_in = NumberInFilter(field_name="user_id", lookup_expr="in")

    class Meta:
        model = OrganisationRoles
        fields = ("user_id_in",)


class OrphanUserEmailFilter(filters.FilterSet):
    # FIXME: Filtering ONLY works with ',' as separator, multiple queries with the same name will
    # cause only the latest value to be used!
    email_in = TextInFilter(field_name="email", lookup_expr="in", required=True)

    class Meta:
        model = get_user_model()
        fields = ("email_in",)


class UserIdentitiesFilter(filters.FilterSet):
    # FIXME: Filtering ONLY works with ',' as separator, multiple queries with the same name will
    # cause only the latest value to be used!
    identity_in = TextInFilter(
        field_name="identity_id", lookup_expr="in", required=True
    )

    class Meta:
        model = get_user_model()
        fields = ("identity_in",)
