from __future__ import unicode_literals

import yaml
import uuid as uuid
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.contrib import admin
from model_utils.managers import InheritanceManager

from yaml.dumper import Dumper
from yaml.representer import SafeRepresenter


class YamlDumper(Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(YamlDumper, self).increase_indent(flow, False)


YamlDumper.add_representer(str, SafeRepresenter.represent_str)
YamlDumper.add_representer(unicode, SafeRepresenter.represent_unicode)


class GraphBase(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, default = None)
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


class Notification(models.Model):

    class JSONAPIMeta:
        resource_name = "switchnotifications"

    graph = models.ForeignKey(GraphBase, related_name='notifications')
    title = models.CharField(max_length=512)
    message = models.CharField(max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    severity = models.IntegerField(default=0)
    viewed = models.BooleanField(default=False)


class Application(GraphBase):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    description = models.CharField(max_length=1024, null=True)
    public_view = models.BooleanField(default=False)
    public_editable = models.BooleanField(default=False)
    # Status: 0 no plan virtual infrastructure; 1 planned; 2 provisioned; 3 deployed
    status = models.IntegerField(default=0)

    class JSONAPIMeta:
        resource_name = "switchapps"

    def __unicode__(self):
        return 'SwitchApp: ' + self.title + ' by ' + self.user.username

    def get_tosca(self):
        artifact_types = {
            "tosca.artifacts.Deployment.Image.Container.Docker": {
                "derived_from": "tosca.artifacts.Deployment.Image"
            }
        }

        data_types = {
            "Switch.datatypes.QoS.AppComponent": {
                "derived_from": "tosca.datatypes.Root",
                "properties":{
                    "response_time":{
                        "type": "string"
                    }
                }
            },
            "Switch.datatypes.Application.Connection.EndPoint": {
                "derived_from": "tosca.datatypes.Root",
                "properties": {
                    "address": {
                        "type": "string"
                    },
                    "component_name": {
                        "type": "string"
                    },
                    "netmask": {
                        "type": "string"
                    },
                    "port_name": {
                        "type": "string"
                    }
                }
            },
            "Switch.datatypes.Application.Connection.Multicast": {
                "derived_from": "tosca.datatypes.Root",
                "properties": {
                    "multicastAddrIP": {
                        "type": "string"
                    },
                    "multicastAddrPort": {
                        "type": "integer"
                    }
                }
            },
            "Switch.datatypes.Network.EndPoint": {
                "derived_from": "tosca.datatypes.Root",
                "properties": {
                    "address": {
                        "type": "string"
                    },
                    "host_name": {
                        "type": "string"
                    },
                    "netmask": {
                        "type": "string"
                    },
                    "port_name": {
                        "type": "string"
                    }
                }
            },
            "Switch.datatypes.Network.Multicast": {
                "derived_from": "tosca.datatypes.Root",
                "properties": {
                    "multicastAddrIP": {
                        "type": "string"
                    },
                    "multicastAddrPort": {
                        "type": "integer"
                    }
                }
            }
        }

        node_types = {
          "Switch.nodes.Application.Container.Docker": {
            "derived_from": "tosca.nodes.Container.Application",
            "properties": {
              "QoS": {
                "type": "Switch.datatypes.QoS.AppComponent"
              }
            },
            "artifacts": {
              "docker_image": {
                "type": "tosca.artifacts.Deployment.Image.Container.Docker"
              }
            },
            "interfaces": {
              "Standard": {
                "create": {
                  "inputs": {
                    "command": {
                      "type": "string"
                    },
                    "exported_ports": {
                      "type": "list",
                      "entry_schema": {
                        "type": "string"
                      }
                    },
                    "port_bindings": {
                      "type": "list",
                      "entry_schema": {
                        "type": "string"
                      }
                    }
                  }
                }
              }
            }
          }
        }

        repositories = {}

        components = []
        external = []
        network = []
        attributes = []
        groups = []
        components_connections = []
        services_connections = []
        virtual_machines = []
        virtual_networks = []

        instances = Instance.objects.filter(graph=self).select_subclasses()

        for instance in instances:
            try:
                tosca_node_type = instance.component.get_base_instance().get_tosca_type()
                key, value = tosca_node_type.popitem()
                if key not in node_types:
                    node_types[key] = value

                graph_obj = instance.get_tosca()
                if instance.component.type.title == 'Component':
                    components.append(graph_obj)
                elif instance.component.type.title == 'External Component':
                    external.append(graph_obj)
                elif instance.component.type.title == 'Component Group':
                    groups.append(graph_obj)
                elif instance.component.type.title == 'Component Link':
                    components_connections.append(graph_obj)
                elif instance.component.type.title == 'Network':
                    network.append(graph_obj)
                elif instance.component.type.title == 'Virtual Machine':
                    virtual_machines.append(graph_obj)
                elif instance.component.type.title == 'Virtual Network':
                    virtual_networks.append(graph_obj)
                elif instance.component.type.switch_class.title == 'switch.Attribute':
                    attributes.append(graph_obj)

            except Exception as e:
                print e.message

        for service_link in self.service_links.all():
            data_obj = {
                str(service_link.source.uuid) + '--' + str(service_link.target.uuid): {
                    'target': {'id': str(service_link.target.uuid)},
                    'source': {'id': str(service_link.source.uuid)}
                }
            }
            services_connections.append(data_obj)

        data = {}
        data['tosca_definitions_version'] = "tosca_simple_yaml_1_0"
        data['description'] = self.description
        data['artifact_types'] = artifact_types
        data['data_types'] = data_types
        data['node_types'] = node_types
        data['repositories'] = repositories

        data['topology_template']={}
        node_templates = data['topology_template'].setdefault('node_templates', {})


        if len(components) > 0:
            node_templates['components'] = components

        if len(external) > 0:
            node_templates['external_components'] = external

        if len(network) > 0:
            node_templates['network_components'] = network

        if len(attributes) > 0:
            node_templates['attributes'] = attributes

        if len(groups) > 0:
            node_templates['groups']['node_templates'] = groups

        if len(components_connections) > 0:
            connections = node_templates.setdefault('connections', {})
            connections['components_connections'] = components_connections

        if len(services_connections) > 0:
            connections = node_templates.setdefault('connections', {})
            connections['services_connections'] = services_connections

        if len(virtual_machines) > 0:
            connections = node_templates.setdefault('virtual_resources', {})
            connections['virtual_machines'] = virtual_machines

        if len(virtual_networks) > 0:
            connections = node_templates.setdefault('virtual_resources', {})
            connections['virtual_networks'] = virtual_networks

        return {
            'data': data
        }


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
    title = models.CharField(max_length=512, null=True)
    classpath = models.CharField(max_length=512, null=True)
    is_core_component = models.BooleanField(default=False)
    is_template_component = models.BooleanField(default=False)

    class JSONAPIMeta:
        resource_name = "switchcomponentclass"

    def __unicode__(self):
        return self.title


class ComponentType(models.Model):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')
    title = models.CharField(max_length=512, null=True)
    switch_class = models.ForeignKey(ComponentClass, related_name='types')
    primary_colour = models.CharField(max_length=512, null=True)
    secondary_colour = models.CharField(max_length=512, null=True)
    icon_name = models.CharField(max_length=1024, null=True)
    icon_style = models.CharField(max_length=1024, null=True)
    icon_class = models.CharField(max_length=1024, null=True)
    icon_svg = models.CharField(max_length=1024, null=True)
    icon_code = models.CharField(max_length=512, null=True)
    icon_colour = models.CharField(max_length=512, null=True)

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


class ComponentTypeProperty(models.Model):
    name = models.CharField(max_length=512, null=False)
    type = models.CharField(max_length=512, null=False)
    default_value = models.CharField(max_length=512, null=True)
    component_type = models.ForeignKey(ComponentType, related_name='properties')


    class JSONAPIMeta:
        resource_name = "switchcomponenttypeproperties"

    def __unicode__(self):
        return self.name


class Component(GraphBase):
    type = models.ForeignKey(ComponentType, related_name='components', null=True)

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


class Instance(models.Model):
    objects = InheritanceManager()
    uuid = models.UUIDField(default=uuid.uuid4, editable=True)
    graph = models.ForeignKey(GraphBase, related_name='instances')
    component = models.ForeignKey(Component, related_name='child_instances')
    neighbors = models.ManyToManyField('self', through='ServiceLink', symmetrical=False)
    title = models.CharField(max_length=512, null=True)
    mode = models.CharField(max_length=512, null=True)
    properties = models.TextField(null=True, default='data: enter metadata as YAML')
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
        data_obj = {}
        properties = {}

        if 'enter metadata as YAML' not in self.properties:
            metadata = yaml.load(str(self.properties).replace("\t", "    "))
            properties.update(metadata)

        properties['title'] = self.title

        data_obj[str(self.uuid)] = properties

        return data_obj

    def get_tosca_type(self):
        data_obj = {}
        properties = {}

        metadata = yaml.load(str(self.properties).replace("\t", "    "))
        properties.update(metadata)

        data_obj[self.title] = properties

        return data_obj


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
        properties = data_obj[str(self.uuid)]

        if self.component.type.title == 'Component Group':
            for child in self.children.all():
                properties.setdefault('members', []).append(str(child.uuid))

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

        return data_obj


class ComponentPort(models.Model):
    instance = models.ForeignKey(Instance, related_name='ports')
    type = models.CharField(max_length=512, null=True)
    title = models.CharField(max_length=512, null=True)
    uuid = models.CharField(max_length=512, null=True)

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
        properties = data_obj[str(self.uuid)]
        properties['target'] = {'id': str(self.target.instance.uuid), 'port': self.target.uuid}
        properties['source'] = {'id': str(self.source.instance.uuid), 'port': self.source.uuid}

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
    return '/'.join(['documents', str(instance.user.id), filename])


class SwitchDocument(models.Model):
    user = models.ForeignKey(User)
    description = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to=generate_file_name)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class JSONAPIMeta:
        resource_name = "switchdocuments"

    def __unicode__(self):
        return 'Document: ' + self.file.name + ' (' + str(self.description) + ')'
