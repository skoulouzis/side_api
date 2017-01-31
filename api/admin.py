from django import forms
from django.contrib import admin

# Register your models here.
from api.models import Application, Component, ComponentClass, ComponentType, ComponentTypeProperty, \
    ServiceComponent, SwitchDocument, DataType, DataTypeProperty, ToscaClass, SwitchRepository, SwitchArtifact, \
    SwitchDocumentType, Notification


class ComponentTypePropertyInline(admin.TabularInline):
    model = ComponentTypeProperty


class ComponentTypeAdmin(admin.ModelAdmin):
    inlines = [
        ComponentTypePropertyInline,
    ]

class DataTypePropertyInline(admin.TabularInline):
    model = DataTypeProperty
    fk_name = 'parent_data_type'


class DataTypeAdmin(admin.ModelAdmin):
    inlines = [
        DataTypePropertyInline,
    ]


admin.site.register(Application)
admin.site.register(Component)
admin.site.register(ComponentType, ComponentTypeAdmin)
admin.site.register(ComponentTypeProperty)
admin.site.register(DataType, DataTypeAdmin)
admin.site.register(DataTypeProperty)
admin.site.register(ComponentClass)
admin.site.register(ToscaClass)
admin.site.register(SwitchRepository)
admin.site.register(SwitchArtifact)
admin.site.register(ServiceComponent)
admin.site.register(SwitchDocument)
admin.site.register(SwitchDocumentType)
admin.site.register(Notification)