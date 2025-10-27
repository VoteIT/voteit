from datetime import timedelta

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.invites.models import MeetingInvite
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_PROPOSER
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

    def test_should_expire(self):
        self.assertFalse(self.meeting.invites.should_expire())
        self.assertFalse(MeetingInvite.objects.should_expire())
        self.inv1.created = self.inv1.created - timedelta(days=10)
        self.inv1.save()
        self.assertFalse(self.meeting.invites.should_expire())
        self.assertFalse(MeetingInvite.objects.should_expire())
        self.meeting.ongoing()
        self.meeting.close()
        self.meeting.save()
        self.assertFalse(self.meeting.invites.should_expire())
        self.assertFalse(MeetingInvite.objects.should_expire())
        self.meeting.end_time = self.meeting.end_time - timedelta(days=10)
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
