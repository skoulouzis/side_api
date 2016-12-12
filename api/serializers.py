import json

from rest_framework import serializers
from models import Application, Component, ComponentType, Instance, NestedComponent, ServiceComponent, ComponentPort, \
    ServiceLink, GraphBase
from models import Application, Component, ComponentType, Instance, NestedComponent, ServiceComponent, SwitchDocument
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')


class ApplicationSerializer(serializers.ModelSerializer):
    visible = serializers.SerializerMethodField(read_only=True, required=False)
    editable = serializers.SerializerMethodField(read_only=True, required=False)
    belongs_to_user = serializers.SerializerMethodField(read_only=True, required=False)
    user = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = Application
        fields = ('id', 'uuid', 'title', 'description', 'user', 'public_view', 'public_editable',
                  'status', 'belongs_to_user', 'visible', 'editable')

    def get_visible(self, obj):
        return self.context['request'].user == obj.user or obj.public_editable or obj.public_view

    def get_editable(self, obj):
        return self.context['request'].user == obj.user or obj.public_editable

    def get_belongs_to_user(self, obj):
        return self.context['request'].user == obj.user


class ComponentSerializer(serializers.ModelSerializer):
    type = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    belongs_to_user = serializers.SerializerMethodField(read_only=True, required=False)
    editable = serializers.SerializerMethodField(read_only=True, required=False)

    class Meta:
        model = Component
        fields = ('id', 'title', 'type', 'editable', 'belongs_to_user', 'is_core_component', 'is_template_component')

    def get_belongs_to_user(self, obj):
        return self.context['request'].user == obj.user

    def get_editable(self, obj):
        return self.context['request'].user == obj.user


class ComponentTypeSerializer(serializers.ModelSerializer):
    switch_class = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    is_core_component = serializers.SerializerMethodField(read_only=True, required=False)
    is_template_component = serializers.SerializerMethodField(read_only=True, required=False)
    is_component_group = serializers.SerializerMethodField(read_only=True, required=False)
    classpath = serializers.SerializerMethodField(read_only=True, required=False)

    class Meta:
        model = ComponentType
        fields = ('id', 'title', 'primary_colour', 'secondary_colour', 'icon_name', 'icon_class', 'icon_style', 'icon_svg', 'icon_code', 'icon_colour', 'switch_class', 'is_core_component', 'is_template_component', 'is_component_group', 'classpath')

    def get_classpath(self, obj):
        return obj.computed_class()

    def get_is_template_component(self, obj):
        return obj.is_template()

    def get_is_core_component(self, obj):
        return obj.is_core()

    def get_is_component_group(self, obj):
        return obj.switch_class.title == 'switch.Group'


class InstanceSerializer(serializers.ModelSerializer):
    graph = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    component = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    ports = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    editable = serializers.SerializerMethodField(read_only=True, required=False)
    deleteable = serializers.SerializerMethodField(read_only=True, required=False)
    properties = serializers.CharField(allow_null=True)

    class Meta:
        model = Instance
        fields = ('id', 'uuid', 'title', 'mode', 'properties', 'graph', 'editable', 'deleteable', 'component', 'last_x', 'last_y', 'ports')

    def get_editable(self, obj):
        return self.context['request'].user == obj.graph.user

    def get_deleteable(self, obj):
        return obj.graph.pk != obj.component.pk

    def create(self, validated_data):
        uuid = validated_data.get('uuid', None)
        graph = validated_data.get('graph', None)
        if uuid is not None:
            instance = Instance.objects.filter(uuid=uuid, graph=graph).first()
            if instance is not None:
                return instance

        instance = Instance.objects.create(**validated_data)
        return instance


class SwitchDocumentSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    belongs_to_user = serializers.SerializerMethodField(read_only=True, required=False)

    class Meta:
        model = SwitchDocument
        fields = ('id', 'description', 'file', 'user', 'belongs_to_user')

    def get_belongs_to_user(self, obj):
        return self.context['request'].user == obj.user


class GraphSerializer(serializers.ModelSerializer):

    class Meta:
        model = GraphBase
        fields = ('id', 'title')


class PortSerializer(serializers.ModelSerializer):
    instance = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = ComponentPort
        fields = ('id', 'instance', 'type', 'title', 'uuid')


class ServiceLinkSerializer(serializers.ModelSerializer):
    graph = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    source = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    target = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = ServiceLink
        fields = ('id', 'graph', 'source', 'target', 'uuid')
