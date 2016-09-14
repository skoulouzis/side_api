import json
import yaml
import os

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
from models import SwitchApp, SwitchAppGraph, SwitchComponent
from serializers import UserSerializer, SwitchAppSerializer, SwitchAppGraphSerializer, \
    SwitchComponentSerializer
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from side_api import settings


class SwitchAppViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows SwitchApps to be CRUDed.
    """
    serializer_class = SwitchAppSerializer
    authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)

    def list(self, request, **kwargs):
        apps = SwitchApp.objects.filter()
        # apps = SwitchApp.objects.filter(user=self.request.user)
        serializer = self.get_serializer(apps, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return SwitchApp.objects.filter()

    def perform_create(self, serializer):
        app = serializer.save(user=self.request.user)
        SwitchAppGraph.objects.create(app_id=app.id)

    @detail_route(methods=['get'], permission_classes=[])
    def tosca(self, request, pk=None, *args, **kwargs):
        graph = SwitchAppGraph.objects.filter(app_id=pk).latest('updated_at')
        with open(graph.file.url, 'r') as f:
            graph_json = json.loads(f.read())

        components = []
        external = []
        network = []
        attributes = []
        groups = []

        for cell in graph_json['cells']:
            data_obj = {}
            if cell['type'].startswith('switch'):
                db_record = SwitchComponent.objects.get(uuid=cell['id'])
                # data_obj['id'] = db_record.id
                data_obj['title'] = db_record.title
                data_obj['uuid'] = cell['id']

                if db_record.properties != 'data: "enter metadata as YAML"':
                    metadata = yaml.load(str(db_record.properties).replace("\t","    "))
                    data_obj.update(metadata)

                if cell['type'] == 'switch.Component':
                    data_obj['scaling_mode'] = db_record.mode
                    data_obj['inPorts'] = cell['inPorts']
                    data_obj['outPorts'] = cell['outPorts']
                    if 'parent' in cell:
                        data_obj['group'] = cell['parent']
                    if db_record.type == 'Component':
                        components.append(data_obj)
                    elif db_record.type == 'Network':
                        network.append(data_obj)
                    elif db_record.type == 'External Component':
                        external.append(data_obj)

                if cell['type'] == 'switch.Attribute':
                    data_obj['class'] = db_record.type
                    attributes.append(data_obj)

                if cell['type'] == 'switch.Group':
                    if 'embeds' in cell:
                        data_obj['members'] = cell['embeds']
                    groups.append(data_obj)

        data = {
            'data': {
                'components': components,
                'external_components': external,
                'network_components': network,
                'elements': attributes,
                'groups': groups
            }
        }

        return JsonResponse(data)


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

    @list_route(permission_classes=[])
    def latest(self, request, switchapps_pk=None, *args, **kwargs):
        graph = self.queryset.filter(app_id=switchapps_pk).latest('updated_at')
        serializer = self.get_serializer(graph)
        return Response(serializer.data)

    def put(self, request, switchapps_pk=None, **kwargs):
        json_data = request.data
        graph = self.queryset.filter(app_id=switchapps_pk).latest('updated_at')

        suffixes = ['second', 'first']
        suffixes_next = ['third', 'second']
        uuid = str(graph.app.uuid)

        if os.path.isfile(os.path.join(settings.BASE_DIR, 'graphs', uuid + '_third.json')):
            os.remove(os.path.join(settings.BASE_DIR, 'graphs', uuid + '_third.json'))

        for suffix in suffixes:
            for filename in os.listdir(os.path.join(settings.BASE_DIR, 'graphs')):
                if filename.startswith(uuid):
                    if filename.endswith(suffix + '.json'):
                        new_name = "%s_%s.json" % (uuid, suffixes_next[suffixes.index(suffix)])
                        os.rename(os.path.join(settings.BASE_DIR, 'graphs', filename),
                                  os.path.join(settings.BASE_DIR, 'graphs', new_name))

        for filename in os.listdir(os.path.join(settings.BASE_DIR, 'graphs')):
            if filename == uuid + '.json':
                os.rename(os.path.join(settings.BASE_DIR, 'graphs', filename),
                          os.path.join(settings.BASE_DIR, 'graphs', uuid + '_first.json'))

        graph.file.save(uuid + '.json', ContentFile(json.dumps(json_data)))
        graph.file.close()
        serializer = self.get_serializer(graph)
        return Response(serializer.data)


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
