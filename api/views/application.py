import os
import xml.etree.ElementTree as ET

from django.http import JsonResponse
from rest_framework import viewsets, status
from rest_framework.decorators import list_route, detail_route
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_extensions.mixins import PaginateByMaxMixin

from api.models import *
from api.serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from side_api import settings, utils
from api.services import JenaFusekiService, DripManagerService


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

    @list_route(methods=['get'], permission_classes=[])
    def kb_classes(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        classes = kb_service.getClasses()
        return JsonResponse(classes)

    @list_route(methods=['get'], permission_classes=[])
    def kb_application_component_type(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        component_types = kb_service.getAllApplicationComponentTypes()
        return JsonResponse(component_types, safe= False)

    @list_route(methods=['get'], permission_classes=[])
    def kb_component_type(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        component_type = kb_service.getApplicationComponentType(request.data)
        return JsonResponse(component_type)

    @list_route(methods=['get'], permission_classes=[])
    def kb_component_profile(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        component_profile = kb_service.getApplicationComponentProfile()
        return JsonResponse(component_profile)

    @detail_route(methods=['get'], permission_classes=[])
    def kb_virtual_infrastructure(self, request, pk=None, *args, **kwargs):
        kb_service = JenaFusekiService(utils.getPropertyFromConfigFile("ASAP_API", "url"))
        virtual_infrastrucutre = kb_service.getVirtualInfrastructure()
        return JsonResponse(virtual_infrastrucutre)

    @detail_route(methods=['post'])
    def clone(self, request, pk=None, *args, **kwargs):
        app = Application.objects.filter(id=pk).first()
        old_app_pk = app.pk
        app.pk = None
        app.id = None
        app.title = "copy of " + app.title
        app.save()

        old_app = Application.objects.filter(id=old_app_pk).first()
        old_app.clone_instances_in_graph(app, 0, 0)

        return Response(status=status.HTTP_204_NO_CONTENT)


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
                # validation_result = json.loads(self.validate(request=request, pk=pk).content)
                # if validation_result['result'] == "error":
                #     result = 'error'
                #     details.append('Please make sure that the application is valid before to plan the virtual infrastructure')
                # else:
                    # app_tosca = json.loads(self.tosca(request=request, pk=pk).content)
                    # path_app_tosca = "/home/fran/Documents/SWITCH/switch_tosca_profile/planner/example_planner_input.yaml"
                    #
                    # drip_manager_service = DripManagerService(
                    #     utils.getPropertyFromConfigFile("DRIP_MANAGER_API", "url"))
                    # drip_manager_response = drip_manager_service.planning_virtual_infrastructure(request.user, path_app_tosca)
                    #
                    # if drip_manager_response.status_code == 200:
                    #     root = ET.fromstring(drip_manager_response.text)
                    #     tosca_files = root.findall("./file")
                    #     for tosca_file in tosca_files:
                    #         tosca_level = tosca_file.attrib['level']
                    #         tosca_file_name = tosca_file.attrib['name']
                    #         toca_content = yaml.load(tosca_file.text.replace("\\n", "\n"))
                    #
                    #     result = 'ok'
                    #     details.append('plan done correctly')
                    #     app.status = 1
                    #     app.save()

                    # Temporary simulate the planner
                    # For each hw requirement in the app create a vm and link it to the requirement
                for graph_req in app.instances.filter(component__type__title='Requirement').all():
                    # Create virtual machine component if it doesn't exist
                    component_vm, created = Component.objects.get_or_create(user=request.user,
                            title='VM', type=ComponentType.objects.get(title='Virtual Machine'))
                    if created:
                        Instance.objects.create(graph=component_vm, component=component_vm, title=component_vm.title,
                                                last_x=400, last_y=200, mode='single')

                    # Create a graph_virtual_machine element that satisfies the requirement, storing it in the db
                    graph_vm = ServiceComponent.objects.create(component=component_vm, graph=app,
                                title='VM_' + graph_req.title, mode=graph_req.mode,
                                last_x=graph_req.last_x, last_y=graph_req.last_y + 80)

                    vr_properties = {
                        "type": "switch/compute",
                        "OStype": "Ubuntu 16.04",
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
                    # else:
                    #     result = 'error'
                    #     details.append('planification of virtual infrastructure has failed')

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
                node_templates = app_tosca_json['data']['topology_template']['node_templates']

                uuid = str(app.uuid)
                with open(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '.yml'), 'w') as f:
                    credentials = {
                        'publicKeyPath': 'id_rsa.pub',
                        'userName': app.user.username
                    }
                    yaml.dump(credentials, f, Dumper=YamlDumper, default_flow_style=False)

                    if 'virtual_machines' in node_templates['virtual_resources'] and len(node_templates['virtual_resources']['virtual_machines']) > 0:
                        components={'components': []}
                        for vm in node_templates['virtual_resources']['virtual_machines']:
                            component= vm.values()[0]
                            component['name']=vm.keys()[0]
                            components['components'].append(component)
                        yaml.dump(components, f, Dumper=YamlDumper, default_flow_style=False)

                    if 'components_connections' in node_templates['connections'] and len(node_templates['connections']['components_connections'])>0:
                        connections = {'connections': []}
                        for component_connection in node_templates['connections']['components_connections']:
                            connection = component_connection.values()[0]
                            connection['name'] = component_connection.keys()[0]
                            # Adapt it to provisioner format
                            for vm in node_templates['virtual_resources']['virtual_machines']:
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
                            for vm in node_templates['virtual_resources']['virtual_machines']:
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

                toscaFiles = []
                toscaFiles.append(toscaFile)
                with open(os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '_all.yml'),
                          'w') as f:
                    topologies = []
                    for topologyFile in toscaFiles:
                        topology = {
                            'topology': os.path.splitext(os.path.basename(toscaFile))[0],
                            'cloudProvider': "EC2"
                        }
                        topologies.append(topology)
                    yaml.dump({'topologies': topologies}, f, Dumper=YamlDumper, default_flow_style=False)

                allTopologyFile = os.path.join(settings.MEDIA_ROOT, 'documents', str(request.user.id), uuid + '_all.yml')

                drip_manager_service = DripManagerService(utils.getPropertyFromConfigFile("DRIP_MANAGER_API", "url"))
                drip_manager_response = drip_manager_service.upload_tosca(request.user, allTopologyFile, toscaFiles)

                if drip_manager_response.status_code == 200:

                    action_number = drip_manager_response.text[drip_manager_response.text.find('Action number: ')+15:]

                    ssh_key_document = SwitchDocument.objects.filter(user=request.user, description="Public ssh key").first()
                    drip_manager_response = drip_manager_service.conf_user_key(request.user, ssh_key_document, action_number)

                    if drip_manager_response.status_code == 200:
                        conf_script_document = SwitchDocument.objects.filter(user=request.user,
                                                                         description="nodejs web ssh server").first()
                        drip_manager_response = drip_manager_service.conf_script(request.user, conf_script_document,
                                                                                 action_number)

                        if drip_manager_response.status_code == 200:
                            drip_manager_response = drip_manager_service.execute(request.user, action_number)
                            if drip_manager_response.status_code == 200:
                                root = ET.fromstring(drip_manager_response.text)
                                result_tosca = root.findall("./file")[0]
                                tosca_provisioned_infrastructure = yaml.load(result_tosca.text.replace("\\n","\n"))

                                for vm_provisioned in tosca_provisioned_infrastructure['components']:
                                    vm_component = Instance.objects.get(uuid=vm_provisioned['name'])
                                    vm_component.title += ' (' + vm_provisioned['public_address'] + ')'
                                    vm_component.properties = yaml.dump(vm_provisioned, Dumper=YamlDumper, default_flow_style=False)
                                    vm_component.save()

                                drip_manager_response = drip_manager_service.setup_docker_orchestrator(request.user, action_number, "kubernetes")

                                if drip_manager_response.status_code == 200:
                                    result = 'ok'
                                    details.append('provision done correctly')

                                    app.status = 2
                                    app.save()

        if drip_manager_response.status_code != 200:
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

    @detail_route(methods=['get'], permission_classes=[])
    def run(self, request, pk=None, *args, **kwargs):
        app = Application.objects.get(id=pk)
        app_instance = ApplicationInstance.objects.create(application=app)
        app_instance.clone_from_application()
        return Response(app_instance.get_graph())


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