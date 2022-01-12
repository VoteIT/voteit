from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import BaseModel
from typing import Dict
from voteit.meeting.models import Meeting

User = get_user_model()


# class MeetingInviteManagerTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.invites.models import MeetingInvite
#         from voteit.invites.registries import invite_data
#
#         @invite_data
#         class DummySchema(BaseModel):
#             dummy: int
#
#         cls.MeetingInvite = MeetingInvite
#         cls.manager = MeetingInvite.objects
#         cls.meeting = Meeting.objects.create()
#         cls.user = User.objects.create(username="someone")
#
#         cls.inv1 = MeetingInvite.objects.create(
#             meeting=cls.meeting,
#             created_by=cls.user,
#             invite_data={"email": "a@betahaus.net", "dummy": 1},
#         )
#         cls.inv2 = MeetingInvite.objects.create(
#             meeting=cls.meeting,
#             created_by=cls.user,
#             invite_data={"email": "b@betahaus.net"},
#         )
#
#     @classmethod
#     def tearDownClass(cls):
#         from voteit.invites.registries import invite_data
#
#         del invite_data["dummy"]
#         super().tearDownClass()
#
#     def test_query_email(self):
#         self.assertEqual(
#             {self.inv1}, set(self.manager.find_invites(email="a@betahaus.net"))
#         )
#         self.assertEqual(
#             set(), set(self.manager.find_invites(email="None@betahaus.net"))
#         )
#
#     def test_bad_query(self):
#         self.assertEqual(set(), set(self.manager.find_invites()))
#         self.assertEqual(set(), set(self.manager.find_invites(hello="world")))
#         self.assertEqual(
#             set(), set(self.manager.find_invites(email=None))
#         )  # None is always skipped
#
#     def test_multiple_emails(self):
#         self.assertEqual(
#             {self.inv1}, set(self.manager.find_invites(email={"a@betahaus.net"}))
#         )
#         self.assertEqual(
#             {self.inv1, self.inv2},
#             set(self.manager.find_invites(email={"a@betahaus.net", "b@betahaus.net"})),
#         )
#         self.assertEqual(
#             {self.inv1, self.inv2},
#             set(self.manager.find_invites(email=["a@betahaus.net", "b@betahaus.net"])),
#         )
#         self.assertEqual(
#             set(),
#             set(self.manager.find_invites(email=[])),
#         )
#
#     def test_multiple_queries(self):
#         self.assertEqual(
#             {self.inv1, self.inv2},
#             set(self.manager.find_invites(email=["b@betahaus.net"], dummy=1)),
#         )
#
#     def test_bad_query_type(self):
#         self.assertRaises(ValueError, self.manager.find_invites, email=123)
#         self.assertRaises(ValueError, self.manager.find_invites, dummy="abc")


class MeetingInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.invites.models import MeetingInvite

        cls.meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="someone")

        cls.invite: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            created_by=cls.user,
            invite_data="a@betahaus.net",
            roles=["participant"],
        )

    def test_accept(self):
        self.invite.accept(self.user)
        self.assertEqual(self.user, self.invite.used_by)
        self.assertEqual({"participant"}, self.meeting.get_roles(self.user))
