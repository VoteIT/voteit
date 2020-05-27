from voteit.core.component import Registry
from voteit.poll.abcs import PollMethod, ElectoralRegisterPolicy


poll_methods = Registry(PollMethod)

er_policy = Registry(ElectoralRegisterPolicy)
