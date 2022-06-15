from __future__ import annotations

import os
import traceback

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from django.db import transaction
from django.db.models import Model
from dolly.core import Importer

from voteit.discussion.models import DiscussionPost
from voteit.organisation.models import Organisation
from voteit.poll.app.polls.combined_simple import CombinedSimplePollResult
from voteit.poll.app.polls.combined_simple import CombinedSimpleVoteSchema
from voteit.poll.app.polls.dutt import DuttResultSchema
from voteit.poll.app.polls.dutt import DuttVoteSchema
from voteit.poll.app.polls.majority import MajorityPollResult
from voteit.poll.app.polls.majority import MajorityVoteSchema
from voteit.poll.app.polls.schulze import RepeatedSchulzeResult
from voteit.poll.app.polls.schulze import SchulzePollResult
from voteit.poll.app.polls.schulze import SchulzeVoteSchema
from voteit.poll.app.polls.scottish_stv import STVResultSchema
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.schemas import RankingSchema
from voteit.proposal.models import Proposal
from voteit.reactions.models import Reaction
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem


class Command(BaseCommand):
    help = "Import all organisation related things. Create a new organisation or merge with an existing."

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            help="Input file to read from",
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help='Nominates a specific database to load fixtures into. Defaults to the "default" database.',
        )
        parser.add_argument(
            "--dry-run",
            default=False,
            action="store_true",
            help="Do nothing, just report",
        )
        parser.add_argument(
            "--merge",
            help="Merge with this organisation pk. The organisation object itself won't be imported.",
        )
        # parser.add_argument(
        #     "-o",
        #     help="Output filemap",
        # )
        parser.add_argument(
            "--reuse-userid",
            help="Reuse organisation users with the same userid. "
            "It only works on existing organisations with --merge.",
            default=False,
            action="store_true",
        )

    def handle(self, *args, **options):
        rel_fn = options["filename"]
        reuse_userid = options["reuse_userid"]
        merge_org = options["merge"]
        if not merge_org and reuse_userid:
            raise ValueError("reuse userid can only be specified together with merge.")
        dry_run = options["dry_run"]
        # quiet = options["quiet"]
        if dry_run:  # and not quiet:
            print("!! Dry run - nothing will be saved !!")
        filename = os.path.join(os.getcwd(), rel_fn)
        importer = Importer.from_filename(filename)
        importer.print_log = True
        # There are some reverse dependencies here, but they're for attributes we don't really need to care about
        # so we'll simply ignore them to solve the conflict.
        # This will destroy data, but active list or speaker should never be imported anyway.
        importer.add_clear_attrs(SpeakerListSystem, "active_list")
        importer.add_clear_attrs(SpeakerList, "current")
        importer.add_clear_attrs(Organisation, "author", "last_modified_by")
        importer.add_pre_save(Reaction, update_reactions_reference)
        importer.add_pre_commit(update_all_poll_results)
        importer.add_pre_commit(update_all_votes)
        importer.add_pre_commit(verify_json_attrs)
        importer.add_explicit_dependency(Reaction, Proposal, DiscussionPost)
        if merge_org:
            assert len(importer.data.get(Organisation, [])) == 1
            deserialized_org = next(iter(importer.data[Organisation]))
            org = Organisation.objects.get(pk=merge_org)
            importer.replace_deserialized_object(deserialized_org, org)
            importer.add_log(
                mod=Organisation,
                act="merge",
                msg=f"Replacing organisation from import with organisation we want to merge with",
            )
            User = get_user_model()
            # Since the exclude operation is a bit more complex than just keywords we'll do it semi-manual here.
            # Even if this is slower, we make sure that we'll never match users outside of this org.
            exclude_qs = User.objects.all().exclude(organisation=org).distinct()
            attrs = ["username", "email"]
            if reuse_userid:
                attrs.append("userid")
            for attr in attrs:
                round_qs = importer.match_and_update(User, attr, exclude_qs=exclude_qs)
                exclude_qs = round_qs | exclude_qs
        try:
            with transaction.atomic(durable=True):
                importer()
                if dry_run:
                    print("!! DRY-RUN - nothing saved !!")
                    transaction.set_rollback(True)
        except Exception as exc:
            traceback.print_exc()
        else:
            print("DONE!")


def verify_json_attrs(importer):
    for deserialized in importer.data.get(Poll, ()):
        for attr in ["settings", "result"]:
            verify_schema_attr(deserialized.object, attr)
    for deserialized in importer.data.get(Vote, ()):
        verify_schema_attr(deserialized.object, "vote")
    for deserialized in importer.data.get(SpeakerListSystem, ()):
        verify_schema_attr(deserialized.object, "settings")


def verify_schema_attr(obj, attr):
    """
    Touch attributes that will validate stored json data.
    """
    try:
        getattr(obj, attr)
    except ValueError as exc:
        print(f"{obj} caused error. obj PK: {obj.pk} - attr: {attr}")
        raise exc


def remap_schulze_round(importer, result: dict):
    new_pairs = []
    for pair in result.pairs:
        # [ [1,2], v]
        remapped = []
        for x in pair[0]:
            remapped.append(importer.get_remap_obj(Proposal, x).pk)
        new_pairs.append([remapped, pair[1]])
    result.pairs = new_pairs
    result.candidates = [
        importer.get_remap_obj(Proposal, x).pk for x in result.candidates
    ]
    result.winner = importer.get_remap_obj(Proposal, result.winner).pk
    strong_new_pairs = []
    for pair in result.strong_pairs:
        # [ [1,2], v]
        remapped = []
        for x in pair[0]:
            remapped.append(importer.get_remap_obj(Proposal, x).pk)
        strong_new_pairs.append([remapped, pair[1]])
    result.strong_pairs = strong_new_pairs
    if result.tied_winners:
        result.tied_winners = [
            importer.get_remap_obj(Proposal, x).pk for x in result.tied_winners
        ]


def update_all_poll_results(importer: Importer):
    """
    Polls and proposals have relations to each other but we can't assume proposals are processed first.
    """

    for deserialized in importer.data.get(Poll, ()):
        if not deserialized.object.result_data:
            continue
        method_name = deserialized.object.method_name
        result = deserialized.object.result
        result.denied = [importer.get_remap_obj(Proposal, x).pk for x in result.denied]
        result.approved = [
            importer.get_remap_obj(Proposal, x).pk for x in result.approved
        ]
        if method_name == "combined_simple":
            result: CombinedSimplePollResult
            reformatted = {}
            for (k, v) in result.results.items():
                reformatted[importer.get_remap_obj(Proposal, k).pk] = v
            result.results = reformatted
        elif method_name == "majority":
            result: MajorityPollResult
            for prop_result in result.results:
                prop_result.proposal = importer.get_remap_obj(
                    Proposal, prop_result.proposal
                ).pk
        elif method_name == "dutt":
            result: DuttResultSchema
            for prop_result in result.results:
                prop_result.proposal = importer.get_remap_obj(
                    Proposal, prop_result.proposal
                ).pk
        elif method_name == "schulze":
            result: SchulzePollResult
            remap_schulze_round(importer, result)
        elif method_name == "repeated_schulze":
            result: RepeatedSchulzeResult
            result.candidates = [
                importer.get_remap_obj(Proposal, x).pk for x in result.candidates
            ]
            for res_round in result.rounds:
                remap_schulze_round(importer, res_round)
        elif method_name == "scottish_stv":
            result: STVResultSchema
            for stv_round in result.rounds:
                stv_round.selected = [
                    importer.get_remap_obj(Proposal, x).pk for x in stv_round.selected
                ]
                stv_round.vote_count = [
                    (importer.get_remap_obj(Proposal, k).pk, v)
                    for k, v in stv_round.vote_count
                ]
        else:
            raise ValueError(
                f"Need to handle remapping of results for method {method_name}"
            )
        deserialized.object.result = result.dict()
        Model.save_base(deserialized.object, raw=True)


def update_all_votes(importer: Importer):
    """
    Votes relate to proposals that will have changed PK. The json-data in votes must be changed too.
    """
    for deserialized in importer.data.get(Vote, []):
        vote: Vote = deserialized.object
        if vote.abstain:
            continue
        method_name = vote.poll.method_name
        vote_data = vote.vote
        if method_name == "combined_simple":
            vote_data: CombinedSimpleVoteSchema
            for attr in ("yes", "no", "abstain"):
                new_pks = [
                    importer.get_remap_obj(Proposal, pk).pk
                    for pk in getattr(vote_data, attr)
                ]
                setattr(vote_data, attr, new_pks)
        elif method_name == "majority":
            vote_data: MajorityVoteSchema
            vote_data.choice = importer.get_remap_obj(Proposal, vote_data.choice).pk
        elif method_name == "dutt":
            vote_data: DuttVoteSchema
            vote_data.choices = [
                importer.get_remap_obj(Proposal, pk).pk for pk in vote_data.choices
            ]
        elif method_name in ("schulze", "repeated_schulze"):
            vote_data: SchulzeVoteSchema
            vote_data.ranking = [
                (importer.get_remap_obj(Proposal, pk).pk, rank)
                for (pk, rank) in vote_data.ranking
            ]
        elif method_name in ("irv", "scottish_stv"):
            vote_data: RankingSchema
            vote_data.choices = [
                importer.get_remap_obj(Proposal, pk).pk for pk in vote_data.choices
            ]
        else:
            raise ValueError(
                f"Need to handle remapping of vote for method {method_name}"
            )
        vote.vote = vote_data
        Model.save_base(vote, raw=True)


def update_reactions_reference(importer: Importer, *items: Reaction):
    for reaction in items:
        model = reaction.content_type.model_class()
        reaction.object = importer.get_remap_obj(model, reaction.object_id)
