from django.contrib import admin

# Register your models here.
from api.models import Application, Component, ComponentClass, ComponentType, ServiceComponent

admin.site.register(Application)
admin.site.register(Component)
admin.site.register(ComponentType)
admin.site.register(ComponentClass)
admin.site.register(ServiceComponent)