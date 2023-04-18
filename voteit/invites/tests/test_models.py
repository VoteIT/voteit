from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.invites.models import MeetingInvite
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.organisation.models import Organisation

User = get_user_model()


class MeetingInviteManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.manager = MeetingInvite.objects
        cls.meeting: Meeting = cls.org.meetings.create()
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
        self.assertEqual((1, 1, 1), result)

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
        self.assertEqual((1, 2, 0), result)
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER}, self.meeting.get_roles(self.user)
        )

    def test_find_multi_user_data_exact(self):
        exact, bogus = self.meeting.invites.find_multi_user_data(
            {"email": "a@betahaus.net", "swedish_ssn": "121212-1212"}
        )
        self.assertEqual({self.inv1}, set(exact))
        self.assertEqual({}, bogus)

    def test_find_multi_user_data_problematic_clash(self):
        exact, bogus = self.meeting.invites.find_multi_user_data(
            {"email": "a@betahaus.net", "swedish_ssn": "abc-404"}
        )
        self.assertEqual(set(), set(exact))
        self.assertEqual({self.inv1}, set(bogus.get("email", [])))

    def test_find_multi_user_data_has_more_data_we_dont_query(self):
        exact, bogus = self.meeting.invites.find_multi_user_data(
            {"email": "a@betahaus.net"}
        )
        self.assertEqual({self.inv1}, set(exact))
        self.assertEqual({}, bogus)

    def test_find_multi_user_data_odd_intersection(self):
        # Note: This should never be saved in the database
        self.inv2.user_data["swedish_ssn"] = "121212-1212"
        self.inv2.save()
        exact, bogus = self.meeting.invites.find_multi_user_data(
            {"email": "a@betahaus.net", "swedish_ssn": "121212-1212"},
            {"email": "b@betahaus.net", "swedish_ssn": "121212-1212"},
        )
        self.assertEqual({self.inv1, self.inv2}, set(exact))
        self.assertEqual({}, bogus)

    def test_test_find_multi_user_data_meeting_filter_not_applied(self):
        with self.assertRaises(IntegrityError) as cm:
            MeetingInvite.objects.find_multi_user_data({"email": "jeff@barnes.com"})
        self.assertEqual("Queryset doesn't contain meeting filter", str(cm.exception))


class MeetingInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="someone")
        cls.invite: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            user_data={"email": "a@betahaus.net"},
            roles=["participant"],
        )

    def test_accept(self):
        self.invite.accept(self.user)
        self.assertEqual(self.user, self.invite.used_by)
        self.assertEqual({"participant"}, self.meeting.get_roles(self.user))
