from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import serializers

from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


User: UserType = get_user_model()


class RolesFieldTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.new_user = User.objects.create(username="new_kid")
        cls.roles = cls.meeting.roles.get(user=cls.moderator)

    @property
    def _cut(self):
        from voteit.core.rest_api.fields import RolesField

        return RolesField

    @property
    def _Serializer(self):
        from voteit.meeting.models import MeetingRoles

        class _Serializer(serializers.ModelSerializer):
            assigned = self._cut()

            class Meta:
                model = MeetingRoles
                fields = ["assigned", "user", "context"]

        return _Serializer

    def test_get(self):
        serializer = self._Serializer(self.roles)
        self.assertEqual(
            {
                "user": self.moderator.pk,
                "context": self.meeting.pk,
                "assigned": [ROLE_MODERATOR, ROLE_PARTICIPANT],
            },
            serializer.data,
        )

    def test_patch(self):
        serializer = self._Serializer(
            self.roles,
            data={"assigned": [ROLE_MODERATOR, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER]},
            partial=True,
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(
            {
                "user": self.moderator.pk,
                "context": self.meeting.pk,
                "assigned": [ROLE_MODERATOR, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER],
            },
            serializer.data,
        )

    def test_patch_bad_role(self):
        serializer = self._Serializer(
            self.roles,
            data={"assigned": ["jeff"]},
            partial=True,
        )
        serializer.is_valid()
        self.assertIn("assigned", serializer.errors)

    def test_create(self):
        serializer = self._Serializer(
            data={
                "user": self.new_user.pk,
                "context": self.meeting.pk,
                "assigned": [ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER],
            },
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(
            {ROLE_POTENTIAL_VOTER, ROLE_PARTICIPANT},
            self.meeting.get_roles(self.new_user),
        )

    def test_create_bad_role(self):
        serializer = self._Serializer(
            data={
                "user": self.new_user.pk,
                "context": self.meeting.pk,
                "assigned": ["Hello"],
            },
        )
        serializer.is_valid()
        self.assertIn("assigned", serializer.errors)


class RoleFieldTests(TestCase):
    # @classmethod
    # def setUpTestData(cls):

    @property
    def _cut(self):
        from voteit.core.rest_api.fields import RoleField

        return RoleField

    @property
    def _Serializer(self):
        class _Serializer(serializers.Serializer):
            role = self._cut(valid_roles={ROLE_PARTICIPANT})

        return _Serializer

    def test_valid(self):
        serializer = self._Serializer(
            data={
                "role": ROLE_PARTICIPANT,
            },
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)

    def test_invalid(self):
        serializer = self._Serializer(
            data={
                "role": ROLE_POTENTIAL_VOTER,
            },
        )
        serializer.is_valid()
        self.assertIn("role", serializer.errors)
