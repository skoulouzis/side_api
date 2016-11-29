import json
import yaml
import os
import subprocess
import uuid

from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import list_route, detail_route, parser_classes
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.filters import DjangoFilterBackend, SearchFilter
from rest_framework.views import APIView
from rest_framework_extensions.mixins import PaginateByMaxMixin

from api.permissions import BelongsToUser, AppBelongsToUser
from models import *
from serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from side_api import settings, utils
from services import JenaFusekiService

from yaml.dumper import Dumper
from yaml.representer import SafeRepresenter


class YamlDumper(Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(YamlDumper, self).increase_indent(flow, False)

YamlDumper.add_representer(str, SafeRepresenter.represent_str)
YamlDumper.add_representer(unicode, SafeRepresenter.represent_unicode)


class ApplicationViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
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
    def kb_classes(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        classes = kb_service.getClasses()
        return JsonResponse(classes)

    @list_route(methods=['get'], permission_classes=[])
    def kb_application_component_type(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        component_types = kb_service.getAllApplicationComponentTypes()
        return JsonResponse(component_types, safe= False)

    @detail_route(methods=['get'], permission_classes=[])
    def kb_component_type(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        component_type = kb_service.getApplicationComponentType(request.data)
        return JsonResponse(component_type)

    @detail_route(methods=['get'], permission_classes=[])
    def kb_component_profile(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        component_profile = kb_service.getApplicationComponentProfile()
        return JsonResponse(component_profile)

    @detail_route(methods=['get'], permission_classes=[])
    def kb_virtual_infrastructure(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        virtual_infrastrucutre = kb_service.getVirtualInfrastructure()
        return JsonResponse(virtual_infrastrucutre)


    @detail_route(methods=['get'], permission_classes=[])
    def tosca(self, request, pk=None, *args, **kwargs):

        app = Application.objects.filter(id=pk).first()

        return JsonResponse(app.get_tosca())

    @detail_route(methods=['get'], permission_classes=[])
    def validate(self, request, pk=None, *args, **kwargs):
        details = []
        app = Application.objects.filter(id=pk).first()

        for instance in app.get_instances():
            instance_properties = yaml.load(str(instance.properties).replace("\t", "    "))
            for name,value in instance_properties.items():
                if value == "SET_ITS_VALUE":
                    details.append("Component '"  + instance.title + "' needs its property '" + name + "' to be set.")

        if len(details)==0:
            result = 'ok'
            details.append('validation done correctly')
        else:
            result = 'error'

        validation_result = {
            'result': result,
            'details': details
        }

        return JsonResponse(validation_result)

    @detail_route(methods=['get'], permission_classes=[])
    def planVirtualInfrastructure(self, request, pk=None, *args, **kwargs):
        # TODO: implement the planning of the virtual infrastructure
        result = ''
        details = []
        app = Application.objects.get(id=pk)
        if app.status >= 1:
            result = 'error'
            details.append('application has already a planned infrastructure')
        else:
            #  num_hw_req = Instance.objects.filter(graph__id=app.uuid, component__type__title='Requirement').count()
            num_hw_req = app.instances.filter(component__type__title='Requirement').count()
            if num_hw_req == 0:
                result = 'error'
                details.append('no hardware requirements defined')
            else:
                validation_result = json.loads(self.validate(request=request, pk=pk).content)
                if validation_result['result'] == "error":
                    result = 'error'
                    details.append('Please make sure that the application is valid before to plan the virtual infrastructure')
                else:
                    app_tosca_json = json.loads(self.tosca(request=request, pk=pk).content)
                    return_code = subprocess.call(['java', '-jar', os.path.join(settings.BASE_DIR, 'external_tools', 'planner', 'SwitchPlanner_test.jar'), pk])
                    if return_code == 0:
                        result = 'ok'
                        details.append('plan done correctly')
                        app.status = 1
                        app.save()

                        # Temporary simulate the planner
                        # For each hw requirement in the app create a vm and link it to the requirement
                        for graph_req in app.instances.filter(component__type__title='Requirement').all():
                            # Create virtual machine component if it doesn't exist
                            component_vm, created = Component.objects.get_or_create(user=request.user,
                                    title='VM', type=ComponentType.objects.get(title='Virtual Machine'))

                            # Create a graph_virtual_machine element that satisfies the requirement, storing it in the db
                            graph_vm = ServiceComponent.objects.create(component=component_vm, graph=app,
                                        title='VM_' + graph_req.title, mode=graph_req.mode,
                                        last_x=graph_req.last_x, last_y=graph_req.last_y + 80)

                            vr_properties = {
                                "type": "switch/compute",
                                "OStype": "Ubuntu 14.04",
                                "script": "",
                                "installation": "",
                                "public_address": str(graph_vm.uuid)
                            }

                            # Depending on the requirement properties the virtual machine will be different
                            requirement_properties = yaml.load(str(graph_req.properties).replace("\t", "    "))
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
                            for graph_service_link in ServiceLink.objects.filter(graph=app, source=graph_req).all():
                                # Add a ethernet port for every component link to the requirement
                                for graph_component_link in ComponentLink.objects.filter(source__instance=graph_service_link.target).all():
                                    ethernet_port = {
                                        "name": graph_component_link.source.title,
                                        "connection_name": str(graph_component_link.uuid) + ".source"
                                    }
                                    vr_properties.setdefault('ethernet_port', []).append(ethernet_port)
                                for graph_component_link in ComponentLink.objects.filter(target__instance=graph_service_link.target).all():
                                    ethernet_port = {
                                        "name": graph_component_link.target.title,
                                        "connection_name": str(graph_component_link.uuid) + ".target"
                                    }
                                    vr_properties.setdefault('ethernet_port', []).append(ethernet_port)

                            graph_vm.properties = yaml.dump(vr_properties, Dumper=YamlDumper, default_flow_style=False)
                            graph_vm.save()

                            # Create a service_link between the new vm and the requirement
                            graph_service_link_vm_req = ServiceLink.objects.create(graph=app, source=graph_vm, target=graph_req)
                            graph_service_link_vm_req.save()
                    else:
                        result = 'error'
                        details.append('planification of virtual infrastructure has failed')

        planning_vi_result = {
            'result': result,
            'details': details
        }

        return JsonResponse(planning_vi_result)

    @detail_route(methods=['get'], permission_classes=[])
    def provisionVirtualInfrastructure(self, request, pk=None, *args, **kwargs):
        # TODO: implement the provision of the virtual infrastructure
        result = ''
        details = []

        app = Application.objects.get(id=pk)
        if app.status < 1:
            result = 'error'
            details.append('virtual infrastructure has not been planned yet')
        elif app.status >= 2:
            result = 'error'
            details.append('application has already a provisioned infrastructure')
        else:
            validation_result = json.loads(self.validate(request=request, pk=pk).content)
            if validation_result['result'] == "error":
                result = 'error'
                details.append('Please make sure that the application is valid before to provision the virtual infrastructure')
            else:
                # get the tosca file of the application
                app_tosca_json = json.loads(self.tosca(request=request, pk=pk).content)

                uuid = str(app.uuid)
                with open(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '.yml'), 'w') as f:
                    credentials = {
                        'publicKeyPath': os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id),'id_rsa.pub'),
                        'userName': app.user.username
                    }
                    yaml.dump(credentials, f, Dumper=YamlDumper, default_flow_style=False)

                    if 'virtual_machines' in app_tosca_json['data']['virtual_resources'] and len(app_tosca_json['data']['virtual_resources']['virtual_machines']) > 0:
                        components={'components': []}
                        for vm in app_tosca_json['data']['virtual_resources']['virtual_machines']:
                            component= vm.values()[0]
                            component['name']=vm.keys()[0]
                            components['components'].append(component)
                        yaml.dump(components, f, Dumper=YamlDumper, default_flow_style=False)

                    if 'components_connections' in app_tosca_json['data']['connections'] and len(app_tosca_json['data']['connections']['components_connections'])>0:
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
                                        connection['target']['port_name'] = ethernet_port['name']

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
                                        connection['source']['port_name'] = ethernet_port['name']

                            connection['source']['netmask'] = connection['netmask']
                            connection['source']['address'] = connection['source_address']

                            del connection['source']['id']
                            del connection['source']['port']

                            del connection['netmask']
                            del connection['target_address']
                            del connection['source_address']

                            connections['connections'].append(connection)
                        yaml.dump(connections, f, Dumper=YamlDumper, default_flow_style=False)

                confFile = os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), 'rootkey.csv')
                toscaFile = os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '.yml')
                certsFolder = os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id))
                return_code = subprocess.call(['java', '-jar',
                                               os.path.join(settings.BASE_DIR, 'external_tools', 'provisioner', 'EC2Provision_test.jar'),
                                               confFile, toscaFile, certsFolder],
                                              cwd=os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id)))

                if return_code == 0:
                    result = 'ok'
                    details.append('provision done correctly')

                    app.status = 2
                    app.save()

                    with open(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '_provisioned.yml'), 'r') as f:
                        tosca_provisioned_infrastructure = yaml.load(f.read())

                    for vm_provisioned in tosca_provisioned_infrastructure['components']:
                        vm_component = Instance.objects.get(uuid=vm_provisioned['name'])
                        vm_component.title += ' (' + vm_provisioned['public_address'] + ')'
                        vm_component.properties = yaml.dump(vm_provisioned, Dumper=YamlDumper, default_flow_style=False)
                        vm_component.save()

                else:
                    result = 'error'
                    details.append('provision has failed')

        # Delete files input and output files used by the provisioner
        if os.path.isfile(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '.yml')):
            os.remove(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '.yml'))
        if os.path.isfile(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '_provisioned.yml')):
            os.remove(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '_provisioned.yml'))

        provision_vi_result = {
            'result': result,
            'details': details
        }

        return JsonResponse(provision_vi_result)


class ComponentGraphView(PaginateByMaxMixin, APIView):
    """
    API endpoint that allows SwitchApps to be CRUDed.
    """
    serializer_class = ComponentSerializer
    authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def get(self, request, pk=None):
        component = Component.objects.filter(id=pk).first()
        return Response(component.get_graph())

    def post(self, request, pk=None):
        component = Component.objects.filter(id=pk).first()
        component.put_graph(request.data)
        return Response(component.get_graph())


class ApplicationGraphView(PaginateByMaxMixin, APIView):
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
        app.put_graph(request.data)
        return Response(app.get_graph())


class UserViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
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


class ComponentViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = ComponentSerializer

    def get_queryset(self):
        is_core_component = self.request.query_params.get('is_core_component', None)
        is_template_component = self.request.query_params.get('is_template_component', None)
        queryset = Component.objects.filter()

        if is_core_component is not None:
            queryset = queryset.filter(type__switch_class__is_core_component=is_core_component)
        elif is_template_component is not None:
            queryset = queryset.filter(type__switch_class__is_template_component=is_template_component)

        return queryset

    def perform_create(self, serializer):
        switch_type = ComponentType.objects.get(id=self.request.data['type']['id'])
        component = serializer.save(type=switch_type, user=self.request.user)

        instance = Instance.objects.create(graph=component, component=component, title=component.title, last_x=400, last_y=200, mode='single')

        if component.type.switch_class.title == 'switch.Component' or component.type.switch_class.title == 'switch.Group':
            nested_component = NestedComponent(instance_ptr=instance)
            nested_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.VirtualResource' or component.type.switch_class.title == 'switch.Attribute':
            service_component = ServiceComponent(instance_ptr=instance)
            service_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.ComponentLink':
            component_link = ComponentLink(instance_ptr=instance)
            component_link.save_base(raw=True)


class ComponentTypeViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = ComponentTypeSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    queryset = ComponentType.objects.all()
    parser_classes = (JSONParser,)


class InstanceViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = InstanceSerializer

    def get_queryset(self):
        graph_id = self.request.query_params.get('graph_id', None)
        uuid = self.request.query_params.get('uuid', None)
        if graph_id is not None:
            queryset = Instance.objects.filter(graph_id=graph_id)
            if uuid is not None:
                queryset = Instance.objects.filter(graph_id=graph_id, uuid=uuid)
        else:
            queryset = Instance.objects.filter(graph__user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        if self.request.data['graph_type'] == 'app':
            graph = Application.objects.filter(id=self.request.data['graph_id']).first()
        else:
            graph = Component.objects.filter(id=self.request.data['graph_id']).first()

        component = Component.objects.filter(id=self.request.data['component_id']).first()

        if component.type.title == "Requirement" and self.request.data['properties'] == "data: enter metadata as YAML":
            properties = {}
            properties['machine_type'] = "SET_ITS_VALUE"
            properties['location'] = "SET_ITS_VALUE"
            self.request.data['properties'] = yaml.dump(properties, Dumper=YamlDumper, default_flow_style=False)
        elif component.type.title == "ComponentLink" and self.request.data['properties'] == "data: enter metadata as YAML":
            properties = {}
            properties['netmask'] = "SET_ITS_VALUE"
            properties['source_address'] = "SET_ITS_VALUE"
            properties['target_address'] = "SET_ITS_VALUE"
            properties['bandwidth'] = "SET_ITS_VALUE"
            properties['latency'] = "SET_ITS_VALUE"
            self.request.data['properties'] = yaml.dump(properties, Dumper=YamlDumper, default_flow_style=False)

        instance = serializer.save(graph=graph, component=component, properties=self.request.data['properties'])
        instance.save()

        nested_component = None

        if component.type.switch_class.title == 'switch.Component' or component.type.switch_class.title == 'switch.Group':
            nested_component = NestedComponent(instance_ptr=instance)
            nested_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.VirtualResource' or component.type.switch_class.title == 'switch.Attribute':
            service_component = ServiceComponent(instance_ptr=instance)
            service_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.ComponentLink':
            component_link = ComponentLink(instance_ptr=instance)
            component_link.save_base(raw=True)

        base_instance = component.get_base_instance()
        x_change = base_instance.last_x - instance.last_x
        y_change = base_instance.last_y - instance.last_y

        instance_translations = {}
        port_translations = {}

        try:
            # clone any supporting components
            instances = component.get_instances()
            for template_instance in instances:
                # if it's not the main component, clone it!
                old_pk = template_instance.pk

                if template_instance != base_instance:
                    template_instance.pk = None
                    template_instance.id = None
                    template_instance.graph = graph
                    template_instance.last_x = template_instance.last_x - x_change
                    template_instance.last_y = template_instance.last_y - y_change
                    template_instance.uuid = uuid.uuid4()
                    template_instance.save()
                    new_pk = template_instance.pk

                    instance_translations[old_pk] = new_pk
                elif nested_component is not None:
                    template_instance = nested_component
                    instance_translations[old_pk] = instance.pk

                for port in ComponentPort.objects.filter(instance_id=old_pk).all():
                    old_pk = port.pk
                    port.instance = template_instance
                    port.pk = None
                    port.id = None
                    port.uuid = uuid.uuid4()
                    port.save()
                    new_pk = port.pk

                    port_translations[old_pk] = new_pk

            for component_link in ComponentLink.objects.filter(graph=component).all():
                component_link.source_id = port_translations[component_link.source_id]
                component_link.target_id = port_translations[component_link.target_id]
                component_link.save()

            for service_link in ServiceLink.objects.filter(graph=component).all():
                service_link.pk = None
                service_link.id = None
                service_link.graph = graph
                service_link.source_id = instance_translations[service_link.source_id]
                service_link.target_id = instance_translations[service_link.target_id]
                service_link.save()

        except Exception as e:
            print e.message


class SwitchDocumentViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated, )
    serializer_class = SwitchDocumentSerializer
    queryset = SwitchDocument.objects.all()
    parser_classes = (JSONParser,FormParser,MultiPartParser,)


    def list(self, request, **kwargs):
        documents = SwitchDocument.objects.filter()
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return SwitchDocument.objects.filter()

    def perform_create(self, serializer):
        document = serializer.save(user=self.request.user)
