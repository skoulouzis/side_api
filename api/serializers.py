from rest_framework import serializers
from models import TodoItem
from django.contrib.auth.models import User


class TodoItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TodoItem
        fields = ('label', 'text', 'done')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')