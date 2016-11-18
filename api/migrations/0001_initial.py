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
            name='Application',
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
            name='Component',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
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
            ],
        ),
        migrations.CreateModel(
            name='ServiceLink',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('app', models.ForeignKey(related_name='service_links', to='api.Application')),
            ],
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
            name='app',
            field=models.ForeignKey(related_name='instances', to='api.Application'),
        ),
        migrations.AddField(
            model_name='instance',
            name='component',
            field=models.ForeignKey(related_name='instances', to='api.Component'),
        ),
        migrations.AddField(
            model_name='instance',
            name='neighbors',
            field=models.ManyToManyField(to='api.Instance', through='api.ServiceLink'),
        ),
        migrations.AddField(
            model_name='component',
            name='type',
            field=models.ForeignKey(related_name='components', to='api.ComponentType', null=True),
        ),
        migrations.AddField(
            model_name='component',
            name='user',
            field=models.ForeignKey(default=None, blank=True, to=settings.AUTH_USER_MODEL, null=True),
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
