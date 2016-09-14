from __future__ import unicode_literals

import uuid as uuid
from django.contrib.auth.models import User
from django.db import models

from api import admin


class SwitchApp(models.Model):
    user = models.ForeignKey(User)
    title = models.CharField(max_length=512)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    description = models.CharField(max_length=1024, null=True)
    public_view = models.BooleanField(default=False)
    public_editable = models.BooleanField(default=False)

    class JSONAPIMeta:
        resource_name = "switchapps"

    def __unicode__(self):
        return 'SwitchApp: ' + self.title + ' by ' + self.user.username


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

    def __unicode__(self):
        return 'SwitchApp: ' + self.title + '(' + str(self.uuid) + ') in ' + self.app.title


class SwitchComponentAdmin(admin.ModelAdmin):
    fields = ('title', 'uuid', 'app_title')