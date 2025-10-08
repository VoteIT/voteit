from http import HTTPStatus
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import override_settings
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.agenda.models import AgendaItem
from voteit.components.app.components.dialects import DialectsFilter
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
from voteit.organisation.models import Organisation
from voteit.poll.registries import er_policy
from voteit.poll.registries import vote_transfer_policies
from voteit.poll.testing import UnrestrictedVoteTransferER
from voteit.poll.testing import UnrestrictedVoteTransferPolicy
from voteit.speaker.app.list_methods.simple import Simple
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


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

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)

    def test_create(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world"}
        participant = User.objects.get(username="participant")
        org_manager = User.objects.get(username="org_manager")
        for user, status in (
            (None, 401),
            (org_manager, 201),
            (participant, 403),
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
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertEqual(meeting.organisation.pk, 1)

    def test_create_creator_becomes_moderator(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world"}
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
        response = self.client.post(url, data)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertTrue(meeting.has_roles(org_manager, ROLE_MODERATOR))

    def test_create_public_ignored_but_visible_in_lists_works(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world", "visible_in_lists": True, "public": True}
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
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
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
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
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
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
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
        response = self.client.post(url, data=data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertEqual("main_subst", meeting.installed_dialect)

    def test_create_with_dialect_and_vote_transfer(self):
        url = reverse("meeting-list")
        data = {"title": "Stuff", "install_dialect": "unrestricted_vote_transfer"}
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
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
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_get(self):
        url = reverse("meeting-detail", kwargs={"pk": self.meeting.pk})
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
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

    def test_get_visible_in_lists(self):
        url = reverse("meeting-detail", kwargs={"pk": self.meeting.pk})
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        # Check that user can't view details if not participant and not visible in lists
        self.meeting.participants.remove(participant)
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
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            UnrestrictedVoteTransferPolicy.name,
            response.json()["vote_transfer_policy"],
        )

    def test_transition_moderator(self):
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        data = {"transition": "ongoing"}
        self.client.force_login(moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_bad_transition_moderator(self):
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        data = {"transition": "wooohoooo"}
        self.client.force_login(moderator)
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
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_delete(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_delete_participant(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_archived(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_change(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.patch(url, {"title": "A brave new title"})
        self.assertEqual(response.status_code, 200)
        self.meeting.refresh_from_db()
        self.assertEqual("A brave new title", self.meeting.title)

    def test_change_archived(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.patch(url, {"title": "Not allowed"})
        self.assertEqual(response.status_code, 403)

    def test_change_agenda_order(self):
        url = reverse("meeting-set-agenda-order", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.post(url, {"order": [3, 1, 2]})
        self.assertEqual(201, response.status_code)
        one = AgendaItem.objects.get(pk=1)
        two = AgendaItem.objects.get(pk=2)
        three = AgendaItem.objects.get(pk=3)
        self.assertEqual(2, one.order)
        self.assertEqual(3, two.order)
        self.assertEqual(1, three.order)


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

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_create(self):
        url = reverse("meeting-groups-list")
        data = {"title": "Hello world", "meeting": self.meeting.pk}

        for user, status in (
            (None, 401),
            (self.moderator, 201),
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
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.meeting_group.pk, data.get("pk", None))

    def test_get_wrong_user(self):
        self.client.force_login(self.anon)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_list_no_meeting(self):
        url = reverse("meeting-groups-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_list(self):
        url = reverse("meeting-groups-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, len(data))
        self.assertEqual(
            {self.meeting_group.pk, self.meeting_group_two.pk}, {x["pk"] for x in data}
        )

    def test_change(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(url, data={"title": "Hello"})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("Hello", data["title"])

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(url, data={"title": "Hello"})
        self.assertEqual(403, response.status_code)

    def test_delete(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)

    def test_delete_with_related_proposal(self):
        prop = self.meeting_group.proposals.create()
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

        for user, status in (
            (None, 401),
            (self.moderator, 201),
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

    def test_get(self):
        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(
            {
                "user": self.moderator.pk,
                "role": self.role.pk,
                "meeting_group": self.meeting_group.pk,
                "pk": self.membership.pk,
                "votes": None,
            },
            data,
        )

    def test_list_no_grp(self):
        url = reverse("group-memberships-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_list(self):
        url = reverse("group-memberships-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(self.membership.pk, data[0]["pk"])

    def test_change(self):
        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        response = self.client.patch(url, data={"role": ""})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(None, data["role"])

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        response = self.client.patch(url, data={"role": ""})
        self.assertEqual(403, response.status_code)

    def test_delete(self):
        self.client.force_login(self.moderator)
        url = reverse("group-memberships-detail", kwargs={"pk": self.membership.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)

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
        self.assertEqual(403, response.status_code)

    def test_with_filter_participant(self):
        self.client.force_login(self.participant)
        url = reverse("meeting-roles-list")
        response = self.client.get(
            url,
            {
                "meeting": self.meeting.pk,
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

    def test_same_org_but_another_meeting_so_not_allowed(self):
        self.client.force_login(self.user_jeff)
        url = reverse("meeting-roles-list")
        response = self.client.get(url, {"meeting": self.other_meeting.pk})
        self.assertEqual(403, response.status_code)

    @property
    def roles_url(self):
        return reverse("meeting-roles-list")

    def test_roles_n1(self):
        self.client.force_login(self.moderator)
        # n+1 participants
        for i in range(5):
            self.meeting.participants.create(username=f"participant_{i}")
        with self.assertNumQueries(6):
            self.client.get(self.roles_url, data={"meeting": self.meeting.pk})

    def test_participant_name_search(self):
        self.client.force_login(self.participant)
        response = self.client.get(
            self.roles_url,
            {
                "meeting": self.meeting.pk,
                "search": "Jeff",
            },
        )
        self.assertContains(response, "Jeff")
        self.assertEqual(len(response.json()), 1)

    def test_participant_userid_search(self):
        self.client.force_login(self.participant)
        response = self.client.get(
            self.roles_url, {"meeting": self.meeting.pk, "search": "k"}
        )
        self.assertContains(response, "Jeff")
        self.assertEqual(len(response.json()), 1)

    def test_participant_role_search(self):
        for role in (ROLE_PROPOSER, ROLE_DISCUSSER):
            user = self.meeting.participants.create(
                username=role, userid=role, first_name=role.title
            )
            self.meeting.add_roles(user, role)
        self.client.force_login(self.participant)
        response = self.client.get(
            self.roles_url,
            {"meeting": self.meeting.pk, "any_roles": [ROLE_PROPOSER, ROLE_DISCUSSER]},
        )
        self.assertEqual(len(response.json()), 2, "Should match any of the roles")
        response = self.client.get(
            self.roles_url,
            {"meeting": self.meeting.pk, "any_roles": ROLE_PARTICIPANT},
        )
        self.assertContains(response, "Jeff")
        self.assertEqual(len(response.json()), 5, "Should match all users")


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
        self.assertContains(
            response, "permission meeting.moderate_meeting", status_code=403
        )

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
                f"title,groupid,votes",
                f"Özgür,ozgur,5",
                f"好,ni-hao,8",
                f"Fika nu kör vi,fika-nu-kor-vi,",
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
        int_user = cls.meeting.participants.create(
            username="hao", first_name="Özgür", last_name="好"
        )

    def test_not_allowed(self):
        url = reverse("export-participants-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertContains(
            response, "permission meeting.moderate_meeting", status_code=403
        )

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
