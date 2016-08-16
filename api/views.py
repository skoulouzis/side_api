import json

from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, FileResponse
from rest_framework import viewsets
from rest_framework.decorators import list_route, detail_route
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FileUploadParser, JSONParser
from rest_framework.response import Response
from rest_framework.filters import DjangoFilterBackend, SearchFilter
from rest_framework import views
from rest_framework_xml.parsers import XMLParser

from api.permissions import BelongsToUser, AppBelongsToUser
from models import TodoItem, SwitchApp, SwitchAppGraph, SwitchComponent
from serializers import TodoItemSerializer, UserSerializer, SwitchAppSerializer, SwitchAppGraphSerializer, \
    SwitchComponentSerializer
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

class TodoItemViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows TodoItems to be CRUDed.
    """
    serializer_class = TodoItemSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated, BelongsToUser,)

    def get_queryset(self):
        return TodoItem.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SwitchAppViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows TodoItems to be CRUDed.
    """
    serializer_class = SwitchAppSerializer
    authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)

    def list(self, request, **kwargs):
        apps = SwitchApp.objects.filter(user=self.request.user)
        serializer = self.get_serializer(apps, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return SwitchApp.objects.filter()

    def perform_create(self, serializer):
        app = serializer.save(user=self.request.user)
        SwitchAppGraph.objects.create(app_id=app.id)


class SwitchAppGraphViewSet(viewsets.ModelViewSet):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated, AppBelongsToUser,)
    serializer_class = SwitchAppGraphSerializer
    queryset = SwitchAppGraph.objects.all()
    parser_classes = (JSONParser,)

    def list(self, request, switchapps_pk=None, **kwargs):
        graphs = self.queryset.filter(app_id=switchapps_pk)
        serializer = self.get_serializer(graphs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None, switchapps_pk=None):
        graph = self.queryset.get(id=pk, app_id=switchapps_pk)
        serializer = self.get_serializer(graph)
        return Response(serializer.data)

    @list_route(permission_classes=[IsAuthenticated])
    def latest(self, request, switchapps_pk=None, *args, **kwargs):
        graph = self.queryset.filter(app_id=switchapps_pk).latest('updated_at')
        serializer = self.get_serializer(graph)
        return Response(serializer.data)

    def put(self, request, switchapps_pk=None, **kwargs):
        json_data = request.data
        graph = self.queryset.filter(app_id=switchapps_pk).latest('updated_at')
        graph.file.save(str(graph.app.uuid)+'.json', ContentFile(json.dumps(json_data)))
        serializer = self.get_serializer(graph)
        return Response(serializer.data)

    @detail_route(methods=['get'],permission_classes=[IsAuthenticated])
    def json(self, request, pk=None, switchapps_pk=None, *args, **kwargs):
        graph = self.queryset.get(id=pk, app_id=switchapps_pk)
        file = open(graph.file.url, 'r')
        return FileResponse(file)

    @detail_route(methods=['get'], permission_classes=[IsAuthenticated])
    def tosca(self, request, pk=None, switchapps_pk=None, *args, **kwargs):
        graph = self.queryset.get(id=pk, app_id=switchapps_pk)
        file = open(graph.file.url, 'r')
        return FileResponse(file)


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


class SwitchComponentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows TodoItems to be CRUDed.
    """
    serializer_class = SwitchComponentSerializer

    def get_queryset(self):
        app_id = self.request.query_params.get('app_id', None)
        uuid = self.request.query_params.get('uuid', None)
        if app_id is not None:
            queryset = SwitchComponent.objects.filter(app_id=app_id)
            if uuid is not None:
                queryset = SwitchComponent.objects.filter(app_id=app_id, uuid=uuid)
        else:
            queryset = SwitchComponent.objects.filter(app__user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        app_id = self.request.data['app_id']
        app = SwitchApp.objects.filter(id=app_id).first()
        serializer.save(app=app)