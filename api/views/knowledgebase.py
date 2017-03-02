import requests
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import list_route, detail_route, api_view
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.filters import DjangoFilterBackend, SearchFilter
from rest_framework.views import APIView
from rest_framework_extensions.mixins import PaginateByMaxMixin

from api.models import *
from api.serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from side_api import utils
from api.services import DripManagerService


class ProviderViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = ()

    def get_queryset(self):
        return None


def get_provider_details(pk):
    r = requests.get('http://elab.lab.uvalight.net:8080/profiles/' + pk)
    json_data = r.json()

    attributes = json_data['cloud profile']['cloud platform']
    attributes['accessed_via'] = attributes.pop('accessed via')
    clouds = attributes.pop('provides cloud')
    vm_images = json_data['cloud profile']['virtual machine images']
    vm_types = json_data['cloud profile']['virtual machines types']

    cloud_response = []
    image_response = []
    type_response = []

    for cloud in clouds:
        cloud_data = {
            'type': 'cloud',
            'id': cloud['identifier']
        }
        cloud_response.append(cloud_data)

    for image in vm_images:
        image_data = {
            'type': 'vmimage',
            'id': image['identifier']
        }
        image_response.append(image_data)

    for type in vm_types:
        type_data = {
            'type': 'vmtype',
            'id': type['identifier']
        }
        type_response.append(type_data)

    response = {
        'type': 'provider',
        'id': pk,
        'attributes': attributes,
        'relationships': {
            'clouds': {
                'meta': {
                    'count': len(cloud_response)
                },
                'data': cloud_response
            },
            'images': {
                'meta': {
                    'count': len(image_response)
                },
                'data': image_response
            },
            'types': {
                'meta': {
                    'count': len(type_response)
                },
                'data': type_response
            }
        }
    }

    return response


@api_view()
def providers_list(request):
    r = requests.get('http://elab.lab.uvalight.net:8080/profiles')
    json_data = r.json()

    response = []

    for pk in json_data['identifiers']:
        response.append(get_provider_details(pk))

    return Response(response)


@api_view()
def providers_detail(request, pk):
    return Response(get_provider_details(pk))
