from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from voteit.app.sfs.rest_api import serializers
from voteit.core.rest_api import router
from voteit.core.rules import is_not_finished
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.group_votes_before_poll import GroupVotesBeforePoll
from voteit.core import PERM

DELEGATION_LEADER_ROLE_ID = "leader"


@router.register("sfs-delegation-voters", basename="sfs-delegation-voters")
class SetDelegationVotersViewSet(viewsets.GenericViewSet):
    queryset = MeetingGroup.objects.all()
    serializer_class = serializers.SetDelegationVotersSerializer

    @action(detail=True, methods=["post"], url_path="set", url_name="set")
    def set_delegation_voters(self, request, pk=None):
        meeting_group: MeetingGroup = self.get_object()
        if not request.user.has_perm(MeetingGroup.get_perm(PERM.VIEW), meeting_group):
            raise PermissionDenied()
        if not is_not_finished(request.user, meeting_group.meeting):
            raise ValidationError({"non_field_errors": ["Meeting closed."]})
        if not meeting_group.votes:
            raise ValidationError({"non_field_errors": ["This group has no votes."]})
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        weights = serializer.validated_data["weights"]
        total_dist_votes = sum(x["weight"] for x in weights)
        if total_dist_votes != meeting_group.votes:
            raise ValidationError(
                {
                    "weights": [
                        f"Bad vote sum. You've set {total_dist_votes} but "
                        f"the group has {meeting_group.votes} votes."
                    ]
                }
            )
        meeting = meeting_group.meeting
        if meeting.er_policy_name != GroupVotesBeforePoll.name:
            raise ValidationError(
                {
                    "non_field_errors": [
                        f"This message is only valid while using {GroupVotesBeforePoll.name} electoral register policy."
                    ]
                }
            )
        if not (
            meeting_group.memberships.filter(
                user=request.user, role__role_id=DELEGATION_LEADER_ROLE_ID
            ).exists()
            or request.user.has_perm(Meeting.get_perm(PERM.CHANGE), meeting)
        ):
            raise ValidationError(
                {"non_field_errors": ["You're not delegation leader or moderator."]}
            )
        user_pks = {x["user"] for x in weights}
        group_member_pks = set(meeting_group.members.all().values_list("pk", flat=True))
        non_members = user_pks - group_member_pks
        if non_members:
            raise ValidationError(
                {
                    "weights": [
                        f"The following user PKs aren't members of that group: "
                        f"{', '.join(str(x) for x in non_members)}."
                    ]
                }
            )
        potential_voter_user_pks = set(
            meeting.roles.filter(
                user_id__in=user_pks, assigned__contains=ROLE_POTENTIAL_VOTER
            ).values_list("user_id", flat=True)
        )
        non_potential_voters = user_pks - potential_voter_user_pks
        if non_potential_voters:
            raise ValidationError(
                {
                    "weights": [
                        f"The following user PKs aren't potential voters: "
                        f"{', '.join(str(x) for x in non_potential_voters)}."
                    ]
                }
            )
        for membership in meeting_group.memberships.filter(
            votes__gt=0, user_id__in=group_member_pks - user_pks
        ):
            membership.votes = None
            membership.save()
        for vw in weights:
            meeting_group.memberships.update_or_create(
                user_id=vw["user"],
                defaults={"votes": vw["weight"]},
            )
        return Response({"weights": weights}, status=200)
