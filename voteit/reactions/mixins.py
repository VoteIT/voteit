from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from voteit.reactions.models import Reaction


class Reactable(models.Model):
    reaction_set = GenericRelation(Reaction)

    class Meta:
        abstract = True
