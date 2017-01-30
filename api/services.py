import json
import os
import re

from rest_framework.views import APIView
from django.http import HttpResponse
import urllib2
import requests

from side_api import utils, settings

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



class DripManagerService:
    def __init__(self,drip_manager_endpoint):
        if drip_manager_endpoint is not None:
            self.drip_manager_endpoint = drip_manager_endpoint
        else:
            self.drip_manager_endpoint = utils.getPropertyFromConfigFile("DRIP_MANAGER_API", "url")

    def register(self, user):
        xml = """<?xml version='1.0' encoding='utf-8'?>
        <register>
            <user>""" + user.username + """</user>
            <pwd>""" + user.password + """</pwd>
        </register>"""
        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/account/register", data=xml, headers=headers)
        return r

    def configure_ec2_account(self,user,amazon_root_key,california_key,virginia_key):
        line1 = amazon_root_key.file.readline()
        line2 = amazon_root_key.file.readline()
        ca_key = california_key.file.read()
        vi_key = virginia_key.file.read()

        xml = """<?xml version='1.0' encoding='utf-8'?>
        <configure>
            <user>""" + user.username + """</user>
            <pwd>""" + user.password + """</pwd>
            <keyid>""" + line1.split("=")[1] + """</keyid>
 	        <key>""" + line2.split("=")[1] + """</key>
 	        <loginKey domain_name="Virginia">""" + re.sub(r'\r?\n','\\\\n', vi_key) + """</loginKey>
 	        <loginKey domain_name="California">""" + re.sub(r'\r?\n','\\\\n', ca_key) + """</loginKey>
        </configure>"""
        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/account/configure/ec2", data=xml, headers=headers)
        return r


    def planning_virtual_infrastructure(self, user, path_app_tosca):
        with open(path_app_tosca, 'r') as f:
            app_tosca = f.read()

        xml = """<?xml version='1.0' encoding='utf-8'?>
        <plan>
            <user>""" + user.username + """</user>
            <pwd>""" + user.password + """</pwd>"""

        xml += """<file>"""+ re.sub(r'\r?\n','\\\\n', app_tosca) + """</file>"""
        xml += """</plan>"""

        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/plan/planning", data=xml, headers=headers)
        return r


    def upload_tosca(self, user, path_all_topology_file, path_tosca_files):
        xml = """<?xml version='1.0' encoding='utf-8'?>
        <upload>
            <user>""" + user.username + """</user>
            <pwd>""" + user.password + """</pwd>"""

        for path_tosca_file in path_tosca_files:
            with open(path_tosca_file, 'r') as f:
                tosca_content = f.read()
            xml += """<file name='""" + os.path.basename(path_tosca_file) + """' level='1'>"""+ re.sub(r'\r?\n','\\\\n',tosca_content) + """</file>"""

        with open(path_all_topology_file, 'r') as f:
            tosca_content = f.read()
        xml +="""<file name='""" + os.path.basename(path_all_topology_file) + """' level='0'>"""+ re.sub(r'\r?\n','\\\\n', tosca_content) + """</file>"""

        xml +="""</upload>"""
        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/provision/upload", data=xml, headers=headers)
        return r


    def conf_user_key(self, user, user_ssh_document, action_number):
        xml = """<?xml version='1.0' encoding='utf-8'?>
         <confUserKey>
             <user>""" + user.username + """</user>
             <pwd>""" + user.password + """</pwd>
             <userKey name="id_rsa.pub">""" + re.sub(r'\r?\n','\\\\n', user_ssh_document.file.read()) + """</userKey>
             <action>""" + action_number + """</action>
        </confUserKey>"""
        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/provision/confuserkey", data=xml, headers=headers)
        return r

    def conf_script(self, user, conf_script_file, action_number):
        with open(conf_script_file, 'r') as f:
            script = f.read()
        xml = """<?xml version='1.0' encoding='utf-8'?>
         <confScript>
             <user>""" + user.username + """</user>
             <pwd>""" + user.password + """</pwd>
             <script><![CDATA[""" + re.sub(r'\r?\n','\\\\n',script) + """]]></script>
             <action>""" + action_number + """</action>
        </confScript>"""
        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/provision/confscript", data=xml, headers=headers)
        return r

    def execute(self, user, action_number):
        xml = """<?xml version='1.0' encoding='utf-8'?>
         <execute>
             <user>""" + user.username + """</user>
             <pwd>""" + user.password + """</pwd>
             <action>""" + action_number + """</action>
        </execute>"""
        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/provision/execute", data=xml, headers=headers)
        return r


    def setup_docker_orchestrator(self, user, action_number, docker_orchestrator_type):
        xml = """<?xml version='1.0' encoding='utf-8'?>
         <deploy>
             <user>""" + user.username + """</user>
             <pwd>""" + user.password + """</pwd>
             <action>""" + action_number + """</action>
        </deploy>"""
        headers = {'Content-Type': 'text/xml'}
        r = requests.post(self.drip_manager_endpoint + "/deploy/" + docker_orchestrator_type, data=xml, headers=headers)
        return r
