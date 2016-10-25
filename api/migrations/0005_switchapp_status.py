# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_auto_20160915_1632'),
    ]

    operations = [
        migrations.AddField(
            model_name='switchapp',
            name='status',
            field=models.IntegerField(default=0),
        ),
    ]
