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
            name='ComponentClass',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='ComponentPort',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('type', models.CharField(max_length=512, null=True)),
                ('title', models.CharField(max_length=512, null=True)),
                ('uuid', models.CharField(max_length=512, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='ComponentType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512, null=True)),
                ('primary_colour', models.CharField(max_length=512, null=True)),
                ('secondary_colour', models.CharField(max_length=512, null=True)),
                ('icon_name', models.CharField(max_length=1024, null=True)),
                ('icon_style', models.CharField(max_length=1024, null=True)),
                ('icon_class', models.CharField(max_length=1024, null=True)),
                ('icon_svg', models.CharField(max_length=1024, null=True)),
                ('icon_code', models.CharField(max_length=512, null=True)),
                ('icon_colour', models.CharField(max_length=512, null=True)),
                ('switch_class', models.ForeignKey(related_name='types', to='api.ComponentClass')),
            ],
        ),
        migrations.CreateModel(
            name='GraphBase',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='Instance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('uuid', models.UUIDField()),
                ('title', models.CharField(max_length=512, null=True)),
                ('mode', models.CharField(max_length=512, null=True)),
                ('properties', models.TextField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_x', models.IntegerField(default=0, null=True)),
                ('last_y', models.IntegerField(default=0, null=True)),
                ('template', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='ServiceLink',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
        ),
        migrations.CreateModel(
            name='Application',
            fields=[
                ('graphbase_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.GraphBase')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('description', models.CharField(max_length=1024, null=True)),
                ('public_view', models.BooleanField(default=False)),
                ('public_editable', models.BooleanField(default=False)),
                ('status', models.IntegerField(default=0)),
            ],
            bases=('api.graphbase',),
        ),
        migrations.CreateModel(
            name='Component',
            fields=[
                ('graphbase_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.GraphBase')),
                ('type', models.ForeignKey(related_name='components', to='api.ComponentType', null=True)),
            ],
            bases=('api.graphbase',),
        ),
        migrations.CreateModel(
            name='ComponentLink',
            fields=[
                ('instance_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.Instance')),
            ],
            bases=('api.instance',),
        ),
        migrations.CreateModel(
            name='NestedComponent',
            fields=[
                ('instance_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.Instance')),
                ('parent', models.ForeignKey(related_name='children', blank=True, to='api.NestedComponent', null=True)),
            ],
            bases=('api.instance',),
        ),
        migrations.CreateModel(
            name='ServiceComponent',
            fields=[
                ('instance_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='api.Instance')),
            ],
            bases=('api.instance',),
        ),
        migrations.AddField(
            model_name='servicelink',
            name='graph',
            field=models.ForeignKey(related_name='service_links', to='api.GraphBase'),
        ),
        migrations.AddField(
            model_name='servicelink',
            name='source',
            field=models.ForeignKey(related_name='sources', to='api.Instance'),
        ),
        migrations.AddField(
            model_name='servicelink',
            name='target',
            field=models.ForeignKey(related_name='targets', to='api.Instance'),
        ),
        migrations.AddField(
            model_name='instance',
            name='graph',
            field=models.ForeignKey(related_name='instances', to='api.GraphBase'),
        ),
        migrations.AddField(
            model_name='instance',
            name='neighbors',
            field=models.ManyToManyField(to='api.Instance', through='api.ServiceLink'),
        ),
        migrations.AddField(
            model_name='graphbase',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='instance',
            name='component',
            field=models.ForeignKey(related_name='child_instances', to='api.Component'),
        ),
        migrations.AddField(
            model_name='componentport',
            name='instance',
            field=models.ForeignKey(related_name='ports', to='api.NestedComponent'),
        ),
        migrations.AddField(
            model_name='componentlink',
            name='source',
            field=models.ForeignKey(related_name='targets', blank=True, to='api.ComponentPort', null=True),
        ),
        migrations.AddField(
            model_name='componentlink',
            name='target',
            field=models.ForeignKey(related_name='sources', blank=True, to='api.ComponentPort', null=True),
        ),
    ]
