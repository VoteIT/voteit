from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.dispatch import receiver
from django.test import TestCase

from auditlog.context import set_actor
from auditlog.models import LogEntry
from voteit.core.testing import mk_hashtag
from voteit.meeting.models import Meeting


class UserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.core.models import User

        cls.user = User.objects.create(username="blaha")

    def test_valid_userid_guard(self):
        self.assertFalse(self.user.valid_userid_guard())  # Empty
        self.user.userid = "blaha"
        self.assertTrue(self.user.valid_userid_guard())
        self.user.userid = "äö"
        self.assertFalse(self.user.valid_userid_guard())  # Bad!
        self.user.userid = "ABC"
        self.assertFalse(self.user.valid_userid_guard())  # Bad too!


class RolesTests(TestCase):
    # The roles tests use the MeetingRoles class instead, since it's kind of hard to test abstract db models in django

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation
        from voteit.meeting.roles import ROLE_PARTICIPANT
        from voteit.meeting.roles import ROLE_DISCUSSER
        from voteit.meeting.roles import ROLE_PROPOSER
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
        from voteit.meeting.models import MeetingRoles

        cls.ROLE_PARTICIPANT = ROLE_PARTICIPANT
        cls.ROLE_DISCUSSER = ROLE_DISCUSSER
        cls.ROLE_PROPOSER = ROLE_PROPOSER
        cls.ROLE_MODERATOR = ROLE_MODERATOR
        cls.ROLE_POTENTIAL_VOTER = ROLE_POTENTIAL_VOTER
        cls.MeetingRoles = MeetingRoles
        User = get_user_model()
        org = Organisation.objects.create()
        cls.user = User.objects.create(username="jane", organisation=org)
        cls.meeting = Meeting.objects.create(organisation=org)
        cls.roles = MeetingRoles.objects.create(user=cls.user, context=cls.meeting)

    def test_get_roles(self):
        self.assertIsNone(self.meeting.get_roles(self.user))
        self.roles.add(self.ROLE_PARTICIPANT)
        self.roles.save()
        self.assertEqual({self.ROLE_PARTICIPANT}, self.meeting.get_roles(self.user))

    def test_get_required_roles(self):
        self.assertEqual(
            {self.ROLE_PARTICIPANT, self.ROLE_PROPOSER},
            self.roles.get_required_roles(self.ROLE_PROPOSER),
        )
        self.assertEqual(
            {self.ROLE_PARTICIPANT},
            self.roles.get_required_roles(self.ROLE_PARTICIPANT),
        )
        self.assertEqual(
            {self.ROLE_PARTICIPANT, self.ROLE_DISCUSSER},
            self.roles.get_required_roles(self.ROLE_DISCUSSER),
        )

    def test_get_reverse_required_roles(self):
        self.assertEqual(
            {self.ROLE_PROPOSER},
            self.roles.get_reverse_required_roles(self.ROLE_PROPOSER),
        )
        self.assertEqual(
            {
                self.ROLE_PARTICIPANT,
                self.ROLE_PROPOSER,
                self.ROLE_DISCUSSER,
                self.ROLE_POTENTIAL_VOTER,
                self.ROLE_MODERATOR,
            },
            self.roles.get_reverse_required_roles(self.ROLE_PARTICIPANT),
        )
        self.assertEqual(
            {self.ROLE_DISCUSSER},
            self.roles.get_reverse_required_roles(self.ROLE_DISCUSSER),
        )

    def test_add_role(self):
        self.assertNotIn(self.ROLE_PARTICIPANT, self.roles)
        self.roles.add(self.ROLE_PARTICIPANT)
        self.assertIn(self.ROLE_PARTICIPANT, self.roles)

    def test_remove_role(self):
        self.roles.add(self.ROLE_PARTICIPANT)
        self.assertIn(self.ROLE_PARTICIPANT, self.roles)
        self.roles.remove(self.ROLE_PARTICIPANT)
        self.assertNotIn(self.ROLE_PARTICIPANT, self.roles)

    def test_set_invalid_role(self):
        from voteit.organisation.roles import ROLE_MEETING_CREATOR

        self.assertRaises(AssertionError, self.roles.add, ROLE_MEETING_CREATOR)

    def test_role_requirement_add(self):
        self.roles.add(self.ROLE_PROPOSER)
        self.assertIn(self.ROLE_PARTICIPANT, self.roles)
        self.assertIn(self.ROLE_PROPOSER, self.roles)

    def test_role_requirement_remove(self):
        self.roles.add(self.ROLE_PARTICIPANT, self.ROLE_PROPOSER)
        self.assertIn(self.ROLE_PARTICIPANT, self.roles)
        self.assertIn(self.ROLE_PROPOSER, self.roles)
        # This will cause proposer to be removed too since it doesn't work without participant
        self.roles.remove(self.ROLE_PARTICIPANT)
        self.assertNotIn(self.ROLE_PARTICIPANT, self.roles)
        self.assertNotIn(self.ROLE_PROPOSER, self.roles)

    def test_signal_roles_added(self):
        from voteit.core.signals import roles_added

        L = []

        @receiver(roles_added, sender=self.MeetingRoles)
        def my_listener(roles=(), **kw):
            L.extend(roles)

        self.roles.add(self.ROLE_PROPOSER)
        self.assertIn(self.ROLE_PROPOSER, L)
        self.assertIn(self.ROLE_PARTICIPANT, L)

    def test_signal_roles_removed(self):
        from voteit.core.signals import roles_removed

        L = []
        self.roles.add(self.ROLE_PROPOSER)

        @receiver(roles_removed, sender=self.MeetingRoles)
        def my_listener(roles=(), **kw):
            L.extend(roles)

        self.roles.remove(self.ROLE_PARTICIPANT)
        self.assertIn(self.ROLE_PROPOSER, L)
        self.assertIn(self.ROLE_PARTICIPANT, L)

    def test_roles_object_removed_when_assignment_empty(self):
        self.roles.add(self.ROLE_PARTICIPANT)
        self.roles.remove(self.ROLE_PARTICIPANT)
        # Roles deleted
        self.assertFalse(
            self.MeetingRoles.objects.filter(
                user=self.user, context=self.meeting
            ).exists()
        )

    def test_assign_roles_to_user_within_another_org(self):
        from voteit.organisation.models import Organisation

        new_org = Organisation.objects.create()
        with self.assertRaises(IntegrityError):
            new_org.add_roles(self.user, "org_manager")


class BaseContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Testing abstract model through meeting model
        from voteit.organisation.models import Organisation
        from voteit.meeting.models import Meeting

        org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = Meeting.objects.create(organisation=org)
        cls.user = org.users.create(username="ivan")

    def test_body_isnt_mangled_by_bleach(self):
        text = f"{mk_hashtag('KörVi')}!"
        self.meeting.body = text
        self.meeting.save()
        self.assertIn("class", text)
        self.assertIn("<span", text)
        self.assertIn("KörVi", text)
        self.assertIn("data-index", text)
        self.assertIn("data-index", text)
        self.assertIn("data-value", text)
        self.assertIn("data-id", text)
        self.assertIn("data-denotation-char", text)
        self.assertEqual(len(text), len(self.meeting.body))

    def test_body_with_bad_stuff(self):
        self.meeting.body = "<javascript>is annoying"
        self.meeting.save()
        self.assertEqual("&lt;javascript&gt;is annoying", self.meeting.body)


class AuditLogTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.moderator = User.objects.get(username="moderator")

    def test_get_additional_data(self):
        meeting = Meeting.objects.create()
        m_logs_qs = LogEntry.objects.get_for_object(meeting)
        self.assertEqual(1, m_logs_qs.count())
        first = m_logs_qs.first()
        self.assertEqual({"m": meeting.pk}, first.additional_data)
        ai = meeting.agenda_items.create()
        ai_logs_qs = LogEntry.objects.get_for_object(ai)
        self.assertEqual(1, ai_logs_qs.count())
        first = ai_logs_qs.first()
        self.assertEqual({"m": meeting.pk, "ai": ai.pk}, first.additional_data)
        prop = ai.proposals.create(
            body="Important stuff",
        )
        p_logs_qs = LogEntry.objects.get_for_object(prop)
        self.assertEqual(1, p_logs_qs.count())
        first = p_logs_qs.first()
        self.assertEqual({"ai": ai.pk}, first.additional_data)

    def test_get_additional_data_and_delete(self):
        meeting = Meeting.objects.create()
        ai = meeting.agenda_items.create()
        ai_pk = ai.pk
        prop = ai.proposals.create()
        prop_id = prop.pk
        ai.delete()
        qs = LogEntry.objects.filter(object_id=prop_id)
        log = qs.first()
        self.assertEqual(ai_pk, log.additional_data.get("ai"))


class RolesContextTests(TestCase):
    # The roles tests use the Meeting class instead, since it's kind of hard to test abstract db models in django
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_PARTICIPANT
        from voteit.meeting.roles import ROLE_DISCUSSER
        from voteit.meeting.roles import ROLE_PROPOSER
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

        cls.ROLE_PARTICIPANT = ROLE_PARTICIPANT
        cls.ROLE_DISCUSSER = ROLE_DISCUSSER
        cls.ROLE_PROPOSER = ROLE_PROPOSER
        cls.ROLE_MODERATOR = ROLE_MODERATOR
        cls.ROLE_POTENTIAL_VOTER = ROLE_POTENTIAL_VOTER

        User = get_user_model()

        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        # cls.roles = cls.meeting.roles.filter(user=cls.moderator).get()

    def test_add_roles(self):
        self.assertIsNone(
            self.meeting.add_roles(self.moderator, self.ROLE_MODERATOR),
        )
        self.assertEqual(
            {self.ROLE_PROPOSER},
            self.meeting.add_roles(self.moderator, self.ROLE_PROPOSER),
        )

    def test_remove_roles(self):
        self.assertIsNone(
            self.meeting.remove_roles(self.moderator, self.ROLE_PROPOSER),
        )
        self.assertEqual(
            {self.ROLE_MODERATOR},
            self.meeting.remove_roles(self.moderator, self.ROLE_MODERATOR),
        )

    def test_get_roles(self):
        self.assertEqual(
            {self.ROLE_MODERATOR, self.ROLE_PARTICIPANT},
            self.meeting.get_roles(self.moderator),
        )
        self.meeting.remove_roles(
            self.moderator, self.ROLE_MODERATOR, self.ROLE_PARTICIPANT
        )
        self.assertIsNone(self.meeting.get_roles(self.moderator))

    def test_has_roles(self):
        self.assertTrue(self.meeting.has_roles(self.moderator, self.ROLE_MODERATOR))
        self.assertTrue(
            self.meeting.has_roles(
                self.moderator, self.ROLE_MODERATOR, self.ROLE_PARTICIPANT
            )
        )
        self.assertFalse(
            self.meeting.has_roles(
                self.moderator, self.ROLE_MODERATOR, self.ROLE_PROPOSER
            )
        )

    def test_has_any_roles(self):
        self.assertTrue(self.meeting.has_any_roles(self.moderator, self.ROLE_MODERATOR))
        self.assertTrue(
            self.meeting.has_any_roles(
                self.moderator, self.ROLE_MODERATOR, self.ROLE_PARTICIPANT
            )
        )
        self.assertTrue(
            self.meeting.has_any_roles(
                self.moderator, self.ROLE_MODERATOR, self.ROLE_PROPOSER
            )
        )

    def test_get_userids_with_roles(self):
        self.assertEqual(
            {self.moderator.pk},
            set(self.meeting.get_userids_with_roles(self.ROLE_MODERATOR)),
        )
        self.assertEqual(
            {self.moderator.pk},
            set(
                self.meeting.get_userids_with_roles(
                    self.ROLE_MODERATOR, self.ROLE_PARTICIPANT
                )
            ),
        )
        self.assertEqual(
            set(),
            set(
                self.meeting.get_userids_with_roles(
                    self.ROLE_MODERATOR, self.ROLE_PROPOSER
                )
            ),
        )

    def test_get_userids_with_any_roles(self):
        self.assertEqual(
            {self.moderator.pk},
            set(self.meeting.get_userids_with_any_roles(self.ROLE_MODERATOR)),
        )
        self.assertEqual(
            {self.moderator.pk, self.participant.pk},
            set(
                self.meeting.get_userids_with_any_roles(
                    self.ROLE_MODERATOR, self.ROLE_PARTICIPANT
                )
            ),
        )
        self.assertEqual(
            {self.moderator.pk},
            set(
                self.meeting.get_userids_with_any_roles(
                    self.ROLE_MODERATOR, self.ROLE_PROPOSER
                )
            ),
        )
