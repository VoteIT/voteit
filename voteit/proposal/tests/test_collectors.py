from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.registry import batch_for
from voteit.messaging.state import AppState
from voteit.messaging.testing import payloads_of
from voteit.messaging.testing import run_collector
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.proposal.collectors import _fetch_mentions_map
from voteit.proposal.diff import Changes
from voteit.proposal.collectors import attach_proposals
from voteit.proposal.messages import ProposalChanged
from voteit.proposal.messages import TextDocumentChanged
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api.serializers import DiffProposalDetailSerializer
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer
from voteit.proposal.rest_api.serializers import TextDocumentSerializer

User = get_user_model()


def _wire(payloads) -> dict[int, dict]:
    """The payloads as they reach the client, keyed by pk.

    Routing through the real batch message is the point: it applies
    ``AddedOrUpdatedSchema``'s datetime normalisation, which is the one
    transformation the .values() route relies on and the serializer route does
    not go through.
    """
    batch_cls = batch_for(ProposalChanged)
    dumped = batch_cls(payload={"items": list(payloads)}).model_dump(mode="json")
    return {item["pk"]: item for item in dumped["payload"]["items"]}


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AttachProposalsEquivalenceTests(TestCase):
    """``attach_proposals`` builds payloads with .values(), not the serializer.

    That is only safe while the serializer's extra fields stay hand-injectable,
    so the equivalence is asserted rather than assumed -- the same guarantee
    ``voteit/agenda/tests/test_collectors.py`` gives ``agenda.items``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(title="M")
        cls.moderator = User.objects.create(username="mod")
        cls.author = User.objects.create(username="author")
        cls.mentioned = User.objects.create(username="mentioned")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.author, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.mentioned, ROLE_PARTICIPANT)

        cls.ai = cls.meeting.agenda_items.create(title="Public", state="upcoming")
        cls.plain = cls.ai.proposals.create(
            body="We are Devo", author=cls.author, tags=["x"]
        )
        # Two mentions on one proposal: the case _fetch_mentions_map exists for.
        cls.mentioning = cls.ai.proposals.create(body="Hi", author=cls.author)
        cls.mentioning.mentions.set([cls.author, cls.mentioned])

        # Long enough that brief and full diffs actually differ -- see
        # test_the_diff_fixture_can_tell_brief_from_full.
        cls.text = cls.ai.text_documents.create(
            body=(
                "The bureaucracy is expanding to meet the needs of the "
                "expanding bureaucracy and nobody anywhere can possibly stop "
                "it from happening ever again today"
            )
        )
        cls.para = cls.text.text_paragraphs.all().first()
        cls.diff = DiffProposal.objects.create(
            paragraph=cls.para,
            agenda_item=cls.ai,
            author=cls.author,
            body=cls.para.body.replace("nobody", "everybody"),
        )

        cls.private_ai = cls.meeting.agenda_items.create(title="Private")
        cls.private_prop = cls.private_ai.proposals.create(body="Secret")

    def _from_collector(self, *, include_private: bool) -> dict[int, dict]:
        state = AppState()
        attach_proposals(self.meeting, state, include_private=include_private)
        return _wire(p.model_dump() for p in payloads_of(state, ProposalChanged))

    def _from_serializers(self, *, include_private: bool) -> dict[int, dict]:
        """What the collector claims to be equivalent to."""
        plain_qs = Proposal.objects.filter(
            agenda_item__meeting=self.meeting, diffproposal__isnull=True
        )
        diff_qs = DiffProposal.objects.filter(agenda_item__meeting=self.meeting)
        if not include_private:
            plain_qs = plain_qs.exclude(agenda_item__state="private")
            diff_qs = diff_qs.exclude(agenda_item__state="private")
        payloads = [
            {**data, "m": self.meeting.pk}
            for data in ProposalDetailSerializer(plain_qs, many=True).data
        ]
        payloads += [
            {**data, "m": self.meeting.pk}
            for data in DiffProposalDetailSerializer(diff_qs, many=True).data
        ]
        return _wire(payloads)

    def test_values_matches_the_serializer(self):
        """Identical frames, whichever route built them."""
        self.assertEqual(
            self._from_serializers(include_private=True),
            self._from_collector(include_private=True),
        )

    def test_values_matches_the_serializer_without_private(self):
        self.assertEqual(
            self._from_serializers(include_private=False),
            self._from_collector(include_private=False),
        )

    def test_body_diff_brief_matches_the_serializer(self):
        """The collector recomputes the diff instead of calling the serializer.

        ``attach_proposals`` annotates ``paragraph__body`` and builds
        ``Changes(...)`` itself; ``DiffProposalDetailSerializer`` reaches through
        the FK in a method field. Two implementations, one required answer.
        """
        collected = self._from_collector(include_private=True)[self.diff.pk]
        expected = DiffProposalDetailSerializer(self.diff).data["body_diff_brief"]
        self.assertEqual(expected, collected["body_diff_brief"])
        self.assertIn("everybody", collected["body_diff_brief"])

    def test_the_diff_fixture_can_tell_brief_from_full(self):
        """Keeps the assertion above honest.

        ``get_html`` only elides unchanged runs longer than ``WORD_CAP``, so on
        a short paragraph brief and full are byte-identical and the equality
        test passes whichever flag the collector happens to pass. This pins the
        fixture to a paragraph where the two genuinely diverge.
        """
        full = Changes(self.para.body, self.diff.body).get_html(brief=False)
        brief = Changes(self.para.body, self.diff.body).get_html(brief=True)
        self.assertNotEqual(full, brief)
        self.assertIn("[...]", brief)
        collected = self._from_collector(include_private=True)[self.diff.pk]
        self.assertEqual(brief, collected["body_diff_brief"])

    def test_payload_keys_are_the_serializer_keys_plus_m(self):
        """A field added to either serializer must show up here or fail."""
        collected = self._from_collector(include_private=True)
        self.assertEqual(
            set(ProposalDetailSerializer().fields) | {"m"},
            set(collected[self.plain.pk]),
        )
        self.assertEqual(
            set(DiffProposalDetailSerializer().fields) | {"m"},
            set(collected[self.diff.pk]),
        )

    def test_every_values_field_is_a_concrete_column(self):
        """A method field added to a serializer must fail loudly, not silently.

        .values() raises FieldError for anything that is not a column, so
        running the collector at all is the assertion. This is what stops the
        set arithmetic in attach_proposals from quietly selecting nonsense.
        """
        self._from_collector(include_private=True)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AttachProposalsMentionsTests(TestCase):
    """Mentions are injected separately to dodge the M2M .values() fan-out."""

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(title="M")
        cls.user = User.objects.create(username="u")
        cls.other = User.objects.create(username="o")
        cls.meeting.add_roles(cls.user, ROLE_MODERATOR, ROLE_PARTICIPANT)
        cls.ai = cls.meeting.agenda_items.create(state="upcoming")
        cls.prop = cls.ai.proposals.create(body="Hi")
        cls.prop.mentions.set([cls.user, cls.other])

    def _payloads(self):
        state = AppState()
        attach_proposals(self.meeting, state, include_private=True)
        return payloads_of(state, ProposalChanged)

    def test_two_mentions_do_not_duplicate_the_proposal(self):
        """The bug the separate query exists to prevent.

        An M2M inside .values() yields one row per relationship, so this
        proposal would arrive twice if mentions were selected inline.
        """
        payloads = self._payloads()
        self.assertEqual(1, len(payloads))
        self.assertEqual({self.user.pk, self.other.pk}, set(payloads[0].mentions))

    def test_proposal_without_mentions_gets_an_empty_list(self):
        other = self.ai.proposals.create(body="No mentions")
        by_pk = {p.pk: p for p in self._payloads()}
        self.assertEqual([], by_pk[other.pk].mentions)

    def test_fetch_mentions_map_short_circuits_on_no_pks(self):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual({}, _fetch_mentions_map([]))
        self.assertEqual(0, len(ctx))

    def test_query_count_is_flat_in_the_number_of_proposals(self):
        """No N+1: adding proposals with mentions must not add queries."""
        with CaptureQueriesContext(connection) as before:
            self._payloads()

        for i in range(5):
            prop = self.ai.proposals.create(body=f"Extra {i}")
            prop.mentions.set([self.user, self.other])

        with CaptureQueriesContext(connection) as after:
            payloads = self._payloads()

        self.assertEqual(6, len(payloads))
        self.assertEqual(len(before), len(after))


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class ProposalsCollectorTests(TestCase):
    """The `proposal.proposals` collector: visibility and shape."""

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(title="M")
        cls.user = User.objects.create(username="u")
        cls.meeting.add_roles(cls.user, ROLE_MODERATOR, ROLE_PARTICIPANT)

        cls.ai = cls.meeting.agenda_items.create(title="Public", state="upcoming")
        cls.plain = cls.ai.proposals.create(body="Public prop")
        cls.text = cls.ai.text_documents.create(body="Original text.")
        cls.para = cls.text.text_paragraphs.all().first()
        cls.diff = DiffProposal.objects.create(
            paragraph=cls.para, agenda_item=cls.ai, body="Amended text."
        )

        cls.private_ai = cls.meeting.agenda_items.create(title="Private")
        cls.private_prop = cls.private_ai.proposals.create(body="Secret")

    def _pks(self, channel_cls):
        state = run_collector(
            "proposal.proposals", self.meeting, self.user, channel_cls=channel_cls
        )
        return {p.pk for p in payloads_of(state, ProposalChanged)}

    def test_moderators_see_private_agenda_items(self):
        self.assertEqual(
            {self.plain.pk, self.diff.pk, self.private_prop.pk},
            self._pks(ModeratorsChannel),
        )

    def test_participants_do_not(self):
        self.assertEqual({self.plain.pk, self.diff.pk}, self._pks(ParticipantsChannel))

    def test_plain_and_diff_arrive_in_one_batch(self):
        state = run_collector(
            "proposal.proposals",
            self.meeting,
            self.user,
            channel_cls=ModeratorsChannel,
        )
        actions = [m.action for m in state]
        self.assertEqual(["proposal.changed.batch"], actions)

    def test_shortname_distinguishes_the_subtype(self):
        state = run_collector(
            "proposal.proposals",
            self.meeting,
            self.user,
            channel_cls=ModeratorsChannel,
        )
        by_pk = {p.pk: p for p in payloads_of(state, ProposalChanged)}
        self.assertEqual("proposal", by_pk[self.plain.pk].shortname)
        self.assertEqual("diff_proposal", by_pk[self.diff.pk].shortname)

    def test_meeting_pk_is_injected_as_m(self):
        """`m` is websocket-only -- no REST response carries it."""
        state = run_collector(
            "proposal.proposals",
            self.meeting,
            self.user,
            channel_cls=ModeratorsChannel,
        )
        for payload in payloads_of(state, ProposalChanged):
            self.assertEqual(self.meeting.pk, payload.m)

    def test_diff_proposals_are_not_sent_twice(self):
        """A DiffProposal is also a Proposal row; the plain query must skip it."""
        pks = list(
            p.pk
            for p in payloads_of(
                run_collector(
                    "proposal.proposals",
                    self.meeting,
                    self.user,
                    channel_cls=ModeratorsChannel,
                ),
                ProposalChanged,
            )
        )
        self.assertEqual(len(pks), len(set(pks)))

    def test_other_meetings_are_not_included(self):
        other_meeting = Meeting.objects.create(title="Other")
        other_ai = other_meeting.agenda_items.create(state="upcoming")
        other_ai.proposals.create(body="Not mine")
        self.assertNotIn(
            "Not mine",
            {
                p.body
                for p in payloads_of(
                    run_collector(
                        "proposal.proposals",
                        self.meeting,
                        self.user,
                        channel_cls=ModeratorsChannel,
                    ),
                    ProposalChanged,
                )
            },
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class TextDocumentsCollectorTests(TestCase):
    """`proposal.text_documents`, on the agenda item channel."""

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(title="M")
        cls.user = User.objects.create(username="u")
        cls.meeting.add_roles(cls.user, ROLE_MODERATOR, ROLE_PARTICIPANT)
        cls.ai = cls.meeting.agenda_items.create(state="upcoming")
        cls.other_ai = cls.meeting.agenda_items.create(state="upcoming")
        cls.text = cls.ai.text_documents.create(
            body="First para.\n\nSecond para.", title="Doc"
        )
        cls.other_text = cls.other_ai.text_documents.create(body="Elsewhere.")

    def _payloads(self, ai):
        state = run_collector(
            "proposal.text_documents", ai, self.user, channel_cls=AgendaItemChannel
        )
        return payloads_of(state, TextDocumentChanged)

    def test_only_this_agenda_items_documents(self):
        self.assertEqual({self.text.pk}, {p.pk for p in self._payloads(self.ai)})
        self.assertEqual(
            {self.other_text.pk}, {p.pk for p in self._payloads(self.other_ai)}
        )

    def test_matches_the_serializer(self):
        """This collector uses the serializer directly, so this pins the wiring."""
        expected = TextDocumentSerializer(self.text).data
        payload = self._payloads(self.ai)[0].model_dump()
        self.assertEqual(expected["base_tag"], payload["base_tag"])
        self.assertEqual(expected["title"], payload["title"])
        self.assertEqual(len(expected["paragraphs"]), len(payload["paragraphs"]))

    def test_paragraphs_are_nested(self):
        payload = self._payloads(self.ai)[0]
        self.assertEqual(2, len(payload.paragraphs))

    def test_empty_agenda_item_sends_nothing(self):
        empty_ai = self.meeting.agenda_items.create(state="upcoming")
        self.assertEqual([], self._payloads(empty_ai))
