import json

from rest_framework import serializers

from api.models import ComponentTypeProperty, ComponentPort
from models import Application, Component, ComponentType, ComponentInstance, NestedComponent, ServiceComponent, ComponentPort, ServiceLink, GraphBase,SwitchDocument, \
    ApplicationInstance, Notification, SwitchDocumentType, DependencyLink, SwitchArtifact, SwitchRepository, ToscaClass, \
    ComponentClass, DataType, DataTypeProperty, DRIPIDs
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('graph', 'nType', 'title', 'message', 'created_at', 'severity', 'viewed')


class ApplicationSerializer(serializers.ModelSerializer):
    visible = serializers.SerializerMethodField(read_only=True, required=False)
    editable = serializers.SerializerMethodField(read_only=True, required=False)
    belongs_to_user = serializers.SerializerMethodField(read_only=True, required=False)
    user = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    notifications = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    unread_notifications = serializers.SerializerMethodField(read_only=True, required=False)

    class Meta:
        model = Application
        fields = ('id', 'uuid', 'title', 'description', 'user', 'public_view', 'public_editable',
                  'status', 'belongs_to_user', 'visible', 'editable', 'notifications', 'unread_notifications')

    def get_visible(self, obj):
        return self.context['request'].user == obj.user or obj.public_editable or obj.public_view

    def get_editable(self, obj):
        return self.context['request'].user == obj.user or obj.public_editable

    def get_belongs_to_user(self, obj):
        return self.context['request'].user == obj.user

    def get_unread_notifications(self, obj):
        qs = Notification.objects.filter(graph__id=obj.pk, viewed=False)
        return len(qs)


class ApplicationInstanceSerializer(serializers.ModelSerializer):
    belongs_to_user = serializers.SerializerMethodField(read_only=True, required=False)
    notifications = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    unread_notifications = serializers.SerializerMethodField(read_only=True, required=False)

    class Meta:
        model = ApplicationInstance
        fields = ('id', 'title', 'status', 'belongs_to_user', 'created_at', 'notifications', 'unread_notifications')

    def get_belongs_to_user(self, obj):
        return self.context['request'].user == obj.application.user

    def get_unread_notifications(self, obj):
        qs = Notification.objects.filter(graph__id=obj.pk, viewed=False)
        return len(qs)


class ComponentSerializer(serializers.ModelSerializer):
    type = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    belongs_to_user = serializers.SerializerMethodField(read_only=True, required=False)
    editable = serializers.SerializerMethodField(read_only=True, required=False)
    is_deletable = serializers.SerializerMethodField(read_only=True, required=False)

    class Meta:
        model = Component
        fields = ('id', 'title', 'type', 'editable', 'is_deletable', 'belongs_to_user', 'is_core_component', 'is_template_component')

    def get_belongs_to_user(self, obj):
        return self.context['request'].user == obj.user

    def get_editable(self, obj):
        return self.context['request'].user == obj.user

    def get_is_deletable(self, obj):
        return obj.pk != obj.type.pk


class ComponentTypeSerializer(serializers.ModelSerializer):
    switch_class = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    is_component_group = serializers.SerializerMethodField(read_only=True, required=False)
    classpath = serializers.SerializerMethodField(read_only=True, required=False)
    parent = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    artifacts = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    properties = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = ComponentType
        fields = ('id', 'title', 'primary_colour', 'secondary_colour', 'icon_name', 'icon_class', 'icon_style',
                  'icon_svg', 'icon_code', 'icon_colour', 'switch_class', 'is_core', 'is_template', 'is_concrete',
                  'is_component_group', 'classpath', 'parent', 'artifacts', 'properties')

    def create(self, validated_data):
        obj = ComponentType.objects.create(**validated_data)
        parent_id = self.initial_data['parent_id']
        switch_class_id = self.initial_data['switch_class_id']
        classpath  = self.initial_data['classpath']
        classpath = classpath.rsplit('.', 1)
        parent_tosca = ToscaClass.objects.get(id=5)
        tosca_class, created = ToscaClass.objects.get_or_create(type='N', is_normative=False, prefix=classpath[0], parent=parent_tosca, name=classpath[1])
        obj.parent = ComponentType.objects.get(id=parent_id)
        obj.switch_class = ComponentClass.objects.get(id=switch_class_id)
        obj.tosca_class = tosca_class
        obj.save()
        return obj

    def get_classpath(self, obj):
        return obj.computed_class()

    def get_is_component_group(self, obj):
        return obj.switch_class.title == 'switch.Group'


class ComponentClassSerializer(serializers.ModelSerializer):

    class Meta:
        model = ComponentType
        fields = ('id', 'title')


class PortSerializer(serializers.ModelSerializer):
    instance = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = ComponentPort
        fields = ('instance', 'type', 'title', 'uuid')


class InstanceSerializer(serializers.ModelSerializer):
    graph = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    component = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    ports = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    editable = serializers.SerializerMethodField(read_only=True, required=False)
    deleteable = serializers.SerializerMethodField(read_only=True, required=False)
    properties = serializers.CharField(allow_blank=True)
    artifacts = serializers.CharField(allow_blank=True)

    class Meta:
        model = ComponentInstance
        fields = ('id', 'title', 'uuid', 'mode', 'properties', 'artifacts', 'graph', 'editable', 'deleteable', 'component', 'last_x', 'last_y', 'ports')


    def get_editable(self, obj):
        return self.context['request'].user == obj.graph.user

    def get_deleteable(self, obj):
        return obj.graph.pk != obj.component.pk

    # def get_included(self, obj):
    #     component_instance_id = obj.id
    #     ports = ComponentPort.objects.filter(instance=component_instance_id)
    #     ports_data = []
    #     for port in ports:
    #         port_data = {
    #             'type': 'switchcomponentports',
    #             'id': port.id.__str__(),
    #             'attributes': {
    #                 'id': port.id.__str__(),
    #                 'type': port.type,
    #                 'uuid': port.uuid,
    #                 'title': port.title,
    #                 'instance': port.instance.id
    #                 }
    #         }
    #         ports_data.append(port_data)
    #     return ports_data

    def create(self, validated_data):
        uuid = validated_data.get('uuid', None)
        graph = validated_data.get('graph', None)
        if uuid is not None:
            instance = ComponentInstance.objects.filter(uuid=uuid, graph=graph).first()
            if instance is not None:
                return instance

        instance = ComponentInstance.objects.create(**validated_data)
        return instance


class SwitchDocumentSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    belongs_to_user = serializers.SerializerMethodField(read_only=True, required=False)
    document_type = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = SwitchDocument
        fields = ('id', 'description', 'file', 'document_type', 'user', 'belongs_to_user')

    def get_belongs_to_user(self, obj):
        return self.context['request'].user == obj.user


class SwitchDocumentTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = SwitchDocumentType
        fields = ('id', 'name', 'description')


class SwitchArtifactSerializer(serializers.ModelSerializer):
    repository = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = SwitchArtifact
        fields = ('id', 'name', 'file', 'repository')

    def create(self, validated_data):
        obj = SwitchArtifact.objects.create(**validated_data)
        obj.repository = SwitchRepository.objects.get(id=1)
        obj.type = ToscaClass.objects.get(id=21)
        obj.save()

        if 'bound_to' in self.initial_data:
            bound_to = self.initial_data['bound_to']
            parent = ComponentType.objects.get(id=bound_to)
            parent.artifacts.add(obj)
            parent.save()

        return obj


class SwitchRepositorySerializer(serializers.ModelSerializer):

    class Meta:
        model = SwitchRepository
        fields = ('id', 'name', 'description', 'url', 'credential')


class GraphSerializer(serializers.ModelSerializer):

    class Meta:
        model = GraphBase
        fields = ('id', 'title')


class ServiceLinkSerializer(serializers.ModelSerializer):
    graph = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    source = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    target = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = ServiceLink
        fields = ('id', 'graph', 'source', 'target', 'uuid')


class DependencyLinkSerializer(serializers.ModelSerializer):
    graph = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    dependant = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    dependency = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = DependencyLink
        fields = ('id', 'graph', 'dependant', 'dependency', 'uuid')


class ComponentTypePropertySerializer(serializers.ModelSerializer):
    component_type = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    data_type = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = ComponentTypeProperty
        fields = ('id', 'name', 'default_value', 'required', 'component_type', 'collection_type', 'data_type')


class DataTypeSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    properties = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = DataType
        fields = ('id', 'name', 'default_value', 'parent', 'properties')


class DataTypePropertySerializer(serializers.ModelSerializer):
    data_type = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    parent_data_type = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = DataTypeProperty
        fields = ('id', 'name', 'default_value', 'required', 'data_type', 'collection_type', 'parent_data_type')


class DRIPIDSerializer(serializers.ModelSerializer):

    class Meta:
        model = DRIPIDs
        fields = ('application', 'tosca_ID', 'plan_ID', 'provision_ID', 'deployment_ID')
