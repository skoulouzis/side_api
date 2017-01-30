from rest_framework import viewsets
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_extensions.mixins import PaginateByMaxMixin

from api.models import *
from api.serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated


class ComponentTypeViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = ComponentTypeSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    queryset = ComponentType.objects.all()
    parser_classes = (JSONParser,)

    def get_queryset(self):
        is_core_component = self.request.query_params.get('is_core', None)
        is_template_component = self.request.query_params.get('is_template', None)
        queryset = ComponentType.objects.filter()

        if is_core_component is not None:
            queryset = queryset.filter(switch_class__is_core_component=is_core_component)
        elif is_template_component is not None:
            queryset = queryset.filter(switch_class__is_template_component=is_template_component)

        return queryset


class ComponentViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = ComponentSerializer

    def get_queryset(self):
        is_core_component = self.request.query_params.get('is_core_component', None)
        is_template_component = self.request.query_params.get('is_template_component', None)
        component_id = self.request.query_params.get('component_id', None)
        queryset = Component.objects.filter()

        if is_core_component is not None:
            queryset = queryset.filter(type__switch_class__is_core_component=is_core_component)
        elif is_template_component is not None:
            queryset = queryset.filter(type__switch_class__is_template_component=is_template_component)

        if component_id is not None:
            queryset = queryset.filter().exclude(pk=int(component_id))

        return queryset

    def perform_create(self, serializer):
        switch_type = ComponentType.objects.get(id=self.request.data['type']['id'])
        component = serializer.save(type=switch_type, user=self.request.user)

        instance = Instance.objects.create(graph=component, component=component, title=component.title,
                                           last_x=400, last_y=200, mode='single', properties=component.get_default_properties_value(),
                                           artifacts=component.get_default_artifacts_value())

        if component.type.switch_class.title == 'switch.Component' or component.type.switch_class.title == 'switch.Group':
            nested_component = NestedComponent(instance_ptr=instance)
            nested_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.VirtualResource' or component.type.switch_class.title == 'switch.Attribute':
            service_component = ServiceComponent(instance_ptr=instance)
            service_component.save_base(raw=True)

        elif component.type.switch_class.title == 'switch.ComponentLink':
            component_link = ComponentLink(instance_ptr=instance)
            component_link.save_base(raw=True)


class ComponentGraphView(PaginateByMaxMixin, APIView):
    """
    API endpoint that allows SwitchApps to be CRUDed.
    """
    serializer_class = ComponentSerializer
    authentication_classes = (TokenAuthentication,)
    # permission_classes = (IsAuthenticated, BelongsToUser,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def get(self, request, pk=None):
        component = Component.objects.filter(id=pk).first()
        return Response(component.get_graph())

    def post(self, request, pk=None):
        component = Component.objects.filter(id=pk).first()
        component.put_graph(request.data)
        return Response(component.get_graph())