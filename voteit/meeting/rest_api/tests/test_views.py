from http import HTTPStatus
from json import loads
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import override_settings
from pythonjsonlogger.jsonlogger import JsonFormatter
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.active.components import ActiveUsersComponent
from voteit.agenda.models import AgendaItem
from voteit.components.app.components.dialects import DialectsFilter
from voteit.components.app.components.proposal_print import ProposalPrint
from voteit.core.testing import run_permission_tests
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.dialects import DialectHandler
from voteit.meeting.dialects import get_named_paths
from voteit.meeting.messages import MeetingDialectChanged
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.signals import group_role_added
from voteit.meeting.signals import group_role_removed
from voteit.meeting.tests.fixtures import DIALECT_FIXTURES
from voteit.notes.components import NotesComponent
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.registries import er_policy
from voteit.poll.registries import vote_transfer_policies
from voteit.poll.testing import UnrestrictedVoteTransferER
from voteit.poll.testing import UnrestrictedVoteTransferPolicy
from voteit.speaker.app.list_methods.simple import Simple
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()

_json_formatter = JsonFormatter()


def _record_to_dict(record):
    return loads(_json_formatter.format(record))


@override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
@patch.dict(
    vote_transfer_policies,
    {UnrestrictedVoteTransferPolicy.name: UnrestrictedVoteTransferPolicy},
)
@patch.dict(
    er_policy,
    {UnrestrictedVoteTransferER.name: UnrestrictedVoteTransferER},
)
class MeetingViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.get(pk=1)
        cls.org.components.create(
            component_name=DialectsFilter.name,
            settings={
                "include": ["unrestricted_vote_transfer"],
            },
        )
        cls.meeting = cls.org.meetings.get(pk=1)
        cls.meeting.components.create(component_name=ProposalPrint.name, enabled=True)
        cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        cls.meeting.components.create(component_name=NotesComponent.name, enabled=True)
        cls.participant = User.objects.get(username="participant")
        cls.org_manager = User.objects.get(username="org_manager")
        cls.moderator = User.objects.get(username="moderator")

    def test_create(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world"}
        for user, status in (
            (None, 401),
            (self.org_manager, 201),
            (self.participant, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_meeting_org_fetched_from_user(self):
        url = reverse("meeting-list")
        data = {
            "title": "Stuff",
            "organisation": -1,
        }
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertEqual(meeting.organisation.pk, 1)

    def test_create_creator_becomes_moderator(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world"}
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertTrue(meeting.has_roles(self.org_manager, ROLE_MODERATOR))

    def test_create_public_ignored_but_visible_in_lists_works(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world", "visible_in_lists": True, "public": True}
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertTrue(meeting.visible_in_lists)
        self.assertFalse(meeting.public)

    def test_create_with_sls_and_no_room(self):
        url = reverse("meeting-list")
        data = {
            "title": "Stuff",
            "sls": {"method_name": Simple.name},
        }
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data=data)
        self.assertEqual(
            {"sls": ["Specifying sls without room isn't allowed."]}, response.json()
        )
        self.assertEqual(response.status_code, 400)

    def test_create_with_sls(self):
        url = reverse("meeting-list")
        data = {
            "title": "Stuff",
            "room": {"title": "Hello"},
            "sls": {"method_name": Simple.name},
        }
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data=data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        sls = meeting.speaker_systems.all().first()
        self.assertIsInstance(sls, SpeakerListSystem)
        self.assertEqual(Simple.name, sls.method_name)

    def test_create_with_dialect(self):
        url = reverse("meeting-list")
        data = {"title": "Stuff", "install_dialect": "main_subst"}
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data=data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertEqual("main_subst", meeting.installed_dialect)

    def test_create_with_er_policy(self):
        url = reverse("meeting-list")
        data = {"title": "Stuff", "er_policy_name": AutoAlways.name}
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data=data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertEqual(AutoAlways.name, meeting.er_policy_name)

    def test_create_with_dialect_and_vote_transfer(self):
        url = reverse("meeting-list")
        data = {"title": "Stuff", "install_dialect": "unrestricted_vote_transfer"}
        self.client.force_login(self.org_manager)
        response = self.client.post(url, data=data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertEqual("unrestricted_vote_transfer", meeting.installed_dialect)
        self.assertIsInstance(
            meeting.vote_transfer_policy, UnrestrictedVoteTransferPolicy
        )

    def test_list(self):
        url = reverse("meeting-list")
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_list_n1(self):
        self.org.meetings.create(er_policy_name=AutoAlways.name, public=True)
        url = reverse("meeting-list")
        self.client.force_login(self.participant)
        with self.assertNumQueries(4):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(2, len(response.json()))

    def test_get(self):
        url = reverse("meeting-detail", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                "pk": self.meeting.pk,
                "body": "I wish a was a text about this meeting",
                "current_user_roles": ["pa"],
                "dialect": None,
                "end_time": None,
                "er_policy_name": "auto_before_poll",
                "group_roles_active": False,
                "group_votes_active": False,
                "installed_dialect": None,
                "organisation": 1,
                "public": False,
                "start_time": None,
                "state": "upcoming",
                "title": "Testfixture meeting",
                "visible_in_lists": False,
                "vote_transfer_policy": None,
            },
            response.json(),
        )

    def test_get_n1(self):
        url = reverse("meeting-detail", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        with self.assertNumQueries(4):  # Way too high!
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_visible_in_lists(self):
        url = reverse("meeting-detail", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        # Check that user can't view details if not participant and not visible in lists
        self.meeting.participants.remove(self.participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        # Check that user can view details if not participant, but visible in lists
        self.meeting.visible_in_lists = True
        self.meeting.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_get_with_vt(self):
        self.meeting.er_policy_name = UnrestrictedVoteTransferER.name
        self.meeting.save()
        url = reverse("meeting-detail", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            UnrestrictedVoteTransferPolicy.name,
            response.json()["vote_transfer_policy"],
        )

    def test_transition_moderator(self):
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        data = {"transition": "ongoing"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_bad_transition_moderator(self):
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        data = {"transition": "wooohoooo"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        data = {"transition": "ongoing"}
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            401,
        )
        self.client.force_login(self.participant)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_delete(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_delete_participant(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        self.client.force_login(self.participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_archived(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse("meeting-detail", kwargs={"pk": 1})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_change(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, {"title": "A brave new title"})
        self.assertEqual(response.status_code, 200)
        self.meeting.refresh_from_db()
        self.assertEqual("A brave new title", self.meeting.title)

    def test_er_policy_with_locked_dialect(self):
        path = None
        for name, path in get_named_paths():
            if name == "unrestricted_vote_transfer":
                break
        if not path:
            self.fail("Could not find dialect 'unrestricted_vote_transfer'")
        handler = DialectHandler.load_from_file("unrestricted_vote_transfer", path)
        handler.install(self.meeting)
        self.client.force_login(self.moderator)
        url = reverse("meeting-detail", kwargs={"pk": 1})
        response = self.client.patch(url, {"er_policy_name": AutoAlways.name})
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual(
            {"er_policy_name": ["Meeting dialect locks electoral register policy"]},
            data,
        )

    def test_change_archived(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse("meeting-detail", kwargs={"pk": 1})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, {"title": "Not allowed"})
        self.assertEqual(response.status_code, 403)

    def test_change_agenda_order(self):
        url = reverse("meeting-set-agenda-order", kwargs={"pk": 1})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"order": [3, 1, 2]})
        self.assertEqual(201, response.status_code)
        one = AgendaItem.objects.get(pk=1)
        two = AgendaItem.objects.get(pk=2)
        three = AgendaItem.objects.get(pk=3)
        self.assertEqual(2, one.order)
        self.assertEqual(3, two.order)
        self.assertEqual(1, three.order)

    def test_install_dialect(self):
        url = reverse("meeting-install-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"dialect": "main_subst"})
        self.assertEqual(200, response.status_code)
        self.meeting.refresh_from_db()
        self.assertEqual("main_subst", self.meeting.installed_dialect)

    @patch.object(MeetingChannel, "sync_publish")
    def test_install_dialect_sends_notification(self, mock_publish):
        url = reverse("meeting-install-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        self.client.post(url, {"dialect": "main_subst"})
        published_types = [type(c.args[0]) for c in mock_publish.mock_calls]
        self.assertIn(MeetingDialectChanged, published_types)
        msg = next(
            c.args[0]
            for c in mock_publish.mock_calls
            if isinstance(c.args[0], MeetingDialectChanged)
        )
        self.assertEqual(self.meeting.pk, msg.data.pk)

    def test_install_dialect_already_installed(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(
            installed_dialect="main_subst"
        )
        url = reverse("meeting-install-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"dialect": "main_subst"})
        self.assertEqual(400, response.status_code)

    def test_install_dialect_invalid_name(self):
        url = reverse("meeting-install-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"dialect": "does_not_exist"})
        self.assertEqual(400, response.status_code)

    def test_install_dialect_forbidden_for_participant(self):
        url = reverse("meeting-install-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, {"dialect": "main_subst"})
        self.assertEqual(403, response.status_code)

    def test_install_dialect_forbidden_when_not_upcoming(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(state="ongoing")
        url = reverse("meeting-install-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"dialect": "main_subst"})
        self.assertEqual(403, response.status_code)

    def test_remove_dialect(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(
            installed_dialect="main_subst"
        )
        url = reverse("meeting-remove-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {})
        self.assertEqual(200, response.status_code)
        self.meeting.refresh_from_db()
        self.assertIsNone(self.meeting.installed_dialect)

    @patch.object(MeetingChannel, "sync_publish")
    def test_remove_dialect_sends_notification(self, mock_publish):
        Meeting.objects.filter(pk=self.meeting.pk).update(
            installed_dialect="main_subst"
        )
        url = reverse("meeting-remove-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        self.client.post(url, {})
        published_types = [type(c.args[0]) for c in mock_publish.mock_calls]
        self.assertIn(MeetingDialectChanged, published_types)
        msg = next(
            c.args[0]
            for c in mock_publish.mock_calls
            if isinstance(c.args[0], MeetingDialectChanged)
        )
        self.assertEqual(self.meeting.pk, msg.data.pk)

    def test_remove_dialect_none_installed(self):
        url = reverse("meeting-remove-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {})
        self.assertEqual(400, response.status_code)

    def test_remove_dialect_forbidden_for_participant(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(
            installed_dialect="main_subst"
        )
        url = reverse("meeting-remove-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, {})
        self.assertEqual(403, response.status_code)

    def test_remove_dialect_forbidden_when_not_upcoming(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(
            state="ongoing", installed_dialect="main_subst"
        )
        url = reverse("meeting-remove-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {})
        self.assertEqual(403, response.status_code)

    def test_remove_dialect_with_groups_flag(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(
            installed_dialect="main_subst"
        )
        url = reverse("meeting-remove-dialect", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"groups": True})
        self.assertEqual(200, response.status_code)
        self.meeting.refresh_from_db()
        self.assertIsNone(self.meeting.installed_dialect)


class MeetingGroupViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.anon = User.objects.create(username="anon")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting_group: MeetingGroup = MeetingGroup.objects.create(
            meeting=cls.meeting, title="one"
        )
        cls.meeting_group_two: MeetingGroup = MeetingGroup.objects.create(
            meeting=cls.meeting, title="two"
        )

    def test_create(self):
        url = reverse("meeting-groups-list")
        data = {"title": "Hello world", "meeting": self.meeting.pk}
        for func, args in run_permission_tests(
            self,
            url=url,
            data=data,
            expected=[
                (self.moderator, 201, data),
                (self.anon, 403),
                (self.participant, 403, {}),
            ],
            method="post",
        ):
            func(*args)

    def test_create_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        data = {"title": "Hello world", "meeting": self.meeting.pk}
        url = reverse("meeting-groups-list")
        response = self.client.post(url, data)
        self.assertEqual(403, response.status_code)

    def test_create_no_meeting(self):
        self.client.force_login(self.moderator)
        data = {"title": "Hello world"}
        url = reverse("meeting-groups-list")
        response = self.client.post(url, data)
        self.assertEqual(400, response.status_code)

    def test_get(self):
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            expected=[
                (self.moderator, 200, {"pk": self.meeting_group.pk}),
                (self.anon, 404),
                (self.participant, 200),
            ],
        ):
            func(*args)

    def test_list(self):
        url = reverse("meeting-groups-list")
        data = {"meeting": self.meeting.pk}
        for func, params in run_permission_tests(
            self,
            url=url,
            data=data,
            expected=[
                (self.moderator, 200, []),
                (self.anon, 200, []),
                (self.participant, 200, []),
            ],
        ):
            func(*params)

    def test_change(self):
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        data = {"title": "Hello"}
        for func, params in run_permission_tests(
            self,
            url=url,
            method="patch",
            data=data,
            expected=[
                (self.moderator, 200, {"title": "Hello"}),
                (self.anon, 404),
                (self.participant, 403),
            ],
        ):
            func(*params)

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(url, data={"title": "Hello"})
        self.assertEqual(403, response.status_code)

    def test_delete(self):
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        for func, params in run_permission_tests(
            self,
            url=url,
            method="delete",
            expected=[
                (self.moderator, 204),
                (self.anon, 404),
                (self.participant, 403),
            ],
        ):
            func(*params)

    def test_delete_with_related_proposal(self):
        self.meeting_group.proposals.create()
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.delete(url)
        self.assertContains(
            response, "Meeting group is author of proposals", status_code=403
        )

    def test_delete_with_relation_to_other_group(self):
        self.meeting.groups.create(delegate_to=self.meeting_group)
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.delete(url)
        self.assertContains(
            response, "has a relation to another group", status_code=403
        )

    def test_delete_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.delete(url)
        self.assertEqual(403, response.status_code)

    def test_delegate_to(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(
            url, data={"delegate_to": self.meeting_group_two.pk}
        )
        self.assertEqual(200, response.status_code)
        self.meeting_group.refresh_from_db()
        self.assertEqual(self.meeting_group.delegate_to_id, self.meeting_group_two.pk)
        # And set null
        response = self.client.patch(url, data={"delegate_to": None})
        self.assertEqual(200, response.status_code)
        self.meeting_group.refresh_from_db()
        self.assertIsNone(self.meeting_group.delegate_to)

    def test_delegate_to_self(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(url, data={"delegate_to": self.meeting_group.pk})
        self.assertContains(response, "Delegate to yourself", status_code=400)

    def test_delegate_to_group_with_delegation(self):
        self.meeting_group_two.delegate_to = self.meeting_group
        self.meeting_group_two.save()
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(
            url, data={"delegate_to": self.meeting_group_two.pk}
        )
        self.assertContains(
            response, "Already delegates to another group", status_code=400
        )

    def test_delegate_from_group_with_delegation(self):
        self.meeting.groups.create(title="new", delegate_to=self.meeting_group)
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(
            url, data={"delegate_to": self.meeting_group_two.pk}
        )
        self.assertContains(
            response, "Other groups delegates to your group", status_code=400
        )


class BulkCreateMeetingGroupsTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.anon = User.objects.create(username="anon")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.existing_group: MeetingGroup = cls.meeting.groups.create(
            title="A", groupid="a"
        )

    def _url(self):
        return reverse("meeting-groups-bulk-create")

    def test_bulk_create(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {
                "meeting": self.meeting.pk,
                "groups": [
                    {"title": "B", "groupid": "B"},  # new, groupid lowercased
                    {"title": "Aha", "groupid": "a", "votes": 1},  # updates existing
                ],
            },
            format="json",
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"created": 1, "updated": 1}, response.json())
        self.assertEqual(
            [
                {"groupid": "a", "title": "Aha", "votes": 1},
                {"groupid": "b", "title": "B", "votes": None},
            ],
            list(
                self.meeting.groups.all()
                .order_by("pk")
                .values("title", "groupid", "votes")
            ),
        )

    def test_bulk_create_tsv(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {"meeting": self.meeting.pk, "groups": "B\tB\nAha\ta\t1"},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"created": 1, "updated": 1}, response.json())

    def test_bulk_create_participant(self):
        self.client.force_login(self.participant)
        response = self.client.post(
            self._url(),
            {"meeting": self.meeting.pk, "groups": [{"title": "B", "groupid": "b"}]},
            format="json",
        )
        self.assertEqual(
            400, response.status_code
        )  # meeting field rejects non-moderators

    def test_bulk_create_anon(self):
        response = self.client.post(
            self._url(),
            {"meeting": self.meeting.pk, "groups": [{"title": "B", "groupid": "b"}]},
            format="json",
        )
        self.assertEqual(401, response.status_code)

    def test_bulk_create_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {"meeting": self.meeting.pk, "groups": [{"title": "B", "groupid": "b"}]},
            format="json",
        )
        self.assertEqual(400, response.status_code)

    def test_bulk_create_duplicate_groupid(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {
                "meeting": self.meeting.pk,
                "groups": [
                    {"title": "a", "groupid": "a"},
                    {"title": "B", "groupid": "A"},  # lowercased becomes "a"
                ],
            },
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("Duplicate groupids", str(response.json()))

    def test_bulk_create_duplicate_title(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {
                "meeting": self.meeting.pk,
                "groups": [
                    {"title": "a", "groupid": "a"},
                    {"title": "A", "groupid": "b"},  # same title, case-insensitive
                ],
            },
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("Duplicate titles", str(response.json()))


class GroupMembershipViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.anon = User.objects.create(username="anon")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.group_roles_active = True
        cls.meeting.save()
        cls.meeting_group: MeetingGroup = MeetingGroup.objects.create(
            meeting=cls.meeting
        )
        cls.role = cls.meeting.group_roles.create(
            title="Wizard", role_id="wiz", roles=[ROLE_POTENTIAL_VOTER]
        )
        cls.membership: GroupMembership = cls.meeting_group.memberships.create(
            user=cls.moderator, role=cls.role
        )

    def test_create(self):
        url = reverse("group-memberships-list")
        data = {"user": self.participant.pk, "meeting_group": self.meeting_group.pk}
        for func, params in run_permission_tests(
            self,
            url=url,
            data=data,
            method="POST",
            expected=[(None, 401), (self.moderator, 201), (self.participant, 403)],
        ):
            func(*params)

    def test_get(self):
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        for func, params in run_permission_tests(
            self,
            url=url,
            expected=[
                (None, 401),
                (self.moderator, 200),
                (self.participant, 200),
                (self.anon, 404),
            ],
        ):
            func(*params)

    def test_list(self):
        url = reverse("group-memberships-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        # Always empty
        self.assertEqual([], response.json())

    def test_change(self):
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        for func, params in run_permission_tests(
            self,
            url=url,
            method="PATCH",
            data={"role": None},
            expected=[
                (None, 401),
                (self.moderator, 200, {"role": None}),
                (self.participant, 403),
                (self.anon, 404),
            ],
        ):
            func(*params)

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        for func, params in run_permission_tests(
            self,
            url=url,
            method="PATCH",
            data={"role": None},
            expected=[
                (None, 401),
                (self.moderator, 403, {}),
                (self.participant, 403),
                (self.anon, 404),
            ],
        ):
            func(*params)

    def test_delete(self):
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        for func, params in run_permission_tests(
            self,
            url=url,
            method="DELETE",
            expected=[
                (None, 401),
                (self.moderator, 204, {}),
                (self.participant, 403),
                (self.anon, 404),
            ],
        ):
            func(*params)

    def test_delete_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        response = self.client.delete(url)
        self.assertEqual(403, response.status_code)

    def test_create_with_roles_disabled(self):
        self.membership.delete()
        self.meeting.group_roles_active = False
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("group-memberships-list")
        self.client.force_login(self.moderator)
        response = self.client.post(
            url,
            data={
                "role": self.role.pk,
                "user": self.moderator.pk,
                "meeting_group": self.meeting_group.pk,
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("role", response.json())

    def test_create_delegates_to_signal(self):
        self.membership.delete()
        L = []

        @receiver(group_role_added, sender=GroupMembership)
        def listener(instance, role, **kwargs):
            L.append(role)

        self.client.force_login(self.moderator)
        url = reverse("group-memberships-list")
        self.client.force_login(self.moderator)
        response = self.client.post(
            url,
            data={
                "role": self.role.pk,
                "user": self.moderator.pk,
                "meeting_group": self.meeting_group.pk,
            },
        )
        self.assertEqual(201, response.status_code)
        self.assertEqual([self.role], L)

    def test_patch_remove_role_delegates_to_signal(self):
        L = []

        @receiver(group_role_removed, sender=GroupMembership)
        def listener(instance, role, **kwargs):
            L.append(role)

        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"role": ""})
        self.assertEqual(200, response.status_code)
        self.assertEqual([self.role], L)

    def test_patch_add_role_delegates_to_signal(self):
        self.membership.role = None
        self.membership.save()
        L = []

        @receiver(group_role_added, sender=GroupMembership)
        def listener(instance, role, **kwargs):
            L.append(role)

        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"role": self.role.pk})
        self.assertEqual(200, response.status_code)
        self.assertEqual([self.role], L)

    def test_patch_same_role_sends_no_signal(self):
        L = []

        @receiver(group_role_added, sender=GroupMembership)
        def listener(instance, role, **kwargs):
            L.append(role)

        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"role": self.role.pk})
        self.assertEqual(200, response.status_code)
        self.assertEqual([], L)

    def test_patch_add_role_with_meeting_roles_disabled(self):
        self.membership.role = None
        self.membership.save()
        self.meeting.group_roles_active = False
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"role": self.role.pk})
        self.assertEqual(400, response.status_code)
        self.assertIn("role", response.json())

    def test_delete_delegates_to_signal(self):
        L = []

        @receiver(group_role_removed, sender=GroupMembership)
        def listener(instance, role, **kwargs):
            L.append(role)

        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)
        self.assertEqual([self.role], L)


class MeetingRolesViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.org_manager = User.objects.get(username="org_manager")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.user_jeff = cls.meeting.participants.create(
            username="jeff", userid="key", first_name="Jeff", last_name="Jefferson"
        )
        cls.meeting.add_roles(cls.user_jeff, ROLE_PARTICIPANT)
        cls.other_meeting = Meeting.objects.create()
        cls.other_meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.other_meeting.add_roles(cls.participant, ROLE_PARTICIPANT)

    def test_org_manager_without_meeting(self):
        self.client.force_login(self.org_manager)
        url = reverse("meeting-roles-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_org_manager_with_meeting(self):
        self.client.force_login(self.org_manager)
        url = reverse("meeting-roles-list")
        response = self.client.get(url, {"meeting": self.meeting.pk})
        data = response.json()
        self.assertEqual(200, response.status_code, data)
        self.assertEqual([], data)

    def test_with_filter_participant(self):
        self.client.force_login(self.participant)
        url = reverse("meeting-roles-list")
        response = self.client.get(
            url,
            {
                "context": self.meeting.pk,
                "user_id_in": f"{self.participant.pk},{self.user_jeff.pk}",
            },
        )
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, len(data))
        self.assertEqual(
            {self.participant.pk, self.user_jeff.pk},
            {x["user"]["pk"] for x in data},
        )

    def test_participant_with_temp_context(self):
        self.client.force_login(self.participant)
        url = reverse("meeting-roles-list")
        response = self.client.get(url, {"context": self.meeting.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(
            {self.participant.pk, self.user_jeff.pk, self.moderator.pk},
            {x["user"]["pk"] for x in data},
        )

    def test_same_org_but_another_meeting(self):
        self.client.force_login(self.user_jeff)
        url = reverse("meeting-roles-list")
        response = self.client.get(url, {"meeting": self.other_meeting.pk})
        data = response.json()
        self.assertEqual(200, response.status_code, data)
        self.assertEqual([], data)

    @property
    def roles_url(self):
        return reverse("meeting-roles-list")

    def test_participant_name_search(self):
        self.client.force_login(self.participant)
        response = self.client.get(
            self.roles_url,
            {
                "context": self.meeting.pk,
                "search": "Jeff",
            },
        )
        self.assertContains(response, "Jeff")
        self.assertEqual(len(response.json()), 1)

    def test_participant_userid_search(self):
        self.client.force_login(self.participant)
        response = self.client.get(
            self.roles_url, {"context": self.meeting.pk, "search": "k"}
        )
        self.assertContains(response, "Jeff")
        self.assertEqual(len(response.json()), 1)


class MeetingRolesChangeTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    add_url = reverse("meeting-roles-add-roles")
    remove_url = reverse("meeting-roles-remove-roles")

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.org_manager = User.objects.get(username="org_manager")

    def _add_payload(self, user=None, roles=None):
        return {
            "meeting": self.meeting.pk,
            "user": (user or self.participant).pk,
            "roles": [str(x) for x in (roles or [ROLE_DISCUSSER])],
        }

    def test_add_unauthorized(self):
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_add_participant_forbidden(self):
        self.client.force_login(self.participant)
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.FORBIDDEN, response.status_code)

    def test_add_moderator(self):
        self.client.force_login(self.moderator)
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertIn(str(ROLE_DISCUSSER), response.json()["assigned"])

    def test_add_org_manager(self):
        self.client.force_login(self.org_manager)
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertIn(str(ROLE_DISCUSSER), response.json()["assigned"])

    def test_add_nonexistent_user(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.add_url,
            {**self._add_payload(), "user": -1},
            format="json",
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_add_logs_change(self):
        self.client.force_login(self.moderator)
        with self.assertLogs("voteit.event.roles") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.add_url, self._add_payload(), format="json")
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = _record_to_dict(logs.records[0])
        data.pop("taskName", None)
        self.assertEqual(
            {
                "message": "Added",
                "context_name": "meeting",
                "context": self.meeting.pk,
                "org": self.meeting.organisation_id,
                "meeting": self.meeting.pk,
                "actor": self.moderator.pk,
                "for_user": self.participant.pk,
                "roles": [str(ROLE_DISCUSSER)],
            },
            data,
        )

    def test_add_bad_role(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.add_url, self._add_payload(roles=["jeff"]), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_add_user_from_other_org(self):
        other_org = Organisation.objects.create(title="Other org")
        other_user = other_org.users.create(username="alien")
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.add_url, self._add_payload(user=other_user), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_remove_unauthorized(self):
        response = self.client.post(self.remove_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_remove_participant_forbidden(self):
        self.client.force_login(self.participant)
        response = self.client.post(self.remove_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.FORBIDDEN, response.status_code)

    def test_remove_moderator(self):
        self.meeting.add_roles(self.participant, ROLE_DISCUSSER)
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url, self._add_payload(roles=[ROLE_DISCUSSER]), format="json"
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertNotIn(str(ROLE_DISCUSSER), response.json()["assigned"])

    def test_remove_last_role_returns_no_content(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url, self._add_payload(roles=[ROLE_PARTICIPANT]), format="json"
        )
        self.assertEqual(HTTPStatus.NO_CONTENT, response.status_code)

    def test_remove_nonexistent_user(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url,
            {**self._add_payload(), "user": -1},
            format="json",
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_remove_logs_change(self):
        self.client.force_login(self.moderator)
        with self.assertLogs("voteit.event.roles") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    self.remove_url,
                    self._add_payload(roles=[ROLE_PARTICIPANT]),
                    format="json",
                )
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = _record_to_dict(logs.records[0])
        data.pop("taskName", None)
        self.assertEqual(
            {
                "message": "Removed",
                "context_name": "meeting",
                "context": self.meeting.pk,
                "org": self.meeting.organisation_id,
                "meeting": self.meeting.pk,
                "actor": self.moderator.pk,
                "for_user": self.participant.pk,
                "roles": [str(ROLE_PARTICIPANT)],
            },
            data,
        )

    def test_remove_bad_role(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url, self._add_payload(roles=["jeff"]), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_remove_user_from_other_org(self):
        other_org = Organisation.objects.create(title="Other org")
        other_user = other_org.users.create(username="alien2")
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url, self._add_payload(user=other_user), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)


class MeetingRolesAvailableRolesTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    url = reverse("meeting-roles-available")

    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.get(username="participant")

    def test_anonymous_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(HTTPStatus.OK, response.status_code)

    def test_returns_all_roles(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.url)
        names = {item["name"] for item in response.json()}
        self.assertEqual(
            {
                str(r)
                for r in (
                    ROLE_PARTICIPANT,
                    ROLE_MODERATOR,
                    ROLE_DISCUSSER,
                    ROLE_POTENTIAL_VOTER,
                    ROLE_PROPOSER,
                )
            },
            names,
        )

    def test_no_predicate_info_in_response(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.url)
        for item in response.json():
            self.assertNotIn("predicate_info", item)

    def test_each_role_has_required_fields(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.url)
        for item in response.json():
            self.assertIn("name", item)
            self.assertIn("title", item)
            self.assertIn("description", item)
            self.assertIn("require_names", item)


class ExportMeetingGroupsViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.turkish = cls.meeting.groups.create(title="Özgür", votes=5)
        cls.chineese = cls.meeting.groups.create(title="好", groupid="ni-hao", votes=8)
        cls.swedish = cls.meeting.groups.create(title="Fika nu kör vi")

    def test_not_allowed(self):
        url = reverse("export-meeting-groups-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_json(self):
        url = reverse("export-meeting-groups-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        data = response.json()
        data = sorted(data, key=lambda x: x["groupid"])
        self.assertEqual(
            [
                {
                    "title": "Fika nu kör vi",
                    "groupid": "fika-nu-kor-vi",
                    "votes": None,
                },
                {"title": "好", "groupid": "ni-hao", "votes": 8},
                {
                    "title": "Özgür",
                    "groupid": "ozgur",
                    "votes": 5,
                },
            ],
            data,
        )

    def test_csv(self):
        url = reverse("export-meeting-groups-csv", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual("text/csv", response.headers.get("Content-Type"))
        rows = {x.decode() for x in response.content.splitlines()}
        self.assertEqual(
            {
                "title,groupid,votes",
                "Özgür,ozgur,5",
                "好,ni-hao,8",
                "Fika nu kör vi,fika-nu-kor-vi,",
            },
            set(rows),
        )


class ExportParticipantsViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting.participants.create(
            username="hao", first_name="Özgür", last_name="好"
        )

    def test_not_allowed(self):
        url = reverse("export-participants-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_json(self):
        url = reverse("export-participants-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        data = response.json()
        self.assertIn(
            {
                "first_name": "Participant",
                "last_name": "",
                "email": "participant@voteit.se",
                "userid": "participant",
                "moderator": False,
                "potential_voter": False,
                "discusser": False,
                "proposer": False,
            },
            data,
        )

    def test_csv(self):
        url = reverse("export-participants-csv", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual("text/csv", response.headers.get("Content-Type"))
        rows = response.content.splitlines()
        self.assertIn(
            b"Moderator,,moderator@voteit.se,moderator,True,False,False,False",
            rows,
        )
        self.assertIn(
            b"\xc3\x96zg\xc3\xbcr,\xe5\xa5\xbd,,,False,False,False,False",
            rows,
        )


@override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
class MeetingDialectsViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.user = cls.org.users.create(username="user")

    def test_list(self):
        self.client.force_login(self.user)
        url = reverse("meeting-dialects-list")
        response = self.client.get(url)
        self.assertIn(
            {
                "description": "Main and substitute roles",
                "name": "main_subst",
                "title": "Main/subst",
            },
            response.json(),
        )

    def test_list_with_org_filter(self):
        self.org.components.create(
            component_name=DialectsFilter.name,
            settings={
                "include": ["one"],
                "exclude": ["main_subst", "three"],
            },
        )
        self.client.force_login(self.user)
        url = reverse("meeting-dialects-list")
        response = self.client.get(url)
        self.assertEqual(
            [
                {"description": "", "name": "one", "title": "Hello"},
                {"description": "", "name": "two", "title": "Two!"},
            ],
            response.json(),
        )
