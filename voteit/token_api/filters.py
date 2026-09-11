from functools import cache
from functools import reduce
from operator import or_

from django import forms
from django.db import models
from django_filters import rest_framework as filters

from voteit.invites.abcs import InviteUserDataAdapter
from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.models import MeetingRoles


class UserDataField(forms.CharField):
    """
    Runs the value through the adapter schema, the same way as on create,
    so it matches the normalised form that's stored.
    """

    def __init__(self, *args, adapter: type[InviteUserDataAdapter], **kwargs):
        self.adapter = adapter
        super().__init__(*args, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value in self.empty_values:
            return value
        name = self.adapter.name
        try:
            return getattr(self.adapter.schema(**{name: value}), name)
        except ValueError:
            raise forms.ValidationError(f"{value!r} is not a valid {name}.")


class UserDataFilter(filters.BaseCSVFilter, filters.CharFilter):
    field_class = UserDataField

    def __init__(self, adapter: type[InviteUserDataAdapter], **kwargs):
        self.adapter = adapter
        kwargs.setdefault("label", adapter.title)
        super().__init__(field_name="user_data", adapter=adapter, **kwargs)

    def filter(self, qs, value):
        if values := [v for v in value or () if v]:
            return qs.filter(self.adapter.query(*values))
        return qs


class RolesFilter(filters.BaseCSVFilter, filters.ChoiceFilter):
    def filter(self, qs, value):
        if values := [v for v in value or () if v]:
            return qs.filter(reduce(or_, [models.Q(roles__contains=v) for v in values]))
        return qs


class ChoiceInFilter(filters.BaseInFilter, filters.ChoiceFilter):
    pass


class MeetingInviteFilterSet(filters.FilterSet):
    """
    Comma-separated values match any of them, different params must all match.
    """

    roles = RolesFilter(
        choices=[(str(r), r.title) for r in MeetingRoles.valid_roles.values()],
        label="Roles",
    )
    state = ChoiceInFilter(
        choices=MeetingInvite._meta.get_field("state").choices,
        label="State",
    )

    class Meta:
        model = MeetingInvite
        fields = ()


@cache
def get_invite_filterset_class() -> type[MeetingInviteFilterSet]:
    """
    Adds a filter for each user data key in the invite adapter registry.
    They can't be declared on the class, since adapters register in ready()
    and may not all be there when this module is imported.
    """
    reg = get_invite_adapter_registry()
    user_data_filters = {
        name: UserDataFilter(reg[name]) for name in sorted(reg.user_data_keys)
    }
    return type(MeetingInviteFilterSet)(
        "UserDataMeetingInviteFilterSet", (MeetingInviteFilterSet,), user_data_filters
    )
