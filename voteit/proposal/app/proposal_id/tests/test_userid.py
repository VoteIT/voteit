from django.test import TestCase


class ProposalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.user = cls.meeting.participants.create(
            username="not-used", userid="jane-doe"
        )

    @property
    def _cut(self):
        from voteit.proposal.app.proposal_id import UseridPID

        return UseridPID

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

    # Irrelevant because of new userid proposalid policy?
    # User could have posted 40 group proposals, which should not affect starting prop_id number.
    # def test_silly_previous(self):
    #     prop = self.ai.proposals.create(author=self.user, prop_id="jane-doe-hello")
    #     self.assertEqual("jane-doe-hello", prop.prop_id)
    #     prop2 = self.ai.proposals.create(author=self.user)
    #     self.assertEqual("jane-doe-2", prop2.prop_id)  # Skipping and guessing

    def test_meeting_group_id(self):
        group = self.meeting.groups.create(title="King's College")
        prop = self.ai.proposals.create(author=self.user, meeting_group=group)
        prop2 = self.ai.proposals.create(author=self.user, meeting_group=group)
        user_prop = self.ai.proposals.create(author=self.user)
        self.assertEqual(prop.prop_id, "kings-college-1")
        self.assertEqual(prop2.prop_id, "kings-college-2")
        self.assertEqual(user_prop.prop_id, "jane-doe-1")
