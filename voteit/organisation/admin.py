from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from envelope.models import Connection

try:
    from voteit_org.models import Membership
    from voteit_org.models import MembershipType
except ImportError:
    Membership = None
    MembershipType = None

from voteit.organisation.models import AccessToken
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER


User = get_user_model()


class InactiveOrgFilter(admin.SimpleListFilter):
    title = "Inactive"
    parameter_name = "inactive"
    search_param = "active"

    def lookups(self, request, model_admin):
        """
        URL query str + Human-readable
        """
        return (
            ("inc", "Include inactive"),
            ("only", "Only inactive"),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        v = self.value()
        if v == "inc":
            return queryset
        elif v == "only":
            return queryset.filter(**{self.search_param: False})
        return queryset.filter(**{self.search_param: True})

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": "Hide    ",
        }
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == str(lookup),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }


class MemberYearFilter(admin.SimpleListFilter):
    title = "Year"
    parameter_name = "year"
    search_param = "memberships__year"

    def lookups(self, request, model_admin):
        """
        URL query str + Human-readable
        """
        if Membership:
            values = []
            if v := self.value():
                if v.startswith("not"):
                    values.append((f"not{v[3:]}", f"Negate {v[3:]}"))
                else:
                    values.append((f"not{v}", f"Negate {v}"))
            values.extend(
                [
                    (x, x)
                    for x in sorted(
                        Membership.objects.values_list("year", flat=True).distinct()
                    )
                ]
            )
            return values
        return ()

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if v := self.value():
            if v.startswith("not"):
                v = v[3:]
                return queryset.exclude(**{self.search_param: v})
            else:
                return queryset.filter(**{self.search_param: v})
        return queryset


class MemberTypeFilter(admin.SimpleListFilter):
    title = "Membertype"
    parameter_name = "mtype"
    search_param = "memberships__membership_type"

    def lookups(self, request, model_admin):
        """
        URL query str + Human-readable
        """
        if MembershipType:
            values = []
            if v := self.value():
                if v.startswith("not"):
                    if negated := MembershipType.objects.filter(pk=v[3:]).first():
                        values.append((f"not{v[3:]}", f"Negate {negated.title}"))
                else:
                    if selected := MembershipType.objects.filter(pk=v).first():
                        values.append((f"not{v}", f"Negate {selected.title}"))
            values.extend(
                [
                    (x.pk, x.title)
                    for x in sorted(MembershipType.objects.all().order_by("title"))
                ]
            )
            return values
        return ()

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if v := self.value():
            if v.startswith("not"):
                v = v[3:]
                return queryset.exclude(**{self.search_param: v})
            else:
                return queryset.filter(**{self.search_param: v})
        return queryset


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    search_fields = ("title",)
    list_display = (
        "title",
        "meeting_count",
        "users_count",
        "manager_count",
        "meeting_creator_count",
    )
    autocomplete_fields = ("mentions",)
    list_filter = (
        InactiveOrgFilter,
        MemberYearFilter,
        MemberTypeFilter,
    )
    actions = [
        "mark_as_active",
        "mark_as_inactive",
        "mark_as_member",
    ]

    @admin.display(description="Managers")
    def manager_count(self, obj: Organisation):
        return obj.managers__count

    @admin.display(description="Meeting Creators")
    def meeting_creator_count(self, obj: Organisation):
        return obj.meeting_creator__count
        # return obj.roles.filter(assigned__contains=ROLE_MEETING_CREATOR).count()

    @admin.display(description="Online users")
    def users_count(self, obj: Organisation):
        return f"{obj.users.filter(pk__in=self.online_user_pks).count()} / {obj.users.count()}"

    @admin.display(description="Meetings")
    def meeting_count(self, obj: Organisation):
        return obj.meeting__count

    @cached_property
    def online_user_pks(self):
        recent_connections_qs = Connection.objects.filter(
            online=True, last_action__gt=now() - timedelta(minutes=10)
        )
        return recent_connections_qs.values_list("user_id", flat=True).distinct()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            meeting__count=models.Count("meetings", distinct=True),
            meeting_creator__count=models.Count(
                "roles",
                distinct=True,
                filter=models.Q(roles__assigned__contains=ROLE_MEETING_CREATOR),
            ),
            managers__count=models.Count(
                "roles",
                distinct=True,
                filter=models.Q(roles__assigned__contains=ROLE_ORG_MANAGER),
            ),
        )
        return qs

    @admin.display(description="Mark as active")
    def mark_as_active(self, request, queryset):
        queryset = queryset.filter(active=False)
        changed = queryset.update(active=True)
        self.message_user(
            request,
            f"Marked {changed} active",
            messages.SUCCESS,
        )

    @admin.action(description="Mark as inactive")
    def mark_as_inactive(self, request, queryset):
        queryset = queryset.filter(active=True)
        changed = queryset.update(active=False)
        self.message_user(
            request,
            f"Marked {changed} inactive",
            messages.SUCCESS,
        )

    @admin.action(description="Create member for negated type and year")
    def mark_as_member(self, request, queryset):
        year = request.GET.get("year")
        mtype = request.GET.get("mtype")
        if not (year and year.startswith("not") and mtype and mtype.startswith("not")):
            self.message_user(
                request,
                f"Both year and membership type must be selected and negated",
                messages.ERROR,
            )
            return
        year = year[3:]
        mtype = mtype[3:]
        queryset = queryset.exclude(memberships__year=year).exclude(
            memberships__membership_type=mtype
        )
        for org in queryset:
            org.memberships.create(year=year, membership_type_id=mtype)
        self.message_user(
            request,
            f"{queryset.count()} organisations marked as members",
            messages.SUCCESS,
        )


@admin.register(OrganisationRoles)
class OrganisationRolesAdmin(admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "get_assigned", "context"
    list_filter = ("context",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )

    def get_assigned(self, instance):
        return instance.assigned


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    autocomplete_fields = ("user",)
    list_display = "user", "updated"
    list_filter = ("user__organisation",)


@admin.register(TermsOfService)
class TermsOfServiceAdmin(admin.ModelAdmin):
    pass


@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    pass


@admin.register(OAuth2Provider)
class OAuth2ProviderAdmin(admin.ModelAdmin):
    pass
