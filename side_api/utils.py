import ConfigParser
from side_api import settings

from yaml.dumper import Dumper
from yaml.representer import SafeRepresenter


def getPropertyFromConfigFile (sectionName, propertyName):
    config = ConfigParser.RawConfigParser()
    config.read(settings.BASE_DIR + '/config.properties')

    return config.get(sectionName, propertyName)


class YamlDumper(Dumper):

    def __init__(self, stream, default_style=None, default_flow_style=None, canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None, encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None):
        super(YamlDumper, self).__init__(stream, default_style, default_flow_style, canonical, indent, width, allow_unicode,
                       line_break, encoding, explicit_start, explicit_end, version, tags)
        self.add_representer(str, SafeRepresenter.represent_str)
        self.add_representer(unicode, SafeRepresenter.represent_unicode)

    def increase_indent(self, flow=False, indentless=False):
        return super(YamlDumper, self).increase_indent(flow, False)
