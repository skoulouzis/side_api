import os
import re
import xml.etree.ElementTree as ET
import requests
import datetime
import string
from requests.auth import HTTPBasicAuth

from django.http import JsonResponse, HttpResponse
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
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
import json
import ruamel.yaml as yaml
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# TODO: Permissions were nuked in most classes, as I was testing this. Uncomment!


class ApplicationViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    """
    API endpoints that deal with application.
    """
    serializer_class = ApplicationSerializer
    # authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    # permission_classes = (IsAuthenticated,)
    cloud_credentials_id = ''

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
        app.uuid = uuid.uuid4()
        app.title = "copy of " + app.title
        app.save()

        old_app = Application.objects.filter(id=old_app_pk).first()
        old_app.clone_instances_in_graph(app, 0, 0)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_tosca_dictionary(self, request, pk=None):

        # TODO: This should be moved to app where the rest of TOSCA generation is.
        # Actually it would make even more sense to have this inside the Serializers...
        # Ok this will actually make a lot of sense. Might try this...
        # TODO: We have no way of actually parsing the TOASCA atm. Is it needed?
        self.validate(request, pk)
        tosca = {}
        tosca_node_templates = {}
        application_networks = {}
        application_volumens = {}
        tosca_app_items = ComponentInstance.objects.filter(graph_id=pk)
        #TODO: Compleate hack. There is no way this should make it to the final version.
        monitoring_adapter_instance = tosca_app_items.filter(component_id=244).first()
        monitoring_adapter_name = ""
        if monitoring_adapter_instance is not None:
            monitoring_adapter_name = monitoring_adapter_instance.title

        for component in tosca_app_items:
            # IDs lower than 50 are "NF" systems.
            if component.component_id > 50:
                component_type_id = Component.objects.filter(graphbase_ptr_id=component.component_id).first().type_id
                component_tosca_class_id = ComponentType.objects.filter(id=component_type_id).first().tosca_class_id
                component_tosca_class = ToscaClass.objects.filter(id=component_tosca_class_id).first()
                tosca_container_name = component_tosca_class.prefix + '.' + component_tosca_class.name
                artifacts = yaml.load(component.artifacts, Loader=yaml.Loader)
                properties = yaml.load(component.properties, Loader=yaml.Loader)
                # TODO: This is hardcoded value. So it obviously only works for an instance that is running on our servers!
                # Luckily no one is going to use this anyway...
                properties['TOSCA'] = DQ("http://i213.cscloud.cf.ac.uk:7001/api/switchapps/" + pk + "/tosca")

                #TODO: This is now found in a seperate "service" - The names of SIDE components are wrong! WRONG!
                ports_map = {}
                if 'ports_mapping' in properties:
                    ports_map = properties['ports_mapping']
                    del properties['ports_mapping']

                component_properties = {}
                component_requirements = {}
                component_dependencies = []
                component_networks = []
                component_volumes = []
                component_constraints = {}
                component_infrastructure_requirements = {}
                component_variables = {}
                connected_services = ServiceLink.objects.filter(target_id=component.id)

                # TODO: MIght make sense to have some try - catch or something to see if yaml is correct....
                for service in connected_services:
                    service_instance = tosca_app_items.filter(id=service.source_id).first()
                    if service_instance.component_id == 5:
                        if monitoring_adapter_instance is not None:
                            properties['MONITORING_PROXY'] = DQ(monitoring_adapter_name)
                            component_dependencies.append(monitoring_adapter_name)
                            component_networks.append("monitoring_v2")
                    if service_instance.component_id == 6:
                        component_constraints = yaml.load(service_instance.properties, Loader=yaml.Loader)
                    if service_instance.component_id == 8:
                        component_infrastructure_requirements = yaml.load(service_instance.properties, Loader=yaml.Loader)
                    if service_instance.component_id == 31:
                        component_networks.append(service_instance.title)
                        application_networks[service_instance.title] = yaml.load(service_instance.properties, Loader=yaml.Loader)
                    if service_instance.component_id == 23:
                        component_volumes.append(service_instance.title)
                        application_volumens[service_instance.title] = yaml.load(service_instance.properties, Loader=yaml.Loader)
                    if service_instance.component_id == 24:
                        ports_map = yaml.load(service_instance.properties, Loader=yaml.Loader)
                    if service_instance.component_id == 25:
                        component_variables = yaml.load(service_instance.properties, Loader=yaml.Loader)
                    # TODO: add the same logic for Alarm_trigger if applicable.
                    # TODO: Same logic for hw_requirements

                if component_volumes:
                    component_requirements['volumes'] = component_volumes
                if component_networks:
                    component_requirements['networks'] = component_networks
                if component_variables:
                    component_properties['Environment_variables'] = component_variables
                if component_infrastructure_requirements:
                    component_properties['Infrastructure_requirements'] = component_infrastructure_requirements
                if component_constraints:
                    component_properties['Constraints'] = component_constraints
                if ports_map:
                    component_properties['ports_mapping'] = ports_map
                component_properties['scaling_mode'] = component.mode

                # TODO: Change the logic of this to make it based on dependancy connections! Because this is a mess!
                # This can wait!
                instance_ports = ComponentPort.objects.filter(instance_id=component.id, type="out")
                for instance_port in instance_ports:
                    out_port_destinations = ComponentLink.objects.filter(source_id=instance_port.id)
                    for port_destination in out_port_destinations:
                        component_requirements_port_id = port_destination.target_id
                        component_requirements_instance_id = ComponentPort.objects.filter(
                            id=component_requirements_port_id).first().instance_id
                        component_requirements_instance = ComponentInstance.objects.filter(
                            id=component_requirements_instance_id).first()
                        component_requirement_title = component_requirements_instance.title
                        component_dependencies.append(component_requirement_title)
                dependency_links = DependencyLink.objects.filter(dependant_id=component.id)
                for dependency_link in dependency_links:
                    component_requirements_instance = dependency_link.dependency
                    component_dependencies.append(component_requirements_instance.title)
                if component_dependencies:
                    component_requirements['dependency'] = component_dependencies

                # TODO: add hardware requirements

                tosca_node_templates[DQ(component.title)] = {
                    'type': SQ(tosca_container_name),
                    'artifacts': artifacts,
                    'properties': component_properties,
                    'requirements': component_requirements

                }
        app = Application.objects.filter(id=pk).first()
        # TODO: Remove unneeded definitions from node types. (Nooo! Think of the children!)
        tosca = app.get_tosca()
        tosca["topology_template"] = {
            'node_templates': tosca_node_templates,
            'network_templates': application_networks,
            'volume_templates': application_volumens
            }
        return tosca

    @detail_route(methods=['get'], permission_classes=[])
    def tosca(self, request, pk=None, *args, **kwargs):

        tosca = self.get_tosca_dictionary(request, pk)
        tosca_yml = yaml.round_trip_dump(tosca,  explicit_start=True)
        return HttpResponse(tosca_yml, content_type='text/plain')

    @detail_route(methods=['get'], permission_classes=[])
    def get_monitoring_url(self, request, pk=None, *args, **kwargs):
        # Screw this!
        chartName = request.GET.get('chartName', '')
        secondTime = datetime.datetime.now()
        firstTime = secondTime - datetime.timedelta(minutes=60)
        secondTime_String = secondTime.strftime("%Y-%m-%d %H:%M:%S")
        firstTime_String = firstTime.strftime("%Y-%m-%d %H:%M:%S")
        tosca_app_items = ComponentInstance.objects.filter(graph_id=pk)
        containerID = "f7a1ed4f3bd94ce3b942dbb75477a806"
        jcatascopija_adress = "http://194.249.1.175:8080"
        # "http://194.249.0.44:8080/JCatascopia-Web/restAPI/metrics/8e62a0612a404367be02c2b19a563fb0:"
        # +chartName + "?firstTime=2017-12-21%2009:20:00&secondTime=2017-12-21%2017:35:04",
        url = jcatascopija_adress \
            + "/JCatascopia-Web/restAPI/metrics/" \
            + containerID \
            + ":" + chartName \
            + "?firstTime=" + firstTime_String \
            + "&secondTime=" + secondTime_String

        monitoring_dic = {
            "url": url
        }
        return JsonResponse(monitoring_dic)

    @detail_route(methods=['get'], permission_classes=[])
    def tosca_json(self, request, pk=None, *args, **kwargs):

        tosca = self.get_tosca_dictionary(request, pk)
        tosca_data = {'data': tosca}
        return JsonResponse(tosca_data)

    @detail_route(methods=['get'], permission_classes=[])
    def validate(self, request, pk=None, *args, **kwargs):
        # TODO: Make V2
        details = []
        app = Application.objects.filter(id=pk).first()
        DRIP_IDs = DRIPIDs.objects.filter(application=app).first()
        if not DRIP_IDs:
            DRIP_IDs = DRIPIDs.objects.create(application=app)

        # for instance in app.get_instances():
        #    if "SET_ITS_VALUE" in str(instance.properties):
        #       details.append("Component '" + instance.title + "' needs all its properties to be set.")

        if app.needs_monitoring_server():
            app.create_monitoring_server()
        if len(details) == 0:
            result = 'ok'
            details.append('validation done correctly')
        else:
            result = 'error'

        validation_result = {
            'result': result,
            'details': details
        }

        return JsonResponse(validation_result)

    def validation_done(self, pk):
        validation_result = json.loads(self.validate(request=None, pk=pk).content)
        if validation_result['result'] == "error":
            return False
        else:
            return True

    @detail_route(methods=['post'], permission_classes=[])
    def upload_credentials(self, request,  drip_username, drip_password):

        # TODO: This needs a new view so that the user can input this data directly to DRIP
        # Prefer to pass this data directly to DRIP withou saving it to the MySQL so that we do not need to
        # deal with security.


        # drip credentials
        drip_host = 'https://drip.vlan400.uvalight.net:8443/drip-api'
        drip_credentials_endpoint = '/user/v1.0/credentials/cloud/'
        secret_key = "key"
        cloud_provider = "ec2"
        acces_key = "key"


        # ID and timestamp feel like something that DRIP should return not something I should provide!
        # What are attributes?
        credentials_json = {
                "secretKey": secret_key,
                "cloudProvider Name": cloud_provider,
                "accessKeyId": acces_key,
                "attributes": {
                    "property1": {},
                    "property2": {}
                },
                "owner": drip_username
            }
        # TODO: uncoment when DRIP service available
        # cloud_credentials_id = requests.post(drip_host + drip_credentials_endpoint,
        #               json=credentials_json,
        #               auth=HTTPBasicAuth(drip_username, drip_password))

        # store data to a new model

    @detail_route(methods=['get'], permission_classes=[])
    def get_DRIP_IDs(self, request, pk=None, *args, **kwargs):
        DRIP_IDs = DRIPIDs.objects.first(application=pk).first()
        Serialized_IDs = DRIPIDSerializer(DRIP_IDs)
        return JsonResponse(Serialized_IDs)

    def upload_tosca(self, request, pk,  DRIP_IDs):
        dripAPI = DripApi.objects.first()

        app_tosca_yaml = self.tosca(request, pk)
        # Clean old TOSCA
        if DRIP_IDs.tosca_ID:
            tosca_id = DRIP_IDs.tosca_ID
            delete_response = requests.delete(dripAPI.address + 'tosca/' + tosca_id,
                                              auth=HTTPBasicAuth(dripAPI.username, dripAPI.password),
                                              verify=False)
        # Upload new TOSCA
        tosca_post_response = requests.post(dripAPI.address + 'tosca' + '/post',
                                            verify=False,
                                            data=app_tosca_yaml,
                                            auth=(dripAPI.username, dripAPI.password))

        tosca_drip_id = tosca_post_response.content
        DRIP_IDs.tosca_ID = tosca_drip_id
        DRIP_IDs.save()



    @detail_route(methods=['get'], permission_classes=[])
    def plan(self, request, pk=None, *args, **kwargs):
        # TODO: Think about making this more transparent. This should be something that is stored in the application?
        drip_host = 'https://drip.vlan400.uvalight.net:8443/drip-api'
        drip_tosca_endpoint = '/user/v1.0/tosca'
        drip_plan_endpoint = '/user/v1.0/planner/plan'
        drip_username = 'matej'
        drip_password = 'switch-1nt3gr4t1on'
        # TODO: This will be removed once DRIP user registration is complete. aka never.
        result = 'error'
        details = []
        app = Application.objects.get(id=pk)
        DRIP_IDs = DRIPIDs.objects.filter(application=app).first()
        if not DRIP_IDs:
            DRIP_IDs = DRIPIDs.objects.create(application=app)


        if False: #app.get_status('Planed'):
            details.append('application has already a planned infrastructure')
        # TODO: move this to validation.
        # elif not app.validate_requirements():
        #     result = 'error'
        #     details.append('Please make sure to define hardware requirements for all software components')
        # elif not self.validation_done(pk):
        #     #bla bla
        #     details.append('Please make sure that the application is valid before to plan the virtual infrastructure')

        # Calling the DRIP API
        else:

            self.upload_tosca(request, pk,  DRIP_IDs)

            # Clean old plan
            if DRIP_IDs.plan_ID:
                plan_id = DRIP_IDs.plan_ID
                delete_adress = drip_host + '/user/v1.0/planner/' + plan_id
                delete_response = requests.delete(delete_adress,
                                                  auth=HTTPBasicAuth(drip_username, drip_password),
                                                  verify=False)

            plan_response = requests.get(drip_host + drip_plan_endpoint + '/' + tosca_drip_id,
                                         auth=HTTPBasicAuth(drip_username, drip_password),
                                         verify=False)

            if plan_response.status_code == 200:
                plan_id = plan_response.content
                DRIP_IDs.plan_ID = plan_id
                DRIP_IDs.save()
                plan_yml = requests.get(drip_host + '/user/v1.0/planner/' + plan_id + '/?format=yml',
                                        auth=HTTPBasicAuth(drip_username, drip_password),
                                        verify=False)
                with open('planer2.yml', 'w') as f:
                    print >> f, plan_yml.content
                result = 'OK'
                details.append('plan done correctly')
                app.status = 1
                app.drip_plan_id = 'planID'
                app.save()
            else:
                details.append('planning of virtual infrastructure has failed')

        planning_vi_result = {
            'result': result,
            'details': details
        }
        return JsonResponse(planning_vi_result)

    @list_route(methods=['get'], permission_classes=[])
    def delete_drip_ids(self, request, pk=None, *args, **kwargs):
        # Not really an useful method!
        drip_host = 'https://drip.vlan400.uvalight.net:8443/drip-api'
        drip_tosca_endpoint = '/user/v1.0/tosca'
        drip_plan_endpoint = '/user/v1.0/planner/plan'
        drip_username = 'matej'
        drip_password = 'switch-1nt3gr4t1on'

        planer_id_response = requests.get(drip_host + '/user/v1.0/planner/ids',
                                         auth=HTTPBasicAuth(drip_username, drip_password),
                                         verify=False)
        print planer_id_response.content

        planer_id_table = yaml.load(planer_id_response.content, Loader=yaml.Loader)

        for plan_id in planer_id_table:
            print plan_id
            delete_adress = drip_host + '/user/v1.0/planner/' + plan_id
            delete_response = requests.delete(delete_adress,
                                              auth=HTTPBasicAuth(drip_username, drip_password),
                                              verify=False)

        planer_id_response = requests.get(drip_host + '/user/v1.0/tosca/ids',
                                          auth=HTTPBasicAuth(drip_username, drip_password),
                                          verify=False)
        print planer_id_response.content

        planer_id_table = yaml.load(planer_id_response.content, Loader=yaml.Loader)

        for plan_id in planer_id_table:
            print plan_id
            delete_adress = drip_host + '/user/v1.0/tosca/' + plan_id
            delete_response = requests.delete(delete_adress,
                                              auth=HTTPBasicAuth(drip_username, drip_password),
                                              verify=False)

        planning_vi_result = {
            'result': "OK",
            'details': "OK"
        }
        return JsonResponse(planning_vi_result)


    @detail_route(methods=['get'], permission_classes=[])
    def provision(self, request, pk=None, *args, **kwargs):
        drip_host = 'https://drip.vlan400.uvalight.net:8443/drip-api'
        drip_provisioner_endpoint = '/user/v1.0/provisioner/provision'
        drip_keyID_store_endpoint = '/user/v1.0/keys/ids'
        drip_cloud_credentials_ids ='/user/v1.0/credentials/cloud/ids'
        drip_username = 'matej'
        drip_password = 'switch-1nt3gr4t1on'

        # TODO: ^ This will be removed once DRIP user registration is complete.


        result = 'error'
        details = []
        app = Application.objects.get(id=pk)

        # TODO: We cuould use the DRIP_IDs to generate this information.
        if not app.get_status('Planed'):
            details.append('virtual infrastructure has not been planned yet')
        elif app.get_status('Provisioned'):
            details.append('application has already a provisioned infrastructure')
        elif app.get_status('Deployed'):
            details.append('application is already deployed on provisioned infrastructure')
        elif not self.validation_done(pk):
            details.append('Please make sure that the application is valid before provisioning virtual infrastructure')
        else:
            DRIP_IDs = DRIPIDs.objects.filter(application=app).first()

            # TODO: Get available credentials IDs
            drip_credentials_response = requests.get(drip_host + drip_cloud_credentials_ids,
                                                     auth=HTTPBasicAuth(drip_username, drip_password),
                                                     verify=False)
            # TODO: Parse yaml to list (Needed?)
            drip_credentials_ids = drip_credentials_response.content

            plan_id = DRIP_IDs.plan_ID

            provision_json = {
                "cloudCredentialsIDs": ["5a6f88c9e4b01f03ba0c1658"],
                "planID": plan_id
            }

            provision_response = requests.post(drip_host + drip_provisioner_endpoint,
                                               json=provision_json,
                                               auth=HTTPBasicAuth(drip_username, drip_password),
                                               verify=False)

            details.append('Application provisioned')
            result = 'OK'

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
    # authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    # permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def get(self, request, pk=None):
        app = Application.objects.filter(id=pk).first()
        response = app.get_graph()
        return Response(response)

    def post(self, request, pk=None):
        app = Application.objects.filter(id=pk).first()
        app.put_graph(request.data)
        return Response(app.get_graph())
