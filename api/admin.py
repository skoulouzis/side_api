from django import forms
from django.contrib import admin

# Register your models here.
from api.models import Application, Component, ComponentClass, ComponentType, ComponentTypeProperty, ServiceComponent, SwitchDocument


class ComponentTypePropertyInline(admin.TabularInline):
    model = ComponentTypeProperty

class ComponentTypeAdmin(admin.ModelAdmin):
    inlines = [
        ComponentTypePropertyInline,
    ]

    def get_changeform_initial_data(self, request):
        return {'icon_name': 'custom_initial_value'}

admin.site.register(Application)
admin.site.register(Component)
admin.site.register(ComponentType, ComponentTypeAdmin)
admin.site.register(ComponentTypeProperty)
admin.site.register(ComponentClass)
admin.site.register(ServiceComponent)
admin.site.register(SwitchDocument)


