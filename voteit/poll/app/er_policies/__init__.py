def register():
    from .auto_always import AutoAlways  # noqa
    from .auto_before_poll import AutoBeforePoll  # noqa
    from .group_auto_rnd_before_poll import GroupAutoRandomBeforePoll  # noqa
    from .group_votes_before_poll import GroupVotesBeforePoll  # noqa
    from .main_or_subst_er import MainSubstActivePolicy  # noqa
    from .main_subst_delegate import MainSubstDelegatePolicy  # noqa
    from .presence_check import PresenceCheckPolicy  # noqa
    from .manual import Manual  # noqa
    from .manual_trigger import ManualTrigger  # noqa
