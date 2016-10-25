from django.contrib import admin

# Register your models here.
from api.models import SwitchApp, SwitchAppGraph, SwitchComponent, SwitchComponentClass, SwitchComponentType, SwitchAppGraphService

admin.site.register(SwitchApp)
admin.site.register(SwitchAppGraph)
admin.site.register(SwitchComponent)
admin.site.register(SwitchComponentType)
admin.site.register(SwitchComponentClass)
admin.site.register(SwitchAppGraphService)