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
from models import *
from serializers import *
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
                properties = {}
                # data_obj['id'] = db_record.id
                properties['title'] = db_record.title
                # data_obj['uuid'] = cell['id']

                if 'enter metadata as YAML' not in db_record.properties:
                    metadata = yaml.load(str(db_record.properties).replace("\t","    "))
                    properties.update(metadata)

                if cell['type'] == 'switch.Component':
                    properties['scaling_mode'] = db_record.mode
                    properties['inPorts'] = cell['inPorts']
                    properties['outPorts'] = cell['outPorts']
                    if 'parent' in cell:
                        properties['group'] = cell['parent']

                    data_obj[cell['id']] = properties

                    if db_record.type == 'Component':
                        components.append(data_obj)
                    elif db_record.type == 'Network':
                        network.append(data_obj)
                    elif db_record.type == 'External Component':
                        external.append(data_obj)

                if cell['type'] == 'switch.Attribute':
                    properties['class'] = db_record.type

                    data_obj[cell['id']] = properties
                    attributes.append(data_obj)

                if cell['type'] == 'switch.Group':
                    if 'embeds' in cell:
                        properties['members'] = cell['embeds']

                    data_obj[cell['id']] = properties
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
    def generated(self, request, switchapps_pk=None, *args, **kwargs):
        components = SwitchAppGraphBase.objects.filter(component__app_id=switchapps_pk).all()

        graph_components = []
        graph_groups = []
        graph_links = []
        graph_attributes = []
        graph_services = []

        response_cells = []

        for cell in components:
            try:
                graph_obj = {'type': cell.type,
                             'position': {},
                             'attrs': {},
                             'inPorts': [],
                             'outPorts': []}
                graph_obj['position']['x'] = cell.last_x
                graph_obj['position']['y'] = cell.last_y

                component = cell.component
                graph_obj['id'] = component.uuid
                graph_obj['attrs']['switch_class'] = component.type
                graph_obj['attrs']['switch_title'] = component.title
                graph_obj['attrs']['switch_type'] = component.title
                graph_obj['attrs']['.label'] = {"html": component.title, "fill": "#333"}

                if component.switch_type is None:
                    switch_type = SwitchComponentType.objects.filter(title=component.type).first()
                    if switch_type is not None:
                        component.switch_type = switch_type
                        component.save()

                if component.switch_type is not None:
                    graph_obj['attrs']['.icon'] = {"d": component.switch_type.icon_svg, "fill": component.switch_type.icon_colour}

                    if cell.type == 'switch.Component':
                        inPorts = SwitchAppGraphPort.objects.filter(graph_component=cell, type='in').all()
                        outPorts = SwitchAppGraphPort.objects.filter(graph_component=cell, type='out').all()
                        stroke_opacity = ".0"
                        fill_opacity = ".0"

                        if component.mode != 'single':
                            stroke_opacity = "1"
                            fill_opacity = ".95"

                        graph_obj['attrs']['.body'] = {
                                        "fill": component.switch_type.primary_colour,
                                        "stroke-width": 1,
                                        "rx": 4,
                                        "ry": 4,
                                        "fill-opacity": "1"
                                    }
                        graph_obj['attrs']['.multi'] = {
                                        "stroke-opacity": stroke_opacity,
                                        "fill-opacity": fill_opacity,
                                        "rx": 4,
                                        "ry": 4,
                                        "stroke-width": 1,
                                        "fill": component.switch_type.secondary_colour
                                    }
                        graph_obj['attrs']['.multi2'] = {
                                        "stroke-opacity": stroke_opacity,
                                        "fill-opacity": fill_opacity,
                                        "rx": 4,
                                        "ry": 4,
                                        "stroke-width": 1,
                                        "fill": component.switch_type.secondary_colour
                                    }

                        if len(inPorts) > 0:
                            gap = 100 / (len(inPorts) * 2)
                            portlen = 0

                            for port in inPorts:
                                graph_obj['inPorts'].append(port.title)
                                key = '.inPorts>.port%s' % str(portlen)
                                ref_y = (portlen * 2 * gap) + gap
                                portlen += 1
                                graph_obj['attrs'][key] = {'ref': '.body', 'ref-y': ref_y}
                                graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                                graph_obj['attrs'][key + '>.port-body'] = {'type': 'in', 'id': port.title}

                        if len(outPorts) > 0:
                            gap = 100 / (len(outPorts) * 2)
                            portlen = 0

                            for port in outPorts:
                                graph_obj['outPorts'].append(port.title)
                                key = '.outPorts>.port%s' % str(portlen)
                                ref_y = (portlen * 2 * gap) + gap
                                portlen += 1
                                graph_obj['attrs'][key] = {'ref': '.body', 'ref-dx': 0, 'ref-y': ref_y}
                                graph_obj['attrs'][key + '>.port-label'] = {'text': port.title}
                                graph_obj['attrs'][key + '>.port-body'] = {'type': 'in', 'id': port.title}

                        height = len(inPorts) if len(inPorts) > len(outPorts) else len(outPorts)
                        if height < 2:
                            height = 30
                        else:
                            height *= 25

                        graph_component = SwitchAppGraphComponent.objects.filter(id=cell.id).first()

                        if graph_component.parent is not None:
                            graph_obj['parent'] = graph_component.parent.component.uuid

                        graph_obj['size'] = {"width": 100, "height": height}
                        response_cells.append(graph_obj)
                    elif cell.type == 'switch.Group':
                        graph_groups.append(cell)
                        graph_obj['embeds'] = []

                        graph_component = SwitchAppGraphComponent.objects.filter(id=cell.id).first()

                        for child in graph_component.children.all():
                            graph_obj['embeds'].append(child.component.uuid)

                        response_cells.append(graph_obj)
                    elif cell.type == 'switch.Attribute':
                        graph_obj['attrs']['.body'] = {
                                        "fill": component.switch_type.primary_colour,
                                        "stroke": component.switch_type.secondary_colour,
                                        "stroke-width": 2,
                                        "fill-opacity": ".95"
                                    }

                        graph_attributes.append(cell)
                        graph_obj['size'] = {"width": 30, "height": 30}
                        response_cells.append(graph_obj)
                    elif cell.type == 'switch.Service':
                        graph_obj['attrs']['.body'] = {
                                        "fill": component.switch_type.primary_colour,
                                        "stroke": component.switch_type.secondary_colour,
                                        "stroke-width": 2,
                                        "fill-opacity": ".95"
                                    }

                        graph_services.append(cell)
                        graph_obj['size'] = {"width": 35, "height": 35}
                        response_cells.append(graph_obj)

                if cell.type == 'switch.ComponentLink':
                    graph_obj = {'type': 'link', 'id': component.uuid, 'attrs': {}, "embeds": ""}
                    graph_obj['attrs']['switch_class'] = component.type
                    graph_obj['attrs']['switch_title'] = component.title
                    graph_component = SwitchAppGraphComponentLink.objects.filter(id=cell.id).first()
                    graph_obj['target'] = {
                        "port": graph_component.target.title,
                        "id": graph_component.target.graph_component.component.uuid
                    }
                    graph_obj['source'] = {
                        "port": graph_component.source.title,
                        "id": graph_component.source.graph_component.component.uuid
                    }

                    if graph_component.source.graph_component.component.mode == 'onetomany':
                        source_text = '1..*'
                        source_rect = 'white'
                    elif graph_component.source.graph_component.component.mode == 'zerotomany':
                        source_text = '0..*'
                        source_rect = 'white'
                    else:
                        source_text = ''
                        source_rect = 'none'

                    if graph_component.target.graph_component.component.mode == 'onetomany':
                        target_text = '1..*'
                        target_rect = 'white'
                    elif graph_component.target.graph_component.component.mode == 'zerotomany':
                        target_text = '0..*'
                        target_rect = 'white'
                    else:
                        target_text = ''
                        target_rect = 'none'

                    graph_obj['labels'] = [
                            {
                                "position": 0.2,
                                "attrs": {
                                    "text": {
                                        "text": source_text,
                                        "fill": "black"
                                    },
                                    "rect": {
                                        "fill": source_rect
                                    }
                                }
                            },
                            {
                                "position": 0.8,
                                "attrs": {
                                    "text": {
                                        "text": target_text,
                                        "fill": "black"
                                    },
                                    "rect": {
                                        "fill": target_rect
                                    }
                                }
                            },
                            {
                                "position": 0.5,
                                "attrs": {
                                    "text": {
                                        "text": graph_component.component.title,
                                        "fill": "black"
                                    },
                                    "rect": {
                                        "fill": "white"
                                    }
                                }
                            }
                        ]

                    graph_links.append(cell)
                    response_cells.append(graph_obj)


            except Exception as e:
                print e.message

        service_links = SwitchAppGraphServiceLink.objects.filter(source__component__app_id=switchapps_pk).all()
        for cell in service_links:
            try:
                graph_obj = {'type': 'link', 'attrs': {
                    ".marker-target": {
                        "stroke": "#4b4a67",
                        "d": "M 10 0 L 0 5 L 10 10 z",
                        "fill": "#4b4a67"
                    }
                }, 'target': {
                    "id": cell.target.component.uuid
                }, 'source': {
                    "id": cell.source.component.uuid
                }}

                if cell.target.component.mode == 'onetomany':
                    target_text = '1..*'
                    target_rect = 'white'
                elif cell.target.component.mode == 'zerotomany':
                    target_text = '0..*'
                    target_rect = 'white'
                else:
                    target_text = ''
                    target_rect = 'none'

                graph_obj['labels'] = [
                        {
                            "position": 0.2,
                            "attrs": {
                                "text": {
                                    "text": "",
                                    "fill": "black"
                                },
                                "rect": {
                                    "fill": "none"
                                }
                            }
                        },
                        {
                            "position": 0.8,
                            "attrs": {
                                "text": {
                                    "text": target_text,
                                    "fill": "black"
                                },
                                "rect": {
                                    "fill": target_rect
                                }
                            }
                        }
                    ]

                graph_links.append(cell)
                response_cells.append(graph_obj)


            except Exception as e:
                print e.message

        return Response({
                'type': 'graphs',
                'id': str(switchapps_pk),
                'attributes': {
                    'graph': {
                        'cells': response_cells
                    }
                }
            })

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

        try:
            graph_components = []
            graph_groups = []
            graph_links = []
            graph_attributes = []
            graph_services = []

            for cell in json_data['cells']:
                if cell['type'] == 'switch.Component':
                    graph_components.append(cell)
                elif cell['type'] == 'switch.Group':
                    graph_groups.append(cell)
                elif cell['type'] == 'switch.Attribute':
                    graph_attributes.append(cell)
                elif cell['type'] == 'switch.Service':
                    graph_services.append(cell)
                elif cell['type'] == 'link':
                    graph_links.append(cell)

            for cell in graph_groups:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphComponent.objects.get_or_create(component=component, type='switch.Group')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

            for cell in graph_attributes:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphService.objects.get_or_create(component=component, type='switch.Attribute')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

            for cell in graph_services:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphService.objects.get_or_create(component=component, type='switch.Service')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

            for cell in graph_components:
                component = SwitchComponent.objects.filter(uuid=cell['id'], app_id=switchapps_pk).first()
                if component is not None:
                    graph_obj, created = SwitchAppGraphComponent.objects.get_or_create(component=component, type='switch.Component')
                    graph_obj.last_x = cell['position']['x']
                    graph_obj.last_y = cell['position']['y']
                    graph_obj.save()

                    port_objs = []

                    if 'parent' in cell:
                        parent = SwitchComponent.objects.filter(uuid=cell['parent'], app_id=switchapps_pk).first()
                        parent_obj, created = SwitchAppGraphComponent.objects.get_or_create(component=parent)
                        graph_obj.parent = parent_obj

                    if 'inPorts' in cell:
                        for port in cell['inPorts']:
                            port_obj, created = SwitchAppGraphPort.objects.get_or_create(graph_component=graph_obj, type='in', title=port)
                            port_objs.append(port_obj)

                        graph_obj.ports = port_objs

                    if 'outPorts' in cell:
                        for port in cell['outPorts']:
                            port_obj, created = SwitchAppGraphPort.objects.get_or_create(graph_component=graph_obj, type='out', title=port)
                            port_objs.append(port_obj)

                        graph_obj.ports = port_objs

                    old_port_objs = SwitchAppGraphPort.objects.filter(graph_component=graph_obj)
                    for old_port in old_port_objs:
                        if old_port not in port_objs:
                            old_port.delete()

                    graph_obj.save()

            for obj in SwitchAppGraphServiceLink.objects.filter(source__component__app_id=switchapps_pk).all():
                obj.delete()

            for cell in graph_links:
                is_connection = False
                graph_obj = None
                source_obj = None
                target_obj = None

                if 'source' in cell:
                    source = cell['source']
                    component = SwitchComponent.objects.filter(uuid=source['id'], app_id=switchapps_pk).first()
                    if component is not None:
                        if 'port' in source:
                            is_connection = True
                            source_obj, created = SwitchAppGraphPort.objects.get_or_create(graph_component__component=component, type='out', title=source['port'])
                        else:
                            source_obj, created = SwitchAppGraphBase.objects.get_or_create(component=component)

                if 'target' in cell:
                    target = cell['target']
                    component = SwitchComponent.objects.filter(uuid=target['id'], app_id=switchapps_pk).first()
                    if component is not None:
                        if 'port' in target:
                            is_connection = True
                            target_obj, created = SwitchAppGraphPort.objects.get_or_create(graph_component__component=component, type='in', title=target['port'])
                        else:
                            target_obj, created = SwitchAppGraphBase.objects.get_or_create(component=component)

                if is_connection:
                    component, created = SwitchComponent.objects.get_or_create(uuid=cell['id'], app_id=switchapps_pk)
                    if created:
                        component.title = 'connection'
                        component.type = 'ComponentLink'
                        component.save()

                    if component is not None:
                        graph_obj, created = SwitchAppGraphComponentLink.objects.get_or_create(component=component, source=source_obj, target=target_obj, type='switch.ComponentLink')
                else:
                    graph_obj, created = SwitchAppGraphServiceLink.objects.get_or_create(source=source_obj, target=target_obj)

                # print graph_obj
        except Exception as e:
            print e.message

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
