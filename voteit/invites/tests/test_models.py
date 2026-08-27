from datetime import timedelta
from django.utils import timezone

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import override_settings
from django.test import TestCase

from voteit.meeting.dialects import dialect_registry
from voteit.meeting.models import Meeting
from voteit.invites.models import MeetingInvite
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.tests.fixtures import DIALECT_FIXTURES
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

User = get_user_model()


class MeetingInviteManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.manager = MeetingInvite.objects
        cls.meeting: Meeting = cls.org.meetings.create(
            er_policy_name=AutoBeforePoll.name
        )
        cls.user = cls.org.users.create(username="someone")
        cls.inv1: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            roles=[ROLE_PARTICIPANT],
            user_data={"email": "a@betahaus.net", "swedish_ssn": "121212-1212"},
        )
        cls.inv2: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            roles=[ROLE_PARTICIPANT],
            user_data={"email": "b@betahaus.net"},
        )

    def test_query_email(self):
        self.assertEqual(
            {self.inv1},
            set(
                self.manager.find_invites(organisation=self.org, email="a@betahaus.net")
            ),
        )
        self.assertEqual(
            {self.inv2},
            set(
                self.manager.find_invites(organisation=self.org, email="b@betahaus.net")
            ),
        )
        self.assertEqual(
            {self.inv2},
            set(
                self.manager.find_invites(
                    organisation=self.org, email=["b@betahaus.net"]
                )
            ),
        )
        self.assertEqual(
            {self.inv1, self.inv2},
            set(
                self.manager.find_invites(
                    organisation=self.org,
                    email=["a@betahaus.net", "b@betahaus.net", "none@betahaus.net"],
                )
            ),
        )
        self.assertEqual(
            set(),
            set(
                self.manager.find_invites(
                    organisation=self.org, email="None@betahaus.net"
                )
            ),
        )

    def test_query_swedish_ssn(self):
        self.assertEqual(
            {self.inv1},
            set(
                self.manager.find_invites(
                    organisation=self.org, swedish_ssn="121212-1212"
                )
            ),
        )
        self.assertEqual(
            {self.inv1},
            set(
                self.manager.find_invites(
                    organisation=self.org, swedish_ssn=["121212-1212", "121212-1313"]
                )
            ),
        )

    def test_query_combined(self):
        self.assertEqual(
            {self.inv1, self.inv2},
            set(
                self.manager.find_invites(
                    organisation=self.org,
                    swedish_ssn=["121212-1212"],
                    email=["b@betahaus.net"],
                )
            ),
        )

    def test_bad_query_empyty(self):
        self.assertEqual(set(), set(self.manager.find_invites(organisation=self.org)))

    def test_bad_query_no_such_kw(self):
        self.assertEqual(
            set(), set(self.manager.find_invites(organisation=self.org, hello="world"))
        )

    def test_bad_query_empty(self):
        self.assertEqual(
            set(), set(self.manager.find_invites(organisation=self.org, email=None))
        )  # None is always skipped

    def test_create_or_update_typed(self):
        self.inv1.roles = [ROLE_PARTICIPANT, ROLE_DISCUSSER]
        self.inv1.save()
        result = self.meeting.invites.create_or_update_typed(
            invite_type="email",
            meeting=self.meeting,
            values=["a@betahaus.net", "b@betahaus.net", "c@betahaus.net"],
            roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER],
        )
        self.assertEqual(3, len(result.pks))
        self.assertEqual(1, result.added)
        self.assertEqual(1, result.changed)
        self.assertEqual(1, result.existed)

    def test_create_or_update_typed_updates_roles(self):
        self.inv1.used_by = self.user
        self.inv1.roles = [ROLE_PARTICIPANT, ROLE_PROPOSER]
        self.inv1.save()
        result = self.meeting.invites.create_or_update_typed(
            invite_type="email",
            meeting=self.meeting,
            values=["a@betahaus.net", "b@betahaus.net", "c@betahaus.net"],
            roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER],
        )
        self.assertEqual(3, len(result.pks))
        self.assertEqual(1, result.added)
        self.assertEqual(2, result.changed)
        self.assertEqual(0, result.existed)
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER}, self.meeting.get_roles(self.user)
        )

    @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    def test_create_or_update_with_dialect_ignored_roles_should_not_clear_assigned_role(
        self,
    ):
        dialect_registry.load()  # Force refresh
        dialect_registry["main_subst"].install(self.meeting)
        self.meeting.add_roles(
            self.user, ROLE_DISCUSSER, ROLE_PROPOSER, ROLE_POTENTIAL_VOTER
        )
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_PROPOSER, ROLE_POTENTIAL_VOTER},
            self.meeting.get_roles(self.user),
        )
        self.inv2.used_by = self.user
        self.inv2.save()
        result = self.meeting.invites.create_or_update_typed(
            invite_type="email",
            meeting=self.meeting,
            values=["b@betahaus.net"],
            roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER],
        )
        self.assertEqual(1, result.changed)
        # Proposer is not blocked by dialect, potential voter is and shouldn't be touched
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_POTENTIAL_VOTER},
            self.meeting.get_roles(self.user),
        )

    @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    def test_create_or_update_with_dialect_ignored_roles_should_block_role_on_invite(
        self,
    ):
        self.inv1.roles = [ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_POTENTIAL_VOTER]
        self.inv1.user_data = {"email": "a@betahaus.net"}
        self.inv1.save()
        self.inv2.roles = [ROLE_PARTICIPANT]
        self.inv2.user_data = {"email": "b@betahaus.net"}
        self.inv2.save()
        dialect_registry.load()  # Force refresh
        dialect_registry["main_subst"].install(self.meeting)
        result = self.meeting.invites.create_or_update_typed(
            invite_type="email",
            meeting=self.meeting,
            values=["a@betahaus.net", "b@betahaus.net", "c@betahaus.net"],
            roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_POTENTIAL_VOTER],
        )
        self.assertEqual(2, result.changed)
        self.assertEqual(1, result.added)
        # Proposer is not blocked by dialect, potential voter is and shouldn't be touched
        self.inv1.refresh_from_db()
        self.inv2.refresh_from_db()
        inv3 = MeetingInvite.objects.get(user_data={"email": "c@betahaus.net"})
        self.assertSetEqual({"di", "pa"}, set(self.inv1.roles))
        self.assertSetEqual({"di", "pa"}, set(self.inv2.roles))
        self.assertSetEqual({"di", "pa"}, set(inv3.roles))

    @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    def test_create_or_update_with_dialect_ignored_roles_should_not_add_role_to_existing_user(
        self,
    ):
        dialect_registry.load()  # Force refresh
        dialect_registry["main_subst"].install(self.meeting)
        self.inv2.used_by = self.user
        self.inv2.save()
        result = self.meeting.invites.create_or_update_typed(
            invite_type="email",
            meeting=self.meeting,
            values=["b@betahaus.net"],
            roles=[
                ROLE_PARTICIPANT,
                ROLE_DISCUSSER,
                ROLE_POTENTIAL_VOTER,
            ],  # Not allowed in interface, but could exist for some reason
        )
        self.assertEqual(1, result.changed)
        # Proposer is not blocked by dialect, potential voter is and shouldn't be touched
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER},
            self.meeting.get_roles(self.user),
        )

    def test_find_mixed_user_data_exact(self):
        exact, bogus = self.meeting.invites.find_mixed_user_data(
            {"email": "a@betahaus.net", "swedish_ssn": "121212-1212"}
        )
        self.assertEqual({self.inv1}, set(exact))
        self.assertEqual({}, bogus)

    def test_find_mixed_user_data_problematic_clash(self):
        exact, bogus = self.meeting.invites.find_mixed_user_data(
            {"email": "a@betahaus.net", "swedish_ssn": "abc-404"}
        )
        self.assertEqual(set(), set(exact))
        self.assertEqual({self.inv1}, set(bogus.get("email", [])))

    def test_find_mixed_user_data_has_more_data_we_dont_query(self):
        exact, bogus = self.meeting.invites.find_mixed_user_data(
            {"email": "a@betahaus.net"}
        )
        self.assertEqual({self.inv1}, set(exact))
        self.assertEqual({}, bogus)

    def test_find_mixed_user_data_odd_intersection(self):
        # Note: This should never be saved in the database
        self.inv2.user_data["swedish_ssn"] = "121212-1212"
        self.inv2.save()
        exact, bogus = self.meeting.invites.find_mixed_user_data(
            {"email": "a@betahaus.net", "swedish_ssn": "121212-1212"},
            {"email": "b@betahaus.net", "swedish_ssn": "121212-1212"},
        )
        self.assertEqual({self.inv1, self.inv2}, set(exact))
        self.assertEqual({}, bogus)

    def test_find_mixed_user_data_meeting_filter_not_applied(self):
        with self.assertRaises(IntegrityError) as cm:
            MeetingInvite.objects.find_mixed_user_data({"email": "jeff@barnes.com"})
        self.assertEqual("Queryset doesn't contain meeting filter", str(cm.exception))

    def test_test_find_mixed_user_data_meeting_filter_not_applied(self):
        with self.assertRaises(IntegrityError) as cm:
            MeetingInvite.objects.find_mixed_user_data({"email": "jeff@barnes.com"})
        self.assertEqual("Queryset doesn't contain meeting filter", str(cm.exception))

    def test_find_mixed_user_data_without_values(self):
        with self.assertNumQueries(0):
            qs, partial = self.meeting.invites.find_mixed_user_data()
        self.assertFalse(qs.exists())
        self.assertFalse(partial)

    def test_create_or_update_mixed(self):
        self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[
                {"email": "a@betahaus.net", "swedish_ssn": "121212-1212"},
                {"email": "jeff@betahaus.net"},
                {
                    "email": "new@betahaus.net",
                    "swedish_ssn": "123",  # Data isn't validated here
                },
            ],
            roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER],
        )

    def test_create_or_update_mixed_removes_role(self):
        self.inv1.roles = [ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_PROPOSER]
        self.inv1.accept(self.user)
        self.inv1.save()
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_PROPOSER},
            self.meeting.get_roles(self.user),
        )
        self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[
                {"email": "a@betahaus.net", "swedish_ssn": "121212-1212"},
                {"email": "jeff@betahaus.net"},
                {
                    "email": "new@betahaus.net",
                    "swedish_ssn": "123",  # Data isn't validated here
                },
            ],
            roles=[ROLE_PARTICIPANT],
        )
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.user))

    def test_create_or_update_mixed_problematic_clash(self):
        with self.assertRaises(IntegrityError) as cm:
            self.meeting.invites.create_or_update_mixed(
                meeting=self.meeting,
                data=[
                    {"email": "jeff@betahaus.net", "swedish_ssn": "121212-1212"},
                    {
                        "email": "new@betahaus.net",
                        "swedish_ssn": "123",  # Data isn't validated here
                    },
                ],
                roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER],
            )
        # for now we'll simply block this behaviour
        self.assertEqual("Partial invites found", str(cm.exception))

    # --- Duplicate rows -------------------------------------------------
    # The same person can legitimately appear on several rows of an import
    # file (one row per group, for instance), so the same user_data dict
    # reaches these methods more than once. It must never trip the
    # unique_meeting_invite_user_data constraint or inflate the counters.

    def test_create_or_update_mixed_duplicate_new_email(self):
        result = self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[{"email": "c@betahaus.net"}, {"email": "c@betahaus.net"}],
            roles=[ROLE_PARTICIPANT],
        )
        self.assertEqual(1, result.added)
        self.assertEqual(0, result.changed)
        self.assertEqual(0, result.existed)
        self.assertEqual(1, len(result.pks))
        self.assertEqual(
            1, self.meeting.invites.filter(user_data__email="c@betahaus.net").count()
        )

    def test_create_or_update_mixed_duplicate_existing_email(self):
        result = self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[{"email": "b@betahaus.net"}, {"email": "b@betahaus.net"}],
            roles=[ROLE_PARTICIPANT],
        )
        self.assertEqual(0, result.added)
        self.assertEqual(0, result.changed)
        self.assertEqual(1, result.existed)
        self.assertEqual({self.inv2.pk}, result.pks)
        self.assertEqual(
            1, self.meeting.invites.filter(user_data__email="b@betahaus.net").count()
        )

    def test_create_or_update_mixed_duplicate_existing_email_with_new_roles(self):
        result = self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[{"email": "b@betahaus.net"}, {"email": "b@betahaus.net"}],
            roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER],
        )
        self.assertEqual(0, result.added)
        self.assertEqual(1, result.changed)
        self.assertEqual(0, result.existed)
        self.inv2.refresh_from_db()
        self.assertEqual([ROLE_DISCUSSER, ROLE_PARTICIPANT], self.inv2.roles)

    def test_create_or_update_mixed_duplicate_multi_key_user_data(self):
        data = {"email": "c@betahaus.net", "swedish_ssn": "131313-1313"}
        result = self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[dict(data), dict(data)],
            roles=[ROLE_PARTICIPANT],
        )
        self.assertEqual(1, result.added)
        self.assertEqual(1, self.meeting.invites.filter(user_data=data).count())

    def test_create_or_update_mixed_duplicate_updates_assigned_roles_once(self):
        self.inv2.accept(self.user)
        self.inv2.save()
        result = self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[{"email": "b@betahaus.net"}, {"email": "b@betahaus.net"}],
            roles=[ROLE_PARTICIPANT, ROLE_DISCUSSER],
        )
        self.assertEqual(1, result.changed)
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER}, self.meeting.get_roles(self.user)
        )

    def test_create_or_update_typed_duplicate_values(self):
        result = self.meeting.invites.create_or_update_typed(
            invite_type="email",
            meeting=self.meeting,
            values=["c@betahaus.net", "c@betahaus.net", "b@betahaus.net"],
            roles=[ROLE_PARTICIPANT],
        )
        self.assertEqual(1, result.added)
        self.assertEqual(0, result.changed)
        self.assertEqual(1, result.existed)
        self.assertEqual(2, len(result.pks))
        self.assertEqual(
            1, self.meeting.invites.filter(user_data__email="c@betahaus.net").count()
        )

    def test_create_or_update_mixed_duplicate_row_from_import(self):
        """
        A file with group/grouprole columns hands the manager only the user_data
        part of each row, so two rows for the same person in different groups
        arrive as identical dicts.
        """
        result = self.meeting.invites.create_or_update_mixed(
            meeting=self.meeting,
            data=[
                # email,group,grouprole -> alice,board,chair
                {"email": "alice@betahaus.net"},
                # email,group,grouprole -> alice,staff,member
                {"email": "alice@betahaus.net"},
            ],
            roles=[ROLE_PARTICIPANT],
        )
        self.assertEqual(1, result.added)
        self.assertEqual(1, len(result.pks))
        self.assertEqual(
            1,
            self.meeting.invites.filter(user_data__email="alice@betahaus.net").count(),
        )

    def test_should_expire(self):
        self.assertFalse(self.meeting.invites.should_expire())
        self.assertFalse(MeetingInvite.objects.should_expire())
        self.inv1.created = self.inv1.created - timedelta(days=40)
        self.inv1.save()
        self.assertFalse(self.meeting.invites.should_expire())
        self.assertFalse(MeetingInvite.objects.should_expire())
        self.meeting.state = "closed"
        self.meeting.end_time = timezone.now()
        self.meeting.save()
        self.assertFalse(self.meeting.invites.should_expire())
        self.assertFalse(MeetingInvite.objects.should_expire())
        self.meeting.end_time = self.meeting.end_time - timedelta(days=40)
        self.meeting.save()
        self.assertSetEqual({self.inv1}, set(self.meeting.invites.should_expire()))
        self.assertSetEqual({self.inv1}, set(MeetingInvite.objects.should_expire()))


class MeetingInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="someone")
        cls.invite: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            user_data={"email": "a@betahaus.net"},
            roles=[ROLE_PARTICIPANT],
        )

    def test_accept(self):
        self.invite.accept(self.user)
        self.assertEqual(self.user, self.invite.used_by)
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.user))

    def test_constraint(self):
        with self.assertRaises(IntegrityError) as cm:
            self.meeting.invites.create(
                user_data={"email": "a@betahaus.net"},
                roles=[ROLE_PARTICIPANT],
            )
        self.assertIn(
            'duplicate key value violates unique constraint "unique_meeting_invite_user_data"',
            str(cm.exception),
        )

    def test_constraint_only_active_with_data(self):
        self.meeting.invites.create(
            user_data={},
            roles=[ROLE_PARTICIPANT],
        )
        self.meeting.invites.create(
            user_data={},
            roles=[ROLE_PARTICIPANT],
        )
        self.assertEqual(2, self.meeting.invites.filter(user_data={}).count())

    def test_mask_sentive_user_data(self):
        invite = self.meeting.invites.create(
            user_data={
                "shoes": "47",
                "email": "somewhere@betahaus.net",
                "swedish_ssn": "121212-1212",
            }
        )
        log = LogEntry.objects.get_for_object(invite).first()
        self.assertEqual(
            [
                "None",
                '{"email": "*where@*us.net", "shoes": "47", "swedish_ssn": "121212*"}',
            ],
            log.changes_dict["user_data"],
        )
