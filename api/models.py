from __future__ import unicode_literals

from django.contrib.auth.models import User
from django.db import models


class TodoItem(models.Model):
    user = models.ForeignKey(User)
    label = models.CharField(max_length=512)
    text = models.TextField(null=True)
    done = models.BooleanField(default=False)

    class JSONAPIMeta:
        resource_name = "todos"