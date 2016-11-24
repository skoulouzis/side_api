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

    def put_graph(self, json_data):

        service_links = []
        component_links = []

        try:
            for obj in self.service_links.all():
                obj.delete()

            for cell in json_data['cells']:  #
                # Do these two last to ensure all linked to components exist...
                if cell['type'] == 'switch.ServiceLink':
                    service_links.append(cell)
                elif cell['type'] == 'switch.ComponentLink':
                    component_links.append(cell)
                else:
                    instance = Instance.objects.filter(uuid=cell['id'], graph=self).select_subclasses().first()
                    instance.type = cell['type']
                    instance.last_x = cell['position']['x']
                    instance.last_y = cell['position']['y']

                    if instance.component.type.switch_class.title == 'switch.Component':
                        port_objs = []

                        if 'parent' in cell and cell['parent'] is not None:
                            parent_obj, created = NestedComponent.objects.get_or_create(uuid=cell['parent'], graph=self)
                            instance.parent = parent_obj

                        if 'inPorts' in cell:
                            for port in cell['inPorts']:
                                port_obj, created = ComponentPort.objects.get_or_create(instance=instance,
                                                                                        uuid=port['id'], type='in')
                                port_obj.title = port['label']
                                port_obj.save()
                                port_objs.append(port_obj)

                            instance.ports = port_objs

                        if 'outPorts' in cell:
                            for port in cell['outPorts']:
                                port_obj, created = ComponentPort.objects.get_or_create(instance=instance,
                                                                                        uuid=port['id'], type='out')
                                port_obj.title = port['label']
                                port_obj.save()
                                port_objs.append(port_obj)

                            instance.ports = port_objs

                        old_port_objs = ComponentPort.objects.filter(instance=instance)

                        for old_port in old_port_objs:
                            if old_port not in port_objs:
                                old_port.delete()

                    instance.save()

            for instance in service_links:
                source_obj = None
                target_obj = None

                if 'source' in instance:
                    source = instance['source']
                    source_obj = Instance.objects.filter(uuid=source['id'], graph=self).first()

                if 'target' in instance:
                    target = instance['target']
                    target_obj = Instance.objects.filter(uuid=target['id'], graph=self).first()

                if source_obj is not None and target_obj is not None:
                    ServiceLink.objects.get_or_create(source=source_obj, target=target_obj, graph=self)

            for instance in component_links:
                source_obj = None
                target_obj = None

                if 'source' in instance:
                    source = instance['source']
                    if 'port' in source:
                        source_obj = ComponentPort.objects.filter(uuid=str(source['port']), type='out').first()

                if 'target' in instance:
                    target = instance['target']
                    if 'port' in target:
                        target_obj = ComponentPort.objects.filter(uuid=str(target['port']), type='in').first()

                if source_obj is not None and target_obj is not None:
                    link, created = ComponentLink.objects.get_or_create(uuid=instance['id'], graph=self)
                    link.source = source_obj
                    link.target = target_obj
                    link.save()

        except Exception as e:
            print e.message


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

        if len(components) > 0:
            data['components'] = components

        if len(external) > 0:
            data['external_components'] = external

        if len(network) > 0:
            data['network_components'] = network

        if len(attributes) > 0:
            data['attributes'] = attributes

        if len(groups) > 0:
            data['groups'] = groups

        if len(components_connections) > 0:
            connections = data.setdefault('connections', {})
            connections['components_connections'] = components_connections

        if len(services_connections) > 0:
            connections = data.setdefault('connections', {})
            connections['services_connections'] = services_connections

        if len(virtual_machines) > 0:
            connections = data.setdefault('virtual_resources', {})
            connections['virtual_machines'] = virtual_machines

        if len(virtual_networks) > 0:
            connections = data.setdefault('virtual_resources', {})
            connections['virtual_networks'] = virtual_networks

        return {
            'data': data
        }


class ComponentClass(models.Model):
    title = models.CharField(max_length=512, null=True)
    is_core_component = models.BooleanField(default=False)
    is_template_component = models.BooleanField(default=False)

    class JSONAPIMeta:
        resource_name = "switchcomponentclass"

    def __unicode__(self):
        return self.title


class ComponentType(models.Model):
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


class Component(GraphBase):
    type = models.ForeignKey(ComponentType, related_name='components', null=True)

    class JSONAPIMeta:
        resource_name = "switchcomponents"

    def get_base_instance(self):
        return Instance.objects.filter(graph=self, component=self).select_subclasses().first()

    def is_core_component(self):
        return self.type.switch_class.title == 'switch.Component'

    def is_template_component(self):
        return self.type.switch_class.title == 'switch.Component' or self.type.switch_class.title != 'switch.Attribute'


class Instance(models.Model):
    objects = InheritanceManager()
    uuid = models.UUIDField(default=uuid.uuid4, editable=True)
    graph = models.ForeignKey(GraphBase, related_name='instances')
    component = models.ForeignKey(Component, related_name='child_instances')
    neighbors = models.ManyToManyField('self', through='ServiceLink', symmetrical=False)
    title = models.CharField(max_length=512, null=True)
    mode = models.CharField(max_length=512, null=True)
    properties = models.TextField(null=True)
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


class NestedComponent(Instance):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "graph_components"

    def get_graph(self):
        graph_obj = super(NestedComponent, self).get_graph()

        if self.component.type.switch_class.title == 'switch.Group':
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
    instance = models.ForeignKey(NestedComponent, related_name='ports')
    type = models.CharField(max_length=512, null=True)
    title = models.CharField(max_length=512, null=True)
    uuid = models.CharField(max_length=512, null=True)

    class JSONAPIMeta:
        resource_name = "graph_ports"


class ComponentLink(Instance):
    source = models.ForeignKey(ComponentPort, null=True, blank=True, related_name='targets')
    target = models.ForeignKey(ComponentPort, null=True, blank=True, related_name='sources')

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "graph_connections"

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
        self.put_link_label(graph_obj, self.title, 'white', 0.5)

        return graph_obj

    def get_tosca(self):
        data_obj = super(ComponentLink, self).get_tosca()
        properties = data_obj[str(self.uuid)]
        properties['target'] = {'id': str(self.target.instance.uuid), 'port': self.target.uuid}
        properties['source'] = {'id': str(self.source.instance.uuid), 'port': self.source.uuid}

        return data_obj


class ServiceLink(models.Model):
    graph = models.ForeignKey(GraphBase, related_name='service_links')
    source = models.ForeignKey(Instance, related_name='sources')
    target = models.ForeignKey(Instance, related_name='targets')

    class JSONAPIMeta:
        resource_name = "graph_connections"

    def get_graph(self):
        graph_obj = {
            'type': 'switch.ServiceLink',
            'attrs': {
                '.marker-target': {
                    'stroke': '#4b4a67',
                    'd': 'M 10 0 L 0 5 L 10 10 z',
                    'fill': '#4b4a67'
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
        return 'Service: ' + self.title + '(' + str(self.type) + ')'

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


class SwitchComponentAdmin(admin.ModelAdmin):
    fields = ('title', 'uuid', 'app_title')


def generate_fileName(instance, filename):
    return '/'.join(['documents', str(instance.user.id), filename])


class SwitchDocument(models.Model):
    user = models.ForeignKey(User)
    description = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to=generate_fileName)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class JSONAPIMeta:
        resource_name = "switchdocument"