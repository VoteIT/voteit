from django.db.models import QuerySet
from rest_framework import exceptions
from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import RichTextSerializerMixin
from voteit.core.rest_api.validators import ValidateGroupAIContext
from voteit.core.utils import get_model_shortname
from voteit.proposal.diff import Changes
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal

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

from voteit.proposal.models import TextDocument

from voteit.proposal.models import TextParagraph


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
    """

    registry = {}

    def __new__(cls, *args, **kwargs):
        shortname = kwargs.get("data", {}).get("shortname", None)
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

    def __new__(cls, instance, *args, **kwargs):
        if isinstance(instance, QuerySet) or isinstance(instance, list):
            return super().__new__(cls, instance=instance, *args, **kwargs)
        shortname = get_model_shortname(instance)
        try:
            serializer = cls.registry[shortname]
        except KeyError:
            raise exceptions.ValidationError({"shortname": "No such type"})
        return serializer(instance, *args, **kwargs)


class ProposalDetailSerializer(RichTextSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Proposal
        read_only_fields = [
            "author",
            "created",
            "state",
            "prop_id",
            "state",
            "pk",
            "agenda_item",
            "meeting_group",
            "name",
        ]
        fields = read_only_fields + [
            "body",
            "tags",
            "mentions",
        ]


class ProposalCreateSerializer(RichTextSerializerMixin, BaseModelSerializer):
    class Meta:
        model = Proposal
        fields = [
            "agenda_item",
            "body",
            "meeting_group",
            "tags",
            "mentions",
        ]
        validators = (ValidateGroupAIContext(),)


class DiffProposalCreateSerializer(ProposalCreateSerializer):
    class Meta(ProposalCreateSerializer.Meta):
        model = DiffProposal
        fields = ["paragraph"] + ProposalCreateSerializer.Meta.fields


class DiffProposalDetailSerializer(ProposalDetailSerializer):
    body_diff = serializers.SerializerMethodField()

    class Meta(ProposalDetailSerializer.Meta):
        model = DiffProposal
        read_only_fields = [
            "paragraph",
            "body_diff",
        ] + ProposalDetailSerializer.Meta.read_only_fields
        fields = read_only_fields + ProposalDetailSerializer.Meta.fields

    def get_body_diff(self, instance: DiffProposal) -> str:
        ch = Changes(instance.paragraph.body, instance.body)
        return ch.get_html(brief=False, no_deleted=False)


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
        ]


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
        ]

    def get_paragraphs(self, instance: TextDocument):
        return TextParagraphSerializer(
            instance.text_paragraphs.all().order_by("paragraph_id"), many=True
        ).data
