import os

from twisted.web import server
from twisted.application import service, internet

from txmjpeg.web import WatchedDir

# this is the core part of any tac file, the creation of the root-level
# application object
application = service.Application("Switcher MJPEG host")
parent = service.MultiService()

# attach the service to its parent application
webservice = internet.TCPServer(8080, server.Site(WatchedDir('/var/mjpeg')))
webservice.setServiceParent(parent)

parent.setServiceParent(application)
