from voteit.core.component import FactoryRegistry
from voteit.poll.abcs import PollMethod, ElectoralRegisterPolicy


poll_methods = FactoryRegistry(PollMethod)

er_policy = FactoryRegistry(ElectoralRegisterPolicy)
