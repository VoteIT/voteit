from __future__ import annotations

from django.test import TransactionTestCase
from django.test import override_settings
from envelope.testing import testing_channel_layers_setting

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
    """Create a source/target user pair with matching identity_id."""
    source = _mk_user(org, f"source_{identity_id}", identity_id=identity_id)
    target = _mk_user(org, f"target_{identity_id}", identity_id=identity_id)
    return source, target


def _mk_meeting(org):
    return Meeting.objects.create(organisation=org)


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class ValidationTests(TransactionTestCase):
    def setUp(self):
        self.org = _mk_org()
        self.other_org = _mk_org()
        self.source, self.target = _mk_pair(self.org)

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


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class MeetingRolesTests(TransactionTestCase):
    def setUp(self):
        from voteit.meeting.roles import ROLE_PARTICIPANT
        from voteit.meeting.roles import ROLE_PROPOSER

        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.meeting = _mk_meeting(self.org)
        self.ROLE_PARTICIPANT = ROLE_PARTICIPANT
        self.ROLE_PROPOSER = ROLE_PROPOSER

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

    def test_dry_run_leaves_db_unchanged(self):
        self.meeting.add_roles(self.source, self.ROLE_PARTICIPANT)
        UserMerger(self.source, self.target, dry_run=True).run()
        self.assertTrue(
            MeetingRoles.objects.filter(user=self.source, context=self.meeting).exists()
        )
        self.assertFalse(
            MeetingRoles.objects.filter(user=self.target, context=self.meeting).exists()
        )


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class OrganisationRolesTests(TransactionTestCase):
    def setUp(self):
        from voteit.organisation.roles import ROLE_ORG_MANAGER
        from voteit.organisation.roles import ROLE_MEETING_CREATOR

        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.ROLE_ORG_MANAGER = ROLE_ORG_MANAGER
        self.ROLE_MEETING_CREATOR = ROLE_MEETING_CREATOR

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


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class VoteTests(TransactionTestCase):
    def setUp(self):
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.models import Poll

        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.meeting = _mk_meeting(self.org)
        self.er = ElectoralRegister.objects.create(meeting=self.meeting)
        self.poll = Poll.objects.create(
            method_name="simple",
            electoral_register=self.er,
            meeting=self.meeting,
        )

    def test_vote_moved_when_no_conflict(self):
        from voteit.poll.models import Vote

        self.er.add_voter(self.source)
        vote = Vote.objects.create(user=self.source, poll=self.poll, abstain=True)
        UserMerger(self.source, self.target).run()
        vote.refresh_from_db()
        self.assertEqual(vote.user, self.target)

    def test_vote_skipped_when_both_voted(self):
        from voteit.poll.models import Vote

        self.er.add_voter(self.source)
        self.er.add_voter(self.target)
        Vote.objects.create(user=self.source, poll=self.poll, abstain=True)
        Vote.objects.create(user=self.target, poll=self.poll, abstain=True)
        log = UserMerger(self.source, self.target).run()
        self.assertTrue(Vote.objects.filter(user=self.source, poll=self.poll).exists())
        self.assertTrue(any("skipped" in msg.lower() for msg in log.skipped))


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class ElectoralRegisterTests(TransactionTestCase):
    def setUp(self):
        from voteit.poll.models import ElectoralRegister

        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.meeting = _mk_meeting(self.org)
        self.er = ElectoralRegister.objects.create(meeting=self.meeting)

    def test_er_key_moved(self):
        from voteit.poll.models import ElectoralRegister

        self.er.add_voter(self.source)
        UserMerger(self.source, self.target).run()
        er = ElectoralRegister.objects.get(pk=self.er.pk)
        self.assertIn(str(self.target.pk), er.voter_data)
        self.assertNotIn(str(self.source.pk), er.voter_data)

    def test_er_skipped_when_both_present(self):
        from voteit.poll.models import ElectoralRegister

        self.er.add_voter(self.source)
        self.er.add_voter(self.target)
        log = UserMerger(self.source, self.target).run()
        er = ElectoralRegister.objects.get(pk=self.er.pk)
        self.assertIn(str(self.source.pk), er.voter_data)
        self.assertTrue(any("ElectoralRegister" in msg for msg in log.skipped))


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class ActiveUserTests(TransactionTestCase):
    def setUp(self):
        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.meeting = _mk_meeting(self.org)

    def test_active_user_deleted(self):
        from voteit.active.models import ActiveUser

        ActiveUser.objects.create(user=self.source, meeting=self.meeting)
        log = UserMerger(self.source, self.target).run()
        self.assertFalse(ActiveUser.objects.filter(user=self.source).exists())
        self.assertTrue(any("deleted" in msg.lower() for msg in log.deleted))


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class ProposalAuthorTests(TransactionTestCase):
    def setUp(self):
        from voteit.agenda.models import AgendaItem

        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.meeting = _mk_meeting(self.org)
        self.ai = AgendaItem.objects.create(meeting=self.meeting)
        self.proposal = self.ai.proposals.create(author=self.source)

    def test_proposal_author_moved(self):
        UserMerger(self.source, self.target).run()
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.author, self.target)


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class SpeakerListOrderTests(TransactionTestCase):
    def setUp(self):
        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.meeting = _mk_meeting(self.org)

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


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class MentionsMoveTests(TransactionTestCase):
    def setUp(self):
        from voteit.agenda.models import AgendaItem

        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)
        self.meeting = _mk_meeting(self.org)
        self.ai = AgendaItem.objects.create(meeting=self.meeting)
        self.proposal = self.ai.proposals.create(author=self.target)
        self.proposal.mentions.add(self.source)

    def test_mentions_moved(self):
        from voteit.proposal.models import Proposal

        UserMerger(self.source, self.target).run()
        proposal = Proposal.objects.get(pk=self.proposal.pk)
        self.assertIn(self.target, proposal.mentions.all())
        self.assertNotIn(self.source, proposal.mentions.all())


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class SourceDeactivatedTests(TransactionTestCase):
    def setUp(self):
        self.org = _mk_org()
        self.source, self.target = _mk_pair(self.org)

    def test_source_deactivated_after_merge(self):
        UserMerger(self.source, self.target).run()
        self.source.refresh_from_db()
        self.assertFalse(self.source.is_active)

    def test_dry_run_source_stays_active(self):
        UserMerger(self.source, self.target, dry_run=True).run()
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)
