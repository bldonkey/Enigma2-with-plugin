# Embedded file name: src/base.py
"""
base functions and classes for api
"""

try:
    from typing import Callable, Optional, TypeVar
    _T = TypeVar('_T')
except ImportError:
    pass

from twisted.internet.protocol import Protocol
from twisted.web.error import Error as WebError
from twisted.web.client import Agent, HTTPConnectionPool, readBody, Response, ResponseDone, ResponseFailed, RequestTransmissionFailed, RequestNotSent
from twisted.web.http_headers import Headers
from twisted.internet.error import ConnectError, DNSLookupError, ConnectionClosed, ConnectingCancelledError
from twisted.internet.defer import CancelledError, Deferred, succeed
from twisted.internet import reactor
from twisted.python.failure import Failure
from . import VERSION
from .utils import getBoxModel
try:
    from .loc import translate as _
except ImportError:
    from gettext import gettext as _

class APIException(Exception):

    def __init__(self, msg, code = 'UNKNOWN'):
        self.msg = msg
        self.code = code

    def __str__(self):
        return '%s (%s)' % (self.msg, self.code)


class AgentException(Exception):
    """Exception raised by Twisted Agent"""
    pass


def _agentError(err):
    """Wrap twisted failure in AgentException"""
    raise AgentException(describeException(err))


def trapException(err):
    return err.trap(CancelledError, DNSLookupError, ConnectError, ConnectionClosed, ConnectingCancelledError, ResponseFailed, RequestTransmissionFailed, RequestNotSent, WebError, APIException)


def wasCancelled(err):
    ex = err.value
    if isinstance(ex, CancelledError):
        return True
    if isinstance(ex, ResponseFailed):
        return any((isinstance(failure.value, CancelledError) for failure in ex.reasons))
    return False


def describeException(err):
    """mask details of connection errors"""
    if err.check(DNSLookupError, ConnectError):
        return '%s (%s)' % (_('No internet connection'), type(err.value).__name__)
    else:
        return err.getErrorMessage()


class HttpService(object):

    def __init__(self):
        model = getBoxModel()
        self.user_agent = 'enigma2/%s %s' % (VERSION, model)


    def getPage(self, url):
        agent = Agent(reactor)
        requested = agent.request(
            b'GET',
            url,
            Headers({'User-Agent': [self.user_agent]}),
            None)
        return requested

    def downloadPage(self, url, filename):
        # def __init__(self):
        #     self.url = url
        #     self.filename = filename

        # def saveFile(self, data):
        #     file = open(self.filename, 'wb')
        #     file.write(data)

        def saveFile(result):
            with open(filename, 'wb') as f:
                f.write(result)

        agent = Agent(reactor)
        requested = agent.request(
            b'GET',
            url,
            Headers({'User-Agent': [self.user_agent]}),
            None)
        return requested.addCallback(readBody).addCallback(saveFile)



class HttpAgent(object):

    def __init__(self):
        model = getBoxModel()
        self.headers = Headers()
        self.headers.addRawHeader('User-Agent', 'enigma2/%s %s' % (VERSION, model))
        self.pool = HTTPConnectionPool(reactor, persistent=True)
        self.pool.maxPersistentPerHost = 3
        self.agent = Agent(reactor, pool=self.pool)

    def getPage(self, url):
        return self.agent.request('GET', url, headers=self.headers).addCallback(self._readResponseBody)

    def downloadPage(self, url, filename):
        return self.agent.request('GET', url, headers=self.headers).addCallback(self._downloadResponseBody, filename)

    def shutDown(self):
        self.pool.closeCachedConnections()

    @staticmethod
    def _readResponseBody(response):
        if 200 <= response.code < 300:
            return readBody(response)
        raise WebError(response.code, response.phrase)

    @staticmethod
    def _downloadResponseBody(response, filename):
        if 200 <= response.code < 300:
            return downloadBody(response, filename)
        raise WebError(response.code, response.phrase or '')


class _DownloadBodyProtocol(Protocol):

    def __init__(self, status, message, deferred, filename):
        self.deferred = deferred
        self.status = status
        self.message = message
        self.fd = open(filename, 'wb')

    def dataReceived(self, data):
        try:
            self.fd.write(data)
        except IOError as err:
            self.deferred.errback(Failure(err))

    def connectionLost(self, reason = ResponseDone):
        if reason.check(ResponseDone):
            try:
                self.fd.close()
                self.deferred.callback(None)
            except IOError as err:
                self.deferred.errback(Failure(err))

        else:
            self.deferred.errback(reason)
            self.fd.close()
        return


def downloadBody(response, filename):

    def cancel(deferred):
        abort = getattr(protocol.transport, 'abortConnection', None)
        if abort is not None:
            abort()
        return

    d = Deferred(cancel)
    protocol = _DownloadBodyProtocol(response.code, response.phrase, d, filename)
    response.deliverBody(protocol)
    return d


class CachedRequest(object):

    def __init__(self, f):
        self._func = f
        self._result = None
        return

    def get(self):
        if self._result is None:
            return self._func().addCallback(self._saveResult)
        else:
            return succeed(self._result)
            return

    def _saveResult(self, result):
        self._result = result
        return result