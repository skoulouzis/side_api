from rest_framework import viewsets
from rest_framework.decorators import detail_route
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework_extensions.mixins import PaginateByMaxMixin

from api.models import *
from api.serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated


class GraphViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = GraphSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    queryset = GraphBase.objects.all()


class InstanceViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = InstanceSerializer

    @detail_route(methods=['post'])
    def link(self, request, pk=None):
        graph_id = request.data.get('graph_id', None)
        source_id = request.data.get('source_id', None)
        target_id = request.data.get('target_id', None)
        link = ComponentLink.objects.filter(pk=pk).first()
        source = ComponentPort.objects.filter(uuid=source_id, instance__graph_id=graph_id).first()
        target = ComponentPort.objects.filter(uuid=target_id, instance__graph_id=graph_id).first()
        link.source = source
        link.target = target
        link.save()
        serializer = self.get_serializer(link, many=False)
        return Response(serializer.data)

    @detail_route(methods=['post'])
    def embed(self, request, pk=None):
        graph_id = request.data.get('graph_id', None)
        parent_id = request.data.get('parent_id', None)
        child = NestedComponent.objects.filter(pk=pk).first()
        child.parent = NestedComponent.objects.filter(uuid=parent_id, instance__graph_id=graph_id).first()
        child.save()
        serializer = self.get_serializer(child, many=False)
        return Response(serializer.data)

    @detail_route(methods=['post'], parser_classes=(JSONParser,))
    def ports(self, request, pk=None):

        new_ports = request.data.get('ports', [])
        instance = Instance.objects.filter(pk=pk).first()

        old_ports = list(ComponentPort.objects.filter(instance=instance).all())
        for port in old_ports:
            for new_port in new_ports:
                if port.uuid == new_port['id']:
                    port.title = new_port['label']
                    port.type = new_port['type']
                    port.save()
                    new_ports.remove(new_port)
                    old_ports.remove(port)
                    break

        for port in old_ports:
            port.delete()

        for port in new_ports:
            ComponentPort.objects.create(uuid=port['id'], title=port['label'], type=port['type'], instance=instance)

        serializer = self.get_serializer(instance, many=False)
        return Response(serializer.data)

    def get_queryset(self):
        graph_id = self.request.query_params.get('graph_id', None)
        uuid = self.request.query_params.get('uuid', None)
        if graph_id is not None:
            queryset = Instance.objects.filter(graph_id=graph_id)
            if uuid is not None:
                queryset = Instance.objects.filter(graph_id=graph_id, uuid=uuid)
        else:
            queryset = Instance.objects.filter()
        return queryset

    def perform_destroy(self, instance):
        target_links = ServiceLink.objects.filter(target_id=instance.id).all()
        for link in target_links:
            source = link.source
            source_links = ServiceLink.objects.filter(source_id=source.id).all()
            if source_links.count() <= 1:
                if source.id is not None:
                    source.delete()
        instance.delete()

    def perform_create(self, serializer):
        graph = GraphBase.objects.filter(id=self.request.data['graph_id']).first()
        component = Component.objects.filter(id=self.request.data['component_id']).first()

        base_instance = component.get_base_instance()

        new_instance = serializer.save(graph=graph, component=component, properties=base_instance.properties,
                                       artifacts=base_instance.artifacts)
        new_instance.save()

        x_change = base_instance.last_x - new_instance.last_x
        y_change = base_instance.last_y - new_instance.last_y

        component.clone_instances_in_graph(graph, x_change, y_change, new_instance)


class PortViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = PortSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    queryset = ComponentPort.objects.all()

    def perform_create(self, serializer):
        instance = dict(self.request.data.get('instance', None))
        if 'id' in instance:
            port = serializer.save(instance_id=instance['id'])


class ServiceLinkViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = ServiceLinkSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    queryset = ServiceLink.objects.all()

    def get_queryset(self):
        graph_id = self.request.query_params.get('graph_id', None)
        uuid = self.request.query_params.get('uuid', None)
        if graph_id is not None:
            queryset = ServiceLink.objects.filter(graph_id=graph_id)
            if uuid is not None:
                queryset = ServiceLink.objects.filter(graph_id=graph_id, uuid=uuid)
        else:
            queryset = ServiceLink.objects.filter(graph__user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        graph = dict(self.request.data.get('graph', None))
        source = dict(self.request.data.get('source', None))
        target = dict(self.request.data.get('target', None))
        if 'id' in graph and 'id' in source and 'id' in target:
            port = serializer.save(graph_id=graph['id'], source_id=source['id'], target_id=target['id'])
