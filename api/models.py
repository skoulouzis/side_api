from __future__ import unicode_literals

import uuid as uuid
from django.contrib.auth.models import User
from django.db import models
from django.contrib import admin


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


class SwitchComponentClass(models.Model):
    title = models.CharField(max_length=512, null=True)

    class JSONAPIMeta:
        resource_name = "switchcomponentclass"

    def __unicode__(self):
        return self.title


class SwitchComponentType(models.Model):
    title = models.CharField(max_length=512, null=True)
    switch_class = models.ForeignKey(SwitchComponentClass, related_name='types')
    primary_colour = models.CharField(max_length=512, null=True)
    secondary_colour = models.CharField(max_length=512, null=True)
    icon_svg = models.CharField(max_length=1024, null=True)
    icon_code = models.CharField(max_length=512, null=True)
    icon_colour = models.CharField(max_length=512, null=True)

    class JSONAPIMeta:
        resource_name = "switchcomponenttype"

    def __unicode__(self):
        return self.title


class SwitchComponent(models.Model):
    app = models.ForeignKey(SwitchApp, related_name='components')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uuid = models.UUIDField(editable=True)
    title = models.CharField(max_length=512, null=True)
    mode = models.CharField(max_length=512, null=True)
    type = models.CharField(max_length=512, null=True)
    switch_type = models.ForeignKey(SwitchComponentType, related_name='components', null=True)
    properties = models.TextField(null=True)

    class JSONAPIMeta:
        resource_name = "switchcomponents"

    def __unicode__(self):
        return 'SwitchApp: ' + self.title + '(' + str(self.uuid) + ') in ' + self.app.title


class SwitchAppGraphBase(models.Model):
    component = models.ForeignKey(SwitchComponent, related_name='graph_component')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    components = models.ManyToManyField('self', through='SwitchAppGraphServiceLink', symmetrical=False)
    type = models.CharField(max_length=512, null=True)
    last_x = models.IntegerField(null=True, default=0)
    last_y = models.IntegerField(null=True, default=0)

    class JSONAPIMeta:
        abstract = True


class SwitchAppGraphComponent(SwitchAppGraphBase):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')

    class JSONAPIMeta:
        resource_name = "graph_components"


class SwitchAppGraphPort(models.Model):
    graph_component = models.ForeignKey(SwitchAppGraphComponent, related_name='ports')
    type = models.CharField(max_length=512, null=True)
    title = models.CharField(max_length=512, null=True)

    class JSONAPIMeta:
        resource_name = "graph_ports"


class SwitchAppGraphComponentLink(SwitchAppGraphBase):
    source = models.ForeignKey(SwitchAppGraphPort, related_name='targets')
    target = models.ForeignKey(SwitchAppGraphPort, related_name='sources')

    class JSONAPIMeta:
        resource_name = "graph_connections"


class SwitchAppGraphServiceLink(models.Model):
    source = models.ForeignKey(SwitchAppGraphBase, related_name='sources')
    target = models.ForeignKey(SwitchAppGraphBase, related_name='targets')

    class JSONAPIMeta:
        resource_name = "graph_connections"


class SwitchAppGraphService(SwitchAppGraphBase):
    class JSONAPIMeta:
        resource_name = "graph_services"

    def __unicode__(self):
        return 'Service: ' + self.component.title + '(' + str(self.type) + ')'


class SwitchComponentAdmin(admin.ModelAdmin):
    fields = ('title', 'uuid', 'app_title')


# class SwitchComponentClassAdmin(admin.ModelAdmin):
#     fields = ('title')
#
#
# class SwitchComponentTypeAdmin(admin.ModelAdmin):
#     fields = ('title', 'switch_class', 'primary_colour', 'secondary_colour', 'icon_colour', 'icon_svg', 'icon_code')