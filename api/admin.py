from django.contrib import admin

# Register your models here.
from api.models import SwitchApp, SwitchAppGraph, SwitchComponent

admin.site.register(SwitchApp)
admin.site.register(SwitchAppGraph)
admin.site.register(SwitchComponent)