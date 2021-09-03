from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.core.utils import get_model_shortname
from voteit.messaging.errors import UnauthorizedError
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.messages.text import TextResponse

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddReactionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.reactions.models import ReactionButton

        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.disc = cls.ai.discussions.create()
        cls.button: ReactionButton = cls.meeting.reaction_buttons.create(
            change_roles=["potential_voter"]
        )
        cls.voter = User.objects.create(username="voter")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.voter, "potential_voter")
        cls.meeting.add_roles(cls.participant, "participant")

    @property
    def _cut(self):
        from voteit.reactions.messages import AddReaction

        return AddReaction

    def _mk_one(self, context, **kw):
        return self._cut(
            {"consumer_name": "abc", "user_pk": self.voter.pk},
            button=self.button.pk,
            content_type=get_model_shortname(context),
            object_id=context.pk,
            **kw,
        )

    def test_add_on_prop(self):
        self.assertFalse(self.prop.reaction_set.count())
        msg = self._mk_one(self.prop)
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)
        self.assertTrue(self.prop.reaction_set.count())

    def test_add_on_discussion(self):
        self.assertFalse(self.prop.reaction_set.count())
        msg = self._mk_one(self.disc)
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)
        self.assertTrue(self.disc.reaction_set.count())

    def test_add_wrong_type(self):
        self.button.allowed_models = ["discussion_post"]
        self.button.save()
        msg = self._mk_one(self.prop)
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_add_on_prop_wrong_perm(self):
        msg = self._mk_one(self.disc)
        msg.mm.user_pk = self.participant.pk
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_duplicate(self):
        self.assertFalse(self.prop.reaction_set.count())
        msg = self._mk_one(self.prop)
        msg.run_job()
        self.assertEqual(1, self.prop.reaction_set.count())
        msg.run_job()
        self.assertEqual(1, self.prop.reaction_set.count())


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class DeleteReactionTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.prop = self.ai.proposals.create()
        self.disc = self.ai.discussions.create()
        self.button = self.meeting.reaction_buttons.create(
            change_roles=["potential_voter"]
        )
        self.voter = User.objects.create(username="voter")
        self.participant = User.objects.create(username="participant")
        self.meeting.add_roles(self.voter, "potential_voter")
        self.meeting.add_roles(self.participant, "participant")
        self.reaction = self.prop.reaction_set.create(
            user=self.voter,
            button=self.button,
            object_id=self.disc.id,
            agenda_item=self.ai,
            content_type=self.disc,
        )

    @property
    def _cut(self):
        from voteit.reactions.messages import DeleteReaction

        return DeleteReaction

    def _mk_one(self):
        return self._cut(
            {"consumer_name": "abc", "user_pk": self.voter.pk},
            pk=self.reaction.pk,
            # reaction_pk=self.reaction.pk,
        )

    def test_delete(self):
        self.assertTrue(self.prop.reaction_set.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.prop.reaction_set.count())


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ListReactionUsersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.disc = cls.ai.discussions.create()
        cls.button = cls.meeting.reaction_buttons.create(
            change_roles=["potential_voter"],
            list_roles=["potential_voter"],
        )
        cls.voter = User.objects.create(username="voter")
        cls.participant = User.objects.create(username="participant")
        cls.outsider = User.objects.create(username="outsider")
        cls.meeting.add_roles(cls.voter, "potential_voter")
        cls.meeting.add_roles(cls.participant, "participant")
        for user in [cls.voter, cls.participant]:
            cls.prop.reaction_set.create(
                user=user,
                button=cls.button,
                object_id=cls.disc.id,
                agenda_item=cls.ai,
                content_type=cls.disc,
            )

    @property
    def _cut(self):
        from voteit.reactions.messages import ListReactionUsers

        return ListReactionUsers

    def _mk_one(self, user, context):
        return self._cut(
            {"consumer_name": "abc", "user_pk": user.pk},
            button=self.button.pk,
            content_type=context.name,
            object_id=context.pk,
        )

    def test_wrong_role(self):
        msg = self._mk_one(self.participant, self.prop)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_outsider(self):
        msg = self._mk_one(self.outsider, self.prop)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_has_correct_role(self):
        msg = self._mk_one(self.voter, self.prop)
        response = msg.run_job()
        self.assertEqual("reaction.list", response.name)
        self.assertEqual(
            {self.voter.pk, self.participant.pk}, set(response.data.userids)
        )
