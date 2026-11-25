from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from rest_framework.test import APITestCase

from voteit.agenda.models import AgendaItem
from voteit.core.testing import FakeCommit
from voteit.core.testing import mk_hashtag
from voteit.core.testing import mk_usertag
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.messaging.testing import MessageCatcher
from voteit.messaging.testing import action_of
from voteit.proposal.messages import ProposalChanged
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import TextDocument
from voteit.proposal.models import TextParagraph

User = get_user_model()


class ProposalsAPITests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.prop = cls.ai.proposals.create(body="Open")
        cls.ai_private: AgendaItem = cls.meeting.agenda_items.create(title="Private")
        cls.prop_private = cls.ai_private.proposals.create(body="Private")
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman\nI am the walrus"
        )
        cls.para: TextParagraph = cls.text_doc.text_paragraphs.first()
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.proposer: User = cls.meeting.participants.create(username="proposer")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.moderator.userid = "moderator"
        cls.moderator.save()
        cls.outsider: User = User.objects.create_user("outsider")
        # cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.proposer, ROLE_PROPOSER)
        # cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.meeting_group = cls.meeting.groups.create()

    def test_create(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
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
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_ai_ne(self):
        url = reverse("proposal-list")
        data = {"body": "bla", "agenda_item": -1, "shortname": "proposal"}
        self.client.force_login(self.proposer)
        response = self.client.post(url, data)
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertDictEqual(
            {"agenda_item": ['Invalid pk "-1" - object does not exist.']}, data
        )

    def test_create_diff_proposal(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
            "shortname": "diff_proposal",
            "paragraph": self.para.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(201, response.status_code)
        self.assertEqual(1, self.para.proposals.all().count())

    def test_create_diff_proposal_has_other_requirements(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
            "shortname": "diff_proposal",
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(400, response.status_code)
        data = response.json()
        self.assertIn("paragraph", data)

    def test_create_diff_proposal_permissions(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
            "shortname": "diff_proposal",
            "paragraph": self.para.pk,
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
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_put_author_proposer(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        data = {
            "body": "Sup?",
            "agenda_item": self.ai.pk,
        }
        self.client.force_login(self.proposer)
        response = self.client.put(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_patch_author_proposer(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        data = {
            "body": "Sup?",
        }
        self.client.force_login(self.proposer)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_patch_author_proposer_moderator_user(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        data = {
            "body": "Sup?",
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        prop.refresh_from_db(fields=("body",))
        self.assertEqual("Sup?", prop.body)

    def test_delete(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, prop.refresh_from_db)

    def test_delete_diff(self):
        diff_prop = self.para.proposals.create(agenda_item=self.ai)
        url = reverse("proposal-detail", kwargs={"pk": diff_prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, diff_prop.refresh_from_db)

    def test_preview_proposal(self):
        url = reverse("proposal-preview")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello!",
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, [data], format="json")
        self.assertEqual(200, response.status_code)
        data = response.json()[0]
        self.assertEqual("Hello!", data["body"])

    def test_preview_proposal_mentions(self):
        url = reverse("proposal-preview")
        data = {
            "agenda_item": self.ai.pk,
            "body": f"Hello {mk_usertag(self.participant)}",
            "mentions": [self.moderator.pk],
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, [data], format="json")
        self.assertEqual(200, response.status_code)
        data = response.json()[0]
        self.assertEqual(
            {self.participant.pk, self.moderator.pk}, set(data["mentions"])
        )

    def test_preview_diff_proposal(self):
        url = reverse("proposal-preview")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello world!",
            "shortname": "diff_proposal",
            "paragraph": self.para.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, [data], format="json")
        self.assertEqual(200, response.status_code)
        data = response.json()[0]
        self.assertEqual("moderator-{n}", data["prop_id"])
        self.assertEqual(
            "Hello world!",
            data["body"],
        )
        self.assertEqual(
            '<span class="text-diff-removed">I am the eggman <br/> I am the walrus</span> <span class="text-diff-added">Hello world!</span>',
            data["body_diff_brief"],
        )

    def test_preview_many(self):
        url = reverse("proposal-preview")
        data = [
            {"agenda_item": self.ai.pk, "body": "One"},
            {"agenda_item": self.ai.pk, "body": "Two"},
        ]
        self.client.force_login(self.moderator)
        response = self.client.post(url, data, format="json")
        self.assertEqual(200, response.status_code)
        self.assertEqual(["One", "Two"], [x["body"] for x in response.json()])

    def test_preview_bad_input(self):
        url = reverse("proposal-preview")
        self.client.force_login(self.moderator)
        item = {"agenda_item": self.ai.pk, "body": "Hello"}
        for data in ([], item, [item] * 21, ["hello"]):
            response = self.client.post(url, data, format="json")
            self.assertEqual(400, response.status_code, data)

    def test_preview_errors_per_item(self):
        url = reverse("proposal-preview")
        data = [
            {"agenda_item": self.ai.pk, "body": "Good"},
            {"agenda_item": -1, "body": "Bad"},
            {"agenda_item": self.ai.pk, "body": "Bad", "shortname": "nope"},
            {"agenda_item": self.ai.pk, "body": "Bad", "shortname": []},
        ]
        self.client.force_login(self.moderator)
        response = self.client.post(url, data, format="json")
        self.assertEqual(400, response.status_code)
        errors = response.json()
        self.assertEqual(4, len(errors))
        self.assertEqual({}, errors[0])
        self.assertIn("agenda_item", errors[1])
        self.assertIn("shortname", errors[2])
        self.assertIn("shortname", errors[3])

    def test_bulk_create(self):
        url = reverse("proposal-bulk-create")
        data = [{"agenda_item": self.ai.pk, "body": body} for body in ("A", "B", "C")]
        self.client.force_login(self.moderator)
        response = self.client.post(url, data, format="json")
        self.assertEqual(201, response.status_code, response.json())
        result = response.json()
        self.assertEqual(["A", "B", "C"], [x["body"] for x in result])
        self.assertEqual(
            ["moderator-1", "moderator-2", "moderator-3"],
            [x["prop_id"] for x in result],
        )
        self.assertEqual(
            ["A", "B", "C"],
            list(
                self.ai.proposals.filter(author=self.moderator)
                .order_by("created")
                .values_list("body", flat=True)
            ),
        )

    def test_bulk_create_publishes_one_batch(self):
        url = reverse("proposal-bulk-create")
        data = [{"agenda_item": self.ai.pk, "body": body} for body in ("A", "B", "C")]
        self.client.force_login(self.moderator)
        with MessageCatcher() as messages:
            # Test data has staged a batcher already; FakeCommit starts clean
            with FakeCommit():
                response = self.client.post(url, data, format="json")
        self.assertEqual(201, response.status_code)
        action = action_of(ProposalChanged)
        batches = [m for m in messages if m.action == f"{action}.batch"]
        # One batch each for moderators and participants, no single messages
        self.assertEqual(2, len(batches))
        self.assertFalse([m for m in messages if m.action == action])
        for batch in batches:
            self.assertEqual(
                ["A", "B", "C"], [item.body for item in batch.payload.items]
            )

    def test_bulk_create_too_many(self):
        url = reverse("proposal-bulk-create")
        data = [{"agenda_item": self.ai.pk, "body": "Hello"}] * 21
        self.client.force_login(self.moderator)
        count = self.ai.proposals.count()
        response = self.client.post(url, data, format="json")
        self.assertEqual(400, response.status_code)
        self.assertEqual(count, self.ai.proposals.count())

    def test_bulk_create_invalid_creates_nothing(self):
        url = reverse("proposal-bulk-create")
        data = [
            {"agenda_item": self.ai.pk, "body": "Good"},
            {"agenda_item": -1, "body": "Bad"},
            {"agenda_item": self.ai.pk, "body": "Also good"},
        ]
        self.client.force_login(self.moderator)
        count = self.ai.proposals.count()
        response = self.client.post(url, data, format="json")
        self.assertEqual(400, response.status_code)
        self.assertEqual(count, self.ai.proposals.count())

    def test_bulk_create_permission(self):
        url = reverse("proposal-bulk-create")
        data = [{"agenda_item": self.ai.pk, "body": "Hello"}]
        for user, status in (
            (None, 401),
            (self.participant, 403),
            (self.proposer, 201),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data, format="json")
            self.assertEqual(status, response.status_code, user)

    def test_bulk_create_diff_proposal(self):
        url = reverse("proposal-bulk-create")
        data = [
            {
                "agenda_item": self.ai.pk,
                "body": "Hello world!",
                "shortname": "diff_proposal",
                "paragraph": self.para.pk,
            }
        ]
        self.client.force_login(self.moderator)
        response = self.client.post(url, data, format="json")
        self.assertEqual(201, response.status_code, response.json())
        self.assertEqual(1, self.para.proposals.count())
        self.assertIn("body_diff_brief", response.json()[0])

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_transition_on_diff_triggers_correct_push(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        diff_prop = self.para.proposals.create(agenda_item=self.ai)
        mock_publish.reset_mock()
        self.assertFalse(mock_publish.called)

        self.client.force_login(self.moderator)
        url = reverse("proposal-event", kwargs={"pk": diff_prop.pk})
        response = self.client.post(url, data={"event": "approve"})
        self.assertEqual(200, response.status_code)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(diff_prop.pk, msg.payload.pk)
        self.assertEqual(self.para.pk, msg.payload.paragraph)

    def test_patch_author_normal_user(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.proposer)
        response = self.client.patch(url, data={"author": self.moderator.pk})
        self.assertEqual(
            response.status_code,
            403,
        )
        self.assertIn(
            "permission 'proposal.change_proposal'", response.json()["detail"]
        )

    def test_patch_author_moderator(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"author": self.moderator.pk})
        self.assertEqual(
            response.status_code,
            200,
        )
        prop.refresh_from_db()
        self.assertEqual(prop.author, self.moderator)

    def test_patch_author_not_in_meeting(self):
        meeting = Meeting.objects.create()
        ai = meeting.agenda_items.create()
        prop = ai.proposals.create(body="I'm from another meeting")
        meeting.add_roles(self.moderator, ROLE_MODERATOR)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"author": self.proposer.pk})
        self.assertEqual(
            response.status_code,
            400,
        )

    def test_patch_meeting_group_null(self):
        url = reverse("proposal-detail", kwargs={"pk": self.prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"meeting_group": None})
        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertIsNone(self.prop.meeting_group)

    def test_patch_meeting_group_not_in_meeting(self):
        meeting = Meeting.objects.create()
        ai = meeting.agenda_items.create()
        prop = ai.proposals.create(body="I'm from another meeting")
        meeting.add_roles(self.moderator, ROLE_MODERATOR)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(
            response.status_code,
            400,
        )

    def test_create_meeting_group_not_in_meeting(self):
        meeting = Meeting.objects.create()
        ai = meeting.agenda_items.create()
        prop = ai.proposals.create(body="I'm from another meeting")
        meeting.add_roles(self.moderator, ROLE_MODERATOR)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(
            response.status_code,
            400,
        )

    def test_patch_meeting_group_normal_user(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.proposer)
        response = self.client.patch(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(
            response.status_code,
            403,
        )
        self.assertIn(
            "permission 'proposal.change_proposal'", response.json()["detail"]
        )

    def test_patch_meeting_group_moderator(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = reverse("proposal-detail", kwargs={"pk": prop.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(
            response.status_code,
            200,
        )
        prop.refresh_from_db()
        self.assertEqual(prop.meeting_group, self.meeting_group)


class TextDocumentAPITests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(state="ongoing")
        cls.ai_private: AgendaItem = cls.meeting.agenda_items.create()
        User = get_user_model()
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.outsider = User.objects.create(username="outsider")
        cls.text_doc: TextDocument = cls.ai.text_documents.create(body="Hello")
        cls.private_text_doc: TextDocument = cls.ai_private.text_documents.create(
            body="Private text"
        )

    def test_create(self):
        url = reverse("text-document-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello world",
            "base_tag": "hi",
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
            (self.participant, 403),
            (self.outsider, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_ai_ne(self):
        url = reverse("text-document-list")
        data = {
            "body": "bla",
            "agenda_item": -1,
            "base_tag": "hi",
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertDictEqual(
            {"agenda_item": ['Invalid pk "-1" - object does not exist.']},
            data,
        )

    def test_list(self):
        url = reverse("text-document-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))

    def test_delete(self):
        url = reverse("text-document-detail", kwargs={"pk": self.text_doc.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, self.text_doc.refresh_from_db)

    def test_put(self):
        url = reverse("text-document-detail", kwargs={"pk": self.text_doc.pk})
        self.client.force_login(self.moderator)
        response = self.client.put(url, {"body": "World", "base_tag": "hoho"})
        self.assertEqual(
            response.status_code,
            200,
        )
        self.text_doc.refresh_from_db()
        self.assertEqual("World", self.text_doc.body)

    def test_patch(self):
        url = reverse("text-document-detail", kwargs={"pk": self.text_doc.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, {"body": "World"})
        self.assertEqual(
            response.status_code,
            200,
        )
        self.text_doc.refresh_from_db()
        self.assertEqual("World", self.text_doc.body)


class ExportProposalsViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai = AgendaItem.objects.get(pk=1)
        cls.participant: User = User.objects.get(
            username="participant",
        )
        cls.moderator: User = User.objects.get(username="moderator")
        cls.group: MeetingGroup = cls.meeting.groups.get(pk=1)
        cls.text: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman.\n\nI am the walrus."
        )
        cls.para = cls.text.text_paragraphs.all().first()
        cls.diffprop = DiffProposal.objects.create(
            paragraph=cls.para,
            agenda_item=cls.ai,
            author=cls.participant,
            meeting_group=cls.group,
        )
        cls.prop = cls.ai.proposals.create(body="We are Devo", author=cls.moderator)

    def test_not_allowed(self):
        self.client.force_login(self.participant)
        url = reverse("export-proposals-json", kwargs={"pk": self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_csv_no_data(self):
        self.ai.proposals.all().delete()
        self.client.force_login(self.moderator)
        url = reverse("export-proposals-csv", kwargs={"pk": self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_json(self):
        url = reverse("export-proposals-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(3, len(data))

    def test_csv(self):
        url = reverse("export-proposals-csv", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/csv", response.headers.get("Content-Type"))
        self.assertEqual(
            f'attachment; filename="proposals_{self.meeting.pk}_export.csv"',
            response.headers.get("Content-Disposition"),
        )
        rows = response.content.splitlines()
        header = rows[0].decode().split(",")
        self.assertNotIn("body_diff_brief", header)
        self.assertEqual(
            [
                "created",
                "modified",
                "state",
                "prop_id",
                "state",
                "pk",
                "agenda_item",
                "shortname",
                "author",
                "body",
                "meeting_group",
                "tags",
                "as_group",
                "userid",
                "group_title",
                "group_id",
                "tags",
                "paragraph",
            ],
            header,
        )
        self.assertEqual(4, len(rows))


class ProposalStateMachineSchemaTests(APITestCase):
    def test_detail(self):
        response = self.client.get("/api/state-machines/ProposalStateMachine/")
        self.assertEqual(200, response.status_code)
        self.assertIn("states", response.data)
        self.assertIn("events", response.data)
