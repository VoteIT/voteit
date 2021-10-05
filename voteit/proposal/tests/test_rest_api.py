from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

User = get_user_model()


class ProposalTestCase(APITestCase):
    def setUp(self) -> None:
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.meeting.roles import ROLE_PROPOSER, ROLE_MODERATOR, ROLE_PARTICIPANT

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.agenda_item: AgendaItem = AgendaItem.objects.create(
            title="Agenda item", meeting=self.meeting, state="ongoing"
        )
        self.participant: User = User.objects.create_user("participant")
        self.moderator: User = User.objects.create_user("moderator")
        self.proposer: User = User.objects.create_user("proposer")
        self.outsider: User = User.objects.create_user("outsider")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.meeting.add_roles(self.proposer, ROLE_PROPOSER)

    def test_create(self):
        url = reverse("proposal-list")
        data = {
            "title": "My proposal",
            "agenda_item": self.agenda_item.pk,
            "shortname": "proposal",
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
            (self.proposer, 201),
            (self.participant, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, status)

    def test_agenda_item_ne(self):
        url = reverse("proposal-list")
        data = {
            "title": "My proposal",
            "agenda_item": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")
