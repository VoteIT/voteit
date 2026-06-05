from __future__ import annotations

from contextlib import suppress
from logging import getLogger
from typing import Mapping
from typing import OrderedDict
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext as _
from pydantic.main import BaseModel
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from statemachine import StateMachine
from statemachine.exceptions import TransitionNotAllowed
from statemachine.utils import qualname

from voteit.core import PERM
from voteit.core.abcs import MeetingContext
from voteit.core.rest_api.utils import meeting_from_unsafe_data
from voteit.core.rest_api.validators import SMEventValidator
from voteit.core.utils import get_tagged_hashtags
from voteit.core.utils import get_tagged_userids
from voteit.core.validators import get_invalid_tags
from voteit.core.validators import valid_userid
from voteit.organisation.utils import get_idproxy_user_data

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.core.models import BaseContent
    from voteit.meeting.models import Meeting
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import MeetingGroup

logger = getLogger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    author_kw = "author"

    def get_request_user(self) -> AbstractUser | None:
        # Validate user?
        request = self.context.get("request")
        if request is not None:
            return request.user

    def validate(self, attrs):
        """
        Validation caveats here:

        - Validation won't work outside of meeting context.
        - Only moderators can specify other authors.
        """
        attrs = super().validate(attrs)
        author = attrs.get(self.author_kw)
        User = get_user_model()
        do_validation = True
        if author is None:
            author = self.get_request_user()
            do_validation = False
        if not isinstance(author, User) and author is not None:
            raise ValidationError(detail={self.author_kw: "Wrong type"})
        if do_validation:
            # First, find meeting
            meeting = None
            if self.instance:
                if isinstance(self.instance, MeetingContext):
                    meeting = self.instance.meeting
            else:
                try:
                    meeting = meeting_from_unsafe_data(self)
                except ValidationError:
                    # Don't die here, there might be contexts outside meeting
                    meeting = None
            if meeting:
                user = self.get_request_user()
                if (
                    user is None
                    or user != author
                    and not user.has_perm(meeting.get_perm(PERM.MODERATE), meeting)
                ):
                    raise PermissionDenied(
                        detail={
                            self.author_kw: "You're not a moderator and may not specify author"
                        }
                    )
                if author not in meeting.participants.all():
                    raise ValidationError(
                        detail={self.author_kw: "Not an existing meeting participant"}
                    )
            else:
                raise ValidationError(
                    detail={
                        self.author_kw: "You've specified author outside of a meeting context"
                    }
                )
        attrs[self.author_kw] = author
        return attrs

    def validate_meeting_group(self, value: MeetingGroup | None):
        """
        - None is always allowed.
        - Moderators can post as any group.
        - Participants can post if they're members of that group.
        """
        from voteit.meeting.models import Meeting
        from voteit.meeting.models import MeetingGroup

        if value is None:
            return value

        user = self.get_request_user()
        if user is None:
            raise ValidationError(detail="Can't find posting user")
        assert isinstance(value, MeetingGroup)  # A weird bug we won't catch
        meeting = None
        if self.instance:
            # An operation on an existing object
            if not isinstance(self.instance, MeetingContext):
                raise ValidationError(detail="Not within a meeting")
            meeting = self.instance.meeting
        else:
            # Tricky part, validate add. Die here if no meeting is found
            meeting = meeting_from_unsafe_data(self)
        assert isinstance(meeting, Meeting)  # Programming bug,not a user error
        if not meeting.groups.filter(pk=value.pk).exists():
            raise ValidationError(_("Meeting group doesn't exist"))
        if (
            user.has_perm(Meeting.get_perm(PERM.MODERATE), meeting)
            or value.members.filter(pk=user.pk).exists()
        ):
            return value
        # Fail for anything else
        raise ValidationError(_("You're not a member of this group"))


class OptionalHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def to_representation(self, value):
        if "request" not in self.context:
            return None
        return super().to_representation(value)


class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = read_only_fields = (
            "pk",
            "email",
            "img_url",
            "image",
            "userid",
            "first_name",
            "last_name",
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        read_only_fields = (
            "pk",
            "img_url",
            "organisation",
        )
        fields = read_only_fields + (
            "userid",
            "first_name",
            "last_name",
            "email",
            "image",
        )

    def validate_userid(self, value: str):
        try:
            valid_userid(value)
        # FIXME We may want to change to djangos default exception
        except ValueError as exc:
            raise ValidationError(str(exc))
        user = self.context["request"].user
        if (
            self.Meta.model.objects.exclude(pk=user.pk)
            .filter(userid=value, organisation=user.organisation)
            .exists()
        ):
            raise ValidationError("Not unique, try something else")
        return value

    def validate_email(self, value: str):
        user = self.context["request"].user
        if user.email == value:
            return value
        valid_emails = get_idproxy_user_data(user).get("email", [])
        if value not in valid_emails:
            raise ValidationError(
                _("Email you specified isn't validated. It must exist on your profile.")
            )
        return value


class UserAndRolesSerializer(UserSerializer):
    """
    Expensive operation, should never be used with many objects, due to O(1+n).
    """

    organisation_roles = serializers.SerializerMethodField()

    def get_organisation_roles(self, instance: AbstractUser):
        roles = instance.organisation_roles.first()
        return [] if roles is None else roles.assigned

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ("organisation_roles",)


class MessageSerializer(serializers.Serializer):
    level = serializers.IntegerField()
    level_tag = serializers.CharField()
    message = serializers.CharField()
    tags = serializers.CharField()


class SMEventSerializer(serializers.Serializer):
    event = serializers.CharField(validators=[SMEventValidator()])

    def update(self, instance, validated_data):
        user = self.context["request"].user
        try:
            self.instance.sm.send(validated_data["event"], user=user)
        except ValidationError as exc:
            if isinstance(exc.detail, Mapping):
                raise exc from exc
            raise ValidationError({"event": exc.detail}) from exc
        except TransitionNotAllowed as exc:
            raise ValidationError({"event": str(exc)}) from exc
        self.instance.save()
        return self.instance


class StateSerializer(serializers.Serializer):
    name = serializers.CharField()
    id = serializers.CharField()


class SMTransitionSerializer(serializers.Serializer):
    source = StateSerializer()
    target = StateSerializer()
    events = serializers.ListSerializer(child=serializers.CharField())
    validators = serializers.ListSerializer(child=serializers.CharField())
    cond = serializers.ListSerializer(child=serializers.CharField())


class StateDetailSerializer(StateSerializer):
    transitions = SMTransitionSerializer(many=True)


class EventDetailSerializer(serializers.Serializer):
    name = serializers.CharField()
    id = serializers.CharField()


class StateMachineSerializer(serializers.Serializer):
    states = StateDetailSerializer(many=True)
    events = serializers.ListSerializer(child=EventDetailSerializer())
    qualname = serializers.SerializerMethodField()
    name = serializers.CharField()

    def get_qualname(self, sm: type[StateMachine]):
        return qualname(sm.__class__)


class PydanticFieldSerializer(serializers.JSONField):
    """
    Handles Pydantic representations and changes them to a rest friendly format.
    It doesn't force pydantic in any way, if it's not a pydantic model it's handled as JSON.
    Note that it has no knowledge of what schema it should expect.

    The encoder/decoder doesn't use pydantic either
    >>> from datetime import datetime

    >>> class Greeting(BaseModel):
    ...     msg: str = "Hello"
    ...     timestamp: datetime = datetime(year=1999, month=12, day=24)
    ...

    Any other object just passes through since this is not really a validator
    >>> field = PydanticFieldSerializer()
    >>> field.to_internal_value({"hello": 1})
    {'hello': 1}

    JSON will be handled via pydantic instead
    >>> result = field.to_internal_value(Greeting(msg="hello"))
    >>> result["msg"]
    'hello'
    >>> result["timestamp"]
    datetime.datetime(1999, 12, 24, 0, 0)

    Empty should be okay too
    >>> field.to_internal_value(None)

    Same goes for the other way around - a dict or pydantic model loaded from model field
    >>> field.to_representation({"hi": "there"})
    {'hi': 'there'}

    >>> result = field.to_representation(Greeting(msg="hello"))
    >>> result["msg"]
    'hello'
    >>> result["timestamp"]
    datetime.datetime(1999, 12, 24, 0, 0)
    """

    def __init__(self, *args, **kwargs):
        """Default to DjangoJSONEncoder since it handles more formats"""
        kwargs.setdefault("encoder", DjangoJSONEncoder)
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, BaseModel):
            data = data.dict()
        return super().to_internal_value(data)

    def to_representation(self, value):
        if isinstance(value, BaseModel):
            value = value.dict()
        return super().to_representation(value)


class RichTextSerializerMixin:
    """
    On models with body, tags and mentions, like voteit.core.models.BaseContent

    Beware of this since it overrides the validate method
    """

    partial: bool
    instance: BaseContent
    # Should body tags always exist within tags field?
    add_body_tags: bool = True
    add_body_mentions: bool = True

    def get_user_queryset(self, attrs: OrderedDict) -> models.QuerySet:
        """
        Figure out which queryset to use depending on what's sent in attrs.
        """
        meeting: Meeting | None = attrs.get("meeting", None)
        if isinstance(meeting, models.Model):
            return meeting.participants
        ai: AgendaItem | None = attrs.get("agenda_item", None)
        if isinstance(ai, models.Model):
            return ai.meeting.participants
        # We won't catch errors here. This is kind of the last chance to not "leak" data
        # about users through mentions, so if this doesn't work we need to raise a validation error.
        with suppress(AttributeError, ObjectDoesNotExist):
            return self.instance.meeting.participants
        with suppress(AttributeError, ObjectDoesNotExist):
            return self.instance.agenda_item.meeting.participants
        logger.warning(
            "There's no suitable context to pick up user mentions from. Serializer: %s Data:\n%s",
            self.__class__.__name__,
            attrs,
        )
        User = get_user_model()
        return User.objects.none()

    # FIXME: body might contain bad html-tags. That will be cleaned on save, but do we want to send error messages?
    def validate(self, attrs: OrderedDict):
        """
        We'll use this to populate attrs. Pretty silly but there's no other obvious way?
        """
        if self.partial and "body" not in attrs:
            body = self.instance.body
        else:
            body = attrs.get("body", "")
        if self.partial and "tags" not in attrs:
            tags = self.instance.tags and set(self.instance.tags) or set()
        else:
            tags = set(attrs.get("tags", []))
            # We only need to check updated
            if bad_tags := get_invalid_tags(tags):
                raise ValidationError(
                    {"tags": ["Tags with invalid format: %s" % ", ".join(bad_tags)]}
                )
        # Body tags
        if self.add_body_tags:
            body_tags = get_tagged_hashtags(body)
            if bad_tags := get_invalid_tags(body_tags):
                raise ValidationError(
                    {"body": ["Tags with invalid format: %s" % ", ".join(bad_tags)]}
                )
            tags.update(body_tags)
        # Proper tag check
        attrs["tags"] = sorted(tags)
        # Body mentions
        body_mentions = self.add_body_mentions and get_tagged_userids(body) or set()
        if self.partial and "mentions" not in attrs:
            mentions = set(self.instance.mentions.all().values_list("pk", flat=True))
        else:
            User = get_user_model()
            mentions = set(
                map(
                    lambda x: isinstance(x, User) and x.pk or x,
                    attrs.get("mentions", []),
                )
            )
        # Validate in 2 steps, so we know where things went wrong
        combined_mentions = mentions | body_mentions
        user_qs = self.get_user_queryset(attrs)
        found_users_qs = user_qs.filter(pk__in=combined_mentions)
        found_user_pks = set(found_users_qs.values_list("pk", flat=True))
        invalid = combined_mentions - found_user_pks
        if invalid:
            msg = _("You can only pick existing users within this meeting")
            if body_mentions - found_user_pks:
                raise ValidationError({"body": msg})
            raise ValidationError({"mentions": msg})
        attrs["mentions"] = list(found_users_qs)
        return super().validate(attrs)


class ExportBaseSerializerMixin(serializers.Serializer):
    userid = serializers.CharField(source="author.userid", required=False)
    group_title = serializers.CharField(source="meeting_group.title", required=False)
    group_id = serializers.CharField(source="meeting_group.groupid", required=False)
    tags = serializers.SerializerMethodField()

    class Meta:
        fields = ["userid", "group_title", "group_id", "tags"]

    def get_tags(self, obj):
        if hasattr(obj, "tags"):
            return ",".join(obj.tags)
        return ""
