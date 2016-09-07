import json

from rest_framework import serializers
from models import SwitchApp, SwitchAppGraph, SwitchComponent
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')


class SwitchAppSerializer(serializers.ModelSerializer):
    editable = serializers.SerializerMethodField(read_only=True, required=False)
    user = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = SwitchApp
        fields = ('id', 'uuid', 'title', 'description', 'user', 'editable')

    def get_editable(self, obj):
        return self.context['request'].user == obj.user

class SwitchComponentSerializer(serializers.ModelSerializer):
    app = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    editable = serializers.SerializerMethodField(read_only=True, required=False)
    properties = serializers.CharField(allow_null=True)

    class Meta:
        model = SwitchComponent
        fields = ('id', 'uuid', 'title', 'type', 'mode', 'properties', 'app', 'editable')

    def get_editable(self, obj):
        return self.context['request'].user == obj.app.user


class SwitchAppGraphSerializer(serializers.ModelSerializer):
    graph = serializers.SerializerMethodField()

    class Meta:
        model = SwitchAppGraph
        fields = ('id', 'created_at', 'updated_at', 'graph')

    def get_graph(self, obj):
        obj.file.open()
        response = json.loads(obj.file.read())
        obj.file.close()
        return response
