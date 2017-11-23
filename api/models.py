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
from django.db.models import Q


class GraphBase(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, default=None)
    title = models.CharField(max_length=255)
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
        return ComponentInstance.objects.filter(graph=self).select_subclasses()

    def get_graph(self):
        response_cells = []
        # This takes all the ComponentInstance objects and all objects of subclasses.
        # Python makes no sense to me.
        instances = ComponentInstance.objects.filter(graph=self).select_subclasses()

        for instance in instances:
            try:
                graph_obj = instance.get_graph()
                response_cells.append(graph_obj)

            except Exception as e:
                print e.message

        # I think this is wrong. It might be tre reason why the links do not keep.
        # Great job for noting it's wrong, but not why.
        for dependency_link in self.service_links.all():
            try:
                graph_obj = dependency_link.get_graph()
                response_cells.append(graph_obj)

                add_parent = True

                for cell in response_cells:
                    if 'id' in cell and cell['id'] == dependency_link.source.uuid:
                        if 'parent' in cell:
                            add_parent = False
                        else:
                            cell['parent'] = dependency_link.target.uuid

                if add_parent:
                    for cell in response_cells:
                        if 'id' in cell and cell['id'] == dependency_link.target.uuid:
                            cell.setdefault('embeds', [])
                            cell['embeds'].append(dependency_link.source.uuid)

            except Exception as e:
                print e.message
        for dependency_link in self.dependency_links.all():
            try:
                graph_obj = dependency_link.get_graph()
                response_cells.append(graph_obj)

            except Exception as e:
                print e.message

        # return JSON with the data.
        return {
            'type': 'graphs',
            'id': str(self.id),
            'attributes': {
                'graph': {
                    'cells': response_cells
                }
            }
        }

    # this now just updates x/y of any component... nothing else :)
    def put_graph(self, json_data):
        try:
            for cell in json_data['cells']:  #
                instance = ComponentInstance.objects.filter(uuid=cell['id'], graph=self).select_subclasses().first()
                if 'position' in cell and cell['position'] is not None:
                    instance.last_x = cell['position']['x']
                    instance.last_y = cell['position']['y']
                    instance.save()
        except Exception as e:
            print e.message

    def clone_instances_in_graph(self, new_graph, x_change, y_change, new_instance=None):
        instance_translations = {}
        port_translations = {}

        for instance in ComponentInstance.objects.filter(graph=self).all():
            old_pk = instance.pk
            old_uuid = instance.uuid

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
                nested_component = NestedComponent(componentinstance_ptr=instance)
                nested_component.save_base(raw=True)

                for port in ComponentPort.objects.filter(instance_id=old_pk).all():
                    old_port_pk = port.pk
                    port.pk = None
                    port.id = None
                    port.instance = instance
                    port.uuid = uuid.uuid4()
                    port.save()
                    port_translations[old_port_pk] = port.pk

            elif instance.component.type.switch_class.title == 'switch.VirtualResource' or instance.component.type.switch_class.title == 'switch.Attribute' or instance.component.type.switch_class.title == 'switch.DST':
                update_vm = False
                instance_properties = yaml.load(instance.properties.replace("\\n", "\n"))
                if 'name' in instance_properties and instance_properties['name'] == str(old_uuid):
                    update_vm = True
                    instance_properties['name'] = str(instance.uuid)
                if 'public_address' in instance_properties and instance_properties['public_address'] == str(old_uuid):
                    update_vm = True
                    instance_properties['public_address'] = str(instance.uuid)
                if update_vm:
                    instance.properties = yaml.dump(instance_properties, Dumper=utils.YamlDumper, default_flow_style=False)
                    instance.save()

                service_component = ServiceComponent(componentinstance_ptr=instance)
                service_component.save_base(raw=True)

            elif instance.component.type.switch_class.title == 'switch.ComponentLink':
                component_link = ComponentLink(componentinstance_ptr=instance)
                component_link.save_base(raw=True)

        for original_nested_component_inside_group in NestedComponent.objects.filter(graph=self, parent__isnull=False):
            nested_component_inside_group = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.id]).first()
            group_nested_component = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.parent.id]).first()
            nested_component_inside_group.parent = group_nested_component
            nested_component_inside_group.save()

        for original_component_link in ComponentLink.objects.filter(graph=self).all():
            component_link = ComponentLink.objects.filter(componentinstance_ptr_id=instance_translations[original_component_link.id]).first()
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
        instances = ComponentInstance.objects.filter(graph=self).select_subclasses()

        for instance in instances:
            if instance.last_x !=0 and instance.last_x < top_x:
                top_x = instance.last_x
            if instance.last_y !=0 and instance.last_y < top_y:
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
            'mid_x': (bottom_x - top_x) / 2 + top_x,
            'mid_y': (bottom_y - top_y) / 2 + top_y,
        }


class Notification(models.Model):

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchnotifications"

    def __unicode__(self):
        return 'Notification: title=' + self.title + ' message=' + self.message + ' graph=' + self.graph.title

    graph = models.ForeignKey(GraphBase, related_name='notifications')
    title = models.CharField(max_length=255)
    nType = models.CharField(max_length=255)
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
    drip_plan_id = models.CharField(max_length=255, blank=True)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchapps"

    def __unicode__(self):
        return 'SwitchApp: ' + self.title + ' by ' + self.user.username

    # TODO: Refactor this so that the actual logic is more transparent. As it stands the functions are convoluted.
    def tosca_add_instances(self, node_templates):
        for tosca_node_key, tosca_node_value in node_templates.iteritems():
            properties = tosca_node_value.get('properties')

            # if not on graph
            if not self.instances.filter(uuid=tosca_node_key).first():
                app_graph_dimensions = self.get_current_graph_dimensions()
                component_type = ComponentType.objects.get(
                    tosca_class__prefix=tosca_node_value.get('type').rsplit('.', 1)[0],
                    tosca_class__name=tosca_node_value.get('type').rsplit('.', 1)[1])
                component = Component.objects.filter(type=component_type).first()
                if component_type.switch_class.title == 'switch.Component':

                    # create
                    instance = NestedComponent.objects.create(
                        component=component,
                        graph=self, title=component_type.title, mode='single',
                        last_x=app_graph_dimensions.get('mid_x'),
                        last_y=app_graph_dimensions.get('bottom_y') + 150,
                        uuid=tosca_node_key)

                    if tosca_node_value.get('artifacts', None):
                        instance.artifacts = yaml.dump(tosca_node_value.get('artifacts'), Dumper=utils.YamlDumper,
                                                       default_flow_style=False)
                        instance.save()

                    # Add in_ports and out_ports
                    in_ports = properties.get('in_ports', None)
                    if in_ports:
                        for in_port_key, in_port_value in in_ports.iteritems():
                            port = ComponentPort.objects.create(uuid=in_port_key,
                                                                title=in_port_value.get('port').strip(),
                                                                type=in_port_value.get('type'),
                                                                instance=instance)
                        del properties['in_ports']

                    out_ports = properties.get('out_ports', None)
                    if out_ports:
                        for out_port_key, out_port_value in out_ports.iteritems():
                            port = ComponentPort.objects.create(uuid=out_port_key,
                                                                title=out_port_value.get('port').strip(),
                                                                type=out_port_value.get('type'),
                                                                instance=instance)
                        del properties['out_ports']

                    qos_attribute = properties.get('QoS', None)
                    if qos_attribute:
                        constraint_instance = ServiceComponent.objects.create(
                            component=Component.objects.get(type__title='Constraint'),
                            graph=self, title='QoS_constraint', mode='single',
                            properties=yaml.dump(qos_attribute, Dumper=utils.YamlDumper,
                                                 default_flow_style=False),
                            last_x=app_graph_dimensions.get('mid_x'),
                            last_y=app_graph_dimensions.get('bottom_y') + 150,
                            uuid=tosca_node_key)
                        constraint_link = ServiceLink.objects.create(graph=self, source=constraint_instance,
                                                                     target=instance)
                        del properties['QoS']

                    instance.properties = yaml.dump(properties, Dumper=utils.YamlDumper, default_flow_style=False),
                    instance.save()

                elif component_type.switch_class.title == 'switch.VirtualResource' or component_type.switch_class.title == 'switch.Attribute' or component_type.switch_class.title == 'switch.DST':
                    instance = ServiceComponent.objects.create(
                        component=component,
                        graph=self, title=component_type.title, mode='single',
                        properties=yaml.dump(properties, Dumper=utils.YamlDumper, default_flow_style=False),
                        last_x=app_graph_dimensions.get('mid_x'),
                        last_y=app_graph_dimensions.get('bottom_y') + 150,
                        uuid=tosca_node_key)

                    if tosca_node_value.get('artifacts', None):
                        instance.artifacts = yaml.dump(tosca_node_value.get('artifacts'), Dumper=utils.YamlDumper,
                                                       default_flow_style=False)
                        instance.save()

                elif component.type.switch_class.title == 'switch.ComponentLink':
                    instance = ComponentLink.objects.create(
                        component=component,
                        graph=self, title=component_type.title, mode='single',
                        last_x=app_graph_dimensions.get('mid_x'),
                        last_y=app_graph_dimensions.get('bottom_y') + 150,
                        uuid=tosca_node_key)

                    properties['netmask'] = properties.get('source').get('netmask')
                    properties['source_address'] = properties.get('source').get('address')
                    properties['target_address'] = properties.get('target').get('address')
                    del properties['target']
                    del properties['source']
                    instance.properties = yaml.dump(properties, Dumper=utils.YamlDumper, default_flow_style=False),
                    instance.save()

    def tosca_update_instances(self, node_templates):
        for tosca_node_key, tosca_node_value in node_templates.iteritems():
            properties = tosca_node_value.get('properties')
            instance = self.instances.get(uuid=tosca_node_key)

            if instance.component.type.switch_class.title == 'switch.Component' or instance.component.type.switch_class.title == 'switch.Attribute':
                in_ports = properties.get('in_ports', None)
                if in_ports:
                    for in_port_key, in_port_value in in_ports.iteritems():
                        port = ComponentPort.objects.get_or_create(uuid=in_port_key,
                                                                   title=in_port_value.get('port').strip(),
                                                                   type=in_port_value.get('type'), instance=instance)
                    del properties['in_ports']

                out_ports = properties.get('out_ports', None)
                if out_ports:
                    for out_port_key, out_port_value in out_ports.iteritems():
                        port = ComponentPort.objects.get_or_create(uuid=out_port_key,
                                                                   title=out_port_value.get('port').strip(),
                                                                   type=out_port_value.get('type'),
                                                                   instance=instance)
                    del properties['out_ports']

                qos_attribute = properties.get('QoS', None)
                if qos_attribute:
                    constraint_link = ServiceLink.objects.filter(graph=self, target=instance,
                                                                 source__component__type__title='Constraint').first()
                    constraint_link.source.properties = yaml.dump({'QoS': qos_attribute}, Dumper=utils.YamlDumper,
                                                                  default_flow_style=False)
                    constraint_link.source.save()
                    del properties['QoS']

                instance.properties = yaml.dump(properties, Dumper=utils.YamlDumper, default_flow_style=False)
                instance.save()

                # Add service links
                tosca_node_requirements = tosca_node_value.get('requirements', None)
                if tosca_node_requirements:
                    for tosca_node_requirement in tosca_node_requirements:
                        source_instance = self.instances.get(uuid=tosca_node_requirement.values()[0])
                        link = ServiceLink.objects.get_or_create(graph=self, source=source_instance, target=instance)

                    # Delete old links
                    for link in ServiceLink.objects.filter(graph=self, target=instance).all():
                        if not any(str(link.source.uuid) in d.values() for d in
                                   tosca_node_requirements) and link.source.component.type.title != 'Constraint':
                            link.delete()

            elif instance.component.type.switch_class.title == 'switch.VirtualResource':
                # Add connections between vms and subnets
                ethernet_ports = properties.get('ethernet_port', None)
                if ethernet_ports:
                    for ethernet_port in ethernet_ports:
                        subnet = ServiceComponent.objects.get(uuid=ethernet_port.get('subnet_name'))
                        link = ServiceLink.objects.get_or_create(graph=self, source=instance, target=subnet)

            elif instance.component.type.switch_class.title == 'switch.ComponentLink':
                if properties.get('source', None):
                    source_port = ComponentPort.objects.get(uuid=properties.get('source').get('port_name'),
                                                            instance=self.instances.get(
                                                                uuid=properties.get('source').get('component_name')))
                    target_port = ComponentPort.objects.get(uuid=properties.get('target').get('port_name'),
                                                            instance=self.instances.get(
                                                                uuid=properties.get('target').get('component_name')))
                    instance.__class__ = ComponentLink
                    instance.source = source_port
                    instance.target = target_port

                    properties['netmask'] = properties.get('source').get('netmask')
                    properties['source_address'] = properties.get('source').get('address')
                    properties['target_address'] = properties.get('target').get('address')
                    del properties['target']
                    del properties['source']
                    instance.properties = yaml.dump(properties, Dumper=utils.YamlDumper, default_flow_style=False)
                    instance.save()

            # Add service links between components and services
            tosca_node_requirements = tosca_node_value.get('requirements', None)
            if tosca_node_requirements:
                for tosca_node_requirement in tosca_node_requirements:
                    source_instance = self.instances.get(uuid=tosca_node_requirement.values()[0])
                    link = ServiceLink.objects.get_or_create(graph=self, source=source_instance, target=instance)

                # Delete old links
                for link in ServiceLink.objects.filter(graph=self, target=instance).all():
                    if not any(str(link.source.uuid) in d.values() for d in
                               tosca_node_requirements) and link.source.component.type.title != 'Constraint':
                        link.delete()

    def tosca_remove_instances(self, node_templates):
        for instance in self.instances.all():
            if str(instance.uuid) not in node_templates.keys() and instance.component.type.title != 'Constraint':
                for link in self.service_links.filter(Q(target=instance) | Q(source=instance)).all():
                    link.delete()
                instance.delete()

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
        # TODO: Change this so that only relevant types remain in TOSCA
        for node_type in ComponentType.objects.all():
            node_types.update(node_type.get_tosca())

        data = {}
        data['description'] = self.description
        if artifact_types:
            data['artifact_types'] = artifact_types
        if data_types:
            data['data_types'] = data_types
        if node_types:
            data['node_types'] = node_types
        if repositories:
            data['repositories'] = repositories

        data['topology_template']={}
        node_templates = data['topology_template'].setdefault('node_templates', {})

        groups = {}

        instances = ComponentInstance.objects.filter(graph=self).select_subclasses()
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

        if groups:
            data['groups'] = groups

        data['tosca_definitions_version'] = "tosca_simple_yaml_1_0"

        return {
            'data': data
        }

    def get_status(self, status_string):
        status_dict = {
            'NoPlan': 0,
            'Planed': 1,
            'Provisioned': 2,
            'Deployed': 3,
        }
        if self.status == status_dict[status_string]:
            return True
        else:
            return False

    def validate_requirements(self):
        num_hw_req = 0
        docker_components = self.instances.filter(component__type__switch_class__title='switch.Component').all()
        for docker_component in docker_components:
            num_hw_req += self.service_links.filter(target=docker_component,
                                                    source__component__type__title='Requirement').count()

        return num_hw_req == docker_components.count()

    def needs_monitoring_server(self):
        monitoring_agents = self.instances.filter(component__type__title='Monitoring Agent').all()
        num_monitoring_server = self.instances.filter(component__type__title='SWITCH.MonitoringServer').count()
        if monitoring_agents.count() > 0 and num_monitoring_server < 1:
            return True
        else:
            return False

    def create_monitoring_server(self):

        monitoring_agents = self.instances.filter(component__type__title='Monitoring Agent').all()

        component_monitoring_server = Component.objects.get(title='monitoring_server',
                                                            type__title='SWITCH.MonitoringServer')

        app_graph_dimensions = self.get_current_graph_dimensions()
        base_instance = component_monitoring_server.get_base_instance()
        graph_monitoring_server = NestedComponent.objects.create(
            component=component_monitoring_server,
            graph=self, title=component_monitoring_server.title, mode=base_instance.mode,
            properties=base_instance.properties, artifacts=base_instance.artifacts,
            last_x=app_graph_dimensions.get('mid_x'),
            last_y=app_graph_dimensions.get('top_y') - 150)

        x_change = base_instance.last_x - graph_monitoring_server.last_x
        y_change = base_instance.last_y - graph_monitoring_server.last_y
        component_monitoring_server.clone_instances_in_graph(self, x_change, y_change,
                                                             graph_monitoring_server)

        for monitoring_agent in monitoring_agents:
            link = ServiceLink.objects.create(graph=self, source=graph_monitoring_server, target=monitoring_agent)

    def tosca_update(self, tosca):
        node_templates = tosca.get("topology_template", None).get("node_templates")
        self.tosca_add_instances(node_templates)
        self.tosca_update_instances(node_templates)
        self.tosca_remove_instances(node_templates)


class DataType(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')
    default_value = models.TextField(blank=True)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchdatatypes"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        if self.parent is not None:
            obj_definition['derived_from'] = self.parent.name
        if self.properties.count() > 0      :
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
                if data_type_property.required:
                    properties[data_type_property.name] = data_type_property.get_default_value()

            return properties


class DataTypeProperty(models.Model):
    SINGLE = 'S'
    MAP = 'M'
    LIST = 'L'
    COLLECTION_TYPE_CHOICES = (
        (SINGLE, 'Single'),
        (MAP, 'Map'),
        (LIST, 'List')
    )

    name = models.CharField(max_length=255)
    data_type = models.ForeignKey(DataType)
    default_value = models.TextField(blank=True)
    required = models.BooleanField(default=True)
    collection_type = models.CharField(
        max_length=2,
        choices=COLLECTION_TYPE_CHOICES,
        default=SINGLE,
    )
    parent_data_type = models.ForeignKey(DataType, related_name='properties')

    class Meta:
        verbose_name_plural = "Data type properties"

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchdatatypeproperties"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        if self.collection_type==DataTypeProperty.MAP:
            obj_definition['type'] = 'map'
            obj_definition['entry_schema'] = {'type':self.data_type.name}
        elif self.collection_type==DataTypeProperty.LIST:
            obj_definition['type'] = 'list'
            obj_definition['entry_schema'] = {'type':self.data_type.name}
        else:
            obj_definition['type'] = self.data_type.name

        if not self.required:
            obj_definition['required'] = 'false'

        return {self.name: obj_definition}

    def get_default_value(self):
        if self.default_value:
            return yaml.load(str(self.default_value).replace("\t", "    "))
        else:
            if self.collection_type == DataTypeProperty.MAP:
                map = {}
                for x in range(0, 3):
                    map[self.data_type.name.rpartition('.')[2] + '_' + str(x)] = self.data_type.get_default_value()
                return map
            elif self.collection_type == DataTypeProperty.LIST:
                list = []
                for x in range(0, 3):
                    list.append({self.data_type.name.rpartition('.')[2] + '_' + str(x): self.data_type.get_default_value()})
                return list
            else:
                return self.data_type.get_default_value()


class ToscaClass(models.Model):
    NODE_TYPE = 'N'
    ARTIFACT_TYPE = 'A'
    GROUP_TYPE = 'G'
    RELATIONSHIP_TYPE = 'R'
    CAPABILITY_TYPE = 'C'
    TYPE_CHOICES = (
        (NODE_TYPE, 'Node type'),
        (ARTIFACT_TYPE, 'Artifact type'),
        (GROUP_TYPE, 'Group type'),
        (RELATIONSHIP_TYPE, 'Relationship type'),
        (CAPABILITY_TYPE, 'Capability type'),
    )

    name = models.CharField(max_length=255)
    type = models.CharField(
        max_length=2,
        choices=TYPE_CHOICES,
        default=NODE_TYPE,
    )
    parent = models.ForeignKey('self', null=True, blank=True)
    prefix = models.CharField(max_length=255)
    is_normative = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Tosca classes"

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "toscaclasses"

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
    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=512)
    credential = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Switch repositories"

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchrepositories"

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
    name = models.CharField(max_length=255, unique=True)
    type = models.ForeignKey(ToscaClass, null=True, blank=True, limit_choices_to={'type': ToscaClass.ARTIFACT_TYPE})
    file = models.CharField(max_length=255, null=True, blank=True)
    repository = models.ForeignKey(SwitchRepository, null=True, blank=True)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchartifacts"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        obj_definition['type'] = self.type.get_full_name()
        obj_definition['file'] = self.file
        obj_definition['repository'] = self.repository.name
        return {self.name: obj_definition}


class SwitchRequirement(models.Model):
    name = models.CharField(max_length=255, unique=True)
    node = models.ForeignKey(ToscaClass, limit_choices_to={'type': ToscaClass.NODE_TYPE}, related_name='req_nodes')
    capability = models.ForeignKey(ToscaClass, limit_choices_to={'type': ToscaClass.CAPABILITY_TYPE}, related_name='cap_nodes')
    relationship = models.ForeignKey(ToscaClass, limit_choices_to={'type': ToscaClass.RELATIONSHIP_TYPE}, related_name='rel_nodes')

    class Meta:
        verbose_name_plural = "Switch requirements"

    class JSONAPIMeta:
        resource_name = "switchrequirements"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        obj_definition['node'] = self.node.get_full_name()
        obj_definition['capability'] = self.capability.get_full_name()
        obj_definition['relationship'] = self.relationship.get_full_name()
        return {self.name: obj_definition}


class ApplicationInstance(GraphBase):
    application = models.ForeignKey(Application, related_name='runs')
    type = models.IntegerField(default=0)
    status = models.IntegerField(default=0)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchappinstances"

    def clone_from_application(self):
        instance_translations = {}
        port_translations = {}

        for instance in ComponentInstance.objects.filter(graph=self.application).all():
            clone_instance = False

            old_pk = instance.pk
            instance.pk = None
            instance.id = None
            instance.graph = self
            instance.uuid = uuid.uuid4()

            if instance.component.type.switch_class.title == 'switch.Component':
                instance.save()

                nested_component = NestedComponent(componentinstance_ptr=instance)
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
                instance.component = Component.objects.filter(type__switch_class__title='switch.Host').first()
                instance.last_x = 0
                instance.last_y = 0
                instance.save()

                nested_component = NestedComponent(componentinstance_ptr=instance)
                nested_component.save_base(raw=True)

            elif instance.component.type.switch_class.title == 'switch.ComponentLink':
                instance.save()

                component_link = ComponentLink(componentinstance_ptr=instance)
                component_link.save_base(raw=True)

            instance_translations[old_pk] = instance.pk


        # for original_nested_component_inside_group in NestedComponent.objects.filter(graph=self, parent__isnull=False):
        #     nested_component_inside_group = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.id]).first()
        #     group_nested_component = NestedComponent.objects.filter(id=instance_translations[original_nested_component_inside_group.parent.id]).first()
        #     nested_component_inside_group.parent = group_nested_component
        #     nested_component_inside_group.save()

        for original_component_link in ComponentLink.objects.filter(graph=self.application).all():
            component_link = ComponentLink.objects.filter(componentinstance_ptr_id=instance_translations[original_component_link.id]).first()
            component_link.source_id = port_translations[original_component_link.source_id]
            component_link.target_id = port_translations[original_component_link.target_id]
            component_link.save()

        for original_service in ServiceComponent.objects.filter(graph=self.application).all():
            service = NestedComponent.objects.filter(componentinstance_ptr_id=instance_translations[original_service.id]).first()
            if service is not None:
                print set(original_service.get_source_components())
                deployed_host = NestedComponent.objects.filter(componentinstance_ptr_id=instance_translations[original_service.id]).first()
                for original_component_id in original_service.get_source_components():
                    component = NestedComponent.objects.filter(componentinstance_ptr_id=instance_translations[original_component_id]).first()
                    component.parent = deployed_host
                    component.save()


class ComponentClass(models.Model):
    title = models.CharField(max_length=255)
    classpath = models.CharField(max_length=255, blank=True)
    is_core_component = models.BooleanField(default=False)
    is_template_component = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Component classes"

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchcomponentclass"

    def __unicode__(self):
        return self.title


class ComponentType(models.Model):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')
    title = models.CharField(max_length=255)
    switch_class = models.ForeignKey(ComponentClass, null=True, blank=True, related_name='types')
    primary_colour = models.CharField(max_length=255, blank=True)
    secondary_colour = models.CharField(max_length=255, blank=True)
    icon_name = models.CharField(max_length=1024, blank=True)
    icon_style = models.CharField(max_length=1024, blank=True)
    icon_class = models.CharField(max_length=1024, blank=True)
    icon_svg = models.CharField(max_length=1024, blank=True)
    icon_code = models.CharField(max_length=255, blank=True)
    icon_colour = models.CharField(max_length=255, blank=True)
    tosca_class = models.ForeignKey(ToscaClass, null=True, blank=True, limit_choices_to={'type': ToscaClass.NODE_TYPE})
    artifacts = models.ManyToManyField(SwitchArtifact, blank=True)
    requirements = models.ManyToManyField(SwitchRequirement, blank=True)

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
            return self.parent.is_core()
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

    def is_concrete(self):
        return self.artifacts.count() > 0

    def get_tosca(self):
        if self.tosca_class.is_normative:
            return {}
        else:
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
            if self.requirements.count() > 0:
                requirements = []
                for requirement in self.requirements.all():
                    requirements.append(requirement.get_tosca())
                obj_definition['requirements'] = requirements
            return {self.tosca_class.get_full_name(): obj_definition}

    def get_default_properties_value(self):
        properties = {}

        if self.parent is not None:
            properties.update(self.parent.get_default_properties_value())

        for component_type_property in self.properties.all():
            if component_type_property.required:
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
    SINGLE = 'S'
    MAP = 'M'
    LIST = 'L'
    COLLECTION_TYPE_CHOICES = (
        (SINGLE, 'Single'),
        (MAP, 'Map'),
        (LIST, 'List')
    )

    name = models.CharField(max_length=255)
    data_type = models.ForeignKey(DataType)
    default_value = models.TextField(blank=True)
    collection_type = models.CharField(
        max_length=2,
        choices=COLLECTION_TYPE_CHOICES,
        default=SINGLE,
    )
    required = models.BooleanField(default=True)
    component_type = models.ForeignKey(ComponentType, related_name='properties')

    class Meta:
        verbose_name_plural = "Component type properties"

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchcomponenttypeproperties"

    def __unicode__(self):
        return self.name

    def get_tosca(self):
        obj_definition = {}
        if self.collection_type == ComponentTypeProperty.MAP:
            obj_definition['type'] = 'map'
            obj_definition['entry_schema'] = {'type':self.data_type.name}
        elif self.collection_type == ComponentTypeProperty.LIST:
            obj_definition['type'] = 'list'
            obj_definition['entry_schema'] = {'type':self.data_type.name}
        else:
            obj_definition['type'] = self.data_type.name
            if self.default_value:
                obj_definition['default'] = yaml.load(str(self.default_value).replace("\t", "    "))
        if not self.required:
            obj_definition['required'] = 'false'
        return {self.name: obj_definition}

    def get_default_value(self):
       if self.default_value:
            return yaml.load(str(self.default_value).replace("\t", "    "))
       else:
           if self.collection_type == ComponentTypeProperty.MAP:
                map = {}
                for x in range(0, 3):
                    map[self.data_type.name.rpartition('.')[2] + '_' + str(x)] = self.data_type.get_default_value()
                return map
           elif self.collection_type == ComponentTypeProperty.LIST:
               list = []
               for x in range(0, 3):
                   list.append(
                       {self.data_type.name.rpartition('.')[2] + '_' + str(x): self.data_type.get_default_value()})
               return list
           else:
                return self.data_type.get_default_value()


class Component(GraphBase):
    type = models.ForeignKey(ComponentType, related_name='components', null=False)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchcomponents"

    def __unicode__(self):
        return 'Component: ' + self.title + ' (' + str(self.type.title) + ')'

    def get_base_instance(self):
        return ComponentInstance.objects.filter(graph=self, component=self).select_subclasses().first()

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


class ComponentInstance(models.Model):
    objects = InheritanceManager()
    uuid = models.UUIDField(default=uuid.uuid4, editable=True)
    graph = models.ForeignKey(GraphBase, related_name='instances')
    component = models.ForeignKey(Component, related_name='child_instances')
    neighbors = models.ManyToManyField('self', through='ServiceLink', symmetrical=False)
    title = models.CharField(max_length=255)
    mode = models.CharField(max_length=255, blank=True)
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


class NestedComponent(ComponentInstance):
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
                    'port': " " + port.title + " ",
                    'type': port.type
                }
                properties.setdefault(port.type + '_ports', {}).update({str(port.uuid): port_obj})

            if self.parent is not None:
                properties['group'] = self.parent.uuid

            requirements = []
            for service_link in ServiceLink.objects.filter(target=self).all():
                if service_link.source.component.type.title == 'Requirement':
                    tosca_hw_req = service_link.source.get_tosca()
                    requirements.append({'host':{'node_filter': {'capabilities': tosca_hw_req[str(service_link.source.uuid)]['properties']}}})

                if service_link.source.component.type.title == 'Virtual Machine':
                    requirements.append({'host': str(service_link.source.uuid)})

                if service_link.source.component.type.title == 'Monitoring Agent':
                    requirements.append({'monitored_by': str(service_link.source.uuid)})

                if service_link.source.component.type.title == 'Constraint':
                    tosca_constraint = service_link.source.get_tosca()
                    properties.update(tosca_constraint[str(service_link.source.uuid)]['properties'])

            for dependency_link in DependencyLink.objects.filter(dependant=self).all():
                requirements.append({'dependency': str(dependency_link.dependency.uuid)})

            if requirements:
                data_obj[str(self.uuid)]['requirements'] = requirements

        return data_obj


class ComponentPort(models.Model):
    instance = models.ForeignKey(ComponentInstance, related_name='ports')
    type = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    uuid = models.CharField(max_length=255)

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchcomponentports"


class ComponentLink(ComponentInstance):
    source = models.ForeignKey(ComponentPort, null=True, blank=True, related_name='targets')
    target = models.ForeignKey(ComponentPort, null=True, blank=True, related_name='sources')

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "graph_connections"

    def get_label(self):
        if self.source is not None and self.target is not None:
            return self.source.instance.title.lower().replace(" ", "_") + ":" + self.target.instance.title.lower().replace(" ","_")
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
        properties['target'] = {'address': properties.get('target_address',''), 'component_name': self.target.instance.uuid,
                                'netmask': properties.get('netmask',''),'port_name': self.target.uuid}
        properties['source'] = {'address': properties.get('source_address',''), 'component_name': self.source.instance.uuid,
                                'netmask': properties.get('netmask',''),'port_name': self.source.uuid}
        if 'netmask' in properties:
            del properties['netmask']
        if 'source_address' in properties:
            del properties['source_address']
        if 'target_address' in properties:
            del properties['target_address']

        return data_obj


class DependencyLink(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    graph = models.ForeignKey(GraphBase, related_name='dependency_links')
    dependant = models.ForeignKey(ComponentInstance, related_name='dependencies')
    dependency = models.ForeignKey(ComponentInstance, related_name='dependants')

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchdependencylinks"

    def get_graph(self):
        graph_obj = {
            'id': self.uuid,
            'type': 'switch.DependencyLink',
            'target': {
                'id': self.dependency.uuid
            },
            'source': {
                'id': self.dependant.uuid
            }
        }

        text, fill = self.dependency.get_mode_labels()

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


class ServiceLink(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    graph = models.ForeignKey(GraphBase, related_name='service_links')
    source = models.ForeignKey(ComponentInstance, related_name='sources')
    target = models.ForeignKey(ComponentInstance, related_name='targets')

    class JSONAPIMeta:
        def __init__(self):
            pass

        resource_name = "switchservicelinks"

    def get_graph(self):
        link_type = 'switch.ServiceLink'

        print str(self.pk) + ' ' + self.source.component.type.title + ' --> ' + self.target.component.type.title

        if self.target.component.type.title == 'Monitoring Agent' and self.source.component.type.title == 'SWITCH.MonitoringServer':
            link_type = 'switch.MonitoringLink'

        graph_obj = {
            'id': self.uuid,
            'type': link_type,
            'target': {
                'id': self.target.uuid
            },
            'source': {
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


class ServiceComponent(ComponentInstance):
    class JSONAPIMeta:
        def __init__(self):
            pass

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
        elif self.component.type.switch_class.title == 'switch.DST':
            graph_obj['size'] = {"width": 25, "height": 35}

        return graph_obj

    def get_tosca(self):
        data_obj = super(ServiceComponent, self).get_tosca()
        properties = data_obj[str(self.uuid)]
        # properties['class'] = self.component.type.title

        requirements = []
        for service_link in ServiceLink.objects.filter(target=self).all():
            if service_link.source.component.type.title == 'SWITCH.MonitoringServer':
                requirements.append({'monitor_server_endpoint': str(service_link.source.uuid)})

        if requirements:
            data_obj[str(self.uuid)]['requirements'] = requirements

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
        def __init__(self):
            pass

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
        def __init__(self):
            pass

        resource_name = "switchdocuments"

    def __unicode__(self):
        return str(self.description) + ' (' + self.file.name + ')'


class DSTInstance(models.Model):
    dst_service_id = models.CharField(max_length=255, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    token = models.CharField(max_length=255, blank=True)

    class JSONAPIMeta:
        def __init__(self):
            pass

    @classmethod
    def create(cls, service_id):
        instance = cls(dst_service_id=service_id)
        return instance


class DSTRequest(models.Model):
    dst_instance_id = models.CharField(max_length=255, blank=True)
    date_requested = models.DateTimeField(auto_now_add=True)
    dst_url = models.CharField(max_length=255, blank=True)
    dst_payload = models.TextField(null=True)
    dst_response = models.TextField(null=True)

    class JSONAPIMeta:
        def __init__(self):
            pass


class DSTUpdate(models.Model):
    dst_instance_id = models.CharField(max_length=255, blank=True)
    date_updated = models.DateTimeField(auto_now_add=True)
    dst_query_params = models.TextField(null=True)
    dst_update_payload = models.TextField(null=True)

    class JSONAPIMeta:
        def __init__(self):
            pass