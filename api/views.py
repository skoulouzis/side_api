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
        components = []
        external = []
        network = []
        attributes = []
        groups = []
        components_connections = []
        services_connections = []
        virtual_machines = []
        virtual_networks = []

        for component in SwitchComponent.objects.filter(app_id=pk).all():
            data_obj = {}
            properties = {}
            properties['title'] = component.title
            if 'enter metadata as YAML' not in component.properties:
                metadata = yaml.load(str(component.properties).replace("\t", "    "))
                properties.update(metadata)

            if component.switch_type.switch_class.title == 'switch.Component':
                properties['scaling_mode'] = component.mode

                for port in SwitchAppGraphComponent(component.graph_component).ports.all():
                    properties.setdefault(port.type + 'Ports', []).append(port.title)

                if SwitchAppGraphComponent(component.graph_component).parent is not None:
                    properties['group'] = str(SwitchAppGraphComponent(component.graph_component).parent.component.uuid)

                data_obj[str(component.uuid)] = properties

                # The shape in joint.js "component" can be a "component", a "external component" or a "network"
                if component.switch_type.title == 'Component':
                    components.append(data_obj)
                elif component.switch_type.title == 'Network':
                    network.append(data_obj)
                elif component.switch_type.title == 'External Component':
                    external.append(data_obj)

            if component.switch_type.switch_class.title == 'switch.VirtualResource':
                properties['class'] = component.switch_type.title

                data_obj[str(component.uuid)] = properties

                # The shape in joint.js "VirtualResource" can be a "Virtual Machine" or a "Virtual Network"
                if component.switch_type.title == 'Virtual Machine':
                    virtual_machines.append(data_obj)
                elif component.switch_type.title == 'Virtual Network':
                    virtual_networks.append(data_obj)

            if component.switch_type.switch_class.title == 'switch.Attribute':
                # The shape in joint.js "attribute" can be a "monitoring agent", "event listener", "message passer"
                # "constraint", "adaptation profile" or a "requirement"
                properties['class'] = component.switch_type.title

                data_obj[str(component.uuid)] = properties
                attributes.append(data_obj)

            if component.switch_type.switch_class.title == 'switch.Group':
                for child in SwitchAppGraphComponent(component.graph_component).children.all():
                    properties.setdefault('members', []).append(str(child.component.uuid))

                data_obj[str(component.uuid)] = properties
                groups.append(data_obj)

            if component.switch_type.switch_class.title == 'switch.ComponentLink':
                #SwitchAppGraphComponentLink(component.graph_component)
                graph_component_link = SwitchAppGraphComponentLink.objects.get(component=component)
                target = {}
                target['id'] = str(graph_component_link.target.graph_component.component.uuid)
                target['port'] = graph_component_link.target.title
                properties['target'] = target;
                source = {}
                source['id'] = str(graph_component_link.source.graph_component.component.uuid)
                source['port'] = graph_component_link.source.title
                properties['source'] = source

                data_obj[str(component.uuid)] = properties
                components_connections.append(data_obj)

        for serviceLink in SwitchAppGraphServiceLink.objects.filter(source__component__app_id=pk).all():
            data_obj = {}
            properties = {}
            target = {}
            target['id'] = str(serviceLink.target.component.uuid)
            properties['target'] = target;
            source = {}
            source['id'] = str(serviceLink.source.component.uuid)
            properties['source'] = source

            data_obj[str(serviceLink.source.component.uuid) + '--' +  str(serviceLink.target.component.uuid)] = properties
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
            num_hw_req = SwitchComponent.objects.filter(app_id=pk, switch_type__title='Requirement').count()
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
                    # For each hw requirement in the app create a vm and link it to the requirement
                    for requirement in SwitchComponent.objects.filter(app_id=pk,switch_type__title='Requirement').all():
                        #Create virtual machine that satisfies the requirement, storing it in the db
                        virtual_machine = SwitchComponent.objects.create(app_id=pk, uuid = uuid.uuid4(),
                                title = 'VM_' + requirement.title, mode = 'single', type='Virtual Machine')
                        virtual_machine.switch_type = SwitchComponentType.objects.get(title='Virtual Machine')
                        vr_properties = {
                            "type": "switch/compute",
                            "OStype": "Ubuntu 14.04",
                            "script": os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner','topology','t1','script','install.sh'),
                            "installation": os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner','topology','t1','installation','Server'),
                            "public_address": str(virtual_machine.uuid)
                        }

                        # Depending on the requirement properties the virtual machine will be different
                        requirement_properties = yaml.load(str(requirement.properties).replace("\t", "    "))
                        if 'machine_type' in requirement_properties:
                            if requirement_properties['machine_type'] == "big":
                                vr_properties['nodetype'] = "t2.large"
                            elif requirement_properties['machine_type'] == "small":
                                vr_properties['nodetype'] = "t2.small"
                            else:
                                vr_properties['nodetype'] = "t2.medium"
                        else:
                            vr_properties['nodetype'] = "t2.medium"

                        if 'location' in requirement_properties:
                            if requirement_properties['location'] == "us-east":
                                vr_properties['domain'] = "ec2.us-east-1.amazonaws.com"
                            else:
                                vr_properties['domain'] = "ec2.us-west-1.amazonaws.com"
                        else:
                            vr_properties['domain'] = "ec2.us-east-1.amazonaws.com"

                        # Add a ethernet port to the VM properties for every "component_link" (target and source) of
                        # of every "component" linked to the requirement
                        for graph_service_link in SwitchAppGraphServiceLink.objects.filter(source__component=requirement).all():
                            # Add a ethernet port for every component link to the requirement
                            for graph_component_link in SwitchAppGraphComponentLink.objects.filter(source__graph_component=graph_service_link.target).all():
                                ethernet_port = {
                                    "name": graph_component_link.source.title,
                                    "connection_name": str(graph_component_link.component.uuid) + ".source"
                                }
                                vr_properties.setdefault('ethernet_port', []).append(ethernet_port)
                            for graph_component_link in SwitchAppGraphComponentLink.objects.filter(target__graph_component=graph_service_link.target).all():
                                ethernet_port = {
                                    "name": graph_component_link.target.title,
                                    "connection_name": str(graph_component_link.component.uuid) + ".target"
                                }
                                vr_properties.setdefault('ethernet_port', []).append(ethernet_port)

                        virtual_machine.properties = yaml.dump(vr_properties, Dumper=YamlDumper, default_flow_style=False)

                        virtual_machine.save()

                        #Create a graph_virtual_machine element
                        graph_req= SwitchAppGraphBase.objects.get(component=requirement)
                        graph_vm = SwitchAppGraphService.objects.create(component=virtual_machine,type='switch.VirtualResource',
                                                                        last_x=graph_req.last_x, last_y=graph_req.last_y + 80)
                        graph_vm.save()

                        # Create a service_link between the new vm and the requirement
                        graph_service_link_vm_req= SwitchAppGraphServiceLink.objects.create(source=graph_vm,target=graph_req)
                        graph_service_link_vm_req.save()
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

                with open(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '_provisioned.yml'), 'r') as f:
                    tosca_provisioned_infrastructure = yaml.load(f.read())

                for vm_provisioned in tosca_provisioned_infrastructure['components']:
                    vm_component = SwitchComponent.objects.get(uuid=vm_provisioned['name'])
                    vm_component.title += ' (' + vm_provisioned['public_address'] + ')'
                    vm_component.properties = yaml.dump(vm_provisioned, Dumper=YamlDumper, default_flow_style=False)
                    vm_component.save()

                app.status = 2
                app.save()
            else:
                result = 'error'
                message = 'provision has failed'

        # Delete files input and output files used by the provisioner
        if os.path.isfile(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '.yml')):
            os.remove(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '.yml'))
        if os.path.isfile(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '_provisioned.yml')):
            os.remove(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '_provisioned.yml'))


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
                graph_obj['attrs']['switch'] = {'class': component.type, 'title': component.title, 'type': component.title}
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
                                graph_obj['inPorts'].append({'type': 'in', 'id': str(port.id), 'name': port.title})
                                key = '.inPorts>.port%s' % str(portlen)
                                ref_y = (portlen * 2 * gap) + gap
                                portlen += 1
                                graph_obj['attrs'][key] = {'ref': '.body', 'ref-y': ref_y}
                                graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                                graph_obj['attrs'][key + '>.port-body'] = {'port':{'type': 'in', 'id': str(port.id), 'name': port.title}}

                        if len(outPorts) > 0:
                            gap = 100 / (len(outPorts) * 2)
                            portlen = 0

                            for port in outPorts:
                                graph_obj['outPorts'].append({'type': 'out', 'id': str(port.id), 'name': port.title})
                                key = '.outPorts>.port%s' % str(portlen)
                                ref_y = (portlen * 2 * gap) + gap
                                portlen += 1
                                graph_obj['attrs'][key] = {'ref': '.body', 'ref-dx': 0, 'ref-y': ref_y}
                                graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                                graph_obj['attrs'][key + '>.port-body'] = {'port':{'type': 'out', 'id': str(port.id), 'name': port.title}}

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
                        graph_obj['size'] = {"width": 30, "height": 30}
                        response_cells.append(graph_obj)
                    elif cell.type == 'switch.VirtualResource':
                        graph_obj['attrs']['.body'] = {
                                        "fill": component.switch_type.primary_colour,
                                        "stroke": component.switch_type.secondary_colour,
                                        "stroke-width": 2,
                                        "fill-opacity": ".95"
                                    }
                        graph_obj['size'] = {"width": 35, "height": 35}
                        response_cells.append(graph_obj)

                if cell.type == 'switch.ComponentLink':
                    graph_component = SwitchAppGraphComponentLink.objects.filter(id=cell.id).first()
                    graph_obj['target'] = {
                        "port": graph_component.target.id,
                        "id": graph_component.target.graph_component.component.uuid
                    }
                    graph_obj['attrs']['targetPortObj'] = {"id": graph_component.target.id, "name": graph_component.target.title, "type": 'in'}
                    graph_obj['source'] = {
                        "port": graph_component.source.id,
                        "id": graph_component.source.graph_component.component.uuid
                    }
                    graph_obj['attrs']['sourcePortObj']={"id":graph_component.source.id, "name":graph_component.source.title, "type":'out'}

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
                    response_cells.append(graph_obj)

            except Exception as e:
                print e.message

        service_links = SwitchAppGraphServiceLink.objects.filter(source__component__app_id=switchapps_pk).all()
        for cell in service_links:
            try:
                graph_obj = {'type': 'switch.ServiceLink', 'attrs': {
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
                            if not port['id'].startswith('in'):
                                port_obj = SwitchAppGraphPort.objects.filter(graph_component=graph_obj, id=port['id']).first()
                            else:
                                port_obj = None

                            if port_obj is None:
                                port_obj = SwitchAppGraphPort.objects.create(graph_component=graph_obj,
                                                                                             type=port['type'],
                                                                                             title=port['name'])
                            else:
                                port_obj.title=port['name']
                                port_obj.type=port['type']
                                port_obj.save()

                            port_objs.append(port_obj)

                        graph_obj.ports = port_objs

                    if 'outPorts' in cell:
                        for port in cell['outPorts']:
                            if not port['id'].startswith('out'):
                                port_obj = SwitchAppGraphPort.objects.filter(graph_component=graph_obj, id=port['id']).first()
                            else:
                                port_obj = None

                            if port_obj is None:
                                port_obj = SwitchAppGraphPort.objects.create(graph_component=graph_obj,
                                                                             type=port['type'],
                                                                             title=port['name'])
                            else:
                                port_obj.title = port['name']
                                port_obj.type = port['type']
                                port_obj.save()

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
                            port = cell['attrs']['sourcePortObj']
                            source_obj = SwitchAppGraphPort.objects.filter(id=port['id']).first()
                            if source_obj is None:
                                source_obj = SwitchAppGraphPort.objects.create(graph_component__component=component, type='out', title=port['name'])

                if 'target' in cell:
                    target = cell['target']
                    component = SwitchComponent.objects.filter(uuid=target['id'], app_id=switchapps_pk).first()
                    if component is not None:
                        if 'port' in target:
                            is_connection = True
                            port = cell['attrs']['targetPortObj']
                            target_obj = SwitchAppGraphPort.objects.filter(id=port['id']).first()
                            if target_obj is None:
                                graph_obj = SwitchAppGraphComponent(component.graph_component.first())
                                target_obj = SwitchAppGraphPort.objects.create(graph_component__component=component, type='in', title=port['name'])

                component, created = SwitchComponent.objects.get_or_create(uuid=cell['id'],
                                                                           app_id=switchapps_pk)
                if created:
                    component.title = 'connection'
                    component.switch_type = SwitchComponentType.objects.get(title='ComponentLink')
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
        app = SwitchApp.objects.filter(id=self.request.data['app_id']).first()
        switch_type = SwitchComponentType.objects.get(title=self.request.data['type'])
        serializer.save(app=app, switch_type=switch_type)
