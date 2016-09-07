from __future__ import unicode_literals

import uuid as uuid
from django.contrib.auth.models import User
from django.db import models


class SwitchApp(models.Model):
    user = models.ForeignKey(User)
    title = models.CharField(max_length=512)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    description = models.CharField(max_length=1024, null=True)

    class JSONAPIMeta:
        resource_name = "switchapps"


class SwitchAppGraph(models.Model):
    app = models.ForeignKey(SwitchApp, related_name='graphs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file = models.FileField(upload_to='graphs')

    class JSONAPIMeta:
        resource_name = "graphs"


class SwitchComponent(models.Model):
    app = models.ForeignKey(SwitchApp, related_name='components')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uuid = models.UUIDField(editable=True)
    title = models.CharField(max_length=512, null=True)
    mode = models.CharField(max_length=512, null=True)
    type = models.CharField(max_length=512, null=True)
    properties = models.TextField(null=True)

    class JSONAPIMeta:
        resource_name = "switchcomponents"