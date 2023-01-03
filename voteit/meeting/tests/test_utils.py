import os

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError

from dolly.utils import get_data_id_struct

from voteit.core.utils import get_model_by_shortname
from voteit.meeting.exceptions import DialectError
from voteit.organisation.models import Organisation
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.utils import clone_meeting
from voteit.meeting.utils import collect_meeting
from voteit.meeting.utils import get_default_models_ignored_on_clone
from voteit.participant_number.models import PNSystem
from voteit.participant_number.models import ParticipantNumber
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerList


User = get_user_model()


class MeetingCloneTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        cls.user = User.objects.get(pk=1)

    def test_collect_without_restrictions(self):
        data = collect_meeting(self.meeting)
        items = get_data_id_struct(data)
        self.assertEqual({1}, items.pop(get_model_by_shortname("organisation")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("organisation_roles")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("oauth2_provider")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("meeting")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("meeting_group")))
        self.assertEqual({1, 2, 3}, items.pop(get_model_by_shortname("agenda_item")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("discussion_post")))
        self.assertEqual({1, 2, 3}, items.pop(get_model_by_shortname("proposal")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("electoral_register")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("text_document")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("text_paragraph")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("diff_proposal")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("poll")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("voter_weight")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("meeting_roles")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("vote")))
        self.assertEqual({1, 2, 3}, items.pop(get_model_by_shortname("user")))
        self.assertFalse(items)

    def test_collect_with_default_ignored(self):
        ignored_types = get_default_models_ignored_on_clone()
        data = collect_meeting(self.meeting, exclude=ignored_types)
        for m in ignored_types:
            self.assertNotIn(m, data)
        expected_names = {
            "meeting",
            "meeting_group",
            "agenda_item",
            "discussion_post",
            "proposal",
            "text_document",
            "diff_proposal",
        }
        for name in expected_names:
            m = get_model_by_shortname(name)
            self.assertIsNotNone(m)
            self.assertIsNotNone(data.pop(m))

    def test_clone_meeting(self):
        counted = {}
        ignored_types = get_default_models_ignored_on_clone()
        data = collect_meeting(self.meeting, exclude=ignored_types)
        for m, values in data.items():
            counted[m] = m.objects.all().count()
        initial_pk = self.meeting.pk
        new_meeting = clone_meeting(self.meeting, user=self.user)
        self.assertNotEqual(new_meeting.pk, initial_pk)
        for m, initial_count in counted.items():
            self.assertEqual(initial_count * 2, m.objects.all().count())
        self.assertEqual("Copy of Testfixture meeting", new_meeting.title)
        self.assertEqual(
            {ROLE_MODERATOR, ROLE_PARTICIPANT}, new_meeting.get_roles(self.user)
        )

    def test_clone_with_active_speakerlist(self):
        sls: SpeakerListSystem = self.meeting.speaker_systems.create(
            method_name="simple"
        )
        slist = sls.speaker_lists.create()
        sls.active_list = slist
        sls.save()
        self.assertEqual(1, SpeakerListSystem.objects.count())
        self.assertEqual(1, SpeakerList.objects.count())
        new_meeting = clone_meeting(self.meeting, user=self.user)
        self.assertEqual(2, SpeakerListSystem.objects.count())
        self.assertEqual(1, new_meeting.speaker_systems.count())
        self.assertEqual(1, SpeakerList.objects.count())

    def test_reset_wf(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        self.assertEqual(1, self.meeting.agenda_items.filter(state="private").count())
        self.assertEqual(2, self.meeting.agenda_items.filter(state="upcoming").count())
        new_meeting = clone_meeting(self.meeting, user=self.user, reset_wf=True)
        self.assertEqual("upcoming", new_meeting.state)
        self.assertEqual(3, new_meeting.agenda_items.filter(state="private").count())
        self.assertEqual(0, new_meeting.agenda_items.filter(state="ongoing").count())

    def test_related_to_ignored(self):
        pns: PNSystem = PNSystem.objects.create(meeting=self.meeting)
        number = pns.numbers.create(user=self.user, number=1)
        self.assertEqual(1, ParticipantNumber.objects.count())
        new_meeting = clone_meeting(self.meeting, user=self.user)
        new_meeting.refresh_from_db()
        with self.assertRaises(PNSystem.DoesNotExist):
            new_meeting.pn_system
        self.assertEqual(1, ParticipantNumber.objects.count())


dialect_named_test = {
    "title": "Test",
    "name": "test",
    "roles": [
        {
            "title": "Supervisor",
            "role_id": "supervisor",
            "roles": ["discusser", "proposer"],
        }
    ],
    "groups": [{"title": "Board", "groupid": "board"}],
    "er_policy_name": "auto_before_poll",
    "group_votes_active": True,
    "group_roles_active": True,
}
dialect_minimal = {"title": "Mini", "name": "mini"}
dialect_minimal_requires_test = {"title": "Req", "name": "req", "requires": ["test"]}

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
DIALECT_FIXTURES = os.path.join(TESTS_DIR, "dialect_fixtures")
BAD_DIALECT_FIXTURES = os.path.join(TESTS_DIR, "bad_dialect_fixtures")
CYCLIC_DIALECT_FIXTURES = os.path.join(TESTS_DIR, "cyclic_dialect_fixtures")


class DialectHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()

    @property
    def _cut(self):
        from voteit.meeting.utils import DialectHandler

        return DialectHandler

    def test_load_with_bad_data(self):
        with self.assertRaises(ValidationError):
            self._cut.load_from_dict({})

    def test_install(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        self.assertEqual("test", self.meeting.installed_dialects)
        self.assertEqual("auto_before_poll", self.meeting.er_policy_name)
        self.assertTrue(self.meeting.group_votes_active)
        self.assertTrue(self.meeting.group_roles_active)
        group_role = self.meeting.group_roles.filter(role_id="supervisor").first()
        self.assertIsNotNone(group_role)
        self.assertEqual("Supervisor", group_role.title)
        group = self.meeting.groups.filter(groupid="board").first()
        self.assertIsNotNone(group)
        self.assertEqual("Board", group.title)

    def test_install_adjusts_groups_and_roles(self):
        group_role = self.meeting.group_roles.create(
            title="Jeff", role_id="supervisor", roles=["discusser"]
        )
        group = self.meeting.groups.create(title="Jane", groupid="board")
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        group_role.refresh_from_db()
        group.refresh_from_db()
        self.assertEqual("Supervisor", group_role.title)
        self.assertEqual(["discusser", "proposer"], group_role.roles)
        self.assertEqual("Board", group.title)

    def test_remove(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        self.assertEqual("test", self.meeting.installed_dialects)
        handler.remove(self.meeting)
        self.assertIsNone(self.meeting.installed_dialects)
        self.assertIsNone(self.meeting.group_roles.filter(role_id="supervisor").first())
        self.assertIsNone(self.meeting.groups.filter(groupid="board").first())
        self.assertIsNone(self.meeting.er_policy_name)
        self.assertFalse(self.meeting.group_votes_active)
        self.assertFalse(self.meeting.group_roles_active)

    def test_duplicate_install(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        self.meeting.installed_dialects = handler.data.name
        with self.assertRaises(DialectError):
            handler.install(self.meeting)

    def test_remove_with_none_installed(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        with self.assertRaises(DialectError):
            handler.remove(self.meeting)

    def test_install_requires_other(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        handler_req = self._cut.load_from_dict(dialect_minimal_requires_test)
        handler_req.install(self.meeting)
        self.assertEqual("test,req", self.meeting.installed_dialects)

    def test_install_missing_required(self):
        handler = self._cut.load_from_dict(dialect_minimal_requires_test)
        with self.assertRaises(DialectError):
            handler.install(self.meeting)

    def test_uninstall_leaves_untouched_settings_intact(self):
        self.meeting.group_votes_active = True
        self.meeting.group_roles_active = True
        self.meeting.proposal_id_policy_name = "auto_before_poll"
        self.meeting.save()
        handler = self._cut.load_from_dict(dialect_minimal)
        handler.install(self.meeting)
        handler.remove(self.meeting)
        self.assertTrue(self.meeting.group_votes_active)
        self.assertTrue(self.meeting.group_roles_active)
        self.assertEqual("auto_before_poll", self.meeting.proposal_id_policy_name)

    # @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    # def test_check(self):
    #     self.assertTrue(self._cut.check_files())
    #
    # @override_settings(MEETING_DIALECTS_DIR=BAD_DIALECT_FIXTURES)
    # def test_check_bad_files(self):
    #     with self.assertLogs("voteit.meeting.utils", "ERROR") as cm:
    #         self._cut.check_files()
    #     self.assertTrue(
    #         any(
    #             ["broken.yaml returned data that wasn't a dict" in x for x in cm.output]
    #         )
    #     )
    #     self.assertTrue(
    #         any(["bad_values.yaml caused suppressed exception" in x for x in cm.output])
    #     )
    #     self.assertTrue(
    #         any(
    #             [
    #                 "Dialect bad_req specifies a requirement to 'oh_no' but it doesn't exist."
    #                 in x
    #                 for x in cm.output
    #             ]
    #         )
    #     )


class RecursiveLoadHandlersTests(TestCase):
    @property
    def _fut(self):
        from voteit.meeting.utils import recursive_load_handlers

        return recursive_load_handlers

    @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    def test_recursive(self):
        result = self._fut("three")
        self.assertEqual(["one", "two", "three"], [x.data.name for x in result])

    @override_settings(MEETING_DIALECTS_DIR=BAD_DIALECT_FIXTURES)
    def test_recursive_bad_req(self):
        with self.assertRaises(DialectError):
            self._fut("bad_req")

    @override_settings(MEETING_DIALECTS_DIR=CYCLIC_DIALECT_FIXTURES)
    def test_recursive_cyclic(self):
        with self.assertRaises(DialectError):
            self._fut("one")
