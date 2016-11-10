import ConfigParser
from side_api import settings


def getPropertyFromConfigFile (sectionName, propertyName):
    config = ConfigParser.RawConfigParser()
    config.read(settings.BASE_DIR + '/config.properties')

    return config.get(sectionName, propertyName)