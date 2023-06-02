# Embedded file name: src/updater.py
"""
ANY CHANGES TO THIS FILE MUST BE FULLY TESTED

Do plugin updates, should be simple and reliable.
Must work if main plugin got broken after update.
Therefore we want to have as less imports as possible
"""
from twisted.internet import reactor
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from enigma import quitMainloop
from Components.Console import Console
from Screens.MessageBox import MessageBox
from twisted.internet.defer import Deferred, fail
from . import NAME, VERSION
from .layer import enigma2Qt, eTimer
try:
    from .loc import translate as _
except ImportError as e:
    print('[IPTV] import fail:', e)

def fatalError(err):
    print('[IPTV] plugin error - exit 5')
    print(err.getTraceback())
    f = open('/tmp/error.txt', 'w')
    f.write(str(err))
    f.close()
    quitMainloop(5)


def getPage(url):
    agent = Agent(reactor)
    url = url.encode("ascii")
    requested = agent.request(
        b'GET',
        url,
        Headers({'User-Agent': [('enigma2/%s' % VERSION).encode("ascii")]}),
        None)
    return requested.addErrback(twistedError)


def downloadPage(url, filename):
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
    url = url.encode("ascii")
    requested = agent.request(
        b'GET',
        url,
        Headers({'User-Agent': [('enigma2/%s' % VERSION).encode("ascii")]}),
        None)
    return requested.addCallback(readBody).addCallback(saveFile).addErrback(twistedError)


def twistedError(err):
    """
    Hides certain error details and transforms exceptions to UpdaterException
    Add it right after getPage and downloadPage to handle twisted internal errors gracefully
    """
    from twisted.internet.error import ConnectError, DNSLookupError
    if err.check(ConnectError, DNSLookupError):
        raise UpdaterException('%s (%s)' % (_('No internet connection'), type(err.value).__name__))
    else:
        raise UpdaterException(err.getErrorMessage())


class UpdaterException(Exception):

    def __init__(self, message):
        Exception.__init__(self, message)


def parseVersion(data):
    verStr = data.strip().split('.')
    try:
        return tuple(map(int, verStr))
    except ValueError:
        return tuple([0, 0])


PREFIX = 'enigma2-plugin-extensions-'

class Updater(object):

    def __init__(self):
        self.url = 'http://soft.e-tech.ltd/enigma2/nasche/'
        self._defer = None
        self._installer = None
        self._version = None
        self.console = Console()
        self.timer = eTimer()
        self.timer.callback.append(self.checkUpdate)
        self.onUpdateAvailable = []
        return

    def startTimer(self):
        from random import randint
        self.timer.startLongTimer(79200 + randint(0, 100) * 60 + randint(0, 100))

    def stop(self):
        self.timer.stop()

    def checkUpdate(self):
        self.stop()
        if self._defer is not None:
            return fail(UpdaterException(_('[IPTV] Already checking update!')))
        else:
            curVer = parseVersion(VERSION)
            print('[IPTV] Installed version:', curVer)

            def cb(data):
                nxtVer = parseVersion(data)
                self._version = nxtVer
                print('[IPTV] Available version:', nxtVer)
                if nxtVer > curVer:
                    for f in self.onUpdateAvailable:
                        f()

                    return True
                else:
                    return False

            def eb(err):
                print('[IPTV] Updater error:', err)
                if err.check(UpdaterException):
                    return err
                fatalError(err)

            def finished(arg):
                print('[IPTV] Check update finished')
                self._defer = None
                return arg

            self._defer = getPage(self.url + 'version.txt')
            return self._defer.addCallback(cb).addErrback(eb).addBoth(finished)

    def installUpdate(self):
        print('[IPTV] install update')
        if self._installer is not None:
            return fail(UpdaterException(_('Installer already running!')))
        elif self._version is None:
            return fail(UpdaterException(_('Have not got version to install yet!')))
        else:
            ver_str = '.'.join(map(str, self._version))
            if enigma2Qt:
                ext = 'deb'
            else:
                ext = 'ipk'
            print('[IPTV] download', ver_str, ext)
            file_name = '/tmp/%s.%s' % (NAME, ext)
            self._installer = downloadPage(self.url + '%s_%s_all.%s' % (PREFIX + NAME.lower(), ver_str, ext), file_name)

            def cb(ret):
                return self._install(file_name)

            def eb(err):
                print('[IPTV] Updater error:', err)
                if err.check(UpdaterException):
                    return err
                fatalError(err)

            def finished(arg):
                print('[IPTV] install ended')
                self._installer = None
                return arg

            return self._installer.addCallback(cb).addErrback(eb).addBoth(finished)

    def _install(self, file_name):
        d = Deferred()

        def executed(output, retval, extra_args = None):
            print('[IPTV] exitcode:%d output:\n%s' % (retval, output))
            r = (output, retval)
            d.callback(r)

        if enigma2Qt:
            self.console.ePopen('dpkg -i %s' % file_name, executed)
        else:
            self.console.ePopen('opkg install %s' % file_name, executed)
        return d


iUpdater = Updater()

class UpdaterScreen(MessageBox):

    def __init__(self, session):
        MessageBox.__init__(self, session, _('Checking updates'), MessageBox.TYPE_INFO, enable_input=False)
        self.skinName = 'MessageBox'
        self.onShown.append(self.start)

    def start(self):
        self.onShown.remove(self.start)
        iUpdater.checkUpdate().addCallback(self.install).addErrback(self.error).addErrback(fatalError)

    def install(self, confirmed):
        if confirmed:
            self['text'].setText(_('Installing updates...'))
            iUpdater.installUpdate().addCallback(self.finished).addErrback(self.error).addErrback(fatalError)
        else:
            self.close(False)

    def error(self, err):
        err.trap(UpdaterException)
        self.finished((err.getErrorMessage(), 1))

    def finished(self, result):
        output, retval = result
        if retval == 0:
            self.close(True)
        else:
            self.session.openWithCallback(lambda ret: self.close(False), MessageBox, output, MessageBox.TYPE_ERROR)