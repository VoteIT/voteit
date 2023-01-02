from voteit.core.component import Registry
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.abcs import PollMethod


poll_methods = Registry(PollMethod)

# FIXME Rename to plural
er_policy = Registry(ElectoralRegisterPolicy)
