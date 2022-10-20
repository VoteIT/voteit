from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.invites.workflows import InviteWf
from voteit.meeting.models import Meeting

User = get_user_model()


class CreateInvitesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @property
    def _fut(self):
        from voteit.invites.utils import create_invites

        return create_invites

    @classmethod
    def setUpTestData(cls):
        data = []
        for name in ["one", "two", "three"]:
            data.append(f"{name}@betahaus.net")
        cls.emails = data
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def test_add(self):
        result = self._fut(
            roles=["participant", "discusser"],
            type="email",
            invite_data=self.emails,
            created_by=self.moderator,
            meeting=self.meeting.pk,
        )
        # added, changed, skipped_count
        self.assertEqual((3, 0, 0), (len(result[0]), len(result[1]), result[2]))
        self.assertEqual(3, self.meeting.invites.count())

    def test_add_modifies_already_existing_invites(self):
        invite = self.meeting.invites.create(
            invite_data="one@betahaus.net",
            type="email",
            roles=["participant"],
            created_by=self.moderator,
        )
        # invite_data = row,
        # created_by = created_by,
        # roles = add_data.roles,
        # last_modified_by = created_by,
        result = self._fut(
            roles=["participant", "discusser"],
            type="email",
            invite_data=self.emails,
            created_by=self.moderator,
            meeting=self.meeting.pk,
        )
        self.assertEqual((2, 1, 0), (len(result[0]), len(result[1]), result[2]))
        invite.refresh_from_db()
        self.assertEqual(["participant", "discusser"], invite.roles)

    def test_add_modifies_permissions_for_used_invites(self):
        invite = self.meeting.invites.create(
            invite_data="one@betahaus.net",
            roles=["participant"],
            created_by=self.moderator,
        )
        invite.accept(self.participant)
        invite.save()
        self.assertEqual(InviteWf.ACCEPTED, invite.state)
        self.assertEqual(self.participant, invite.used_by)
        result = self._fut(
            roles=["participant", "discusser"],
            type="email",
            invite_data=self.emails,
            created_by=self.moderator,
            meeting=self.meeting.pk,
        )
        self.assertEqual((2, 1, 0), (len(result[0]), len(result[1]), result[2]))
        self.assertEqual(
            {"participant", "discusser"}, self.meeting.get_roles(self.participant)
        )

    def test_add_modifies_expired_or_revoked_invites(self):
        invite_exp = self.meeting.invites.create(
            invite_data="one@betahaus.net",
            roles=["participant"],
            created_by=self.moderator,
            state=InviteWf.EXPIRED,
        )
        invite_rev = self.meeting.invites.create(
            invite_data="two@betahaus.net",
            roles=["participant"],
            created_by=self.moderator,
            state=InviteWf.REVOKED,
        )
        result = self._fut(
            roles=["participant", "discusser"],
            type="email",
            invite_data=self.emails,
            created_by=self.moderator,
            meeting=self.meeting.pk,
        )
        self.assertEqual((1, 2, 0), (len(result[0]), len(result[1]), result[2]))
        invite_exp.refresh_from_db()
        invite_rev.refresh_from_db()
        self.assertEqual(InviteWf.OPEN, invite_exp.state)
        self.assertEqual(InviteWf.OPEN, invite_rev.state)
