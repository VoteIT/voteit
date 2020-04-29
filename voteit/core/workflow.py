from abc import ABC, abstractmethod
from logging import getLogger
from typing import Dict, Union, List, Set, TypeVar, Tuple, Optional

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from voteit.core import signals
from voteit.core.component import FactoryRegistry

logger = getLogger(__name__)

ALL_STATES = TypeVar("ALL_STATES")


class Transition:
    """ Simple transition objects to keep track of which states connect.
        They always go from one point to another, and require a permission to do so.
    """

    from_state: str
    to_state: str
    permission: str = ""
    title: str = ""
    message: str = ""

    def __init__(self, from_state="", to_state="", permission="", title="", message=""):
        self.from_state = from_state
        self.to_state = to_state
        self.permission = permission
        self.title = title and title or to_state
        self.message = message

    @property
    def name(self) -> Tuple[str, str]:
        return self.from_state, self.to_state


class Workflow(ABC):
    title: str = ""
    description: str = ""
    logger = logger

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def initial_state(self) -> str:
        pass

    @property
    @abstractmethod
    def states(self) -> Dict:
        pass

    @property
    @abstractmethod
    def transitions(self) -> Dict:
        pass

    def __init__(self, context):
        self.context = context

    @property
    def state(self):
        if self.context.wf_state in self.states:
            return self.context.wf_state
        return self.initial_state

    @classmethod
    def add_transitions(
        cls,
        from_states: Union[ALL_STATES, List[str], str] = "",
        to_states: Union[ALL_STATES, List[str], str] = "",
        permission="__NOT_ALLOWED__",
        title=None,
        message=None,
        create_states=False,
    ) -> List[Transition]:
        """
        :param from_states: ALL_STATES or state name, or an iterator with state names.
        :param to_states: ALL_STATES or state name, or an iterator with state names.
        :param permission: The required permission
        :param title: Name of the transition, like "Publish"
        :param message: Message to display when it was executed, like "Item was published"
        :param create_states: Add states or raise error if they don't exist
        :return: created transition(s)
        """
        from_states = cls.get_states(from_states, create=create_states)
        to_states = cls.get_states(to_states, create=create_states)
        results = []
        for fstate in from_states:
            for tstate in to_states:
                if tstate == fstate:
                    continue
                transition = Transition(
                    from_state=fstate,
                    to_state=tstate,
                    permission=permission,
                    title=title and title or cls.states[tstate],
                    message=message,
                )
                if transition.name in cls.transitions:
                    logger.warning(
                        f"Overriding transition {transition.name} in workflow {cls.name}"
                    )
                cls.transitions[transition.name] = transition
                results.append(transition)
        return results

    @classmethod
    def get_states(
        cls, states: Union[ALL_STATES, List[str], str], create: bool = False
    ) -> Set[str]:
        found_states = set()
        if states == ALL_STATES:
            found_states.update(cls.states)
        elif isinstance(states, str):
            found_states.add(states)
        else:
            found_states.update(states)
        for state in found_states:
            if state not in cls.states:
                if create:
                    cls.states[state] = state
                else:
                    raise KeyError("No state called %r for %r" % (state, cls))
        if not found_states:
            raise ValueError("No states to work with")
        return found_states

    def get_transitions(
        self, from_state: Optional[str] = None, user: Optional[User] = None
    ) -> List[Transition]:
        results = []
        for (name, t) in self.transitions.items():
            if from_state is not None:
                if from_state != name[0]:
                    continue
            if user is not None:
                if not user.has_perm(t.permisson, obj=self.context):
                    continue
            results.append(t)
        return results

    def valid_transitions(self, user: User) -> List[Transition]:
        return self.get_transitions(from_state=self.state, user=user)

    def do_transition(self, to_state, user, signal=True, force=False) -> Transition:
        try:
            trans = self.transitions[(self.state, to_state)]
        except KeyError:
            raise ValueError(
                f"No transition from '{self.state}' to '{to_state}' for workflow {self}."
            )

        if not force and not user.has_perm(trans.permission, obj=self.context):
            # Correct exc?
            raise PermissionDenied()
        if signal:
            signals.before_transition.send(
                sender=self.context.__class__, instance=self.context, user=user, transition=trans
            )
        self.context.wf_state = to_state
        if signal:
            signals.after_transition.send(
                sender=self.context.__class__, instance=self.context, user=user, transition=trans
            )
        return trans


workflows = FactoryRegistry(Workflow)
