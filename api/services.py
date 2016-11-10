import json
from rest_framework.views import APIView
from django.http import HttpResponse
import urllib2
import requests

from side_api import utils

def validate(app_id, app_tosca_json):
    # Todo: Implement call to validation service instead of docker hub
    search = 'netstat'
    return_val = urllib2.urlopen('https://registry.hub.docker.com/v1/search?q='+search)

    return HttpResponse(return_val)


class JenaFusekiService:

    def __init__(self,fuseki_endpoint):
        if fuseki_endpoint is not None:
            self.fuseki_endpoint = fuseki_endpoint
        else:
            self.fuseki_endpoint = utils.getPropertyFromConfigFile("ASAP_API", "url")

    def getAllApplicationComponentTypes(self):
        r = requests.get(self.fuseki_endpoint + "/get_all_application_component_types")
        return r.json()

    def getApplicationComponentType(self, component_name):
        payload = {'name': component_name}
        r = requests.get(self.fuseki_endpoint + "/get_application_component_type", params=payload)
        return r.json()

    def getApplicationComponentProfile(self):
        r = requests.get(self.fuseki_endpoint + "/get_application_component_profile")
        return r.json()

    def getVirtualInfrastructure(self):
        r = requests.get(self.fuseki_endpoint + "/get_virtual_infrastructure")
        return r.json()

    def getClasses(self):
        search = """prefix owl: <http://www.w3.org/2002/07/owl#>
            prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            SELECT DISTINCT ?class ?label ?description
            WHERE {
              ?class a owl:Class.
              OPTIONAL { ?class rdfs:label ?label}
              OPTIONAL { ?class rdfs:comment ?description}
            }"""

        payload = {'query': search, 'format': 'JSON', 'limit': 25}
        r = requests.get(self.fuseki_endpoint, params=payload)

        classes = r.json()
        classes_list = {'classes':[d['class'] for d in classes['results']['bindings']]}
        return classes_list
