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
    # authentication_classes = (TokenAuthentication,)
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

        drip_manager_response = drip_manager_service.register(request.user)

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
    # permission_classes = (IsAuthenticated, )
    # authentication_classes = (TokenAuthentication,)
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
    #authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated,)
    queryset = SwitchDocumentType.objects.all()
    parser_classes = (JSONParser,)


class SwitchArtifactViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    #authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated, )
    serializer_class = SwitchArtifactSerializer
    queryset = SwitchArtifact.objects.all()


class SwitchRepositoryViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    #authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated, )
    serializer_class = SwitchRepositorySerializer
    queryset = SwitchRepository.objects.all()


class NotificationViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    #authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated, )
    serializer_class = NotificationSerializer
    notification_class = Notification
    queryset = Notification.objects.all()

    def list(self, request, **kwargs):
        documents = Notification.objects.filter()
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        return Notification.objects.filter()

    def perform_create(self, serializer):
        #  document_type = SwitchDocumentType.objects.get(pk=self.request.data['document_type_id'])
        #  document = serializer.save() #user=self.request.user, document_type=document_type)
        return Response(serializer.data)

    @list_route(methods=['post'], permission_classes=[])
    def new(self, request, pk=None, *args, **kwargs):
        #requestJSON = JSONParser().parse(request.data)
        app = GraphBase.objects.filter(pk=self.request.data['appID']).first()
        notification = Notification.objects.first()
        notification.graph = app
        notification.title = self.request.data['title']
        notification.nType = self.request.data['nType']
        notification.message = self.request.data['message']
        notification.severity = self.request.data['severity']
        notification.id = None
        notification.pk = None
        response = NotificationSerializer(notification)
        notification.save()

        # document_type = SwitchDocumentType.objects.get(pk=self.request.data['document_type_id'])
        # document = notification.save() #user=self.request.user, document_type=document_type)

        return JsonResponse(response.data)


class SwitchDataTypeViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    #authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated, )
    serializer_class = DataTypeSerializer
    queryset = DataType.objects.all()


class SwitchDataTypePropertyViewSet(PaginateByMaxMixin, viewsets.ModelViewSet):
    #authentication_classes = (TokenAuthentication,)
    #permission_classes = (IsAuthenticated, )
    serializer_class = DataTypePropertySerializer
    queryset = DataTypeProperty.objects.all()