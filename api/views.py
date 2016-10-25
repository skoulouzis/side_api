import json
import yaml
import os
import subprocess
import uuid

from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, FileResponse
from rest_framework import viewsets
from rest_framework.decorators import list_route, detail_route
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FileUploadParser, JSONParser
from rest_framework.response import Response
from rest_framework.filters import DjangoFilterBackend, SearchFilter
from rest_framework import views
from rest_framework_xml.parsers import XMLParser

from api.permissions import BelongsToUser, AppBelongsToUser
from models import *
from serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from side_api import settings
import services

from yaml.dumper import Dumper
from yaml.representer import SafeRepresenter


class YamlDumper(Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(YamlDumper, self).increase_indent(flow, False)

YamlDumper.add_representer(str,
       SafeRepresenter.represent_str)

YamlDumper.add_representer(unicode,
        SafeRepresenter.represent_unicode)


class SwitchAppViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows SwitchApps to be CRUDed.
    """
    serializer_class = SwitchAppSerializer
    authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)

    def list(self, request, **kwargs):
        apps = SwitchApp.objects.filter()
        # apps = SwitchApp.objects.filter(user=self.request.user)
        serializer = self.get_serializer(apps, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return SwitchApp.objects.filter()

    def perform_create(self, serializer):
        app = serializer.save(user=self.request.user)
        SwitchAppGraph.objects.create(app_id=app.id)

    @detail_route(methods=['get'], permission_classes=[])
    def tosca(self, request, pk=None, *args, **kwargs):
        graph = SwitchAppGraph.objects.filter(app_id=pk).latest('updated_at')
        with open(graph.file.url, 'r') as f:
            graph_json = json.loads(f.read())

        components = []
        external = []
        network = []
        attributes = []
        groups = []
        components_connections = []
        services_connections = []
        virtual_machines = []
        virtual_networks = []

        for cell in graph_json['cells']:
            data_obj = {}
            #Cell['type'] corresponds with the different shapes we have created for switch in joint.js
            if cell['type'].startswith('switch'):
                db_record = SwitchComponent.objects.get(uuid=cell['id'])
                properties = {}
                # data_obj['id'] = db_record.id
                properties['title'] = db_record.title
                # data_obj['uuid'] = cell['id']

                if 'enter metadata as YAML' not in db_record.properties:
                    metadata = yaml.load(str(db_record.properties).replace("\t","    "))
                    properties.update(metadata)

                if cell['type'] == 'switch.Component':
                    properties['scaling_mode'] = db_record.mode
                    properties['inPorts'] = cell['inPorts']
                    properties['outPorts'] = cell['outPorts']
                    if 'parent' in cell:
                        properties['group'] = cell['parent']

                    data_obj[cell['id']] = properties

                    # The shape in joint.js "component" can be a "component", a "external component" or a "network"
                    if db_record.type == 'Component':
                        components.append(data_obj)
                    elif db_record.type == 'Network':
                        network.append(data_obj)
                    elif db_record.type == 'External Component':
                        external.append(data_obj)

                if cell['type'] == 'switch.VirtualResource':
                    properties['class'] = db_record.type

                    data_obj[cell['id']] = properties

                    # The shape in joint.js "VirtualResource" can be a "Virtual Machine" or a "Virtual Network"
                    if db_record.type == 'Virtual Machine':
                        virtual_machines.append(data_obj)
                    elif db_record.type == 'Virtual Network':
                        virtual_networks.append(data_obj)

                if cell['type'] == 'switch.Attribute':
                    # The shape in joint.js "attribute" can be a "monitoring agent", "event listener", "message passer"
                    # "constraint", "adaptation profile" or a "requirement"
                    properties['class'] = db_record.type

                    data_obj[cell['id']] = properties
                    attributes.append(data_obj)

                if cell['type'] == 'switch.Group':
                    if 'embeds' in cell:
                        properties['members'] = cell['embeds']

                    data_obj[cell['id']] = properties
                    groups.append(data_obj)

                if cell['type'] == 'switch.ComponentLink':
                    target = {}
                    target['id'] = cell['target']['id']
                    target['port'] = cell['target']['port']
                    properties['target'] = target;
                    source = {}
                    source['id'] = cell['source']['id']
                    source['port'] = cell['source']['port']
                    properties['source'] = source

                    data_obj[cell['id']] = properties
                    components_connections.append(data_obj)

                if cell['type'] == 'switch.ServiceLink':
                    target = {}
                    target['id'] = cell['target']['id']
                    properties['target'] = target;
                    source = {}
                    source['id'] = cell['source']['id']
                    properties['source'] = source

                    data_obj[cell['id']] = properties
                    services_connections.append(data_obj)

        data = {
            'data': {
                'components': components,
                'external_components': external,
                'network_components': network,
                'attributes': attributes,
                'groups': groups,
                'connections': {
                    'components_connections': components_connections,
                    'services_connections': services_connections
                },
                'virtual_resources': {
                    'virtual_machines': virtual_machines,
                    'virtual_networks': virtual_networks
                }
            }
        }

        return JsonResponse(data)

    @detail_route(methods=['get'], permission_classes=[])
    def validate(self, request, pk=None, *args, **kwargs):
        #TODO: implement the validation
        app_tosca_json = json.loads(self.tosca(request=request, pk=pk).content)

        formal_validation_result = services.validate(pk,app_tosca_json)
        result = 'ok'
        message = 'validation done correctly'

        validation_result = {
            'validation': {
                'result': result,
                'message': formal_validation_result.content
            }
        }

        return JsonResponse(validation_result)


    @detail_route(methods=['get'], permission_classes=[])
    def planVirtualInfrastructure(self, request, pk=None, *args, **kwargs):
        # TODO: implement the planning of the virtual infrastructure
        result = ''
        message = ''
        app = SwitchApp.objects.get(id=pk)
        if app.status >= 1:
            result = 'error'
            message = 'application has already a planned infrastructure'
        else:
            num_hw_req = SwitchComponent.objects.filter(app_id=pk,type='Requirement').count()
            if num_hw_req == 0:
                result = 'error'
                message = 'no hardware requirements defined'
            else:
                app_tosca_json = json.loads(self.tosca(request=request, pk=pk).content)
                return_code = subprocess.call(['java', '-jar', os.path.join(settings.BASE_DIR, 'external_tools', 'planner', 'test.jar'), pk])
                if return_code == 0:
                    result = 'ok'
                    message = 'plan done correctly'
                    app.status = 1
                    app.save()

                    # Temporary simulate the planner
                    graph = SwitchAppGraph.objects.filter(app_id=pk).latest('updated_at')
                    with open(graph.file.url, 'r') as f:
                        graph_json = json.loads(f.read())

                    for cell in graph_json['cells']:
                        if cell['type'].startswith('switch'):
                            db_record = SwitchComponent.objects.get(uuid=cell['id'])

                            if db_record.type == 'Requirement':
                                # Create virtual machine that satisfies the requirement, storing it in db and displaying it in graph
                                virtual_resource = SwitchComponent.objects.create(app_id=pk, uuid = uuid.uuid4())
                                virtual_resource.title = 'VM_' + cell['attrs']['switch']['title']
                                virtual_resource.mode = 'single'
                                virtual_resource.type = 'Virtual Machine'
                                vr_properties = {
                                    "type": "switch/compute",
                                    "OStype": "Ubuntu 14.04",
                                    "domain": "ec2.us-east-1.amazonaws.com",
                                    "script": os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner','topology','t1','script','install.sh'),
                                    "installation": os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner','topology','t1','installation','Server'),
                                    "public_address": virtual_resource.uuid.urn[9:]
                                }

                                # Get the ports of the component the requirement is linked to
                                # TODO: At the moment it only works when one requirement is linked to only one component
                                for service_connection in app_tosca_json['data']['connections']['services_connections']:
                                    service_connection_key = service_connection.keys()[0]
                                    service_connection_value = service_connection.values()[0]
                                    # Check if the connection is for his requirement
                                    if service_connection_value['source']['id'] == cell['id']:
                                        # find the component link with the requirement
                                        for component in app_tosca_json['data']['components']:
                                            component_key = component.keys()[0]
                                            component_value = component.values()[0]
                                            if (component_key == service_connection_value['target']['id']) and (len(component_value[u'inPorts'])>0 or len(component_value[u'outPorts'])>0):
                                                vr_properties['ethernet_port']=[]
                                                # for each input port in the component see if it is used for connecting to other component
                                                for input_port in component_value[u'inPorts']:
                                                    # Check if port in the component is used to connect to other component
                                                    # TODO: At the moment only works if one port has as max one connection
                                                    for component_connection in app_tosca_json['data']['connections']['components_connections']:
                                                        component_connection_key = component_connection.keys()[0]
                                                        component_connection_value = component_connection.values()[0]
                                                        if component_key == component_connection_value['target']['id']:
                                                            ethernet_port = {
                                                                "name": input_port,
                                                                "connection_name": component_connection_key + ".target"
                                                            }
                                                            vr_properties['ethernet_port'].append(ethernet_port)

                                                # for each output port in the component see if it is used for connecting to other component
                                                for output_port in component_value[u'outPorts']:
                                                    # Check if port in the component is used to connect to other component
                                                    # TODO: At the moment only works if one port has as max one connection
                                                    for component_connection in app_tosca_json['data']['connections']['components_connections']:
                                                        component_connection_key = component_connection.keys()[0]
                                                        component_connection_value = component_connection.values()[0]
                                                        if component_key == component_connection_value['source']['id']:
                                                            ethernet_port = {
                                                                "name": output_port,
                                                                "connection_name": component_connection_key + ".source"
                                                            }
                                                            vr_properties['ethernet_port'].append(ethernet_port)


                                # Depending on the requirement properties the virtual machine will be different
                                requirement_properties = yaml.load(str(db_record.properties).replace("\t", "    "))
                                if 'machine_type' in requirement_properties:
                                    if requirement_properties['machine_type']=="big":
                                        vr_properties['nodetype'] = "t2.large"
                                    elif requirement_properties['machine_type']=="small":
                                        vr_properties['nodetype'] = "t2.small"
                                    else:
                                        vr_properties['nodetype'] = "t2.medium"
                                else:
                                    vr_properties['nodetype'] = "t2.medium"

                                virtual_resource.properties = yaml.dump(vr_properties, Dumper=YamlDumper, default_flow_style=False)
                                virtual_resource.save()

                                vr_cell = {
                                    "angle": 0,
                                    "title": virtual_resource.title,
                                    "attrs": {
                                        ".icon": {
                                            "d": "M1792 288v960q0 13 -9.5 22.5t-22.5 9.5h-1600q-13 0 -22.5 -9.5t-9.5 -22.5v-960q0 -13 9.5 -22.5t22.5 -9.5h1600q13 0 22.5 9.5t9.5 22.5zM1920 1248v-960q0 -66 -47 -113t-113 -47h-736v-128h352q14 0 23 -9t9 -23v-64q0 -14 -9 -23t-23 -9h-832q-14 0 -23 9t-9 23 v64q0 14 9 23t23 9h352v128h-736q-66 0 -113 47t-47 113v960q0 66 47 113t113 47h1600q66 0 113 -47t47 -113z",
                                            "fill": "rgb(255, 255, 255)"
                                        },
                                        "switch": {
                                            "code": "&#xf26c",
                                            "type": "new_virtual_machine",
                                            "class": "Virtual Machine",
                                            "title": virtual_resource.title,
                                        },
                                        ".label": {
                                            "html": virtual_resource.title,
                                            "fill": "#333"
                                        },
                                        ".body": {
                                            "fill-opacity": ".90",
                                            "stroke": "rgb(184, 70, 218)",
                                            "stroke-width": 2,
                                            "fill": "rgb(198, 107, 225)"
                                        }
                                    },
                                    "position": {
                                        "y": cell['position']['y'] + 80,
                                        "x": cell['position']['x'],
                                    },
                                    "z": cell['z'] + 1,
                                    "type": "switch.VirtualResource",
                                    "id": virtual_resource.uuid.urn[9:],
                                    "size": {
                                        "width": 35,
                                        "height": 35
                                    }
                                }
                                graph_json['cells'].append(vr_cell)

                                service_link = SwitchComponent.objects.create(app_id=pk, uuid=uuid.uuid4())
                                service_link.title = 'connection'
                                service_link.mode = 'single'
                                service_link.type = 'ServiceLink'
                                link_properties = {"data": "enter metadata as YAML"}
                                service_link.properties = yaml.dump(link_properties, Dumper=YamlDumper, default_flow_style=False)
                                service_link.save()

                                vr_link = {
                                    "target": {
                                        "id": cell['id']
                                    },
                                    "labels": [
                                        {
                                            "position": 0.2,
                                            "attrs": {
                                                "text": {
                                                    "text": "",
                                                    "fill": "black"
                                                },
                                                "rect": {
                                                    "fill": "none"
                                                }
                                            }
                                        },
                                        {
                                            "position": 0.8,
                                            "attrs": {
                                                "text": {
                                                    "text": "",
                                                    "fill": "black"
                                                },
                                                "rect": {
                                                    "fill": "none"
                                                }
                                            }
                                        }
                                    ],
                                    "source": {
                                        "id": vr_cell['id']
                                    },
                                    "attrs": {
                                        "switch": {
                                            "class": "ServiceLink",
                                            "title": "connection"
                                        }
                                    },
                                    "z": 22,
                                    "type": "switch.ServiceLink",
                                    "id": service_link.uuid.urn[9:]
                                }
                                graph_json['cells'].append(vr_link)

                    with open(graph.file.url, 'w') as f:
                        json.dump(graph_json,f)
                else:
                    result = 'error'
                    message = 'planification of virtual infrastructure has failed'

        plan_result = {
            'plan': {
                'result': result,
                'message': message
            }
        }

        return JsonResponse(plan_result)


    @detail_route(methods=['get'], permission_classes=[])
    def provisionVirtualInfrastructure(self, request, pk=None, *args, **kwargs):
        # TODO: implement the provision of the virtual infrastructure
        result = ''
        message = ''

        app = SwitchApp.objects.get(id=pk)
        if app.status < 1:
            result = 'error'
            message = 'virtual infrastructure has not been planned yet'
        if app.status >= 2:
            result = 'error'
            message = 'application has already a provisioned infrastructure'
        else:
            # get the tosca file of the application
            app_tosca_json = json.loads(self.tosca(request=request, pk=pk).content)

            uuid = str(app.uuid)
            with open(os.path.join(settings.BASE_DIR, 'external_tools','provisioner', uuid + '.yml'), 'w') as f:
                credentials = {
                    'publicKeyPath': os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner','id_rsa.pub'),
                    'userName': "fran"
                }
                yaml.dump(credentials, f, Dumper=YamlDumper, default_flow_style=False)

                if len(app_tosca_json['data']['virtual_resources']['virtual_machines']) > 0:
                    components={'components': []}
                    for vm in app_tosca_json['data']['virtual_resources']['virtual_machines']:
                        component= vm.values()[0]
                        component['name']=vm.keys()[0]
                        components['components'].append(component)
                    yaml.dump(components, f, Dumper=YamlDumper, default_flow_style=False)

                if len(app_tosca_json['data']['connections']['components_connections'])>0:
                    connections = {'connections': []}
                    for component_connection in app_tosca_json['data']['connections']['components_connections']:
                        connection = component_connection.values()[0]
                        connection['name'] = component_connection.keys()[0]
                        # Adapt it to provisioner format
                        for vm in app_tosca_json['data']['virtual_resources']['virtual_machines']:
                            vm_properties = vm.values()[0]
                            vm_key = vm.keys()[0]
                            for ethernet_port in vm_properties['ethernet_port']:
                                if ethernet_port['connection_name'] == connection['name'] + '.target':
                                    connection['target']['component_name'] = vm_key

                        connection['target']['port_name'] = connection['target']['port']
                        connection['target']['netmask'] = connection['netmask']
                        connection['target']['address'] = connection['target_address']
                        del connection['target']['id']
                        del connection['target']['port']

                        #connection['source']['component_name'] = connection['source']['id']
                        for vm in app_tosca_json['data']['virtual_resources']['virtual_machines']:
                            vm_properties = vm.values()[0]
                            vm_key = vm.keys()[0]
                            for ethernet_port in vm_properties['ethernet_port']:
                                if ethernet_port['connection_name'] == connection['name'] + '.source':
                                    connection['source']['component_name'] = vm_key

                        connection['source']['port_name'] = connection['source']['port']
                        connection['source']['netmask'] = connection['netmask']
                        connection['source']['address'] = connection['source_address']

                        del connection['source']['id']
                        del connection['source']['port']

                        del connection['netmask']
                        del connection['target_address']
                        del connection['source_address']

                        connections['connections'].append(connection)
                    yaml.dump(connections, f, Dumper=YamlDumper, default_flow_style=False)

            return_code = subprocess.call(['java', '-jar',
                                           os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', 'EC2Provision_test.jar'),
                                           os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', 'rootkey.csv'),
                                           os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '.yml')],
                                          cwd=os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner'))

            if return_code == 0:
                result = 'ok'
                message = 'provision done correctly'

                graph = SwitchAppGraph.objects.filter(app_id=pk).latest('updated_at')
                with open(graph.file.url, 'r') as f:
                    graph_json = json.loads(f.read())

                with open(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '_provisioned.yml'), 'r') as f:
                    tosca_inf_provisioned = yaml.load(f.read())

                for vm in tosca_inf_provisioned['components']:
                    db_record = SwitchComponent.objects.get(uuid=vm['name'])
                    db_record.properties = yaml.dump(vm, Dumper=YamlDumper, default_flow_style=False)
                    db_record.save()

                    for cell in graph_json['cells']:
                        if cell['id'] == str(db_record.uuid):
                            cell['attrs']['.label']['html'] += ' (' + vm['public_address'] + ')'

                with open(graph.file.url, 'w') as f:
                    json.dump(graph_json, f)

                app.status = 2
                app.save()

                # Delete files input and output files used by the provisioner
                os.remove(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '.yml'))
                os.remove(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '_provisioned.yml'))
            else:
                result = 'error'
                message = 'provision has failed'

        provision_result = {
            'provision': {
                'result': result,
                'message': message
            }
        }

        return JsonResponse(provision_result)


class SwitchAppGraphViewSet(viewsets.ModelViewSet):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated, AppBelongsToUser,)
    serializer_class = SwitchAppGraphSerializer
    queryset = SwitchAppGraph.objects.all()
    parser_classes = (JSONParser,)

    def list(self, request, switchapps_pk=None, **kwargs):
        graphs = self.queryset.filter(app_id=switchapps_pk)
        serializer = self.get_serializer(graphs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None, switchapps_pk=None):
        graph = self.queryset.get(id=pk, app_id=switchapps_pk)
        serializer = self.get_serializer(graph)
        return Response(serializer.data)

    @list_route(permission_classes=[])
    def generated(self, request, switchapps_pk=None, *args, **kwargs):
        components = SwitchAppGraphBase.objects.filter(component__app_id=switchapps_pk).all()

        graph_components = []
        graph_groups = []
        graph_links = []
        graph_attributes = []
        graph_services = []

        response_cells = []

        for cell in components:
            try:
                graph_obj = {'type': cell.type,
                             'position': {},
                             'attrs': {},
                             'inPorts': [],
                             'outPorts': []}
                graph_obj['position']['x'] = cell.last_x
                graph_obj['position']['y'] = cell.last_y

                component = cell.component
                graph_obj['id'] = component.uuid
                graph_obj['attrs']['switch_class'] = component.type
                graph_obj['attrs']['switch_title'] = component.title
                graph_obj['attrs']['switch_type'] = component.title
                graph_obj['attrs']['.label'] = {"html": component.title, "fill": "#333"}

                if component.switch_type is None:
                    switch_type = SwitchComponentType.objects.filter(title=component.type).first()
                    if switch_type is not None:
                        component.switch_type = switch_type
                        component.save()

                if component.switch_type is not None:
                    graph_obj['attrs']['.icon'] = {"d": component.switch_type.icon_svg, "fill": component.switch_type.icon_colour}

                    if cell.type == 'switch.Component':
                        inPorts = SwitchAppGraphPort.objects.filter(graph_component=cell, type='in').all()
                        outPorts = SwitchAppGraphPort.objects.filter(graph_component=cell, type='out').all()
                        stroke_opacity = ".0"
                        fill_opacity = ".0"

                        if component.mode != 'single':
                            stroke_opacity = "1"
                            fill_opacity = ".95"

                        graph_obj['attrs']['.body'] = {
                                        "fill": component.switch_type.primary_colour,
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
                                        "fill": component.switch_type.secondary_colour
                                    }
                        graph_obj['attrs']['.multi2'] = {
                                        "stroke-opacity": stroke_opacity,
                                        "fill-opacity": fill_opacity,
                                        "rx": 4,
                                        "ry": 4,
                                        "stroke-width": 1,
                                        "fill": component.switch_type.secondary_colour
                                    }

                        if len(inPorts) > 0:
                            gap = 100 / (len(inPorts) * 2)
                            portlen = 0

                            for port in inPorts:
                                graph_obj['inPorts'].append(port.title)
                                key = '.inPorts>.port%s' % str(portlen)
                                ref_y = (portlen * 2 * gap) + gap
                                portlen += 1
                                graph_obj['attrs'][key] = {'ref': '.body', 'ref-y': ref_y}
                                graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                                graph_obj['attrs'][key + '>.port-body'] = {'type': 'in', 'id': port.title}

                        if len(outPorts) > 0:
                            gap = 100 / (len(outPorts) * 2)
                            portlen = 0

                            for port in outPorts:
                                graph_obj['outPorts'].append(port.title)
                                key = '.outPorts>.port%s' % str(portlen)
                                ref_y = (portlen * 2 * gap) + gap
                                portlen += 1
                                graph_obj['attrs'][key] = {'ref': '.body', 'ref-dx': 0, 'ref-y': ref_y}
                                graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                                graph_obj['attrs'][key + '>.port-body'] = {'type': 'in', 'id': port.title}

                        height = len(inPorts) if len(inPorts) > len(outPorts) else len(outPorts)
                        if height < 2:
                            height = 30
                        else:
                            height *= 25

                        graph_component = SwitchAppGraphComponent.objects.filter(id=cell.id).first()

                        if graph_component.parent is not None:
                            graph_obj['parent'] = graph_component.parent.component.uuid

                        graph_obj['size'] = {"width": 100, "height": height}
                        response_cells.append(graph_obj)
                    elif cell.type == 'switch.Group':
                        graph_groups.append(cell)
                        graph_obj['embeds'] = []

                        graph_component = SwitchAppGraphComponent.objects.filter(id=cell.id).first()

                        for child in graph_component.children.all():
                            graph_obj['embeds'].append(child.component.uuid)

                        response_cells.append(graph_obj)
                    elif cell.type == 'switch.Attribute':
                        graph_obj['attrs']['.body'] = {
                                        "fill": component.switch_type.primary_colour,
                                        "stroke": component.switch_type.secondary_colour,
                                        "stroke-width": 2,
                                        "fill-opacity": ".95"
                                    }

                        graph_attributes.append(cell)
                        graph_obj['size'] = {"width": 30, "height": 30}
                        response_cells.append(graph_obj)
                    elif cell.type == 'switch.VirtualResource':
                        graph_obj['attrs']['.body'] = {
                                        "fill": component.switch_type.primary_colour,
                                        "stroke": component.switch_type.secondary_colour,
                                        "stroke-width": 2,
                                        "fill-opacity": ".95"
                                    }

                        graph_services.append(cell)
                        graph_obj['size'] = {"width": 35, "height": 35}
                        response_cells.append(graph_obj)

                if cell.type == 'switch.ComponentLink':
                    graph_obj = {'type': 'link', 'id': component.uuid, 'attrs': {}, "embeds": ""}
                    graph_obj['attrs']['switch_class'] = component.type
                    graph_obj['attrs']['switch_title'] = component.title
                    graph_component = SwitchAppGraphComponentLink.objects.filter(id=cell.id).first()
                    graph_obj['target'] = {
                        "port": graph_component.target.title,
                        "id": graph_component.target.graph_component.component.uuid
                    }
                    graph_obj['source'] = {
                        "port": graph_component.source.title,
                        "id": graph_component.source.graph_component.component.uuid
                    }

                    if graph_component.source.graph_component.component.mode == 'onetomany':
                        source_text = '1..*'
                        source_rect = 'white'
                    elif graph_component.source.graph_component.component.mode == 'zerotomany':
                        source_text = '0..*'
                        source_rect = 'white'
                    else:
                        source_text = ''
                        source_rect = 'none'

                    if graph_component.target.graph_component.component.mode == 'onetomany':
                        target_text = '1..*'
                        target_rect = 'white'
                    elif graph_component.target.graph_component.component.mode == 'zerotomany':
                        target_text = '0..*'
                        target_rect = 'white'
                    else:
                        target_text = ''
                        target_rect = 'none'

                    graph_obj['labels'] = [
                            {
                                "position": 0.2,
                                "attrs": {
                                    "text": {
                                        "text": source_text,
                                        "fill": "black"
                                    },
                                    "rect": {
                                        "fill": source_rect
                                    }
                                }
                            },
                            {
                                "position": 0.8,
                                "attrs": {
                                    "text": {
                                        "text": target_text,
                                        "fill": "black"
                                    },
                                    "rect": {
                                        "fill": target_rect
                                    }
                                }
                            },
                            {
                                "position": 0.5,
                                "attrs": {
                                    "text": {
                                        "text": graph_component.component.title,
                                        "fill": "black"
                                    },
                                    "rect": {
                                        "fill": "white"
                                    }
                                }
                            }
                        ]

                    graph_links.append(cell)
                    response_cells.append(graph_obj)


            except Exception as e:
                print e.message

        service_links = SwitchAppGraphServiceLink.objects.filter(source__component__app_id=switchapps_pk).all()
        for cell in service_links:
            try:
                graph_obj = {'type': 'link', 'attrs': {
                    ".marker-target": {
                        "stroke": "#4b4a67",
                        "d": "M 10 0 L 0 5 L 10 10 z",
                        "fill": "#4b4a67"
                    }
                }, 'target': {
                    "id": cell.target.component.uuid
                }, 'source': {
                    "id": cell.source.component.uuid
                }}

                if cell.target.component.mode == 'onetomany':
                    target_text = '1..*'
                    target_rect = 'white'
                elif cell.target.component.mode == 'zerotomany':
                    target_text = '0..*'
                    target_rect = 'white'
                else:
                    target_text = ''
                    target_rect = 'none'

                graph_obj['labels'] = [
                        {
                            "position": 0.2,
                            "attrs": {
                                "text": {
                                    "text": "",
                                    "fill": "black"
                                },
                                "rect": {
                                    "fill": "none"
                                }
                            }
                        },
                        {
                            "position": 0.8,
                            "attrs": {
                                "text": {
                                    "text": target_text,
                                    "fill": "black"
                                },
                                "rect": {
                                    "fill": target_rect
                                }
                            }
                        }
                    ]

                graph_links.append(cell)
                response_cells.append(graph_obj)


            except Exception as e:
                print e.message

        return Response({
                'type': 'graphs',
                'id': str(switchapps_pk),
                'attributes': {
                    'graph': {
                        'cells': response_cells
                    }
                }
            })

    @list_route(permission_classes=[])
    def latest(self, request, switchapps_pk=None, *args, **kwargs):
        graph = self.queryset.filter(app_id=switchapps_pk).latest('updated_at')
        if (graph.file):
            serializer = self.get_serializer(graph)
            return Response(serializer.data)
        else:
            return Response("No graph file for the application has been found")

    def put(self, request, switchapps_pk=None, **kwargs):
        json_data = request.data
        graph = self.queryset.filter(app_id=switchapps_pk).latest('updated_at')

        suffixes = ['second', 'first']
        suffixes_next = ['third', 'second']
        uuid = str(graph.app.uuid)

        if os.path.isfile(os.path.join(settings.BASE_DIR, 'graphs', uuid + '_third.json')):
            os.remove(os.path.join(settings.BASE_DIR, 'graphs', uuid + '_third.json'))

        for suffix in suffixes:
            for filename in os.listdir(os.path.join(settings.BASE_DIR, 'graphs')):
                if filename.startswith(uuid):
                    if filename.endswith(suffix + '.json'):
                        new_name = "%s_%s.json" % (uuid, suffixes_next[suffixes.index(suffix)])
                        os.rename(os.path.join(settings.BASE_DIR, 'graphs', filename),
                                  os.path.join(settings.BASE_DIR, 'graphs', new_name))

        for filename in os.listdir(os.path.join(settings.BASE_DIR, 'graphs')):
            if filename == uuid + '.json':
                os.rename(os.path.join(settings.BASE_DIR, 'graphs', filename),
                          os.path.join(settings.BASE_DIR, 'graphs', uuid + '_first.json'))

        graph.file.save(uuid + '.json', ContentFile(json.dumps(json_data)))
        graph.file.close()

        try:
            graph_components = []
            graph_groups = []
            graph_service_links = []
            graph_component_links = []
            graph_attributes = []
            graph_virtual_resource = []

            for cell in json_data['cells']:
                if cell['type'] == 'switch.Component':
                    graph_components.append(cell)
                elif cell['type'] == 'switch.Group':
                    graph_groups.append(cell)
                elif cell['type'] == 'switch.Attribute':
                    graph_attributes.append(cell)
                elif cell['type'] == 'switch.VirtualResource':
                    graph_virtual_resource.append(cell)
                elif cell['type'] == 'switch.ServiceLink':
                    graph_service_links.append(cell)
                elif cell['type'] == 'switch.ComponentLink':
                    graph_component_links.append(cell)

            for cell in graph_groups:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphComponent.objects.get_or_create(component=component, type='switch.Group')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

            for cell in graph_attributes:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphService.objects.get_or_create(component=component, type='switch.Attribute')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

            for cell in graph_virtual_resource:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphService.objects.get_or_create(component=component, type='switch.VirtualResource')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

            for cell in graph_components:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphComponent.objects.get_or_create(component=component, type='switch.Component')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

                    port_objs = []

                    if 'parent' in cell:
                        parent = SwitchComponent.objects.filter(uuid=cell['parent'], app_id=switchapps_pk).first()
                        parent_obj, created = SwitchAppGraphComponent.objects.get_or_create(component=parent)
                        graph_obj.parent = parent_obj

                    if 'inPorts' in cell:
                        for port in cell['inPorts']:
                            port_obj, created = SwitchAppGraphPort.objects.get_or_create(graph_component=graph_obj, type='in', title=port)
                            port_objs.append(port_obj)

                        graph_obj.ports = port_objs

                    if 'outPorts' in cell:
                        for port in cell['outPorts']:
                            port_obj, created = SwitchAppGraphPort.objects.get_or_create(graph_component=graph_obj, type='out', title=port)
                            port_objs.append(port_obj)

                        graph_obj.ports = port_objs

                    old_port_objs = SwitchAppGraphPort.objects.filter(graph_component=graph_obj)
                    for old_port in old_port_objs:
                        if old_port not in port_objs:
                            old_port.delete()

                    graph_obj.save()

            for obj in SwitchAppGraphServiceLink.objects.filter(source__component__app_id=switchapps_pk).all():
                obj.delete()

            for cell in graph_service_links:
                graph_obj = None
                source_obj = None
                target_obj = None

                if 'source' in cell:
                    source = cell['source']
                    component = SwitchComponent.objects.filter(uuid=source['id'], app_id=switchapps_pk).first()
                    if component is not None:
                        source_obj, created = SwitchAppGraphBase.objects.get_or_create(component=component)

                if 'target' in cell:
                    target = cell['target']
                    component = SwitchComponent.objects.filter(uuid=target['id'], app_id=switchapps_pk).first()
                    if component is not None:
                        target_obj, created = SwitchAppGraphBase.objects.get_or_create(component=component)

                graph_obj, created = SwitchAppGraphServiceLink.objects.get_or_create(source=source_obj, target=target_obj)

            for cell in graph_component_links:
                graph_obj = None
                source_obj = None
                target_obj = None

                if 'source' in cell:
                    source = cell['source']
                    component = SwitchComponent.objects.filter(uuid=source['id'], app_id=switchapps_pk).first()
                    if component is not None:
                        if 'port' in source:
                            source_obj, created = SwitchAppGraphPort.objects.get_or_create(
                                graph_component__component=component, type='out', title=source['port'])

                if 'target' in cell:
                    target = cell['target']
                    component = SwitchComponent.objects.filter(uuid=target['id'], app_id=switchapps_pk).first()
                    if component is not None:
                        if 'port' in target:
                            is_connection = True
                            target_obj, created = SwitchAppGraphPort.objects.get_or_create(
                                graph_component__component=component, type='in', title=target['port'])

                component, created = SwitchComponent.objects.get_or_create(uuid=cell['id'],
                                                                           app_id=switchapps_pk)
                if created:
                    component.title = 'connection'
                    component.type = 'ComponentLink'
                    component.save()

                if component is not None:
                    graph_obj, created = SwitchAppGraphComponentLink.objects.get_or_create(
                        component=component, source=source_obj, target=target_obj,
                        type='switch.ComponentLink')

                # print graph_obj
        except Exception as e:
            print e.message

        serializer = self.get_serializer(graph)
        return Response(serializer.data)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    authentication_classes = (TokenAuthentication,)
    User = get_user_model()
    queryset = User.objects.all()
    filter_backends = (DjangoFilterBackend, SearchFilter)
    filter_fields = ('username', 'email')
    search_fields = ('username', 'email')

    @list_route(permission_classes=[IsAuthenticated])
    def me(self, request, *args, **kwargs):
        User = get_user_model()
        self.object = get_object_or_404(User, pk=request.user.id)
        serializer = self.get_serializer(self.object)
        return Response(serializer.data)


class SwitchComponentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows TodoItems to be CRUDed.
    """
    serializer_class = SwitchComponentSerializer

    def get_queryset(self):
        app_id = self.request.query_params.get('app_id', None)
        uuid = self.request.query_params.get('uuid', None)
        if app_id is not None:
            queryset = SwitchComponent.objects.filter(app_id=app_id)
            if uuid is not None:
                queryset = SwitchComponent.objects.filter(app_id=app_id, uuid=uuid)
        else:
            queryset = SwitchComponent.objects.filter(app__user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        app_id = self.request.data['app_id']
        app = SwitchApp.objects.filter(id=app_id).first()
        serializer.save(app=app)
