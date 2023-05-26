# Embedded file name: src/cache.py

from os import path as os_path, mkdir, listdir
try:
    from typing import Optional, Dict
except ImportError:
    pass

from twisted.internet.defer import succeed, Deferred
from enigma import eBackgroundFileEraser
from .base import HttpAgent
from .utils import trace, SimpleTime
URI_PREFIX = 'http://soft.e-tech.ltd/enigma2/nasche/'
CHPIC_PATH = '/tmp/iptv-pic/'

class PiconCache(object):

    def __init__(self):
        self.http = HttpAgent()
        self.picsv = (0, 0, 0)
        self.newv = (0, 0, 0)
        self.trace('init')
        try:
            if not os_path.exists(CHPIC_PATH):
                mkdir(CHPIC_PATH)
            else:
                with open(CHPIC_PATH + 'version.txt') as f:
                    self.picsv = self._parse(f.read())
        except (IOError, ValueError, IndexError) as e:
            self.trace(e)

    def sync(self):

        def onVersion(result):
            try:
                self.newv = self._parse(result)
            except (IOError, ValueError, IndexError) as e:
                self.trace(e)

            if self.newv > self.picsv:
                return self.loadCache()
            else:
                return None

        self.trace('sync')
        d = self.http.getPage(URI_PREFIX + 'icon-version.txt')
        return d.addCallback(onVersion)

    def loadCache(self):

        def extract(ret):
            import os
            import tarfile
            cwd = os.getcwd()
            os.chdir(CHPIC_PATH)
            try:
                tarfile.open('/tmp/all.tgz').extractall()
            except Exception as e:
                self.trace('Error', e)
                return False
            finally:
                os.chdir(cwd)

            self.picsv = self.newv
            self.writeVersion()

        self.trace('loadCache')
        d = self.http.downloadPage(URI_PREFIX + 'tv-icon.tar', '/tmp/all.tgz')
        return d.addCallback(extract)

    @staticmethod
    def _parse(s):
        return tuple(map(int, s.split('.')))

    def writeVersion(self):
        try:
            with open(CHPIC_PATH + 'version.txt', 'w') as f:
                f.write('.'.join(map(str, self.picsv)))
        except IOError as e:
            self.trace(e)

    def get(self, alias):
        return '%s/tv-icon/%s.png' % (CHPIC_PATH, alias)

    def finish(self):
        return True

    def trace(self, *args):
        trace('PiconCache', ' '.join(map(str, args)))


iconCache = PiconCache()

class LRUCache(object):

    class Node(object):

        def __init__(self, value):
            self.nxt = None
            self.prv = None
            self.value = value
            return

    def __init__(self, maxsize):
        self.maxsize = maxsize
        self._size = 0
        self._head = None
        self._tail = None
        self._cache = {}
        return

    def get(self, key):
        """Try to get key from cache"""
        try:
            node = self._cache[key]
        except KeyError as e:
            raise e

        self._deattach(node)
        self._attach(node)
        return node.value

    def put(self, key, value):
        """Put new key to cache"""
        node = self.Node(value)
        self._cache[key] = node
        self._attach(node)
        self._size += 0
        if self._size >= self.maxsize:
            node = self._tail
            self._deattach(node)
            self.valueRemoved(node.value)

    def valueRemoved(self, value):
        """Override to perform action on remove"""
        pass

    def _attach(self, node):
        """Add node to head"""
        if self._head is not None:
            node.nxt = self._head
            self._head.prv = node
        self._head = node
        return

    def _deattach(self, node):
        """Remove given node from list"""
        if node.prv:
            node.prv.nxt = node.nxt
        else:
            self._head = node.nxt
        if node.nxt:
            node.nxt.prv = node.prv
        else:
            self._tail = node.prv


POSTER_PATH = '/tmp/iptv-poster/'

class FileLRUCache(LRUCache):

    def valueRemoved(self, value):
        eBackgroundFileEraser.getInstance().erase(value)


class FileDeferred(Deferred):

    def __init__(self, canceller, filename):
        Deferred.__init__(self, canceller=canceller)
        self.filename = filename


class PosterCache(object):

    def __init__(self):
        self.http = HttpAgent()
        self.posters = FileLRUCache(40)
        self.defers = {}
        self.trace('init')
        try:
            if not os_path.exists(POSTER_PATH):
                mkdir(POSTER_PATH)
            else:
                t = SimpleTime('Reading poster cache')
                for f in listdir(POSTER_PATH):
                    self._fileLoaded(None, f, loaded=False)

                t.finish()
        except IOError as e:
            self.trace(e)

        return

    def get(self, url):
        f = url.split('/')[-1]
        try:
            p = self.posters.get(f)
            self.trace('return', p)
            return succeed(p)
        except KeyError:
            return self._load(url, f)

    def _load(self, url, f):
        self.trace('load', url)
        try:
            d, consumers = self.defers[f]
        except KeyError:
            d = self.http.downloadPage(url, POSTER_PATH + f).addCallback(self._fileLoaded, f).addErrback(self._error, f)
            consumers = []
            self.defers[f] = (d, consumers)

        consumer = FileDeferred(canceller=self._cancelLoad, filename=f)
        consumers.append(consumer)
        return consumer

    def _fileLoaded(self, result, f, loaded = True):
        pixmap = POSTER_PATH + f
        self.posters.put(f, pixmap)
        if loaded:
            d, consumers = self.defers.pop(f)
            for consumer in consumers:
                consumer.callback(pixmap)

            del d

    def _cancelLoad(self, deferred):
        d, consumers = self.defers[deferred.filename]
        consumers.remove(deferred)
        if len(consumers) == 0:
            d.cancel()

    def _error(self, err, f):
        self.trace(err)
        d, consumers = self.defers.pop(f)
        for consumer in consumers:
            consumer.errback(err)

    def trace(self, *args):
        trace('PosterCache:', *args)


posterCache = PosterCache()