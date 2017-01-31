from __future__ import unicode_literals

import yaml
import uuid as uuid
import sys
import hashlib
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.contrib import admin
from model_utils.managers import InheritanceManager
from side_api import utils

class GraphBase(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, default=None)
    title = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchgraphs"
        abstract = True

    def __unicode__(self):
        return 'SwitchGraph: ' + self.title

    def get_new_notifications(self):
        return self.notifications.filter(viewed=False)

    def get_instances(self):
        return Instance.objects.filter(graph=self).select_subclasses()

    def get_graph(self):
        response_cells = []
        instances = Instance.objects.filter(graph=self).select_subclasses()

        for instance in instances:
            try:
                graph_obj = instance.get_graph()
                response_cells.append(graph_obj)

            except Exception as e:
                print e.message

        for service_link in self.service_links.all():
            try:
                graph_obj = service_link.get_graph()
                response_cells.append(graph_obj)

                add_parent = True

                for cell in response_cells:
                    if 'id' in cell and cell['id'] == service_link.source.uuid:
                        if 'parent' in cell:
                            add_parent = False
                        else:
                            cell['parent'] = service_link.target.uuid

                if add_parent:
                    for cell in response_cells:
                        if 'id' in cell and cell['id'] == service_link.target.uuid:
                            cell.setdefault('embeds', [])
                            cell['embeds'].append(service_link.source.uuid)

            except Exception as e:
                print e.message

        return {
            'type': 'graphs',
            'id': str(self.id),
            'attributes': {
                'graph': {
                    'cells': response_cells
                }
            }
        }

    # this now just updates x/y of any component... nowt else :)
    def put_graph(self, json_data):
        try:
            for cell in json_data['cells']:  #
                instance = Instance.objects.filter(uuid=cell['id'], graph=self).select_subclasses().first()
                if 'position' in cell and cell['position'] is not None:
                    instance.last_x = cell['position']['x']
                    instance.last_y = cell['position']['y']
                    instance.save()
        except Exception as e:
            print e.message

    def clone_instances_in_graph(self, new_graph, x_change, y_change, new_instance=None):
        instance_translations = {}
        port_translations = {}

        for instance in Instance.objects.filter(graph=self).all():
            old_pk = instance.pk

            # we've already created the a copy of the base_instance via the serializer
            # done because ComponentLinks was messing up (wrong id was being returned!)
            if instance.component.pk == self.pk and new_instance is not None:
                instance = new_instance
            else:
                instance.pk = None
                instance.id = None
                instance.graph = new_graph
                instance.uuid = uuid.uuid4()
                instance.last_x = instance.last_x - x_change
                instance.last_y = instance.last_y - y_change
                instance.save()

            instance_translations[old_pk] = instance.pk

            if instance.component.type.switch_class.title == 'switch.Component' or instance.component.type.switch_class.title == 'switch.Group':
                nested_component = NestedComponent(instance_ptr=instance)
                nested_component.save_base(raw=True)

                for port in ComponentPort.objects.filter(instance_id=old_pk).all():
                    old_port_pk = port.pk
                    port.pk = None
                    port.id = None
                    port.instance = instance
                    port.uuid = uuid.uuid4()
                    port.save()
                    port_translations[old_port_pk] = port.pk

            elif instance.component.type.switch_class.title == 'switch.VirtualResource' or instance.component.type.switch_class.title == 'switch.Attribute':
                service_component = ServiceComponent(instance_ptr=instance)
                service_component.save_base(raw=True)

            elif instance.component.type.switch_class.title == 'switch.ComponentLink':
                component_link = ComponentLink(instance_ptr=instance)
                component_link.save_base(raw=True)

        for original_nested_component_inside_group in NestedComponent.objects.filter(graph=self, parent__isnull=False):
            nested_component_inside_group = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.id]).first()
            group_nested_component = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.parent.id]).first()
            nested_component_inside_group.parent = group_nested_component
            nested_component_inside_group.save()

        for original_component_link in ComponentLink.objects.filter(graph=self).all():
            component_link = ComponentLink.objects.filter(instance_ptr_id=instance_translations[original_component_link.id]).first()
            component_link.source_id = port_translations[original_component_link.source_id]
            component_link.target_id = port_translations[original_component_link.target_id]
            component_link.save()

        for service_link in ServiceLink.objects.filter(graph=self).all():
            service_link.pk = None
            service_link.id = None
            service_link.graph = new_graph
            service_link.source_id = instance_translations[service_link.source_id]
            service_link.target_id = instance_translations[service_link.target_id]
            service_link.uuid = uuid.uuid4()
            service_link.save()

    def get_current_graph_dimensions(self):
        top_x = sys.maxint
        top_y = sys.maxint
        bottom_x = 0
        bottom_y = 0
        instances = Instance.objects.filter(graph=self).select_subclasses()

        for instance in instances:
            if instance.last_x < top_x:
                top_x = instance.last_x
            if instance.last_y < top_y:
                top_y = instance.last_y
            if instance.last_x > bottom_x:
                bottom_x = instance.last_x
            if instance.last_y > bottom_y:
                bottom_y = instance.last_y
        return {
            'top_x': top_x,
            'top_y': top_y,
            'bottom_x': bottom_x,
            'bottom_y': bottom_y,
        }


class Notification(models.Model):

    class JSONAPIMeta:
        resource_name = "switchnotifications"

    def __unicode__(self):
        return 'Notification: title=' + self.title + ' message=' + self.message + ' graph=' + self.graph.title

    graph = models.ForeignKey(GraphBase, related_name='notifications')
    title = models.CharField(max_length=512)
    message = models.CharField(max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    severity = models.IntegerField(default=0)
    viewed = models.BooleanField(default=False)


class Application(GraphBase):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    description = models.CharField(max_length=1024, blank=True)
    public_view = models.BooleanField(default=False)
    public_editable = models.BooleanField(default=False)
    # Status: 0 no plan virtual infrastructure; 1 planned; 2 provisioned; 3 deployed
    status = models.IntegerField(default=0)

    class JSONAPIMeta:
        resource_name = "switchapps"

    def __unicode__(self):
        return 'SwitchApp: ' + self.title + ' by ' + self.user.username

    def get_tosca(self):
        repositories = {}
        for repository in SwitchRepository.objects.all():
            repositories.update(repository.get_tosca())

        artifact_types = {}
        for tosca_class in ToscaClass.objects.filter(type=ToscaClass.ARTIFACT_TYPE, is_normative=False).all():
            artifact_types.update(tosca_class.get_tosca())

        data_types = {}
        for data_type in DataType.objects.filter(parent__isnull=False).all():
            data_types.update(data_type.get_tosca())

        node_types = {}
        for node_type in ComponentType.objects.all():
            node_types.update(node_type.get_tosca())

        data = {}
        data['tosca_definitions_version'] = "tosca_simple_yaml_1_0"
        data['description'] = self.description
        data['artifact_types'] = artifact_types
        data['data_types'] = data_types
        data['node_types'] = node_types
        data['repositories'] = repositories

        data['topology_template']={}
        node_templates = data['topology_template'].setdefault('node_templates', {})

        groups = {}

        instances = Instance.objects.filter(graph=self).select_subclasses()
        for instance in instances:
            graph_obj = instance.get_tosca()
            if instance.component.type.get_base_type().title == 'Component':
                node_templates.update(graph_obj)
            # elif instance.component.type.title == 'External Component':
            #     external.append(graph_obj)
            elif instance.component.type.get_base_type().title == 'Component Group':
                 groups.update(graph_obj)
            elif instance.component.type.get_base_type().title == 'Component Link':
                node_templates.update(graph_obj)
            # elif instance.component.type.title == 'Network':
            #     network.append(graph_obj)
            elif instance.component.type.get_base_type().title == 'Virtual Machine':
                node_templates.update(graph_obj)
            elif instance.component.type.get_base_type().title == 'Virtual Network':
                 node_templates.update(graph_obj)
            elif instance.component.type.switch_class.title == 'switch.Attribute':
                if instance.component.type.title == 'Monitoring Agent':
                    node_templates.update(graph_obj)

        data['groups'] = groups

        return {
            'data': data
        }


class DataType(models.Model):
    name = models.CharField(max_length=512)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')
    default_value = models.TextField(blank=True)

    class JSONAPIMeta:
        resource_name = "switchdatatypes"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        if self.parent is not None:
            obj_definition['derived_from'] = self.parent.name
        if self.properties.count() > 0:
            properties = {}
            for property in self.properties.all():
                properties.update(property.get_tosca())
            obj_definition['properties'] = properties
        return {self.name:obj_definition}

    def get_default_value(self):
        if self.default_value:
            return yaml.load(str(self.default_value).replace("\t", "    "))
        else:
            properties = {}

            if self.parent is not None:
                properties.update(self.parent.get_default_value())

            for data_type_property in self.properties.all():
                properties[data_type_property.name] = data_type_property.get_default_value()

            return properties


class DataTypeProperty(models.Model):
    name = models.CharField(max_length=512)
    data_type = models.ForeignKey(DataType)
    default_value = models.TextField(blank=True)
    is_collection = models.BooleanField(default=False)
    parent_data_type = models.ForeignKey(DataType, related_name='properties')

    class Meta:
        verbose_name_plural = "Data type properties"

    class JSONAPIMeta:
        resource_name = "switchdatatypeproperties"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        if self.is_collection:
            obj_definition['type'] = 'map'
            obj_definition['entry_schema'] = {'type':self.data_type.name}
        else:
            obj_definition['type'] = self.data_type.name
        return {self.name: obj_definition}

    def get_default_value(self):
        if self.default_value:
            return yaml.load(str(self.default_value).replace("\t", "    "))
        else:
            if self.is_collection:
                map = {}
                for x in range(0, 3):
                    map[self.data_type.name.rpartition('.')[2] + '_' + str(x)] = self.data_type.get_default_value()
                return map
            else:
                return self.data_type.get_default_value()


class ToscaClass(models.Model):
    NODE_TYPE = 'N'
    ARTIFACT_TYPE = 'A'
    GROUP_TYPE = 'G'
    TYPE_CHOICES = (
        (NODE_TYPE, 'Node type'),
        (ARTIFACT_TYPE, 'Artifact type'),
        (GROUP_TYPE, 'Group type')
    )

    name = models.CharField(max_length=512)
    type = models.CharField(
        max_length=2,
        choices=TYPE_CHOICES,
        default=NODE_TYPE,
    )
    parent = models.ForeignKey('self', null=True, blank=True)
    prefix = models.CharField(max_length=512)
    is_normative = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Tosca classes"

    class JSONAPIMeta:
        resource_name = "toscaclass"

    def __unicode__(self):
        return self.get_full_name()

    def get_full_name(self):
        return self.prefix + '.' + self.name

    def get_tosca(self):
        obj_definition = {}
        if self.parent is not None:
            obj_definition['derived_from'] = self.parent.get_full_name()
        return {self.get_full_name(): obj_definition}


class SwitchRepository(models.Model):
    name = models.CharField(max_length=512, unique=True)
    description = models.CharField(max_length=512, blank=True)
    url = models.URLField(max_length=512)
    credential = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Switch repositories"

    class JSONAPIMeta:
        resource_name = "switchrepository"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        if self.description:
            obj_definition['description'] = self.description
        obj_definition['url'] = self.url
        obj_definition['credential'] = yaml.load(str(self.credential).replace("\t", "    "))
        return {self.name: obj_definition}


class SwitchArtifact(models.Model):
    name = models.CharField(max_length=512, unique=True)
    type = models.ForeignKey(ToscaClass, limit_choices_to={'type': ToscaClass.ARTIFACT_TYPE})
    file = models.CharField(max_length=512)
    repository = models.ForeignKey(SwitchRepository)

    class Meta:
        verbose_name_plural = "Switch artifacts"

    class JSONAPIMeta:
        resource_name = "switchartifact"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        obj_definition['type'] = self.type.get_full_name()
        obj_definition['file'] = self.file
        obj_definition['repository'] = self.repository.name
        return {self.name: obj_definition}


class ApplicationInstance(GraphBase):
    application = models.ForeignKey(Application, related_name='runs')
    type = models.IntegerField(default=0)
    status = models.IntegerField(default=0)

    class JSONAPIMeta:
        resource_name = "switchappinstances"

    def clone_from_application(self):
        instance_translations = {}
        port_translations = {}

        for instance in Instance.objects.filter(graph=self.application).all():
            try:
                clone_instance = False

                old_pk = instance.pk
                instance.pk = None
                instance.id = None
                instance.graph = self
                instance.uuid = uuid.uuid4()

                if instance.component.type.switch_class.title == 'switch.Component':
                    instance.save()

                    nested_component = NestedComponent(instance_ptr=instance)
                    nested_component.save_base(raw=True)

                    for port in ComponentPort.objects.filter(instance_id=old_pk).all():
                        old_port_pk = port.pk
                        port.pk = None
                        port.id = None
                        port.instance = instance
                        port.uuid = uuid.uuid4()
                        port.save()
                        port_translations[old_port_pk] = port.pk

                elif instance.component.type.switch_class.title == 'switch.VirtualResource':
                    instance.component = Component.objects.filter(type__switch_class__title='switch.Host')
                    instance.last_x = 0
                    instance.last_y = 0
                    instance.save()

                    nested_component = NestedComponent(instance_ptr=instance)
                    nested_component.save_base(raw=True)

                elif instance.component.type.switch_class.title == 'switch.ComponentLink':
                    instance.save()

                    component_link = ComponentLink(instance_ptr=instance)
                    component_link.save_base(raw=True)

                instance_translations[old_pk] = instance.pk
            except Exception as e:
                print e.message

        # for original_nested_component_inside_group in NestedComponent.objects.filter(graph=self, parent__isnull=False):
        #     nested_component_inside_group = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.id]).first()
        #     group_nested_component = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.parent.id]).first()
        #     nested_component_inside_group.parent = group_nested_component
        #     nested_component_inside_group.save()

        for original_component_link in ComponentLink.objects.filter(graph=self.application).all():
            component_link = ComponentLink.objects.filter(instance_ptr_id=instance_translations[original_component_link.id]).first()
            component_link.source_id = port_translations[original_component_link.source_id]
            component_link.target_id = port_translations[original_component_link.target_id]
            component_link.save()

        for original_service in ServiceComponent.objects.filter(graph=self.application).all():
            service = NestedComponent.objects.filter(instance_ptr_id=instance_translations[original_service.id]).first()
            if service is not None:
                print set(original_service.get_source_components())
                deployed_host = NestedComponent.objects.filter(instance_ptr_id=instance_translations[original_service.id]).first()
                for original_component_id in original_service.get_source_components():
                    component = NestedComponent.objects.filter(instance_ptr_id=instance_translations[original_component_id]).first()
                    component.parent = deployed_host
                    component.save()


class ComponentClass(models.Model):
    title = models.CharField(max_length=512)
    classpath = models.CharField(max_length=512, blank=True)
    is_core_component = models.BooleanField(default=False)
    is_template_component = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Component classes"

    class JSONAPIMeta:
        resource_name = "switchcomponentclass"

    def __unicode__(self):
        return self.title


class ComponentType(models.Model):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')
    title = models.CharField(max_length=512)
    switch_class = models.ForeignKey(ComponentClass, related_name='types')
    primary_colour = models.CharField(max_length=512, blank=True)
    secondary_colour = models.CharField(max_length=512, blank=True)
    icon_name = models.CharField(max_length=1024, blank=True)
    icon_style = models.CharField(max_length=1024, blank=True)
    icon_class = models.CharField(max_length=1024, blank=True)
    icon_svg = models.CharField(max_length=1024, blank=True)
    icon_code = models.CharField(max_length=512, blank=True)
    icon_colour = models.CharField(max_length=512, blank=True)
    tosca_class = models.ForeignKey(ToscaClass)
    artifacts = models.ManyToManyField(SwitchArtifact, blank=True)

    class JSONAPIMeta:
        resource_name = "switchcomponenttypes"

    def __unicode__(self):
        return self.title

    def get_base_type(self):
        if self.parent is not None:
            return self.parent.get_base_type()
        else:
            return self

    def is_core(self):
        if self.parent is not None:
            return self.parent.is_template()
        else:
            return self.switch_class.is_core_component

    def is_template(self):
        if self.parent is not None:
            return self.parent.is_template()
        else:
            return self.switch_class.is_template_component

    def computed_class(self):
        classpath = self.title.title().replace(' ', '')
        if self.parent is not None:
            classpath = self.parent.computed_class() + '.' + classpath
        else:
            classpath = self.switch_class.title + '.' + classpath
        return classpath

    def get_tosca(self):
        obj_definition = {}

        if self.tosca_class.parent is not None:
            obj_definition['derived_from'] = self.tosca_class.parent.get_full_name()
        if self.properties.count() > 0:
            properties = {}
            for property in self.properties.all():
                properties.update(property.get_tosca())
            obj_definition['properties'] = properties
        if self.artifacts.count() > 0:
            artifacts = {}
            for artifact in self.artifacts.all():
                artifacts.update(artifact.get_tosca())
            obj_definition['artifacts'] = artifacts
        return {self.tosca_class.get_full_name(): obj_definition}

    def get_default_properties_value(self):
        properties = {}

        if self.parent is not None:
            properties.update(self.parent.get_default_properties_value())

        for component_type_property in self.properties.all():
            properties[component_type_property.name] = component_type_property.get_default_value()

        return properties

    def get_default_artifacts_value(self):
        artifacts = {}

        if self.parent is not None:
            artifacts.update(self.parent.get_default_artifacts_value())

        for artifact in self.artifacts.all():
            artifacts.update(artifact.get_tosca())

        return artifacts

    def save(self, *args, **kwargs):
        if self.parent:
            if not self.switch_class:
                self.switch_class = self.parent.switch_class
            if not self.primary_colour:
                self.primary_colour = self.parent.primary_colour
            if not self.secondary_colour:
                self.secondary_colour = self.parent.secondary_colour
            if not self.icon_name:
                self.icon_name = self.parent.icon_name
            if not self.icon_style:
                self.icon_style = self.parent.icon_style
            if not self.icon_class:
                self.icon_class = self.parent.icon_class
            if not self.icon_svg:
                self.icon_svg = self.parent.icon_svg
            if not self.icon_code:
                self.icon_code = self.parent.icon_code
            if not self.icon_colour:
                self.icon_colour = self.parent.icon_colour
        return super(ComponentType, self).save(*args, **kwargs)


class ComponentTypeProperty(models.Model):
    name = models.CharField(max_length=512)
    data_type = models.ForeignKey(DataType)
    default_value = models.TextField(blank=True)
    is_collection = models.BooleanField(default=False)
    component_type = models.ForeignKey(ComponentType, related_name='properties')

    class Meta:
        verbose_name_plural = "Component type properties"

    class JSONAPIMeta:
        resource_name = "switchcomponenttypeproperties"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        if self.is_collection:
            obj_definition['type'] = 'map'
            obj_definition['entry_schema'] = {'type':self.data_type.name}
        else:
            obj_definition['type'] = self.data_type.name
            if self.default_value:
                obj_definition['default'] = yaml.load(str(self.default_value).replace("\t", "    "))
        return {self.name: obj_definition}

    def get_default_value(self):
       if self.default_value:
            return yaml.load(str(self.default_value).replace("\t", "    "))
       else:
           if self.is_collection:
                map = {}
                for x in range(0, 3):
                    map[self.data_type.name.rpartition('.')[2] + '_' + str(x)] = self.data_type.get_default_value()
                return map
           else:
                return self.data_type.get_default_value()


class Component(GraphBase):
    type = models.ForeignKey(ComponentType, related_name='components', null=False)

    class JSONAPIMeta:
        resource_name = "switchcomponents"

    def __unicode__(self):
        return 'Component: ' + self.title + ' (' + str(self.type.title) + ')'

    def get_base_instance(self):
        return Instance.objects.filter(graph=self, component=self).select_subclasses().first()

    def is_core_component(self):
        return self.type.is_core()

    def is_template_component(self):
        return self.type.is_template()

    def get_default_properties_value(self):
        properties = self.type.get_default_properties_value()
        if properties:
            return yaml.dump(properties, Dumper=utils.YamlDumper, default_flow_style=False)
        else:
            return ""

    def get_default_artifacts_value(self):
        artifacts = self.type.get_default_artifacts_value()
        if artifacts:
            return yaml.dump(artifacts, Dumper=utils.YamlDumper, default_flow_style=False)
        else:
            return ""


class Instance(models.Model):
    objects = InheritanceManager()
    uuid = models.UUIDField(default=uuid.uuid4, editable=True)
    graph = models.ForeignKey(GraphBase, related_name='instances')
    component = models.ForeignKey(Component, related_name='child_instances')
    neighbors = models.ManyToManyField('self', through='ServiceLink', symmetrical=False)
    title = models.CharField(max_length=512)
    mode = models.CharField(max_length=512, blank=True)
    properties = models.TextField(blank=True, default='data: enter metadata as YAML')
    artifacts = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_x = models.IntegerField(null=True, default=0)
    last_y = models.IntegerField(null=True, default=0)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchcomponentinstances"
        abstract = True

    def get_mode_labels(self):
        fill = 'white'

        if self.mode == 'onetomany':
            text = '1..*'
        elif self.mode == 'zerotomany':
            text = '0..*'
        else:
            text = ''
            fill = 'none'

        return text, fill

    def get_graph(self):
        graph_obj = {
            'id': self.uuid,
            'type': self.component.type.switch_class.title,
            'position': {
                'x': self.last_x,
                'y': self.last_y
            },
            'attrs': {
                'switch': {
                    'class': self.component.type.switch_class.title,
                    'title': self.title,
                    'type': self.title
                },
                '.label': {
                    'html': self.title,
                    'fill': '#333'
                }
            }
        }

        if self.component.type is not None:
            graph_obj['attrs']['.icon'] = {
                "d": self.component.type.icon_svg,
                "fill": self.component.type.icon_colour
            }

        return graph_obj

    def get_tosca(self):
        obj_definition = {}
        obj_definition['type'] = self.component.type.tosca_class.get_full_name()
        if self.artifacts:
            obj_definition['artifacts'] = yaml.load(str(self.artifacts).replace("\t", "    "))
        if self.properties:
            obj_definition['properties'] = yaml.load(str(self.properties).replace("\t", "    "))
        return {str(self.uuid): obj_definition}


class NestedComponent(Instance):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "graph_components"

    def get_graph(self):
        graph_obj = super(NestedComponent, self).get_graph()

        if self.component.type.switch_class.title in ['switch.Group', 'switch.Host']:
            graph_obj['embeds'] = []

            for child in self.children.all():
                graph_obj['embeds'].append(child.uuid)
        else:
            graph_obj['inPorts'] = []
            graph_obj['outPorts'] = []

            in_ports = ComponentPort.objects.filter(instance=self, type='in').all()
            out_ports = ComponentPort.objects.filter(instance=self, type='out').all()

            stroke_opacity = ".0"
            fill_opacity = ".0"

            if self.mode != 'single':
                stroke_opacity = "1"
                fill_opacity = ".95"

            graph_obj['attrs']['.body'] = {
                "fill": self.component.type.primary_colour,
                "stroke-width": 1,
                "rx": 4,
                "ry": 4,
                "fill-opacity": "1"
            }
            graph_obj['attrs']['.multi'] = {
                "stroke-opacity": stroke_opacity,
                "fill-opacity": fill_opacity,
                "rx": 4,
                "ry": 4,
                "stroke-width": 1,
                "fill": self.component.type.secondary_colour
            }
            graph_obj['attrs']['.multi2'] = graph_obj['attrs']['.multi']

            if len(in_ports) > 0:
                gap = 100 / (len(in_ports) * 2)
                portlen = 0

                for port in in_ports:
                    graph_obj['inPorts'].append({'type': 'in', 'id': str(port.uuid), 'label': port.title})
                    key = '.inPorts>.port%s' % str(portlen)
                    ref_y = (portlen * 2 * gap) + gap
                    portlen += 1
                    graph_obj['attrs'][key] = {'ref': '.body', 'ref-y': ref_y}
                    graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                    graph_obj['attrs'][key + '>.port-body'] = {
                        'port': {'type': 'in', 'id': str(port.uuid), 'name': port.title}}

            if len(out_ports) > 0:
                gap = 100 / (len(out_ports) * 2)
                portlen = 0

                for port in out_ports:
                    graph_obj['outPorts'].append({'type': 'out', 'id': str(port.uuid), 'label': port.title})
                    key = '.outPorts>.port%s' % str(portlen)
                    ref_y = (portlen * 2 * gap) + gap
                    portlen += 1
                    graph_obj['attrs'][key] = {'ref': '.body', 'ref-dx': 0, 'ref-y': ref_y}
                    graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                    graph_obj['attrs'][key + '>.port-body'] = {
                        'port': {'type': 'out', 'id': str(port.uuid), 'name': port.title}}

            height = len(in_ports) if len(in_ports) > len(out_ports) else len(out_ports)

            if height < 2:
                height = 30
            else:
                height *= 25

            if self.parent is not None:
                graph_obj['parent'] = self.parent.uuid
            else:
                graph_obj['parent'] = None

            graph_obj['size'] = {"width": 100, "height": height}

        return graph_obj

    def get_tosca(self):
        data_obj = super(NestedComponent, self).get_tosca()
        properties = data_obj[str(self.uuid)]['properties']

        if self.component.type.title == 'Component Group':
            for child in self.children.all():
                data_obj[str(self.uuid)].setdefault('members', []).append(str(child.uuid))

        else:
            properties['scaling_mode'] = self.mode

            for port in self.ports.all():
                port_obj = {
                    'port': port.title,
                    'type': port.type
                }
                properties.setdefault(port.type + '_ports', []).append({str(port.uuid): port_obj})

            if self.parent is not None:
                properties['group'] = self.parent.uuid

            requirements = {}
            for service_link in ServiceLink.objects.filter(target=self).all():
                if service_link.source.component.type.title == 'Requirement':
                    service_link_req_vm = ServiceLink.objects.filter(target=service_link.source,
                                                                          source__component__type__title='Virtual Machine').first()
                    if service_link_req_vm:
                        # HW req has a VM link to it
                        requirements.update({'host': str(service_link_req_vm.source.uuid)})
                    else:
                        # HW req hasn't got a VM link to it
                        tosca_hw_req = service_link.source.get_tosca()
                        requirements.update({'node_filter': {'capabilities': tosca_hw_req[str(service_link.source.uuid)]['properties']}})
                if service_link.source.component.type.title == 'Monitoring Agent':
                    requirements.update({'monitored_by': str(service_link.source.uuid)})

                if service_link.source.component.type.title == 'Constraint':
                    tosca_constraint = service_link.source.get_tosca()
                    properties.update(tosca_constraint[str(service_link.source.uuid)]['properties'])

            if requirements:
                data_obj[str(self.uuid)]['requirements'] = requirements

        return data_obj


class ComponentPort(models.Model):
    instance = models.ForeignKey(Instance, related_name='ports')
    type = models.CharField(max_length=512)
    title = models.CharField(max_length=512)
    uuid = models.CharField(max_length=512)

    class JSONAPIMeta:
        resource_name = "switchcomponentports"


class ComponentLink(Instance):
    source = models.ForeignKey(ComponentPort, null=True, blank=True, related_name='targets')
    target = models.ForeignKey(ComponentPort, null=True, blank=True, related_name='sources')

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "graph_connections"

    def get_label(self):
        if self.source is not None and self.target is not None:
            return self.source.instance.title.lower().replace(" ","_") + ":" + self.target.instance.title.lower().replace(" ","_")
        else:
            return 'connection'

    def put_link_label(self, graph_obj, text, fill, position):
        graph_obj['labels'].append(
            {
                'position': position,
                'attrs': {
                    'text': {
                        'text': text,
                        'fill': 'black'
                    },
                    'rect': {
                        'fill': fill
                    }
                }
            })

    def put_link_graph(self, graph_obj, component_port, label, type, position):
        graph_obj[label] = {
            'port': component_port.uuid,
            'id': component_port.instance.uuid
        }

        graph_obj['attrs'][label + 'PortObj'] = {
            'id': component_port.id,
            'name': component_port.title,
            'type': type}

        text, fill = component_port.instance.get_mode_labels()

        self.put_link_label(graph_obj, text, fill, position)

    def get_graph(self):
        graph_obj = super(ComponentLink, self).get_graph()
        graph_obj['labels'] = []
        self.put_link_graph(graph_obj, self.target, 'target', 'in', 0.2)
        self.put_link_graph(graph_obj, self.source, 'source', 'out', 0.8)
        self.put_link_label(graph_obj, self.get_label(), 'white', 0.5)

        return graph_obj

    def get_tosca(self):
        data_obj = super(ComponentLink, self).get_tosca()
        properties = data_obj[str(self.uuid)]['properties']
        properties['target'] = {'address': properties['target_address'], 'component_name': self.target.instance.uuid,
                                'netmask': properties['netmask'],'port_name': self.target.uuid}
        properties['source'] = {'address': properties['source_address'], 'component_name': self.source.instance.uuid,
                                'netmask': properties['netmask'],'port_name': self.source.uuid}
        del properties['netmask']
        del properties['source_address']
        del properties['target_address']

        return data_obj


class ServiceLink(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    graph = models.ForeignKey(GraphBase, related_name='service_links')
    source = models.ForeignKey(Instance, related_name='sources')
    target = models.ForeignKey(Instance, related_name='targets')

    class JSONAPIMeta:
        resource_name = "switchservicelinks"

    # todo - check if attrs are needed, i don't think so...
    def get_graph(self):
        graph_obj = {
            'id': self.uuid,
            'type': 'switch.ServiceLink',
            'attrs': {
                '.marker-target': {
                    'stroke': '#fe854f',
                    'd': 'M 10 0 L 0 5 L 10 10 z',
                    'fill': '#7c68fc'
                },
                'connection': {
                    'stroke': '#222138'
                }
            }, 'target': {
                'id': self.target.uuid
            }, 'source': {
                'id': self.source.uuid
            }
        }

        text, fill = self.target.get_mode_labels()

        graph_obj['labels'] = [
            {
                'position': 0.2,
                'attrs': {
                    'text': {
                        'text': "",
                        'fill': 'black'
                    },
                    'rect': {
                        'fill': 'none'
                    }
                }
            },
            {
                'position': 0.8,
                'attrs': {
                    'text': {
                        'text': text,
                        'fill': 'black'
                    },
                    'rect': {
                        'fill': fill
                    }
                }
            }
        ]

        return graph_obj


class ServiceComponent(Instance):
    class JSONAPIMeta:
        resource_name = "graph_services"

    def __unicode__(self):
        return 'Service: ' + self.title + ' (' + str(self.component.type.title) + ')'

    def get_graph(self):
        graph_obj = super(ServiceComponent, self).get_graph()

        graph_obj['attrs']['.body'] = {
            "fill": self.component.type.primary_colour,
            "stroke": self.component.type.secondary_colour,
            "stroke-width": 2,
            "fill-opacity": ".95"
        }

        if self.component.type.switch_class.title == 'switch.Attribute':
            graph_obj['size'] = {"width": 30, "height": 30}
        elif self.component.type.switch_class.title == 'switch.VirtualResource':
            graph_obj['size'] = {"width": 35, "height": 35}

        return graph_obj

    def get_tosca(self):
        data_obj = super(ServiceComponent, self).get_tosca()
        properties = data_obj[str(self.uuid)]
        properties['class'] = self.component.type.title

        return data_obj

    def get_source_components(self, visited=None):
        components = []

        if visited is None:
            visited = []

        for link in ServiceLink.objects.filter(source=self).all():
            if link.id not in visited:
                visited.append(link.id)
                target = ServiceComponent.objects.filter(id=link.target_id).first()
                if target is not None:
                    components += target.get_source_components(visited)
                else:
                    target = NestedComponent.objects.filter(id=link.target_id).first()
                    if target is not None:
                        components.append(target.id)

        return components


class SwitchComponentAdmin(admin.ModelAdmin):
    fields = ('title', 'uuid', 'app_title')


def generate_file_name(instance, filename):
    return '/'.join(['documents', hashlib.md5(str(instance.user.username)).hexdigest(), 'files', filename])


class SwitchDocumentType(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class JSONAPIMeta:
        resource_name = "switchdocumenttypes"

    def __unicode__(self):
        return self.name


class SwitchDocument(models.Model):
    user = models.ForeignKey(User)
    file = models.FileField(upload_to=generate_file_name)
    document_type = models.ForeignKey(SwitchDocumentType)
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class JSONAPIMeta:
        resource_name = "switchdocuments"

    def __unicode__(self):
        return str(self.description) + ' (' + self.file.name + ')'