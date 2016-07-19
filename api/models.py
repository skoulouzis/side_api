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


class SwitchApp(models.Model):
    user = models.ForeignKey(User)
    title = models.CharField(max_length=512)
    uuid = models.CharField(max_length=512)
    description = models.CharField(max_length=1024)

    class JSONAPIMeta:
        resource_name = "switchapps"


class SwitchAppGraph(models.Model):
    app = models.ForeignKey(SwitchApp, related_name='graphs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file = models.FileField(upload_to='graphs')

    class JSONAPIMeta:
        resource_name = "graphs"