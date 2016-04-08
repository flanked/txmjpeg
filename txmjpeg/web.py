import os.path
try:
    from cStringIO import StringIO
except ImportError:
    from cStringIO import StringIO

from twisted.internet import reactor
from twisted.web import resource, static, server
from twisted.python import log, filepath
from twisted.internet.defer import Deferred
from twisted.internet import inotify


class WatcherMixin(object):
    """ Watch a specific path for file or directory changes """

    def __init__(self):
        self.lastModified = 0
        self.producers = []
        self.current_file = None
        self.notifier = None

    def fileNotify(self, ignored, filepath, mask):
        """
        For historical reasons, an opaque handle is passed as first
        parameter. This object should never be used.

        @param filepath: FilePath on which the event happened.
        @param mask: inotify event as hexadecimal masks
        """


        filepath.changed()
        if not filepath.exists():
            for producer in self.producers:
                producer.stopProducing()
            self.removeWatcher()
            return

        lastModified = filepath.getStatusChangeTime()
        if self.lastModified >= lastModified:
            return

        self.lastModified = lastModified
        f = filepath.open()

        if self.current_file:
            # Close the current file to free the buffer
            self.current_file.close()

        self.current_file = StringIO(f.read())
        for producer in self.producers:
            # Create a new file-like object for each producer
            producer.next_file = StringIO(self.current_file.getvalue())
            if producer.paused:
                producer.next()
                # Push producers constantly call resumeProducing, so we must
                # first unpause and then resume
                producer.unpauseProducing()
                producer.resumeProducing()

    def dirNotify(self, ignored, filepath, mask):
        """
        For historical reasons, an opaque handle is passed as first
        parameter. This object should never be used.
        """
        if filepath.isfile():
            if 'create' in inotify.humanReadableMask(mask):
                print "dirNotify event %s on %s" % (
                    ', '.join(inotify.humanReadableMask(mask)), filepath)
                self.add_path(filepath.basename())
            return

        if 'create' in inotify.humanReadableMask(mask):
            self.add_path(filepath.basename())

        if 'delete' in inotify.humanReadableMask(mask):
            self.remove_path(filepath.basename())

    def addWatcher(self, path, callback=None):
        notifier = inotify.INotify()
        notifier.startReading()
        if not isinstance(path, filepath.FilePath):
            path = filepath.FilePath(path)
        log.msg("Adding watcher for", path)
        if path.isfile():
            self.current_file = StringIO(path.open().read())
            callbacks = [self.fileNotify]
        elif path.isdir():
            callbacks = [self.dirNotify]
        if callback:
            callbacks.append(callback)
        notifier.watch(path, callbacks=callbacks)
        self.notifier = notifier

    def removeWatcher(self):
        log.msg("Removing watcher for", self.path)
        self.notifier.stopReading()


class WatchedDir(resource.Resource, WatcherMixin):
    isLeaf = False
    def __init__(self, path):
        resource.Resource.__init__(self)
        WatcherMixin.__init__(self)
        self.path = path

        dir = filepath.FilePath(path)
        self.addWatcher(path)
        if dir.isdir():
            for fp in dir.listdir():
                self.add_path(fp)

    def remove(self):
        for path in self.children.keys():
            self.remove_path(path)
        self.removeWatcher()

    def add_path(self, path):
        root_path = os.path.join(self.path, path)
        log.msg("Adding watched path: ", root_path)
        fp = filepath.FilePath(root_path)
        if not fp.exists():
            raise OSError("Invalid Path: %s" % path)
        if fp.isdir():
            log.msg("adding dir ", path, root_path)
            self.putChild(path, WatchedDir(root_path))
        if fp.isfile():
            self.putChild(path, WatchedFile(root_path))

    def remove_path(self, path):
        resource = self.children.pop(path)
        if isinstance(resource, WatcherMixin):
            resource.removeWatcher()


class WatchedFile(static.File, WatcherMixin):
    """ File resource with an x-mixed-replace mimetype """
    isLeaf = True
    def __init__(self, path):
        WatcherMixin.__init__(self)
        self.path = path
        self.addWatcher(path)

    def add_producer(self, producer):
        log.msg("Adding producer for ", self.path)
        self.producers.append(producer)

    def remove_producer(self, producer):
        log.msg("Removing producer for ", self.path)
        self.producers.remove(producer)

    def render_HEAD(self, request):
        return self.render_GET(request)

    def render_GET(self, request):

        request.setHeader('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        # request.setHeader('Last-Modified', doc.upload_date)

        # if "v" in request.args:
        #    request.setHeader("Expires", datetime.datetime.utcnow() + \
        #                               datetime.timedelta(days=365 * 10))
        #    request.setHeader("Cache-Control", "max-age=" + str(86400 * 365 * 10))
        # else:
        #    request.setHeader("Cache-Control", "public")

        cached = False
        ims_value = request.getHeader("If-Modified-Since")
        if ims_value is not None:
            date_tuple = email.utils.parsedate(ims_value)
            if_since = datetime.datetime.fromtimestamp(time.mktime(date_tuple))
            if if_since >= modified:
                request.set_status(304)
                request.finish()
                cached = True

        if not cached and request.method != 'HEAD':
            # request.setHeader('Content-Length', doc.length)

#                    self.set_header('Content-Disposition',
#                                    'attachment; filename=%s'%video)
            try:
                producer = IteratingStaticProducer(request,
                                    StringIO(self.current_file.getvalue()),
                                    self)
                producer.start()
                self.add_producer(producer)
            except IOError, e:
                log.err("Failed to read the file: ", e)
                request.setResponseCode(404)
                request.finish()
                return ''
            except Exception, e:
                log.err()
                log.err("Unknown error adding producer: %s" % e)
                if request.producer:
                    request.unregisterProducer()
                request.setResponseCode(404)
                request.finish()
                return ''
            return server.NOT_DONE_YET
        return b''


class IteratingStaticProducer(static.StaticProducer):
    """ Interating files until stopped """
    def __init__(self, request, file, watcher=None):
        self.next_file = None
        self.paused = False
        self.watcher = watcher
        static.StaticProducer.__init__(self, request, file)

    def next(self):
        if self.next_file:
            self.fileObject = self.next_file
            self.next_file = None
        else:
            # Pause producing and wait for new data to be available
            # rather than streaming the same content repeatidly
            self.pauseProducing()
            return False
        return True

    def start(self):
        self.addFrame()
        self.request.registerProducer(self, False)

    def addFrame(self):
        self.request.write("--FRAME\r\n")
        self.request.write("Content-Type: image/jpeg\r\n")
        self.request.write("\r\n")

    def resumeProducing(self):
        if not self.request or self.paused:
            return
        data = self.fileObject.read(self.bufferSize)
        if data:
            self.request.write(data)
        else:
            self.addFrame()
            if not self.next():
                return
            data = self.fileObject.read(self.bufferSize)
            if not data:
                raise IOError("Empty File cannot be streamed")
            self.request.write(data)

    def pauseProducing(self):
        self.paused = True

    def unpauseProducing(self):
        self.paused = False

    def stopProducing(self):
        self.request.unregisterProducer()
        self.request.finish()
        static.StaticProducer.stopProducing(self)
        if self.watcher:
            self.watcher.remove_producer(self)

