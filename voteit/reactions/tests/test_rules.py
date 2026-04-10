from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.reactions import PERM_LIST_REACTIONS
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton

User = get_user_model()


class ButtonPermissionTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.button = cls.meeting.reaction_buttons.create(
            change_roles=[ROLE_PARTICIPANT], list_roles=[ROLE_PARTICIPANT]
        )

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_add(self):
        ADD = ReactionButton.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_closed_meeting(self):
        self.meeting.state = "closed"
        self.meeting.save()
        ADD = ReactionButton.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = ReactionButton.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.button))
        self.assertFalse(self.participant.has_perm(CHANGE, self.button))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.button))

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        CHANGE = ReactionButton.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.button))
        self.assertFalse(self.participant.has_perm(CHANGE, self.button))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.button))

    def test_delete(self):
        DELETE = ReactionButton.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.button))
        self.assertFalse(self.participant.has_perm(DELETE, self.button))
        self.assertTrue(self.moderator.has_perm(DELETE, self.button))

    def test_delete_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        DELETE = ReactionButton.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.button))
        self.assertFalse(self.participant.has_perm(DELETE, self.button))
        self.assertFalse(self.moderator.has_perm(DELETE, self.button))

    def test_list_reactions(self):
        LIST_REACTIONS = ReactionButton.get_perm(PERM_LIST_REACTIONS)
        self.assertFalse(self.anon_user.has_perm(LIST_REACTIONS, self.button))
        self.assertTrue(self.participant.has_perm(LIST_REACTIONS, self.button))
        self.assertTrue(self.moderator.has_perm(LIST_REACTIONS, self.button))
        self.button.list_roles.remove(ROLE_PARTICIPANT)
        self.button.save()
        self.assertFalse(self.participant.has_perm(LIST_REACTIONS, self.button))


class ReactionPermissionTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.ai = cls.meeting.agenda_items.create()
        cls.button = cls.meeting.reaction_buttons.create(
            change_roles=[ROLE_PARTICIPANT], list_roles=[ROLE_PARTICIPANT]
        )
        cls.flag = cls.meeting.reaction_buttons.create(flag_mode=True, title="Flag")
        cls.disc = cls.ai.discussions.create()
        cls.reaction = cls.disc.reaction_set.create(
            user=cls.moderator, object=cls.disc, button=cls.button
        )
        cls.flagged = cls.disc.reaction_set.create(
            user=cls.participant, object=cls.disc, button=cls.flag
        )

    def setUp(self):
        self.button.refresh_from_db()
        self.flag.refresh_from_db()

    def test_add_reaction(self):
        ADD = Reaction.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.button))
        self.assertTrue(self.participant.has_perm(ADD, self.button))
        self.assertTrue(self.moderator.has_perm(ADD, self.button))
        self.button.change_roles.remove(ROLE_PARTICIPANT)
        self.button.save()
        self.assertFalse(self.participant.has_perm(ADD, self.button))
        self.assertTrue(self.moderator.has_perm(ADD, self.button))

    def test_add_reaction_flag(self):
        ADD = Reaction.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.flag))
        self.assertFalse(self.participant.has_perm(ADD, self.flag))
        self.assertTrue(self.moderator.has_perm(ADD, self.flag))

    def test_add_reaction_not_active(self):
        self.button.active = False
        self.button.save()
        ADD = Reaction.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.button))
        self.assertFalse(self.participant.has_perm(ADD, self.button))
        self.assertFalse(self.moderator.has_perm(ADD, self.button))

    def test_add_reaction_not_active_and_flag(self):
        ADD = Reaction.get_perm(PERM.ADD)
        self.flag.active = False
        self.flag.save()
        self.assertFalse(self.anon_user.has_perm(ADD, self.flag))
        self.assertFalse(self.participant.has_perm(ADD, self.flag))
        self.assertFalse(self.moderator.has_perm(ADD, self.flag))

    def test_add_reaction_closed_meeting(self):
        self.meeting.state = "closed"
        self.meeting.save()
        ADD = Reaction.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.button))
        self.assertFalse(self.participant.has_perm(ADD, self.button))
        self.assertFalse(self.moderator.has_perm(ADD, self.button))

    def test_delete(self):
        DELETE = Reaction.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.reaction))
        self.assertFalse(self.participant.has_perm(DELETE, self.reaction))
        self.assertTrue(self.moderator.has_perm(DELETE, self.reaction))

    def test_delete_inactive_button(self):
        self.button.active = False
        self.button.save()
        DELETE = Reaction.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.reaction))
        self.assertFalse(self.participant.has_perm(DELETE, self.reaction))
        self.assertFalse(self.moderator.has_perm(DELETE, self.reaction))

    def test_delete_flag(self):
        DELETE = Reaction.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.flagged))
        self.assertFalse(self.participant.has_perm(DELETE, self.flagged))
        self.assertTrue(self.moderator.has_perm(DELETE, self.flagged))

    def test_delete_inactive_flag(self):
        self.flag.active = False
        self.flag.save()
        DELETE = Reaction.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.flagged))
        self.assertFalse(self.participant.has_perm(DELETE, self.flagged))
        self.assertFalse(self.moderator.has_perm(DELETE, self.flagged))

    def test_delete_closed_meeting(self):
        self.meeting.state = "closed"
        self.meeting.save()
        DELETE = Reaction.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.reaction))
        self.assertFalse(self.participant.has_perm(DELETE, self.reaction))
        self.assertFalse(self.moderator.has_perm(DELETE, self.reaction))
