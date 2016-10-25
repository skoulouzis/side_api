# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_switchapp'),
    ]

    operations = [
        migrations.CreateModel(
            name='SwitchAppGraph',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('file', models.FileField(upload_to='graphs')),
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
            ],
        ),
        migrations.RemoveField(
            model_name='todoitem',
            name='user',
        ),
        migrations.AddField(
            model_name='switchapp',
            name='public_editable',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='switchapp',
            name='public_view',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='switchapp',
            name='description',
            field=models.CharField(max_length=1024, null=True),
        ),
        migrations.AlterField(
            model_name='switchapp',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.DeleteModel(
            name='TodoItem',
        ),
        migrations.AddField(
            model_name='switchcomponent',
            name='app',
            field=models.ForeignKey(related_name='components', to='api.SwitchApp'),
        ),
        migrations.AddField(
            model_name='switchappgraph',
            name='app',
            field=models.ForeignKey(related_name='graphs', to='api.SwitchApp'),
        ),
    ]
