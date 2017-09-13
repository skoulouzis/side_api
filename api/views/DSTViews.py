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

from api.models import DSTInstance
from side_api import settings, utils
from api.services import JenaFusekiService, DripManagerService
import json


class DSTInstanceRequest(PaginateByMaxMixin, viewsets.ModelViewSet):

    @detail_route(methods=['post'], permission_classes=[])
    def DSTinstance(self, request, pk=None):

        request_json = json.loads(request.body)
        service_id = request_json["serviceId"]

        instance = DSTInstance.create(service_id)
        instance.save()
        json_result = {
            'instance_id': instance.id
        }
        return JsonResponse(json_result)

    @detail_route(methods=['post'], permission_classes=[])
    def DSTrequest(self, request, pk=None):


        json_result = {
            'url': 'some.url',
            'text': 'status'
        }

        return JsonResponse(json_result)

    @detail_route(methods=['get'], permission_classes=[])
    def DSTupdate(self, request, pk=None):

        json_result = {
            'update': 'status'
        }

        return JsonResponse(json_result)
