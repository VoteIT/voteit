from voteit.access_policy.abcs import AccessPolicy
from voteit.core.component import Registry


access_policies = Registry(AccessPolicy)
