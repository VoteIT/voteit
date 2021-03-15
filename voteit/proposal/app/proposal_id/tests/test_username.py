from django.test import TestCase


class ProposalTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.user = self.meeting.participants.create(username="jane-doe")

    @property
    def _cut(self):
        from voteit.proposal.app.proposal_id import UsernamePID

        return UsernamePID

    def test_username(self):
        prop = self.ai.proposals.create(author=self.user)
        self.assertEqual("jane-doe-1", prop.prop_id)
        prop2 = self.ai.proposals.create(author=self.user)
        self.assertEqual("jane-doe-2", prop2.prop_id)

    def test_already_existing(self):
        other = self.meeting.participants.create(username="hello")
        prop = self.ai.proposals.create(author=other, prop_id="jane-doe-1")
        prop2 = self.ai.proposals.create(author=self.user)
        self.assertEqual("jane-doe-2", prop2.prop_id)

    def test_silly_previous(self):
        prop = self.ai.proposals.create(author=self.user, prop_id="jane-doe-hello")
        self.assertEqual("jane-doe-hello", prop.prop_id)
        prop2 = self.ai.proposals.create(author=self.user)
        self.assertEqual("jane-doe-2", prop2.prop_id)  # Skipping and guessing
