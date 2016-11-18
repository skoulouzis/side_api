import json
import yaml
import os
import subprocess
import uuid

from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, FileResponse
from rest_framework import viewsets
from rest_framework.decorators import list_route, detail_route, parser_classes
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FileUploadParser, JSONParser, FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.filters import DjangoFilterBackend, SearchFilter
from rest_framework import views
from rest_framework.views import APIView
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

YamlDumper.add_representer(str, SafeRepresenter.represent_str)
YamlDumper.add_representer(unicode, SafeRepresenter.represent_unicode)


class ApplicationViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows SwitchApps to be CRUDed.
    """
    serializer_class = ApplicationSerializer
    authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)

    def list(self, request, **kwargs):
        apps = Application.objects.filter()
        # apps = SwitchApp.objects.filter(user=self.request.user)
        serializer = self.get_serializer(apps, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return Application.objects.filter()

    def perform_create(self, serializer):
        app = serializer.save(user=self.request.user)

    @detail_route(methods=['get'], permission_classes=[])
    def tosca(self, request, pk=None, *args, **kwargs):

        app = Application.objects.filter(id=pk).first()

        return JsonResponse(app.get_tosca())

    @detail_route(methods=['get'], permission_classes=[])
    def validate(self, request, pk=None, *args, **kwargs):
        # TODO: implement the validation
        app_tosca_json = json.loads(self.tosca(request=request, pk=pk).content)

        formal_validation_result = services.validate(pk, app_tosca_json)
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
        app = Application.objects.get(id=pk)
        if app.status >= 1:
            result = 'error'
            message = 'application has already a planned infrastructure'
        else:
            num_hw_req = Component.objects.filter(app_id=pk, switch_type__title='Requirement').count()
            if num_hw_req == 0:
                result = 'error'
                message = 'no hardware requirements defined'
            else:
                app_tosca_json = json.loads(self.tosca(request=request, pk=pk).content)
                return_code = subprocess.call(
                    ['java', '-jar', os.path.join(settings.BASE_DIR, 'external_tools', 'planner', 'test.jar'), pk])
                if return_code == 0:
                    result = 'ok'
                    message = 'plan done correctly'
                    app.status = 1
                    app.save()

                    # Temporary simulate the planner
                    # For each hw requirement in the app create a vm and link it to the requirement
                    for requirement in Component.objects.filter(app_id=pk,
                                                                switch_type__title='Requirement').all():
                        # Create virtual machine that satisfies the requirement, storing it in the db
                        virtual_machine = Component.objects.create(app_id=pk, uuid=uuid.uuid4(),
                                                                   title='VM_' + requirement.title, mode='single',
                                                                   type='Virtual Machine')
                        virtual_machine.switch_type = ComponentType.objects.get(title='Virtual Machine')
                        vr_properties = {
                            "type": "switch/compute",
                            "OStype": "Ubuntu 14.04",
                            "script": os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', 'topology', 't1',
                                                   'script', 'install.sh'),
                            "installation": os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', 'topology',
                                                         't1', 'installation', 'Server'),
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
                        for graph_service_link in ServiceLink.objects.filter(
                                source__component=requirement).all():
                            # Add a ethernet port for every component link to the requirement
                            for graph_component_link in ComponentLink.objects.filter(
                                    source__graph_component=graph_service_link.target).all():
                                ethernet_port = {
                                    "name": graph_component_link.source.title,
                                    "connection_name": str(graph_component_link.component.uuid) + ".source"
                                }
                                vr_properties.setdefault('ethernet_port', []).append(ethernet_port)
                            for graph_component_link in ComponentLink.objects.filter(
                                    target__graph_component=graph_service_link.target).all():
                                ethernet_port = {
                                    "name": graph_component_link.target.title,
                                    "connection_name": str(graph_component_link.component.uuid) + ".target"
                                }
                                vr_properties.setdefault('ethernet_port', []).append(ethernet_port)

                        virtual_machine.properties = yaml.dump(vr_properties, Dumper=YamlDumper,
                                                               default_flow_style=False)

                        virtual_machine.save()

                        # Create a graph_virtual_machine element
                        graph_req = Instance.objects.get(component=requirement)
                        graph_vm = ServiceComponent.objects.create(component=virtual_machine,
                                                                   type='switch.VirtualResource',
                                                                   last_x=graph_req.last_x,
                                                                   last_y=graph_req.last_y + 80)
                        graph_vm.save()

                        # Create a service_link between the new vm and the requirement
                        graph_service_link_vm_req = ServiceLink.objects.create(source=graph_vm,
                                                                               target=graph_req)
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

        app = Application.objects.get(id=pk)
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
            with open(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '.yml'), 'w') as f:
                credentials = {
                    'publicKeyPath': os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', 'id_rsa.pub'),
                    'userName': "fran"
                }
                yaml.dump(credentials, f, Dumper=YamlDumper, default_flow_style=False)

                if len(app_tosca_json['data']['virtual_resources']['virtual_machines']) > 0:
                    components = {'components': []}
                    for vm in app_tosca_json['data']['virtual_resources']['virtual_machines']:
                        component = vm.values()[0]
                        component['name'] = vm.keys()[0]
                        components['components'].append(component)
                    yaml.dump(components, f, Dumper=YamlDumper, default_flow_style=False)

                if len(app_tosca_json['data']['connections']['components_connections']) > 0:
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

                        # connection['source']['component_name'] = connection['source']['id']
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
                                           os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner',
                                                        'EC2Provision_test.jar'),
                                           os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner',
                                                        'rootkey.csv'),
                                           os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner',
                                                        uuid + '.yml')],
                                          cwd=os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner'))

            if return_code == 0:
                result = 'ok'
                message = 'provision done correctly'

                with open(os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', uuid + '_provisioned.yml'),
                          'r') as f:
                    tosca_provisioned_infrastructure = yaml.load(f.read())

                for vm_provisioned in tosca_provisioned_infrastructure['components']:
                    vm_component = Component.objects.get(uuid=vm_provisioned['name'])
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


class GraphView(APIView):
    """
    API endpoint that allows SwitchApps to be CRUDed.
    """
    serializer_class = ApplicationSerializer
    authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def get(self, request, pk=None):
        app = Application.objects.filter(id=pk).first()

        return Response(app.get_graph())

    def post(self, request, pk=None):
        app = Application.objects.filter(id=pk).first()

        json_data = request.data
        service_links = []
        component_links = []

        try:
            for obj in app.service_links.all():
                obj.delete()

            for cell in json_data['cells']:#
                # Do these two last to ensure all linked to components exist...
                if cell['type'] == 'switch.ServiceLink':
                    service_links.append(cell)
                elif cell['type'] == 'switch.ComponentLink':
                    component_links.append(cell)
                else:
                    instance = Instance.objects.filter(uuid=cell['id'], app=app).select_subclasses().first()
                    instance.type = cell['type']
                    instance.last_x = cell['position']['x']
                    instance.last_y = cell['position']['y']

                    if instance.component.type.switch_class.title == 'switch.Component':
                        port_objs = []

                        if 'parent' in cell:
                            parent_obj, created = NestedComponent.objects.get_or_create(uuid=cell['parent'], app=app)
                            instance.parent = parent_obj

                        if 'inPorts' in cell:
                            for port in cell['inPorts']:
                                port_obj, created = ComponentPort.objects.get_or_create(instance=instance, uuid=port['id'], type='in')
                                port_obj.title = port['label']
                                port_obj.save()
                                port_objs.append(port_obj)

                            instance.ports = port_objs

                        if 'outPorts' in cell:
                            for port in cell['outPorts']:
                                port_obj, created = ComponentPort.objects.get_or_create(instance=instance, uuid=port['id'], type='out')
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
                    source_obj = Instance.objects.filter(uuid=source['id'], app=app).first()

                if 'target' in instance:
                    target = instance['target']
                    target_obj = Instance.objects.filter(uuid=target['id'], app=app).first()

                if source_obj is not None and target_obj is not None:
                    ServiceLink.objects.get_or_create(source=source_obj, target=target_obj, app=app)

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
                    link, created = ComponentLink.objects.get_or_create(uuid=instance['id'], app=app)
                    link.source = source_obj
                    link.target = target_obj
                    link.save()

        except Exception as e:
            print e.message

        return Response(app.get_graph())


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


class ComponentViewSet(viewsets.ModelViewSet):
    serializer_class = ComponentSerializer

    def list(self, request, **kwargs):
        apps = Component.objects.filter()
        # apps = SwitchApp.objects.filter(user=self.request.user)
        serializer = self.get_serializer(apps, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return Component.objects.filter()

    def perform_create(self, serializer):
        switch_type = ComponentType.objects.get(id=self.request.data['type']['id'])
        serializer.save(type=switch_type, user=self.request.user)


class ComponentTypeViewSet(viewsets.ModelViewSet):
    serializer_class = ComponentTypeSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    queryset = ComponentType.objects.all()
    parser_classes = (JSONParser,)


class InstanceViewSet(viewsets.ModelViewSet):
    serializer_class = InstanceSerializer

    def get_queryset(self):
        app_id = self.request.query_params.get('app_id', None)
        uuid = self.request.query_params.get('uuid', None)
        if app_id is not None:
            queryset = Instance.objects.filter(app_id=app_id)
            if uuid is not None:
                queryset = Instance.objects.filter(app_id=app_id, uuid=uuid)
        else:
            queryset = Instance.objects.filter(app__user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        app = Application.objects.filter(id=self.request.data['app_id']).first()
        component = Component.objects.filter(id=self.request.data['component_id']).first()

        instance = serializer.save(app=app, component=component)
        instance.save()

        if component.type.switch_class.title == 'switch.Component' or component.type.switch_class.title == 'switch.Group':
            nested_component = NestedComponent(instance_ptr=instance)
            nested_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.VirtualResource' or  component.type.switch_class.title == 'switch.Attribute':
            service_component = ServiceComponent(instance_ptr=instance)
            service_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.VirtualResource' or  component.type.switch_class.title == 'switch.Attribute':
            service_component = ServiceComponent(instance_ptr=instance)
            service_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.ComponentLink':
            service_component = ComponentLink(instance_ptr=instance)
            service_component.save_base(raw=True)
