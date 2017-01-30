from django.test import TestCase
from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

import uuid
import json

from django.contrib.auth.models import User
from models import *
from serializers import *


# Create your tests here.
class ModelMethodTests(TestCase):

    def setUp(self):
        self.test_user = User.objects.create_user(username='test_user', email='testuser@test.com', password='testing')

    def tearDown(self):
        self.test_user.delete()

    def test_app_creation_it_does_not_create_app_graph_automatically(self):
        app = SwitchApp.objects.create(user=self.test_user, title='test_app', uuid=uuid.uuid4(), description='test app',
                                       public_view=True, public_editable=True, status=0)

        appGraph = SwitchComponent.objects.filter(app_id=app.id).first()
        self.assertIs(appGraph is None, True)


class ViewMethodTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.test_user = self.createUser('test_user', 'testuser@test.com', 'testing')

    def tearDown(self):
        self.deleteUser(self.test_user.username)

    def createUser(self,username,email,password):
        user = User.objects.create_user(username=username, email=email, password=password)
        Token.objects.create(user=user)
        return user

    def deleteUser(self,username):
        user = User.objects.get(username=username)
        token = Token.objects.get(user__username=username)
        token.delete()
        user.delete()

    def require_authorization(self, user):
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

    def test_switchapps_list_view_with_no_apps(self):
        token = Token.objects.get(user__username='test_user')
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

        response = self.client.get(reverse('switchapps-list'))

        self.assertEqual(response.status_code, 200)


    def test_switchapp_create_view(self):
        """
        Ensure we can create a new application object.
        """
        self.require_authorization(self.test_user)

        data = {"data":{"attributes": {"title": "test_app", "description": "test app", "uuid": 'null', "visible": 'false',
                               "editable": 'false', "belongs_to_user": 'false', "public_view": 'true',
                               "public_editable": 'true', "status": '0'},
                  "relationships": {"user": {"data": 'null'}}, "type": "switchapps"}}

        response = self.client.post(reverse('switchapps-list'),  json.dumps(data), content_type="application/vnd.api+json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SwitchApp.objects.count(), 1)
        self.assertEqual(SwitchApp.objects.get().title, 'test_app')
        self.assertEqual(SwitchApp.objects.get().user, self.test_user)