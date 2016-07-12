from rest_framework import viewsets
from rest_framework.decorators import list_route
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.filters import DjangoFilterBackend, SearchFilter

from api.permissions import BelongsToUser
from models import TodoItem
from serializers import TodoItemSerializer, UserSerializer
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


class UserViewSet(viewsets.ModelViewSet):
    serialdizer_class = UserSerializer
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
        return Response(serializer.ata)