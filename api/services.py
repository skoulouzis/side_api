import json
from rest_framework.views import APIView
from django.http import HttpResponse
import urllib2


def validate(app_id, app_tosca_json):
    # Todo: Implement call to validation service instead of docker hub
    search = 'netstat'
    return_val = urllib2.urlopen('https://registry.hub.docker.com/v1/search?q='+search)

    return HttpResponse(return_val)