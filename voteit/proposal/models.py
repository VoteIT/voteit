from django.db import models

# Create your models here.
from voteit.core.models import BaseContent


class Proposal(BaseContent):
    prop_id = models.CharField(max_length=50)
