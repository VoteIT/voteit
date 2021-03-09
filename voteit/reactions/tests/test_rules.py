from django.contrib.auth import get_user_model
from django.test import TestCase


User = get_user_model()


class ButtonPermissionTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.anon_user = User.objects.create(username="anon")
        self.moderator = User.objects.create(username="moderator")
        self.participant = User.objects.create(username="participant")
        self.meeting.add_roles(self.moderator, "moderator")
        self.meeting.add_roles(self.participant, "participant")
        self.button = self.meeting.reaction_buttons.create(
            change_roles=["participant"], list_roles=["participant"]
        )

    @property
    def p(self):
        from voteit.reactions.permissions import ReactionButtonPermissions

        return ReactionButtonPermissions

    def test_add(self):
        ADD = self.p.ADD
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_view(self):
        VIEW = self.p.VIEW
        self.assertFalse(self.anon_user.has_perm(VIEW, self.button))
        self.assertTrue(self.participant.has_perm(VIEW, self.button))
        self.assertTrue(self.moderator.has_perm(VIEW, self.button))

    def test_view_pub_meeting(self):
        self.meeting.public = True
        self.meeting.save()
        VIEW = self.p.VIEW
        self.assertTrue(self.anon_user.has_perm(VIEW, self.button))
        self.assertTrue(self.participant.has_perm(VIEW, self.button))
        self.assertTrue(self.moderator.has_perm(VIEW, self.button))

    def test_change(self):
        CHANGE = self.p.CHANGE
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.button))
        self.assertFalse(self.participant.has_perm(CHANGE, self.button))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.button))

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        CHANGE = self.p.CHANGE
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.button))
        self.assertFalse(self.participant.has_perm(CHANGE, self.button))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.button))

    def test_delete(self):
        DELETE = self.p.DELETE
        self.assertFalse(self.anon_user.has_perm(DELETE, self.button))
        self.assertFalse(self.participant.has_perm(DELETE, self.button))
        self.assertTrue(self.moderator.has_perm(DELETE, self.button))

    def test_delete_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        DELETE = self.p.DELETE
        self.assertFalse(self.anon_user.has_perm(DELETE, self.button))
        self.assertFalse(self.participant.has_perm(DELETE, self.button))
        self.assertFalse(self.moderator.has_perm(DELETE, self.button))

    def test_list_reactions(self):
        LIST_REACTIONS = self.p.LIST_REACTIONS
        self.assertFalse(self.anon_user.has_perm(LIST_REACTIONS, self.button))
        self.assertTrue(self.participant.has_perm(LIST_REACTIONS, self.button))
        self.assertTrue(self.moderator.has_perm(LIST_REACTIONS, self.button))
        self.button.list_roles.remove("participant")
        self.button.save()
        self.assertFalse(self.participant.has_perm(LIST_REACTIONS, self.button))


class ReactionPermissionTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.anon_user = User.objects.create(username="anon")
        self.moderator = User.objects.create(username="moderator")
        self.participant = User.objects.create(username="participant")
        self.meeting.add_roles(self.moderator, "moderator")
        self.meeting.add_roles(self.participant, "participant")
        self.button = self.meeting.reaction_buttons.create(
            change_roles=["participant"], list_roles=["participant"]
        )
        self.ai = self.meeting.agenda_items.create()
        self.disc = self.ai.discussions.create()
        self.reaction = self.disc.reaction_set.create(
            user=self.moderator, object=self.disc, button=self.button
        )

    @property
    def p(self):
        from voteit.reactions.permissions import ReactionPermissions

        return ReactionPermissions

    def test_add_reaction(self):
        ADD = self.p.ADD
        self.assertFalse(self.anon_user.has_perm(ADD, self.button))
        self.assertTrue(self.participant.has_perm(ADD, self.button))
        self.assertTrue(self.moderator.has_perm(ADD, self.button))
        self.button.change_roles.remove("participant")
        self.button.save()
        self.assertFalse(self.participant.has_perm(ADD, self.button))
        self.assertFalse(self.moderator.has_perm(ADD, self.button))

    def test_add_reaction_not_active(self):
        self.button.active = False
        self.button.save()
        ADD = self.p.ADD
        self.assertFalse(self.anon_user.has_perm(ADD, self.button))
        self.assertFalse(self.participant.has_perm(ADD, self.button))
        self.assertFalse(self.moderator.has_perm(ADD, self.button))

    def test_delete(self):
        DELETE = self.p.DELETE
        self.assertFalse(self.anon_user.has_perm(DELETE, self.reaction))
        self.assertFalse(self.participant.has_perm(DELETE, self.reaction))
        self.assertTrue(self.moderator.has_perm(DELETE, self.reaction))

    def test_delete_inactive_button(self):
        self.button.active = False
        self.button.save()
        DELETE = self.p.DELETE
        self.assertFalse(self.anon_user.has_perm(DELETE, self.reaction))
        self.assertFalse(self.participant.has_perm(DELETE, self.reaction))
        self.assertFalse(self.moderator.has_perm(DELETE, self.reaction))
