from rules import Predicate
from voteit.core.permission import PermissionRegistry

from voteit.core.permission import Permission
from voteit.core.predicate import PredicateRegistry


predicates = PredicateRegistry(Predicate)
permissions = PermissionRegistry(Permission)
