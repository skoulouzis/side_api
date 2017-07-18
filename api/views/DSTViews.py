from rest_framework import viewsets
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_extensions.mixins import PaginateByMaxMixin


from api.models import *
from api.serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated

class DSTInstanceRequest(APIView):

    def post(self, request):
        dst_service_id = request.POST.get('dst_service_id')
        return Response("ffaf")
