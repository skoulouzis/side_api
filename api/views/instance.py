from rest_framework import viewsets
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_extensions.mixins import PaginateByMaxMixin

from api.serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated


class ApplicationInstanceViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = ApplicationInstanceSerializer

    def get_queryset(self):
        queryset = ApplicationInstance.objects.filter(application__user=self.request.user)
        return queryset


class ApplicationInstanceGraphView(PaginateByMaxMixin, APIView):
    """
    API endpoint that allows SwitchApps to be CRUDed.
    """
    serializer_class = ApplicationInstanceSerializer
    authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def get(self, request, pk=None):
        component = ApplicationInstance.objects.filter(id=pk).first()
        return Response(component.get_graph())

    def post(self, request, pk=None):
        component = ApplicationInstance.objects.filter(id=pk).first()
        component.put_graph(request.data)
        return Response(component.get_graph())

