from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from voteit.core.user_merger import UserMerger
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles

SHARED_IDENTITY = "test-identity-id"


def _mk_org():
    return Organisation.objects.create()


def _mk_user(org, username="user", **kwargs):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create(username=username, organisation=org, **kwargs)


def _mk_pair(org, identity_id=SHARED_IDENTITY):
    source = _mk_user(org, f"source_{identity_id}", identity_id=identity_id)
    target = _mk_user(org, f"target_{identity_id}", identity_id=identity_id)
    return source, target


def _mk_meeting(org):
    return Meeting.objects.create(organisation=org)


class ValidationTests(TestCase):
    """Validation errors and source-deactivation behaviour."""

    @classmethod
    def setUpTestData(cls):
        cls.org = _mk_org()
        cls.other_org = _mk_org()
        cls.source, cls.target = _mk_pair(cls.org)

    def test_same_user_raises(self):
        with self.assertRaises(ValueError):
            UserMerger(self.source, self.source).run()

    def test_different_org_raises(self):
        other_user = _mk_user(self.other_org, "other", identity_id=SHARED_IDENTITY)
        with self.assertRaises(ValueError):
            UserMerger(self.source, other_user).run()

    def test_mismatched_identity_id_raises(self):
        other = _mk_user(self.org, "other_ident", identity_id="different-id")
        with self.assertRaises(ValueError):
            UserMerger(self.source, other).run()

    def test_missing_identity_id_raises(self):
        no_id = _mk_user(self.org, "no_id")
        with self.assertRaises(ValueError):
            UserMerger(self.source, no_id).run()

    def test_source_deactivated_after_merge(self):
        UserMerger(self.source, self.target).run()
        self.source.refresh_from_db()
        self.assertFalse(self.source.is_active)

    def test_dry_run_source_stays_active(self):
        UserMerger(self.source, self.target, dry_run=True).run()
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)

    def test_inactive_target_raises(self):
        self.target.is_active = False
        self.target.save()
        with self.assertRaises(ValueError):
            UserMerger(self.source, self.target).run()

    def test_target_deactivated_meanwhile_raises(self):
        """
        Another merge deactivated the target after this one was set up: the
        state under the row lock decides, not the instance passed in.
        """
        from django.contrib.auth import get_user_model

        get_user_model().objects.filter(pk=self.target.pk).update(is_active=False)
        self.assertTrue(self.target.is_active)
        with self.assertRaises(ValueError):
            UserMerger(self.source, self.target).run()
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)

    def test_target_with_removal_requested_raises(self):
        from django.utils.timezone import now

        self.target.removal_requested = now()
        self.target.save()
        with self.assertRaises(ValueError):
            UserMerger(self.source, self.target).run()

    def test_inactive_source_is_allowed(self):
        self.source.is_active = False
        self.source.save()
        UserMerger(self.source, self.target).run()


class RolesTests(TestCase):
    """Meeting and organisation role merging."""

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.roles import ROLE_PARTICIPANT
        from voteit.meeting.roles import ROLE_PROPOSER
        from voteit.organisation.roles import ROLE_MEETING_CREATOR
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        cls.org = _mk_org()
        cls.source, cls.target = _mk_pair(cls.org)
        cls.meeting = _mk_meeting(cls.org)
        cls.ROLE_PARTICIPANT = ROLE_PARTICIPANT
        cls.ROLE_PROPOSER = ROLE_PROPOSER
        cls.ROLE_ORG_MANAGER = ROLE_ORG_MANAGER
        cls.ROLE_MEETING_CREATOR = ROLE_MEETING_CREATOR

    def test_meeting_roles_moved(self):
        self.meeting.add_roles(self.source, self.ROLE_PARTICIPANT)
        UserMerger(self.source, self.target).run()
        self.assertTrue(
            MeetingRoles.objects.filter(user=self.target, context=self.meeting).exists()
        )
        self.assertFalse(
            MeetingRoles.objects.filter(user=self.source, context=self.meeting).exists()
        )

    def test_meeting_roles_merged_when_both_in_meeting(self):
        self.meeting.add_roles(self.source, self.ROLE_PARTICIPANT)
        self.meeting.add_roles(self.target, self.ROLE_PROPOSER)
        log = UserMerger(self.source, self.target).run()
        target_mr = MeetingRoles.objects.get(user=self.target, context=self.meeting)
        self.assertIn(self.ROLE_PARTICIPANT.name, target_mr.assigned)
        self.assertIn(self.ROLE_PROPOSER.name, target_mr.assigned)
        self.assertFalse(
            MeetingRoles.objects.filter(user=self.source, context=self.meeting).exists()
        )
        self.assertTrue(any("merged" in msg for msg in log.merged_roles))

    def test_meeting_roles_dry_run_unchanged(self):
        self.meeting.add_roles(self.source, self.ROLE_PARTICIPANT)
        UserMerger(self.source, self.target, dry_run=True).run()
        self.assertTrue(
            MeetingRoles.objects.filter(user=self.source, context=self.meeting).exists()
        )
        self.assertFalse(
            MeetingRoles.objects.filter(user=self.target, context=self.meeting).exists()
        )

    def test_org_roles_moved(self):
        self.org.add_roles(self.source, self.ROLE_ORG_MANAGER)
        UserMerger(self.source, self.target).run()
        self.assertTrue(
            OrganisationRoles.objects.filter(
                user=self.target, context=self.org
            ).exists()
        )

    def test_org_roles_merged(self):
        self.org.add_roles(self.source, self.ROLE_ORG_MANAGER)
        self.org.add_roles(self.target, self.ROLE_MEETING_CREATOR)
        UserMerger(self.source, self.target).run()
        target_or = OrganisationRoles.objects.get(user=self.target, context=self.org)
        self.assertIn(self.ROLE_ORG_MANAGER.name, target_or.assigned)
        self.assertIn(self.ROLE_MEETING_CREATOR.name, target_or.assigned)


class PollTests(TestCase):
    """Vote and electoral register migration."""

    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.models import Poll

        cls.org = _mk_org()
        cls.source, cls.target = _mk_pair(cls.org)
        cls.meeting = _mk_meeting(cls.org)
        cls.er = ElectoralRegister.objects.create(meeting=cls.meeting)
        cls.poll = Poll.objects.create(
            method_name="simple",
            electoral_register=cls.er,
            meeting=cls.meeting,
        )

    def test_vote_moved_when_no_conflict(self):
        from voteit.poll.models import Vote

        self.er.set_voters_from_dict({self.source.pk: 1})
        vote = Vote.objects.create(user=self.source, poll=self.poll, abstain=True)
        UserMerger(self.source, self.target).run()
        vote.refresh_from_db()
        self.assertEqual(vote.user, self.target)

    def test_vote_skipped_when_both_voted(self):
        from voteit.poll.models import Vote

        self.er.set_voters_from_dict({self.source.pk: 1, self.target.pk: 1})
        Vote.objects.create(user=self.source, poll=self.poll, abstain=True)
        Vote.objects.create(user=self.target, poll=self.poll, abstain=True)
        log = UserMerger(self.source, self.target).run()
        self.assertTrue(Vote.objects.filter(user=self.source, poll=self.poll).exists())
        self.assertTrue(any("skipped" in msg.lower() for msg in log.skipped))

    def test_er_key_moved(self):
        from voteit.poll.models import ElectoralRegister

        self.er.set_voters_from_dict({self.source.pk: 1})
        UserMerger(self.source, self.target).run()
        er = ElectoralRegister.objects.get(pk=self.er.pk)
        self.assertIn(str(self.target.pk), er.voter_data)
        self.assertNotIn(str(self.source.pk), er.voter_data)

    def test_er_skipped_when_both_present(self):
        from voteit.poll.models import ElectoralRegister

        self.er.set_voters_from_dict({self.source.pk: 1, self.target.pk: 1})
        log = UserMerger(self.source, self.target).run()
        er = ElectoralRegister.objects.get(pk=self.er.pk)
        self.assertIn(str(self.source.pk), er.voter_data)
        self.assertTrue(any("ElectoralRegister" in msg for msg in log.skipped))


class ContentTests(TestCase):
    """Active users, proposals, speaker lists, and mentions."""

    @classmethod
    def setUpTestData(cls):
        from voteit.agenda.models import AgendaItem

        cls.org = _mk_org()
        cls.source, cls.target = _mk_pair(cls.org)
        cls.meeting = _mk_meeting(cls.org)
        cls.ai = AgendaItem.objects.create(meeting=cls.meeting)

    def test_active_user_deleted(self):
        from voteit.active.models import ActiveUser

        ActiveUser.objects.create(user=self.source, meeting=self.meeting)
        log = UserMerger(self.source, self.target).run()
        self.assertFalse(ActiveUser.objects.filter(user=self.source).exists())
        self.assertTrue(any("deleted" in msg.lower() for msg in log.deleted))

    def test_proposal_author_moved(self):
        proposal = self.ai.proposals.create(author=self.source)
        UserMerger(self.source, self.target).run()
        proposal.refresh_from_db()
        self.assertEqual(proposal.author, self.target)

    def test_speaker_list_order_updated(self):
        from voteit.speaker.models import Speaker
        from voteit.speaker.models import SpeakerList
        from voteit.speaker.models import SpeakerListSystem

        room = self.meeting.rooms.create()
        sls = SpeakerListSystem.objects.create(method_name="simple", room=room)
        sl = SpeakerList.objects.create(speaker_system=sls, order=str(self.source.pk))
        Speaker.objects.create(user=self.source, speaker_list=sl)
        UserMerger(self.source, self.target).run()
        sl.refresh_from_db()
        self.assertNotIn(str(self.source.pk), sl.order)
        self.assertIn(str(self.target.pk), sl.order)

    def test_mentions_moved(self):
        from voteit.proposal.models import Proposal

        proposal = self.ai.proposals.create(author=self.target)
        proposal.mentions.add(self.source)
        UserMerger(self.source, self.target).run()
        proposal = Proposal.objects.get(pk=proposal.pk)
        self.assertIn(self.target, proposal.mentions.all())
        self.assertNotIn(self.source, proposal.mentions.all())


class MergeConflictsTests(TestCase):
    """
    Crucial data (votes, electoral registers, meeting groups) for more than one
    account in the same meeting blocks a merge, whether or not it collides.
    """

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import MeetingGroup
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.models import Poll

        cls.org = _mk_org()
        cls.source, cls.target = _mk_pair(cls.org)
        cls.meeting = _mk_meeting(cls.org)
        cls.other_meeting = _mk_meeting(cls.org)
        cls.er = ElectoralRegister.objects.create(meeting=cls.meeting)
        cls.poll = Poll.objects.create(
            method_name="simple", electoral_register=cls.er, meeting=cls.meeting
        )
        cls.second_poll = Poll.objects.create(
            method_name="simple", electoral_register=cls.er, meeting=cls.meeting
        )
        cls.other_poll = Poll.objects.create(
            method_name="simple", meeting=cls.other_meeting
        )
        cls.group = MeetingGroup.objects.create(
            meeting=cls.meeting, title="G", groupid="g"
        )

    def _conflicts(self):
        from voteit.core.user_merger import merge_conflicts

        return merge_conflicts([self.source, self.target])

    def _vote(self, user, poll):
        from voteit.poll.models import Vote

        # bulk_create skips the electoral register check in save()
        Vote.objects.bulk_create([Vote(user=user, poll=poll, abstain=True)])

    def test_nothing_crucial(self):
        self.meeting.add_roles(self.source, "pa")
        self.meeting.add_roles(self.target, "pa")
        self.assertEqual(set(), self._conflicts())

    def test_same_poll(self):
        self._vote(self.source, self.poll)
        self._vote(self.target, self.poll)
        self.assertEqual({self.meeting.pk}, self._conflicts())

    def test_different_polls_same_meeting(self):
        self._vote(self.source, self.poll)
        self._vote(self.target, self.second_poll)
        self.assertEqual({self.meeting.pk}, self._conflicts())

    def test_vote_and_electoral_register(self):
        from voteit.poll.models import ElectoralRegister

        self._vote(self.source, self.poll)
        ElectoralRegister.objects.create(
            meeting=self.meeting, voter_data={str(self.target.pk): 1}
        )
        self.assertEqual({self.meeting.pk}, self._conflicts())

    def test_group_and_vote(self):
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(meeting_group=self.group, user=self.source)
        self._vote(self.target, self.poll)
        self.assertEqual({self.meeting.pk}, self._conflicts())

    def test_different_meetings(self):
        self._vote(self.source, self.poll)
        self._vote(self.target, self.other_poll)
        self.assertEqual(set(), self._conflicts())


class GroupMembershipTests(TestCase):
    """GroupMembership.user has related_name="+", so it needs its own handling."""

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import GroupRole
        from voteit.meeting.models import MeetingGroup

        cls.org = _mk_org()
        cls.source, cls.target = _mk_pair(cls.org)
        cls.meeting = _mk_meeting(cls.org)
        cls.role = GroupRole.objects.create(
            meeting=cls.meeting, title="Voter", roles=["pv"]
        )
        cls.group = MeetingGroup.objects.create(
            meeting=cls.meeting, title="G1", groupid="g1"
        )
        cls.shared = MeetingGroup.objects.create(
            meeting=cls.meeting, title="G2", groupid="g2"
        )

    def _memberships(self, user):
        from voteit.meeting.models import GroupMembership

        return GroupMembership.objects.filter(user=user)

    def test_membership_moved_with_role_and_votes(self):
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(
            meeting_group=self.group, user=self.source, role=self.role, votes=2
        )
        UserMerger(self.source, self.target).run()
        self.assertFalse(self._memberships(self.source).exists())
        moved = self._memberships(self.target).get()
        self.assertEqual(self.group, moved.meeting_group)
        self.assertEqual(self.role, moved.role)
        self.assertEqual(2, moved.votes)

    def test_membership_in_shared_group_is_skipped(self):
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.source, votes=1
        )
        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.target, role=self.role, votes=3
        )
        UserMerger(self.source, self.target).run()
        kept = self._memberships(self.target).get()
        self.assertEqual(self.role, kept.role)
        # The group's members still add up to the same vote weight.
        self.assertEqual(4, kept.votes)

    def test_shared_group_takes_the_sources_role(self):
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.source, role=self.role, votes=2
        )
        GroupMembership.objects.create(meeting_group=self.shared, user=self.target)
        UserMerger(self.source, self.target).run()
        kept = self._memberships(self.target).get()
        self.assertEqual(self.role, kept.role)
        self.assertEqual(2, kept.votes)
        self.assertTrue(self.meeting.has_roles(self.target, "pv"))

    def test_shared_group_conflicting_roles_target_keeps_its_own(self):
        from voteit.meeting.models import GroupMembership
        from voteit.meeting.models import GroupRole

        other_role = GroupRole.objects.create(
            meeting=self.meeting, title="Other", roles=[]
        )
        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.source, role=other_role
        )
        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.target, role=self.role
        )
        log = UserMerger(self.source, self.target).run()
        self.assertEqual(self.role, self._memberships(self.target).get().role)
        self.assertTrue(any("dropped" in msg for msg in log.skipped))

    def test_shared_group_dry_run_changes_nothing(self):
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.source, votes=1
        )
        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.target, votes=3
        )
        UserMerger(self.source, self.target, dry_run=True).run()
        self.assertEqual(3, self._memberships(self.target).get().votes)
        self.assertEqual(1, self._memberships(self.source).get().votes)

    def test_membership_survives_source_meeting_roles(self):
        """
        Deleting the source's MeetingRoles cascades into its memberships, so
        they must have moved before that.
        """
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(
            meeting_group=self.group, user=self.source, role=self.role
        )
        self.assertTrue(self.meeting.has_roles(self.source, "pv"))
        UserMerger(self.source, self.target).run()
        self.assertEqual(self.group, self._memberships(self.target).get().meeting_group)
        self.assertTrue(self.meeting.has_roles(self.target, "pv"))

    def test_shared_group_votes_not_counted_twice(self):
        """
        The source has no meeting roles here, so nothing deletes its
        membership. Its votes must still only be counted once.
        """
        from django.db.models import Sum

        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.source, votes=1
        )
        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.target, votes=1
        )
        self.assertIsNone(self.meeting.get_roles(self.source))
        UserMerger(self.source, self.target).run()
        self.assertEqual(2, self._memberships(self.target).get().votes)
        total = GroupMembership.objects.filter(meeting_group=self.shared).aggregate(
            total=Sum("votes")
        )["total"]
        self.assertEqual(2, total)

    def test_changed_memberships_are_published(self):
        from voteit.meeting.messages import GroupMembershipChanged
        from voteit.meeting.models import GroupMembership

        moved = GroupMembership.objects.create(
            meeting_group=self.group, user=self.source
        )
        GroupMembership.objects.create(
            meeting_group=self.shared, user=self.source, votes=1
        )
        combined = GroupMembership.objects.create(
            meeting_group=self.shared, user=self.target, votes=1
        )
        with patch("voteit.meeting.signals.broadcast_meeting") as broadcast:
            UserMerger(self.source, self.target).run()
        sent = {
            call.args[1].payload.pk: call.args[1].payload.model_dump()
            for call in broadcast.call_args_list
            if isinstance(call.args[1], GroupMembershipChanged)
        }
        self.assertEqual(self.target.pk, sent[moved.pk]["user"])
        self.assertEqual(2, sent[combined.pk]["votes"])

    def test_dry_run_publishes_nothing(self):
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(meeting_group=self.group, user=self.source)
        with patch("voteit.meeting.signals.broadcast_meeting") as broadcast:
            UserMerger(self.source, self.target, dry_run=True).run()
        broadcast.assert_not_called()

    def test_dry_run_leaves_memberships(self):
        from voteit.meeting.models import GroupMembership

        GroupMembership.objects.create(meeting_group=self.group, user=self.source)
        log = UserMerger(self.source, self.target, dry_run=True).run()
        self.assertTrue(self._memberships(self.source).exists())
        self.assertTrue(any("GroupMembership" in msg for msg in log.moved))


class PickMergeTargetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = _mk_org()
        cls.meeting = _mk_meeting(cls.org)

    def _pick(self, *users, session_user=None):
        from voteit.core.user_merger import pick_merge_target

        return pick_merge_target(list(users), session_user)

    def test_most_activity(self):
        a, b = _mk_pair(self.org)
        self.meeting.add_roles(b, "pa")
        self.assertEqual(b, self._pick(a, b))

    def test_elevated_beats_activity(self):
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        a, b = _mk_pair(self.org)
        self.meeting.add_roles(b, "pa")
        self.org.add_roles(a, ROLE_ORG_MANAGER)
        self.assertEqual(a, self._pick(a, b))

    def test_session_user_breaks_a_tie(self):
        a, b = _mk_pair(self.org)
        self.assertEqual(b, self._pick(a, b, session_user=b))

    def test_latest_login_breaks_a_tie(self):
        from django.utils.timezone import now

        a, b = _mk_pair(self.org)
        b.last_login = now()
        self.assertEqual(b, self._pick(a, b))


class AdminMergeActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.org = _mk_org()
        cls.meeting = _mk_meeting(cls.org)
        cls.admin_user = get_user_model().objects.create_superuser(
            username="merge-admin"
        )

    def test_more_active_user_becomes_target(self):
        from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
        from django.urls import reverse

        a, b = _mk_pair(self.org)
        self.meeting.add_roles(a, "pa")
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("admin:core_user_changelist"),
            {"action": "merge_users_action", ACTION_CHECKBOX_NAME: [a.pk, b.pk]},
        )
        self.assertEqual(302, response.status_code)
        location = response["Location"]
        self.assertIn(f"source={b.pk}&target={a.pk}", location)
        self.assertIn("score_src=0&score_tgt=1", location)


class AuditTrailTests(TestCase):
    """What a merge leaves in auditlog, which update() alone wouldn't."""

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import MeetingGroup
        from voteit.poll.models import Poll

        cls.org = _mk_org()
        cls.meeting = _mk_meeting(cls.org)
        cls.group = MeetingGroup.objects.create(
            meeting=cls.meeting, title="G", groupid="g"
        )
        cls.poll = Poll.objects.create(method_name="simple", meeting=cls.meeting)

    def setUp(self):
        from social_django.models import UserSocialAuth

        from voteit.meeting.models import GroupMembership
        from voteit.poll.models import Vote

        self.source, self.target = _mk_pair(self.org)
        self.admin = _mk_user(self.org, "merging-admin")
        self.meeting.add_roles(self.source, "pa")
        self.membership = GroupMembership.objects.create(
            meeting_group=self.group, user=self.source
        )
        # bulk_create skips the electoral register check in save()
        (self.vote,) = Vote.objects.bulk_create(
            [Vote(user=self.source, poll=self.poll, abstain=True)]
        )
        self.social = UserSocialAuth.objects.create(
            user=self.source, provider="scoutid", uid="1234567"
        )

    def _entries(self, merger):
        from auditlog.models import LogEntry

        return LogEntry.objects.filter(cid=merger.cid)

    def _for(self, entries, obj):
        from auditlog.models import LogEntry

        return entries.filter(
            content_type__model=obj._meta.model_name,
            object_pk=str(obj.pk),
            action=LogEntry.Action.UPDATE,
        )

    def test_summary_on_both_accounts(self):
        merger = UserMerger(self.source, self.target, actor=self.admin)
        merger.run()
        entries = self._entries(merger)
        merged_from = self._for(entries, self.target).get()
        self.assertEqual(
            {"merged_from": ["None", str(self.source.pk)]}, merged_from.changes_dict
        )
        self.assertEqual(self.org.pk, merged_from.additional_data["o"])
        self.assertEqual(self.source.pk, merged_from.additional_data["merge"]["source"])
        source_entries = self._for(entries, self.source)
        self.assertEqual(
            [
                {"is_active": ["True", "False"]},
                {"merged_into": ["None", str(self.target.pk)]},
            ],
            [entry.changes_dict for entry in source_entries.order_by("pk")],
        )

    def test_moved_rows_are_logged(self):
        merger = UserMerger(self.source, self.target)
        merger.run()
        entries = self._entries(merger)
        expected = {"user": [str(self.source.pk), str(self.target.pk)]}
        for obj in (self.membership, self.vote, self.social):
            with self.subTest(obj.__class__.__name__):
                self.assertEqual(expected, self._for(entries, obj).get().changes_dict)

    def test_log_entries_stay_with_their_actor(self):
        from auditlog.models import LogEntry
        from django.contrib.admin.models import CHANGE
        from django.contrib.admin.models import LogEntry as AdminLogEntry
        from django.contrib.contenttypes.models import ContentType

        audit_entry = LogEntry.objects.log_create(
            self.meeting, force_log=True, action=LogEntry.Action.UPDATE, changes={}
        )
        LogEntry.objects.filter(pk=audit_entry.pk).update(actor=self.source)
        admin_entry = AdminLogEntry.objects.create(
            user=self.source,
            content_type=ContentType.objects.get_for_model(self.meeting),
            object_id=str(self.meeting.pk),
            object_repr="Meeting",
            action_flag=CHANGE,
        )
        UserMerger(self.source, self.target).run()
        audit_entry.refresh_from_db()
        admin_entry.refresh_from_db()
        self.assertEqual(self.source.pk, audit_entry.actor_id)
        self.assertEqual(self.source.pk, admin_entry.user_id)

    def test_every_entry_has_the_actor(self):
        merger = UserMerger(self.source, self.target, actor=self.admin)
        merger.run()
        entries = self._entries(merger)
        # Role signals write some of these, the merger the rest
        self.assertTrue(entries.filter(content_type__model="meetingroles").exists())
        self.assertEqual({self.admin.pk}, set(entries.values_list("actor", flat=True)))

    def test_context_is_restored(self):
        from auditlog.cid import correlation_id

        from voteit.core.user_merger import _merge_actor

        token = correlation_id.set("outer")
        try:
            UserMerger(self.source, self.target, actor=self.admin).run()
            self.assertEqual("outer", correlation_id.get())
            self.assertIsNone(_merge_actor.get())
        finally:
            correlation_id.reset(token)

    def test_dry_run_logs_nothing(self):
        merger = UserMerger(self.source, self.target, dry_run=True)
        merger.run()
        self.assertFalse(self._entries(merger).exists())

    def test_disabled_auditlog_is_respected(self):
        from auditlog.context import disable_auditlog

        merger = UserMerger(self.source, self.target)
        with disable_auditlog():
            merger.run()
        self.assertFalse(self._entries(merger).exists())

    def test_admin_merge_is_attributed_to_the_admin(self):
        from auditlog.models import LogEntry
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        superuser = get_user_model().objects.create_superuser(username="trail-admin")
        self.client.force_login(superuser)
        self.client.post(
            reverse("admin:core_user_merge_confirm"),
            {"source_pk": self.source.pk, "target_pk": self.target.pk, "confirm": "on"},
        )
        entry = LogEntry.objects.get(changes__has_key="merged_from")
        self.assertEqual(superuser, entry.actor)
