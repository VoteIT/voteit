from django.db.models import Manager
from model_utils.managers import InheritanceQuerySet


class AutoInheritanceQuerySet(InheritanceQuerySet):
    def instance_of(self, *models):
        """Disabled here. It may not work when forcing select_subclasses()"""
        raise NotImplementedError(
            "Not available in AutoInheritanceManager. Use plain InheritanceManager for this."
        )


class AutoInheritanceManager(Manager):
    _queryset_class = AutoInheritanceQuerySet

    def get_queryset(self):
        return self._queryset_class(self.model).select_subclasses()
