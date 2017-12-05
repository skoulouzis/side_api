from django import forms
from django.contrib import admin

# Register your models here.
from api.models import *


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


class ComponentInstanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'title')
    list_display_links = ('id', 'title')

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
admin.site.register(SwitchRequirement)
admin.site.register(ServiceComponent)
admin.site.register(SwitchDocument)
admin.site.register(SwitchDocumentType)
admin.site.register(Notification)
admin.site.register(ComponentInstance, ComponentInstanceAdmin)
admin.site.register(ComponentLink)
admin.site.register(ComponentPort)
admin.site.register(GraphBase)
