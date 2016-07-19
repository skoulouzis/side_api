import json

from rest_framework import serializers
from models import TodoItem, SwitchApp, SwitchAppGraph
from django.contrib.auth.models import User


class TodoItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TodoItem
        fields = ('label', 'text', 'done')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')


class SwitchAppSerializer(serializers.ModelSerializer):
    class Meta:
        model = SwitchApp
        fields = ('id', 'uuid', 'title', 'description', 'graphs')


class SwitchAppGraphSerializer(serializers.ModelSerializer):
    graph = serializers.SerializerMethodField()

    class Meta:
        model = SwitchAppGraph
        fields = ('id', 'created_at', 'updated_at', 'graph')

    def get_graph(self, obj):
        return json.loads(obj.file.read())