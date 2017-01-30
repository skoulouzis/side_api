from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import list_route, detail_route
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.filters import DjangoFilterBackend, SearchFilter
from rest_framework_extensions.mixins import PaginateByMaxMixin

from api.models import *
from api.serializers import *
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from side_api import utils
from api.services import DripManagerService


class UserViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
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

    @detail_route(methods=['post'], permission_classes=[])
    def configureEC2account(self, request, pk=None, *args, **kwargs):
        drip_manager_service = DripManagerService(utils.getPropertyFromConfigFile("DRIP_MANAGER_API", "url"))

        aws_root_key_document = SwitchDocument.objects.filter(user=request.user, document_type=SwitchDocumentType.objects.get(name="AWS_ROOT_KEY")).first()
        california_key_document = SwitchDocument.objects.filter(user=request.user, document_type=SwitchDocumentType.objects.get(name="AWS_California_Key")).first()
        virginia_key_document = SwitchDocument.objects.filter(user=request.user, document_type=SwitchDocumentType.objects.get(name="AWS_Virginia_Key")).first()

        details = []

        if aws_root_key_document and california_key_document and virginia_key_document:
            drip_manager_response = drip_manager_service.configure_ec2_account(request.user, aws_root_key_document,
                                                                california_key_document, virginia_key_document)
            if drip_manager_response.status_code == 200:
                result = 'ok'
                details.append(drip_manager_response.text)
            else:
                result = 'error'
                details.append(drip_manager_response.text)
        else:
            result = 'error'
            details.append('Please make sure you to upload files for: AWS root key, california key and virginia key into the system')


        validation_result = {
            'result': result,
            'details': details
        }

        return JsonResponse(validation_result)


class SwitchDocumentViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated, )
    serializer_class = SwitchDocumentSerializer
    queryset = SwitchDocument.objects.all()
    parser_classes = (JSONParser,FormParser,MultiPartParser,)

    def list(self, request, **kwargs):
        documents = SwitchDocument.objects.filter()
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return SwitchDocument.objects.filter()

    def perform_create(self, serializer):
        document_type = SwitchDocumentType.objects.get(pk=self.request.data['document_type_id'])
        document = serializer.save(user=self.request.user, document_type=document_type)


class SwitchDocumentTypeViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    serializer_class = SwitchDocumentTypeSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    queryset = SwitchDocumentType.objects.all()
    parser_classes = (JSONParser,)


class NotificationViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    #authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated, )
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()

    def list(self, request, **kwargs):
        documents = Notification.objects.filter()
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return Notification.objects.filter()