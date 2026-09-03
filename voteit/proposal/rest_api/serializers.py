from contextlib import suppress
from typing import OrderedDict

from django.utils.text import slugify
from django.utils.translation import gettext as _
from rest_framework import exceptions
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import ExportBaseSerializerMixin
from voteit.core.rest_api.serializers import RichTextSerializerMixin
from voteit.core.rest_api.utils import meeting_from_unsafe_data
from voteit.core.rest_api.utils import validate_model_add
from voteit.core.rest_api.validators import ValidateGroupAIContext
from voteit.core.utils import get_model_shortname
from voteit.proposal.diff import Changes
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.models import TextParagraph

__all__ = (
    "GenericCreateProposalSerializer",
    "GenericProposalSerializer",
    "ProposalDetailSerializer",
    "ProposalCreateSerializer",
    "DiffProposalCreateSerializer",
    "DiffProposalDetailSerializer",
    "TextParagraphSerializer",
    "TextDocumentSerializer",
)


class GenericCreateProposalSerializer(serializers.Serializer):
    """
    Select serializer based on instance shortname.

    Don't subclass this, but register any model serializers you'd like to use.

    >>> serializer = GenericCreateProposalSerializer(data={'shortname': 'proposal'})
    >>> serializer.__class__.__name__
    'ProposalCreateSerializer'

    >>> serializer = GenericCreateProposalSerializer(data={'shortname': 'diff_proposal'})
    >>> serializer.__class__.__name__
    'DiffProposalCreateSerializer'

    The default is a regular proposal
    >>> serializer = GenericCreateProposalSerializer(data={})
    >>> serializer.__class__.__name__
    'ProposalCreateSerializer'
    """

    registry = {}

    def __new__(cls, *args, **kwargs):
        shortname = kwargs.get("data", {}).get("shortname", "proposal")
        if shortname is None:
            raise exceptions.ValidationError({"shortname": "Required"})
        try:
            serializer = cls.registry[shortname]
        except KeyError:
            raise exceptions.ValidationError({"shortname": "No such type"})
        return serializer(*args, **kwargs)


class GenericProposalSerializer(serializers.Serializer):
    """
    Select serializer based on instance shortname.

    Don't subclass this, but register any model serializers you'd like to use.

    >>> from voteit.proposal.models import Proposal
    >>> dummy = Proposal()
    >>> serializer = GenericProposalSerializer(dummy)
    >>> serializer.__class__.__name__
    'ProposalDetailSerializer'

    >>> from voteit.proposal.models import DiffProposal
    >>> diff_dummy = DiffProposal()
    >>> serializer = GenericProposalSerializer(diff_dummy)
    >>> serializer.__class__.__name__
    'DiffProposalDetailSerializer'
    """

    registry = {}

    def __new__(cls, instance, *args, many=False, **kwargs):
        if many:
            raise ValueError("Can't use many on this serializer")
        shortname = get_model_shortname(instance)
        try:
            serializer = cls.registry[shortname]
        except KeyError:
            raise exceptions.ValidationError({"shortname": "No such type"})
        return serializer(instance, *args, **kwargs)


class ProposalDetailSerializer(RichTextSerializerMixin, BaseModelSerializer):
    shortname = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        read_only_fields = [
            "created",
            "modified",
            "state",
            "prop_id",
            "state",
            "pk",
            "agenda_item",
            "shortname",
        ]
        fields = read_only_fields + [
            "author",
            "body",
            "meeting_group",
            "mentions",
            "tags",
            "as_group",
        ]

    def get_shortname(self, instance):
        return get_model_shortname(instance)


class ProposalCreateSerializer(RichTextSerializerMixin, BaseModelSerializer):
    prop_id = serializers.SerializerMethodField()

    def get_prop_id(self, instance):
        # FIXME Proposal id method should be used instead
        with suppress(AttributeError):
            return instance.prop_id
        meeting = meeting_from_unsafe_data(self)
        if suggestion := meeting.pid_policy.suggestion(
            author=instance.get("author"),
            meeting_group=instance.get("meeting_group"),
            as_group=instance.get("as_group"),
        ):
            return "%s-{n}" % suggestion

    class Meta:
        model = Proposal
        read_only_fields = [
            "pk",
            "prop_id",
        ]
        fields = [
            "author",
            "agenda_item",
            "body",
            "meeting_group",
            "mentions",
            "prop_id",
            "tags",
            "as_group",
        ] + read_only_fields
        validators = (ValidateGroupAIContext(),)
        extra_kwargs = {
            "agenda_item": {"required": True},
        }

    def validate_agenda_item(self, value):
        validate_model_add(self, Proposal, value)
        return value


class DiffProposalCreateSerializer(ProposalCreateSerializer):
    body_diff_brief = serializers.SerializerMethodField()

    class Meta(ProposalCreateSerializer.Meta):
        model = DiffProposal
        fields = [
            "paragraph",
            "body_diff_brief",
        ] + ProposalCreateSerializer.Meta.fields

    def get_body_diff(
        self, instance: OrderedDict | DiffProposal, brief: bool = False
    ) -> str:
        if isinstance(instance, DiffProposal):
            ch = Changes(instance.paragraph.body, instance.body)
        elif isinstance(instance, dict):
            para = instance["paragraph"]
            if isinstance(para, TextParagraph):
                para = para.pk
            text = TextParagraph.objects.get(pk=para)
            ch = Changes(text.body, instance["body"])
        else:
            raise TypeError("Not a diff proposal or a dict")
        return ch.get_html(brief=brief)

    def get_body_diff_brief(self, instance: OrderedDict | DiffProposal) -> str:
        return self.get_body_diff(instance, brief=True)

    def validate(self, attrs: OrderedDict):
        attrs = super().validate(attrs)
        if isinstance(attrs["paragraph"], TextParagraph):
            if attrs["paragraph"].body == attrs["body"]:
                raise ValidationError({"body": [_("Identical with original text")]})
        else:
            raise TypeError("Got something other than TextParagraph as 'paragraph'")
        return attrs

    def validate_agenda_item(self, value):
        validate_model_add(self, DiffProposal, value)
        return value


class DiffProposalDetailSerializer(ProposalDetailSerializer):
    body_diff_brief = serializers.SerializerMethodField()

    class Meta(ProposalDetailSerializer.Meta):
        model = DiffProposal
        read_only_fields = [
            "paragraph",
            "body_diff_brief",
        ] + ProposalDetailSerializer.Meta.read_only_fields
        fields = read_only_fields + ProposalDetailSerializer.Meta.fields

    def get_body_diff_brief(self, instance: DiffProposal) -> str:
        ch = Changes(instance.paragraph.body, instance.body)
        return ch.get_html(brief=True)

    def validate_body(self, value):
        if self.instance.paragraph.body == value:
            raise ValidationError(_("Identical with original text"))
        return value


GenericProposalSerializer.registry["proposal"] = ProposalDetailSerializer
GenericProposalSerializer.registry["diff_proposal"] = DiffProposalDetailSerializer
GenericCreateProposalSerializer.registry["proposal"] = ProposalCreateSerializer
GenericCreateProposalSerializer.registry["diff_proposal"] = DiffProposalCreateSerializer


class TextParagraphSerializer(serializers.ModelSerializer):
    class Meta:
        model = TextParagraph
        read_only_fields = [
            "paragraph_id",
            "pk",
            "body",
            "tag",
        ]
        fields = read_only_fields


def adjust_tag(value: str) -> str:
    return slugify(value)[:25]


class CreateTextDocumentSerializer(BaseModelSerializer):
    class Meta:
        model = TextDocument
        read_only_fields = [
            "created",
            "modified",
            "pk",
        ]
        fields = read_only_fields + [
            "agenda_item",
            "body",
            "base_tag",
            "title",
        ]
        extra_kwargs = {
            "agenda_item": {"required": True},
        }

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        attrs["base_tag"] = base_tag = adjust_tag(attrs["base_tag"])
        ai = attrs["agenda_item"]
        if isinstance(ai, AgendaItem):
            ai = ai.pk
        if TextDocument.objects.filter(agenda_item=ai, base_tag=base_tag).exists():
            raise ValidationError({"base_tag": _("Must be unique for agenda item")})
        return attrs

    def validate_agenda_item(self, value):
        validate_model_add(self, TextDocument, value)
        return value


class TextDocumentSerializer(serializers.ModelSerializer):
    paragraphs = serializers.SerializerMethodField()

    class Meta:
        model = TextDocument
        read_only_fields = [
            "created",
            "modified",
            "pk",
            "agenda_item",
            "paragraphs",
        ]
        fields = read_only_fields + [
            "body",
            "base_tag",
            "title",
        ]

    def get_paragraphs(self, instance: TextDocument):
        return list(
            TextParagraphSerializer(
                instance.text_paragraphs.all().order_by("paragraph_id"), many=True
            ).data
        )

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        if "base_tag" in attrs:
            attrs["base_tag"] = base_tag = adjust_tag(attrs["base_tag"])
            if (
                self.instance.agenda_item.text_documents.filter(base_tag=base_tag)
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                raise ValidationError({"base_tag": _("Must be unique for agenda item")})
        return attrs


class GenericExportProposalSerializer(serializers.Serializer):
    """
    Select serializer based on instance shortname.

    Don't subclass this, but register any model serializers you'd like to use.

    >>> from voteit.proposal.models import Proposal
    >>> dummy = Proposal()
    >>> serializer = GenericExportProposalSerializer(dummy)
    >>> serializer.__class__.__name__
    'ExportProposalSerializer'

    >>> from voteit.proposal.models import DiffProposal
    >>> diff_dummy = DiffProposal()
    >>> serializer = GenericExportProposalSerializer(diff_dummy)
    >>> serializer.__class__.__name__
    'ExportDiffProposalSerializer'
    """

    registry = {}

    def __new__(cls, instance, *args, many=False, **kwargs):
        if many:
            raise ValueError("Can't use many on this serializer")
        shortname = get_model_shortname(instance)
        try:
            serializer = cls.registry[shortname]
        except KeyError:
            raise exceptions.ValidationError({"shortname": "No such type"})
        return serializer(instance, *args, **kwargs)

    @classmethod
    def get_all_field_names(cls) -> list[str]:
        result = list(cls.registry["proposal"].Meta.fields)
        for serializer in [
            serializer
            for (name, serializer) in cls.registry.items()
            if name != "proposal"
        ]:
            for fname in serializer.Meta.fields:
                if fname not in result:
                    result.append(fname)
        return result


class ExportProposalSerializer(ProposalDetailSerializer, ExportBaseSerializerMixin):
    class Meta(DiffProposalDetailSerializer.Meta):
        fields = (
            list(
                x for x in ProposalDetailSerializer.Meta.fields if x not in ["mentions"]
            )
            + ExportBaseSerializerMixin.Meta.fields
        )


class ExportDiffProposalSerializer(
    ExportBaseSerializerMixin, DiffProposalDetailSerializer
):
    class Meta(DiffProposalDetailSerializer.Meta):
        fields = (
            list(
                x
                for x in DiffProposalDetailSerializer.Meta.fields
                if x not in ["body_diff_brief", "mentions"]
            )
            + ExportBaseSerializerMixin.Meta.fields
        )


GenericExportProposalSerializer.registry["proposal"] = ExportProposalSerializer
GenericExportProposalSerializer.registry["diff_proposal"] = ExportDiffProposalSerializer
