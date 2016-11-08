# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SwitchApp',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('description', models.CharField(max_length=1024, null=True)),
                ('public_view', models.BooleanField(default=False)),
                ('public_editable', models.BooleanField(default=False)),
                ('status', models.IntegerField(default=0)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='SwitchAppGraph',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('file', models.FileField(upload_to='graphs')),
                ('app', models.ForeignKey(related_name='graphs', to='api.SwitchApp')),
            ],
        ),
        migrations.CreateModel(
            name='SwitchAppGraphBase',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('type', models.CharField(max_length=512, null=True)),
                ('last_x', models.IntegerField(default=0, null=True)),
                ('last_y', models.IntegerField(default=0, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='SwitchAppGraphPort',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('type', models.CharField(max_length=512, null=True)),
                ('title', models.CharField(max_length=512, null=True)),
                ('uuid', models.CharField(max_length=512, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='SwitchAppGraphServiceLink',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
        ),
        migrations.CreateModel(
            name='SwitchComponent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('uuid', models.UUIDField()),
                ('title', models.CharField(max_length=512, null=True)),
                ('mode', models.CharField(max_length=512, null=True)),
                ('type', models.CharField(max_length=512, null=True)),
                ('properties', models.TextField(null=True)),
                ('app', models.ForeignKey(related_name='components', to='api.SwitchApp')),
            ],
        ),
        migrations.CreateModel(
            name='SwitchComponentClass',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='SwitchComponentType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512, null=True)),
                ('primary_colour', models.CharField(max_length=512, null=True)),
                ('secondary_colour', models.CharField(max_length=512, null=True)),
                ('icon_svg', models.CharField(max_length=1024, null=True)),
                ('icon_code', models.CharField(max_length=512, null=True)),
                ('icon_colour', models.CharField(max_length=512, null=True)),
                ('switch_class', models.ForeignKey(related_name='types', to='api.SwitchComponentClass')),
            ],
        ),
        migrations.CreateModel(
            name='SwitchAppGraphComponent',
            fields=[
                ('switchappgraphbase_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.SwitchAppGraphBase')),
                ('parent', models.ForeignKey(related_name='children', blank=True, to='api.SwitchAppGraphComponent', null=True)),
            ],
            bases=('api.switchappgraphbase',),
        ),
        migrations.CreateModel(
            name='SwitchAppGraphComponentLink',
            fields=[
                ('switchappgraphbase_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.SwitchAppGraphBase')),
            ],
            bases=('api.switchappgraphbase',),
        ),
        migrations.CreateModel(
            name='SwitchAppGraphService',
            fields=[
                ('switchappgraphbase_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.SwitchAppGraphBase')),
            ],
            bases=('api.switchappgraphbase',),
        ),
        migrations.AddField(
            model_name='switchcomponent',
            name='switch_type',
            field=models.ForeignKey(related_name='components', to='api.SwitchComponentType', null=True),
        ),
        migrations.AddField(
            model_name='switchappgraphservicelink',
            name='source',
            field=models.ForeignKey(related_name='sources', to='api.SwitchAppGraphBase'),
        ),
        migrations.AddField(
            model_name='switchappgraphservicelink',
            name='target',
            field=models.ForeignKey(related_name='targets', to='api.SwitchAppGraphBase'),
        ),
        migrations.AddField(
            model_name='switchappgraphbase',
            name='component',
            field=models.ForeignKey(related_name='graph_component', to='api.SwitchComponent'),
        ),
        migrations.AddField(
            model_name='switchappgraphbase',
            name='components',
            field=models.ManyToManyField(to='api.SwitchAppGraphBase', through='api.SwitchAppGraphServiceLink'),
        ),
        migrations.AddField(
            model_name='switchappgraphport',
            name='graph_component',
            field=models.ForeignKey(related_name='ports', to='api.SwitchAppGraphComponent'),
        ),
        migrations.AddField(
            model_name='switchappgraphcomponentlink',
            name='source',
            field=models.ForeignKey(related_name='targets', to='api.SwitchAppGraphPort'),
        ),
        migrations.AddField(
            model_name='switchappgraphcomponentlink',
            name='target',
            field=models.ForeignKey(related_name='sources', to='api.SwitchAppGraphPort'),
        ),
    ]
