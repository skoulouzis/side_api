import os
import re
import xml.etree.ElementTree as ET
import requests

from requests.auth import HTTPBasicAuth

from django.http import JsonResponse
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

    @detail_route(methods=['get','post'], permission_classes=[])
    def tosca(self, request, pk=None, *args, **kwargs):
        if request.method == 'GET':
            app = Application.objects.filter(id=pk).first()
            tosca = app.get_tosca()
            return JsonResponse(tosca)
        elif request.method == 'POST':
            app = Application.objects.filter(id=pk).first()
            tosca = yaml.load(request.body).get('data', None)
            app.tosca_update(tosca)
            return Response(status=status.HTTP_204_NO_CONTENT)

    @detail_route(methods=['get'], permission_classes=[])
    def validate(self, request, pk=None, *args, **kwargs):
        # TODO: Implement validation from DRIP
        # TODO: Move to Application Model
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
    def plan(self, request, pk=None, *args, **kwargs):
        # TODO Think about making this more transparent. This should be something that is stored in the application?
        drip_host = 'https://drip.vlan400.uvalight.net:8443/drip-api'
        drip_tosca_endpoint = '/user/v1.0/tosca'
        drip_plan_endpoint = '/user/v1.0/planner/plan/'
        # TODO: This will be removed once DRIP user registration is complete.


        result = 'error'
        details = []
        app = Application.objects.get(id=pk)
        # TODO: move this to validation
        if app.needs_monitoring_server():
            app.create_monitoring_server()

        if app.get_status('Planed'):
            details.append('application has already a planned infrastructure')
        # TODO: move this to validation.
        elif not app.validate_requirements():
            result = 'error'
            details.append('Please make sure to define hardware requirements for all software components')
        elif not self.validation_done(pk):
            #bla bla
            details.append('Please make sure that the application is valid before to plan the virtual infrastructure')

        # Calling the DRIP API
        else:
            app_tosca = app.get_tosca()
            # TODO make this call an actual request not working because of the user missing
            tosca_id = 1 # requests.post(drip_host + drip_tosca_endpoint + '/post',
                          #          data=app_tosca,
                          #          auth=HTTPBasicAuth(drip_username, drip_password))

            plan_response = 'OK' # = requests.get(drip_host + drip_plan_endpoint + tosca_id,
                                                # auth=HTTPBasicAuth(drip_username, drip_password))
            if plan_response == 'OK':
                # TODO: Parse plan to get TOSCA ID - need actual access to DRIP
                plan_id = 2
                # get new TOSCA

                # There is a posibility that the planer does not do what was agreed upon. Ie it does not return TOSCA but some random YAMLs.
                # In that case strangle Spiros and revert back to Frans code.
                tosca_download_url = drip_host + drip_tosca_endpoint + plan_id
                planed_tosca_response = 'response'  #  requests.get(drip_host + drip_tosca_endpoint + plan_id, auth=HTTPBasicAuth(drip_username, drip_password))
                # new_tosca = yaml.load(planed_tosca_response.body).get('data', None)
                new_tosca = app_tosca  # TODO Placeholder! Remove!


                # Update application with new TOSCA
                app.tosca_update(new_tosca)

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

    @detail_route(methods=['get'], permission_classes=[])
    def provision(self, request, pk=None, *args, **kwargs):
        drip_host = 'https://drip.vlan400.uvalight.net:8443/drip-api'
        drip_provisioner_endpoint = '/user/v1.0/provisioner/provision'
        drip_keyID_store_endpoint = '/user/v1.0/keys/ids'
        drip_cloud_credentials_ids ='/user/v1.0/credentials/cloud/ids'
        # TODO: This will be removed once DRIP user registration is complete.


        result = 'error'
        details = []
        app = Application.objects.get(id=pk)

        if not app.get_status('Planed'):
            details.append('virtual infrastructure has not been planned yet')
        elif app.get_status('Provisioned'):
            details.append('application has already a provisioned infrastructure')
        elif app.get_status('Deployed'):
            details.append('application is already deployed on provisioned infrastructure')
        elif not self.validation_done(pk):
            details.append('Please make sure that the application is valid before provisioning virtual infrastructure')
        else:
            # get the tosca file of the application post it to DRIP
            app_tosca = app.get_tosca()
            tosca_id = 1  # requests.post(drip_host + drip_tosca_endpoint + '/post',
                                #         data=app_tosca,
                                #         auth=HTTPBasicAuth(drip_username, drip_password))

            drip_cloud_credentials_ids = requests.get(drip_host + drip_cloud_credentials_ids, auth=HTTPBasicAuth(drip_username, drip_password))
            vm_user_key_pair_ids = requests.get(drip_host + drip_keyID_store_endpoint, auth=HTTPBasicAuth(drip_username, drip_password))

            provision_json = {
                "cloudCredentialsIDs": drip_cloud_credentials_ids,
                "planID": tosca_id,
                "userKeyPairIDs": vm_user_key_pair_ids
            }

            provision_response = requests.post(drip_host + drip_provisioner_endpoint,
                                               json=provision_json,
                                               auth=HTTPBasicAuth(drip_username, drip_password))

            # TODO: What exactly does the UI have to show after this? Probably some changes to VM components?
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
        return Response(app.get_graph())

    def post(self, request, pk=None):
        app = Application.objects.filter(id=pk).first()
        app.put_graph(request.data)
        return Response(app.get_graph())
