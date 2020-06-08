import json
from collections import Counter, MutableMapping
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from stvpoll.scottish_stv import ScottishSTV as _ScottishSTV

from voteit.poll.abcs import MultipleWinnerPollMethod
from voteit.poll.abcs import RankedVote
from voteit.poll.registries import poll_methods


class ScottishSTVVote(RankedVote):
    method = models.ForeignKey(
        'poll.ScottishSTV', on_delete=models.CASCADE, related_name='vote_set'
    )


@poll_methods
class ScottishSTV(MultipleWinnerPollMethod):
    """ Scottish STV, a ranked proportional vote method for multiple winners.
    """
    title = _("Scottish STV")
    vote_model = ScottishSTVVote
    proportional = True
    majority_winner = False
    min_losers = 1
    vote_set: models.Manager

    allow_random: bool = models.BooleanField(
        _('Allow random in tiebreaks'), default=True,
        help_text=_('Poll may yield incomplete result if random tiebreak is not allowed. '
                    'Random tiebreaks can sometimes affect the end result.')
    )
    # FIXME: We'll want to store the result in some other way i think /Robin
    result = models.TextField()

    def calculate_result(self, ballots: Counter):
        poll = _ScottishSTV(
            seats=self.winners,
            candidates=self.poll.proposals.all().values_list('id', flat=True),
            random_in_tiebreaks=self.allow_random,
        )
        for (ballot, count) in ballots.items():
            ballot_as_list = [int(r) for r in ballot.split(",")]
            poll.add_ballot(ballot_as_list, count)
        result = poll.calculate().as_dict()
        self.result = json.dumps(result, cls=_DecimalEncoder)
        return result

    def get_result(self) -> dict:
        return json.loads(self.result)


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super(_DecimalEncoder, self).default(o)
