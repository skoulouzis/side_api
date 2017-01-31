import os
import re
import xml.etree.ElementTree as ET

from django.http import JsonResponse
from django.contrib.sites.shortcuts import get_current_site
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
            if "SET_ITS_VALUE" in str(instance.properties):
              details.append("Component '"  + instance.title + "' needs all its properties to be set.")

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
                    planner_input_tosca_file = os.path.join(settings.MEDIA_ROOT, 'documents',
                                                            hashlib.md5(request.user.username).hexdigest(), 'apps',
                                                            str(app.uuid), 'dripPlanner','inputs','planner_input.yml')
                    if not os.path.exists(os.path.dirname(planner_input_tosca_file)):
                        os.makedirs(os.path.dirname(planner_input_tosca_file))
                    with open(planner_input_tosca_file, 'w') as f:
                        yaml.dump(app_tosca_json['data'], f, Dumper=utils.YamlDumper, default_flow_style=False)

                    drip_manager_service = DripManagerService(
                        utils.getPropertyFromConfigFile("DRIP_MANAGER_API", "url"))
                    drip_manager_response = drip_manager_service.planning_virtual_infrastructure(request.user, planner_input_tosca_file)


                    if drip_manager_response.status_code == 200:
                        root = ET.fromstring(drip_manager_response.text)
                        planner_output_tosca_files = root.findall("./file")
                        # TODO: At the moment the planner doesn't return a tosca compliance file, instead it returns a list of yaml files with the infrastructure topologies
                        for tosca_file in planner_output_tosca_files:
                            tosca_level = tosca_file.attrib['level']
                            tosca_file_name = tosca_file.attrib['name']
                            toca_content = yaml.load(tosca_file.text.replace("\\n", "\n"))

                            planner_output_tosca_file = os.path.join(settings.MEDIA_ROOT, 'documents',
                                                            hashlib.md5(request.user.username).hexdigest(), 'apps',
                                                            str(app.uuid), 'dripPlanner','outputs', tosca_file_name)
                            if not os.path.exists(os.path.dirname(planner_output_tosca_file)):
                                os.makedirs(os.path.dirname(planner_output_tosca_file))
                            with open(planner_output_tosca_file, 'w') as f:
                                yaml.dump(toca_content, f, Dumper=utils.YamlDumper, default_flow_style=False)

                            if tosca_level=='1':
                                subnets = {}
                                # Find out which vm corresponds with which application component
                                for vm in toca_content.get("components", None):
                                    docker_image = vm.get("dockers")

                                    component_vm, created = Component.objects.get_or_create(user=request.user,
                                            title='VM', type=ComponentType.objects.get(title='Virtual Machine'))
                                    if created:
                                        Instance.objects.create(graph=component_vm, component=component_vm, title=component_vm.title,
                                                                last_x=400, last_y=200, mode='single')

                                    docker_component = app.instances.filter(artifacts__contains=docker_image).first()
                                    graph_req = app.service_links.filter(target=docker_component, source__component__type__title='Requirement').first().source

                                    # Create a graph_virtual_machine element
                                    graph_vm = ServiceComponent.objects.create(component=component_vm, graph=app,
                                                title='VM_' + graph_req.title, mode=graph_req.mode,
                                                last_x=graph_req.last_x, last_y=graph_req.last_y + 80, uuid=vm.get('name'))

                                    del vm['type']
                                    graph_vm.properties = yaml.dump(vm, Dumper=utils.YamlDumper, default_flow_style=False)
                                    graph_vm.save()

                                    # Create a service_link between the new vm and the requirement
                                    graph_service_link_vm_req = ServiceLink.objects.create(graph=app, source=graph_vm, target=graph_req)
                                    graph_service_link_vm_req.save()

                                    for ethernet_port in vm.get('ethernet_port',[]):
                                        vms_in_subnet = subnets.get(ethernet_port.get('subnet_name'), [])
                                        vms_in_subnet.append(str(graph_vm.uuid))
                                        subnets[ethernet_port.get('subnet_name')]=vms_in_subnet


                                for subnet in toca_content.get("subnets", None):
                                    component_subnet, created = Component.objects.get_or_create(user=request.user,
                                            title='subnet', type=ComponentType.objects.get(title='Virtual Network'))
                                    if created:
                                        Instance.objects.create(graph=component_subnet, component=component_subnet, title=component_subnet.title,
                                                                last_x=400, last_y=200, mode='single')

                                    # Create a graph_virtual_network element
                                    app_graph_dimensions = app.get_current_graph_dimensions()
                                    graph_subnet = ServiceComponent.objects.create(component=component_subnet, graph=app,
                                                title='subnet_' + subnet.get('name'), mode='single',
                                                last_x=app_graph_dimensions.get('bottom_x',0)/2, last_y=app_graph_dimensions.get('bottom_y',0) + 80)

                                    graph_subnet.properties = yaml.dump(subnet, Dumper=utils.YamlDumper, default_flow_style=False)
                                    graph_subnet.save()

                                    # Create a service_link between the subnet and all the vms associated with it
                                    vms_in_subnet = subnets.get(subnet.get('name'), [])
                                    for vm_uuid in vms_in_subnet:
                                        graph_vm = ServiceComponent.objects.get(uuid=vm_uuid)
                                        graph_service_link_vm_req = ServiceLink.objects.create(graph=app, source=graph_vm, target=graph_subnet)
                                        graph_service_link_vm_req.save()

                        result = 'ok'
                        details.append('plan done correctly')
                        app.status = 1
                        app.save()
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

                #TODO: At the monent the provisioner doesn't work with standard tosca so we have prepare the input files from the information our db rather than passing the tosca file
                infrastructure_topologies = {}

                vm_instances = app.instances.filter(component__type__title='Virtual Machine').all()
                for vm_instance in vm_instances:
                    vm_properties = yaml.load(vm_instance.properties.replace("\\n","\n"))
                    vm_properties['type'] = vm_instance.component.type.tosca_class.get_full_name()
                    if vm_properties.get('domain') in infrastructure_topologies:
                        components = infrastructure_topologies.get(vm_properties.get('domain')).get('components')
                        components.append(vm_properties)
                        infrastructure_topologies.get(vm_properties.get('domain'))['components']= components
                    else:
                        infrastructure_topologies[vm_properties.get('domain')] = {'components':[vm_properties], 'subnets': []}

                    service_links_vm_network = ServiceLink.objects.filter(graph=app, source=vm_instance,
                                               target__component__type__title='Virtual Network').all()

                    for service_link_vm_network in service_links_vm_network:
                        network_properties = yaml.load(service_link_vm_network.target.properties.replace("\\n","\n"))
                        subnets = infrastructure_topologies.get(vm_properties.get('domain')).get('subnets')
                        if not any(subnet.get('name', None) == network_properties.get('name') for subnet in subnets):
                            subnets.append(network_properties)
                            infrastructure_topologies.get(vm_properties.get('domain'))['subnets'] = subnets

                # Create all topology file
                all_topology_file = os.path.join(settings.MEDIA_ROOT, 'documents',
                                                 hashlib.md5(request.user.username).hexdigest(), 'apps',
                                                 str(app.uuid), 'dripProvisioner','inputs', 'provisioner_input_all.yml')
                if not os.path.exists(os.path.dirname(all_topology_file)):
                    os.makedirs(os.path.dirname(all_topology_file))
                with open(all_topology_file, 'w') as f:
                    list_topologies = []
                    for domain in infrastructure_topologies:
                        list_topologies.append({'topology': re.sub(r'[\\/*?:"<>|\\.\\-]',"_",domain), 'cloudProvider':domain.split('.')[0]})
                    yaml.dump({'topologies':list_topologies}, f, Dumper=utils.YamlDumper, default_flow_style=False)

                # Create individual files for each topology (cloud provider / region)
                specific_topology_files = []
                for domain, topology in infrastructure_topologies.iteritems():
                    provisioner_input_specific_topology_file = os.path.join(settings.MEDIA_ROOT, 'documents',
                                    hashlib.md5(request.user.username).hexdigest(), 'apps', str(app.uuid),
                                    'dripProvisioner','inputs', re.sub(r'[\\/*?:"<>|\\.\\-]',"_",domain) + '.yml')
                    specific_topology_files.append(provisioner_input_specific_topology_file)
                    if not os.path.exists(os.path.dirname(provisioner_input_specific_topology_file)):
                        os.makedirs(os.path.dirname(provisioner_input_specific_topology_file))
                    with open(provisioner_input_specific_topology_file, 'w') as f:
                        credentials = {
                            'publicKeyPath': 'id_rsa.pub',
                            'userName': app.user.username
                        }
                        yaml.dump(credentials, f, Dumper=utils.YamlDumper, default_flow_style=False)
                        yaml.dump(topology, f, Dumper=utils.YamlDumper, default_flow_style=False)

                drip_manager_service = DripManagerService(utils.getPropertyFromConfigFile("DRIP_MANAGER_API", "url"))
                drip_manager_response = drip_manager_service.upload_tosca(request.user, all_topology_file, specific_topology_files)

                if drip_manager_response.status_code == 200:

                    action_number = drip_manager_response.text[drip_manager_response.text.find('Action number: ')+15:]

                    ssh_key_document = SwitchDocument.objects.filter(user=request.user, document_type=SwitchDocumentType.objects.get(name="PUBLIC_SSH_KEY")).first()
                    drip_manager_response = drip_manager_service.conf_user_key(request.user, ssh_key_document, action_number)

                    if drip_manager_response.status_code == 200:
                        conf_script_file = os.path.join(settings.MEDIA_ROOT, 'webssh_server.sh')
                        shell_script = "#!/bin/bash\n" \
                                       "mkdir webssh_server\n" \
                                       "cd webssh_server\n" \
                                       "apt-get update\n" \
                                       "apt-get -y install nodejs nodejs-legacy npm\n" \
                                       "npm install express pty.js socket.io\n" \
                                       "# wget http://" + get_current_site(request).domain + "/static/js/webssh_server.js\n" \
                                        "wget https://dl.dropboxusercontent.com/u/46267592/webssh_server.js\n" \
                                                                            "node webssh_server.js &\n"
                        with open(conf_script_file, 'w') as f:
                            f.write(shell_script)

                        drip_manager_response = drip_manager_service.conf_script(request.user, conf_script_file, action_number)

                        if drip_manager_response.status_code == 200:
                            drip_manager_response = drip_manager_service.execute(request.user, action_number)
                            if drip_manager_response.status_code == 200:
                                root = ET.fromstring(drip_manager_response.text)
                                provision_output_tosca_files = root.findall("./file")
                                # TODO: At the moment the provisioner doesn't return a tosca compliance file, instead it returns a list of yaml files with the infrastructure topologies
                                for tosca_file in provision_output_tosca_files:
                                    toca_content = yaml.load(tosca_file.text.replace("\\n", "\n"))

                                    provisioner_output_tosca_file = os.path.join(settings.MEDIA_ROOT, 'documents',
                                                hashlib.md5(request.user.username).hexdigest(), 'apps', str(app.uuid),
                                                'dripProvisioner', 'outputs', str(uuid.uuid4()) + '.yml')
                                    if not os.path.exists(os.path.dirname(provisioner_output_tosca_file)):
                                        os.makedirs(os.path.dirname(provisioner_output_tosca_file))
                                    with open(provisioner_output_tosca_file, 'w') as f:
                                        yaml.dump(toca_content, f, Dumper=utils.YamlDumper, default_flow_style=False)

                                    # Update vm instances to register their public ip addresses
                                    for vm_provisioned in toca_content['components']:
                                        vm_component = Instance.objects.get(uuid=vm_provisioned['name'])
                                        vm_component.title += ' (' + vm_provisioned['public_address'] + ')'
                                        del vm_provisioned['type']
                                        vm_component.properties = yaml.dump(vm_provisioned, Dumper=utils.YamlDumper, default_flow_style=False)
                                        vm_component.save()

                                drip_manager_response = drip_manager_service.setup_docker_orchestrator(request.user, action_number, "kubernetes")

                                if drip_manager_response.status_code == 200:
                                    root = ET.fromstring(drip_manager_response.text)
                                    kubernetes_config = yaml.load(root.find("./file").text.replace("\\n", "\n"))
                                    kubernetes_config_file = os.path.join(settings.MEDIA_ROOT, 'documents',
                                                hashlib.md5(request.user.username).hexdigest(), 'apps',
                                                str(app.uuid), 'dripDeployer', 'outputs', str(uuid.uuid4()) + '.yml')
                                    if not os.path.exists(os.path.dirname(kubernetes_config_file)):
                                        os.makedirs(os.path.dirname(kubernetes_config_file))
                                    with open(kubernetes_config_file, 'w') as f:
                                        yaml.dump(kubernetes_config, f, Dumper=utils.YamlDumper, default_flow_style=False)

                                    result = 'ok'
                                    details.append('provision done correctly')

                                    app.status = 2
                                    app.save()

                if drip_manager_response.status_code != 200:
                    result = 'error'
                    details.append('provision has failed')

        provision_vi_result = {
            'result': result,
            'details': details
        }

        return JsonResponse(provision_vi_result)

    @detail_route(methods=['get'], permission_classes=[])
    def deploy(self, request, pk=None, *args, **kwargs):

        result = ''
        details = []
        new_pk = None

        app = Application.objects.get(id=pk)
        try:
            app_instance = ApplicationInstance.objects.create(application=app)
            new_pk = app_instance.id
            app_instance.clone_from_application()
            result = 'success'
            details.append('deployment complete')
        except Exception as e:
            print e.message
            result = 'error'
            details.append('deployment has failed')

        deploy_result = {
            'pk': new_pk,
            'result': result,
            'details': details
        }

        return JsonResponse(deploy_result)


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