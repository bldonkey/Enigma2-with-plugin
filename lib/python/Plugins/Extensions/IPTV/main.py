# Embedded file name: src/main.py

from twisted.python.failure import Failure
from .settings_model import ServerConfigService, DeviceNotFound, ServerConfigManager, languageManager, settingsRepo
try:
    from typing import Optional
except ImportError:
    pass

from datetime import datetime
from Screens.Screen import Screen
from Screens.PluginBrowser import PluginBrowser
from Components.Label import Label
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, SCOPE_SKIN
from skin import loadSkin
from enigma import gRGB
from enigma import addFont, eWindowStyleManager, eWindowStyleSkinned
from enigma import getDesktop
from . import VERSION
from .loc import translate as _
from .api import Api, APIException
from .cache import iconCache
from .settings import resetVideoConfig, getVideoConfig
from .settings_home import TVSetupHome
from .common import fatalError, showBackground
from .base import trapException, describeException, HttpAgent as HttpService
from .chlist import TVChannels
from .utils import trace, getMAC
from .videos_menu import VideosHome
from .langlist import VideoLanguageList
from .videos_model import Caption
from .system import MessageBox
from .notify import updateNotifier, expireNotifier
from .colors import colors
from .crashlogs import CrashLogReporter
addFont(resolveFilename(SCOPE_SKIN, 'IPTV/FreeSans.ttf'), 'TVSansRegular', 100, False)
addFont(resolveFilename(SCOPE_SKIN, 'IPTV/OpenSans-Bold.ttf'), 'TVSansBold', 100, False)
addFont(resolveFilename(SCOPE_SKIN, 'IPTV/OpenSans-Semibold.ttf'), 'TVSansSemi', 100, False)
addFont(resolveFilename(SCOPE_SKIN, 'IPTV/DroidSans.ttf'), 'TVDroid', 100, False)
loadSkin('IPTV/iptv.xml')

class StyleManager(object):

    def __init__(self):
        style = eWindowStyleSkinned()
        colorsStyle = [('Background', colors['darkgray']),
         ('Foreground', colors['white']),
         ('ListboxBackground', 1184274),
         ('ListboxForeground', colors['white']),
         ('ListboxBackgroundSelected', 1184274),
         ('ListboxForegroundSelected', colors['white'])]
        borders = [('bpTop', 'IPTV/window/f_h.png'),
         ('bpLeft', 'IPTV/window/f_v.png'),
         ('bpRight', 'IPTV/window/f_v.png'),
         ('bpBottom', 'IPTV/window/f_h.png'),
         ('bpBottomRight', 'IPTV/window/f_br.png'),
         ('bpBottomLeft', 'IPTV/window/f_bl.png'),
         ('bpTopRight', 'IPTV/window/f_tr.png'),
         ('bpTopLeft', 'IPTV//window/f_tl.png')]
        for key, val in colorsStyle:
            style.setColor(eWindowStyleSkinned.__dict__['col' + key], gRGB(val))

        for key, val in borders:
            png = LoadPixmap(resolveFilename(SCOPE_SKIN, val))
            style.setPixmap(eWindowStyleSkinned.__dict__['bsWindow'], eWindowStyleSkinned.__dict__[key], png)

        borders = [('bpTop', 'IPTV/frame/bh.png'),
         ('bpLeft', 'IPTV/frame/bv.png'),
         ('bpRight', 'IPTV/frame/bv.png'),
         ('bpBottom', 'IPTV/frame/bh.png'),
         ('bpBottomRight', 'IPTV/frame/bbr.png'),
         ('bpBottomLeft', 'IPTV/frame/bbl.png'),
         ('bpTopRight', 'IPTV/frame/btr.png'),
         ('bpTopLeft', 'IPTV/frame/btl.png')]
        for key, val in borders:
            png = LoadPixmap(resolveFilename(SCOPE_SKIN, val))
            style.setPixmap(eWindowStyleSkinned.__dict__['bsListboxEntry'], eWindowStyleSkinned.__dict__[key], png)

        self._style = style
        self._system_style = None
        return

    def apply(self):
        mgr = eWindowStyleManager.getInstance()
        self._system_style = mgr.getStyle(0)
        mgr.setStyle(0, self._style)

    def reset(self):
        mgr = eWindowStyleManager.getInstance()
        mgr.setStyle(0, self._system_style.__ref__())
        del self._system_style


class TVLoading(Screen):

    def __init__(self, session, message = _('Loading...')):
        Screen.__init__(self, session)
        self.skinName = 'TVLoading'
        self['text'] = Label(message)


class Runner(TVLoading):

    def __init__(self, session):
        desktop = getDesktop(0)
        self.resolution = (desktop.size().width(), desktop.size().height())
        self.style_manager = StyleManager()
        self.style_manager.apply()
        TVLoading.__init__(self, session)
        try:
            self.session.pipshown
        except AttributeError:
            self.session.pipshown = False

        self.onShown.append(self.start)
        try:
            self.last_service = self.session.nav.getCurrentlyPlayingServiceOrGroup()
        except AttributeError:
            self.last_service = self.session.nav.getCurrentlyPlayingServiceReference()

        self.onClose.append(self.restoreService)
        self.onstart = 'tv'
        self.db = None
        self.http = HttpService()
        self.config_manager = ServerConfigManager(ServerConfigService(self.http))
        return

    def restoreService(self):
        self.session.nav.playService(self.last_service)

    @staticmethod
    def fixTime(server_time):
        diff = server_time - datetime.now()
        if diff.days > 1:
            print('[IPTV] box time too bad! Try set server time', server_time)
            from os.path import exists
            for f in ['/bin/date',
             '/usr/bin/date',
             '/sbin/date',
             '/usr/sbin/date']:
                if exists(f):
                    try:
                        from subprocess import call as os_call
                        os_call([f, '-s %s' % server_time.strftime('%Y.%m.%d-%H:%M:%S')])
                        break
                    except Exception as e:
                        print('[IPTV] set date failed!', e)

    def start(self):
        self.onShown.remove(self.start)
        print('[IPTV] START', VERSION)
        showBackground()
        updateNotifier.start()
        self.showLoading()
        reporter = CrashLogReporter()
        if reporter.findPendingLogs():
            try:
                reporter.sendNewLogs()
            except Exception as e:
                message = _('Error in sending crashlog') + '\n' + str(e)
                self.session.openWithCallback(lambda ret: self.loadLogin(), MessageBox, message, MessageBox.TYPE_ERROR, timeout=5)
                return

        self.loadLogin()

    def loadLogin(self):
        d = self.config_manager.syncConfig()
        d.addCallback(self.auth).addErrback(self.startError).addErrback(fatalError)

    def showErrorAndRetry(self, message):

        def cb(ret):
            if ret:
                self.openSystemSettings()
            else:
                self.loadLogin()

        choices = [(_('Retry'), False), (_('Open settings'), True)]
        self.session.openWithCallback(cb, MessageBox, message, MessageBox.TYPE_ERROR, list=choices)

    def startError(self, err):
        if err.check(DeviceNotFound):
            message = '%s: %s' % (_('Device not found'), getMAC())
            self.session.openWithCallback(lambda ret: self.loadLogin(), MessageBox, message, MessageBox.TYPE_ERROR)
        else:
            trapException(err)
            message = '%s: %s' % (_('Configuration error'), describeException(err))
            if settingsRepo.login:
                self.showErrorAndRetry(message)
            else:
                self.session.openWithCallback(lambda ret: self.auth(), MessageBox, message, MessageBox.TYPE_ERROR)

    def auth(self, ret = None):
        lang = languageManager.getLanguageShort()
        trace('detected language', lang)
        self.db = Api(settingsRepo.login, settingsRepo.password, settingsRepo.url, settingsRepo.quality, lang, title=settingsRepo.provider)
        self.db.authorize().addCallback(self.authOK).addErrback(self.authErr).addErrback(fatalError)

    def authOK(self, ret):
        self.hideLoading()
        self.fixTime(self.db.server_time)
        message = expireNotifier.start(self.db)

        def proceed(retval = None):
            self.syncSettings()

        if message is None:
            proceed()
        else:
            self.session.openWithCallback(proceed, MessageBox, message, MessageBox.TYPE_INFO)
        return

    def authErr(self, err):
        trace('auth error:', err)
        self.hideLoading()
        e = trapException(err)
        message = _('Authorization error') + '\n' + describeException(err)
        if e == APIException and err.value.code in Api.LOGIN_CODES:
            self.session.openWithCallback(lambda ret: self.loadLogin(), MessageBox, message, MessageBox.TYPE_ERROR)
        else:
            self.showErrorAndRetry(message)

    def syncSettings(self):
        if self.db.settings['interface_lng'] != self.db.language:
            d = self.db.setSettings({'interface_lng': str(self.db.language)})
            d.addCallback(self.settingsOK).addErrback(self.settingsError).addErrback(fatalError)
        else:
            self.run(self.onstart)

    def settingsOK(self, ret):
        self.run(self.onstart)

    def settingsError(self, err):
        trace('settings error', err)
        trapException(err)
        self.run(self.onstart)

    def run(self, ret):
        trace('run', ret)
        if ret == 'settings':

            def cb(restart):
                if restart:
                    self.onstart = 'tv'
                    self.loadLogin()
                else:
                    self.run('tv')

            self.session.openWithCallback(cb, TVSetupHome, self.db, self.style_manager)
        elif ret == 'tv':
            self.showLoading()
            iconCache.sync().addCallback(self.cacheReady).addErrback(self.cacheErr)
        elif ret == 'video':
            self.runVideos()
        elif ret == 'plugins':

            def rerunTv(*args, **kwargs):
                self.style_manager.apply()
                self.run('tv')

            self.style_manager.reset()
            self.session.openWithCallback(rerunTv, PluginBrowser)
        else:
            if ret == 'enigma':
                return self.exit()
            raise Exception('Unknown ret %s' % ret)

    def openSystemSettings(self):

        def cb():
            self.style_manager.apply()
            self.loadLogin()

        self.style_manager.reset()
        from .settings_home import openSystemSettings
        openSystemSettings(self.session, callback=cb)

    def showLoading(self):
        pass

    def hideLoading(self):
        pass

    def cacheReady(self, ret):
        trace('cacheReady', ret)
        self.hideLoading()
        self.loadGroups()

    def cacheErr(self, err):
        trace('cacheErr', err)
        if trapException(err):
            msg = _('Error in loading channel icons.') + '\n' + describeException(err)
            self.session.openWithCallback(self.loadGroups, MessageBox, msg, MessageBox.TYPE_WARNING)
        else:
            fatalError(err)

    def loadGroups(self, ret = None):
        self.db.getChannels().addCallback(self.groupsReady).addErrback(self.groupsErr).addErrback(fatalError)

    def groupsReady(self, groups):
        trace('groupsReady')
        self.hideLoading()
        play_state = settingsRepo.play_state
        self.session.openWithCallback(self.channelsClosed, TVChannels, groups, play_state, self.db)

    def channelsClosed(self, to_run):
        trace('channelsClosed', to_run)
        showBackground()
        self.run(to_run)

    def groupsErr(self, err):
        trace('groups error', err)
        trapException(err)
        message = _('Error loading channels:') + '\n' + describeException(err)
        self.session.openWithCallback(lambda ret: self.loadGroups(), MessageBox, message, MessageBox.TYPE_ERROR)

    def runVideosHome(self, ret = None):
        self.session.openWithCallback(self.videosClosed, VideosHome, self.db)

    def runVideos(self):
        vid, vtype, time = getVideoConfig()
        if vid == 0:
            self.runVideosHome()
        else:
            self.db.getVideo(vid, vtype).addCallback(self.vidReady, time).addErrback(self.vidErr).addErrback(fatalError)

    def vidReady(self, video, time):

        def cb(ret):
            if not ret:
                resetVideoConfig()
                self.runVideosHome()
            else:
                from .videos import VideosWall
                caption = Caption(self.db.title)
                caption.append(_('All movies'))
                caption.setLang(VideoLanguageList.getLanguageTitle())
                self.session.openWithCallback(self.runVideosHome, VideosWall, self.db, {}, caption, video)

        self.session.openWithCallback(cb, MessageBox, _('Continue video %s at') % video['title'] + ' %d:%02d:%02d?' % (time / 3600, time / 60 % 60, time % 60))

    def vidErr(self, err):
        trace('vid error', err)
        e = trapException(err)
        if e == APIException and err.value.code == 'VIDEO_NOT_FOUND':
            resetVideoConfig()
        msg = _('Error') + ':\n' + describeException(err)
        self.session.openWithCallback(self.runVideosHome, MessageBox, msg, MessageBox.TYPE_ERROR)

    def videosClosed(self, to_run = 'tv'):
        self.run(to_run)

    def exit(self, ret = None):
        trace('EXIT')
        self.style_manager.reset()
        del self.style_manager
        expireNotifier.stop()
        updateNotifier.stop()
        self.close()