# Embedded file name: src/videos_player.py

from .settings_model import settingsRepo
try:
    from typing import Optional
except ImportError:
    pass

from twisted.internet.defer import CancelledError
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Slider import Slider
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from enigma import iPlayableService, eServiceReference
from .base import APIException, trapException
from .common import AutoHideScreen, CallbackReceiver, safecb
from .layer import eTimer
from .loc import translate as _
from .settings import TVEnterPassword, setVideoConfig, resetVideoConfig
from .standby import PowerOffMenu, standbyManager
from .system import MessageBox
from .updater import fatalError
from .utils import trace
from .cache import posterCache
from .api import TYPE_MOVIE

class PinManager(object):

    def __init__(self):
        self.pin = None
        return

    def clear(self):
        self.pin = None
        return

    def getPin(self):
        return self.pin


pinManager = PinManager()
EV_START = 0
EV_PLAY = 1
EV_PAUSE = 2
EV_END = 3
RET_STOP = 0
RET_PREV = 1
RET_NEXT = 2
RET_END = 3

class VideosPlayer(AutoHideScreen, CallbackReceiver):
    ALLOW_SUSPEND = Screen.SUSPEND_PAUSES

    def __init__(self, session, db, video, time = 0):
        super(VideosPlayer, self).__init__(session)
        CallbackReceiver.__init__(self)
        self.db = db
        self.video = video
        self.tick_timer = eTimer()
        self.tick_timer.callback.append(self.updateLabels)
        self.want_pos = time
        self.play_sent = False
        self.evtracker = ServiceEventTracker(screen=self, eventmap={iPlayableService.evStart: self.onStart,
         iPlayableService.evStopped: self.onStop,
         iPlayableService.evEnd: self.onEnd,
         iPlayableService.evSOF: self.onSOF,
         iPlayableService.evEOF: self.onEOF,
         iPlayableService.evUpdatedInfo: self.onUpdateInfo})
        self.is_playing = False
        self.is_paused = False
        self.fails = 0
        self.fail_screen = None
        self.onClose.append(self.deleteFailScreen)
        self.protect_pin = pinManager.getPin()
        self.seek = None
        standbyManager.onStandby.append(self.handleStandby)
        self.onClose.append(lambda : standbyManager.onStandby.remove(self.handleStandby))
        self['poster'] = Pixmap()
        self['progress'] = Slider(0, 1000)
        self['title'] = Label()
        self['time'] = Label()
        self['descr'] = Label()
        self['actions'] = ActionMap(['OkCancelActions', 'TPluginActions', 'TVideosActions'], {'info': self.info,
         'cancel': self.confirmStop,
         'stop': self.stop,
         'close': self.stop,
         'power': lambda : standbyManager.enterStandby(self.session),
         'powerMenu': lambda : self.session.open(PowerOffMenu),
         'play': self.unPause,
         'pause': self.pause,
         'playpause': self.playPause,
         'next': self.nextEpisode,
         'prev': self.prevEpisode}, -2)
        self['actions_seek'] = ActionMap(['TSeekActions'], {'seekRight': lambda : self.seekAction(+60),
         'seekLeft': lambda : self.seekAction(-60),
         'seekFwd': lambda : self.seekAction(+300),
         'seekRwd': lambda : self.seekAction(-300)})
        self['actions_audio'] = ActionMap(['InfobarAudioSelectionActions'], {'audioSelection': self.audioSelection})
        self['actions_video'] = ActionMap(['TVideoModeActions'], {'vmode': self.videoModeSelection})
        self.onShown.append(self.start)
        return

    def pauseService(self):
        trace('asked to pause')
        self.pause()

    def unPauseService(self):
        trace('asked to unPause')
        self.unPause()

    def handleStandby(self, sleep):
        if sleep:
            self.powerOff()
        else:
            self.play()

    def powerOff(self):
        self.want_pos = self.getPlayPos() / 90000
        self.session.nav.stopService()
        sref = eServiceReference(1, 0, '')
        self.session.nav.playService(sref)

    def start(self):
        self.onShown.remove(self.start)
        self.play()

    def audioSelection(self):
        from .audio import AudioMenu
        self.session.open(AudioMenu)

    def videoModeSelection(self):
        from .system import TVideoMode
        self.session.open(TVideoMode)

    def info(self):
        if not self.shown:
            self.show()
        else:
            self.hide()

    def hideInfo(self):
        self.hide()

    def play(self):
        if int(self.video['protected']):
            if self.protect_pin is not None:
                self.getUrl(pin=self.protect_pin)
            else:
                self.session.openWithCallback(self.getUrl, TVEnterPassword)
        else:
            self.getUrl(pin=None)
        return

    def getUrl(self, pin):
        self.protect_pin = pin
        if int(self.video['protected']) and pin is None:
            return self.stop()
        else:
            d = self.db.getVideoUrl(self.video['id'], pin)
            d.addCallback(self.playUrl).addErrback(self.urlError)
            d.addErrback(fatalError)
            return

    @safecb
    def urlError(self, err):
        if err.check(APIException) and err.value.code == 'URL_PROTECTED':
            self.protect_pin = None
            cb = lambda ret: self.session.openWithCallback(self.getUrl, TVEnterPassword)
            self.session.openWithCallback(cb, MessageBox, _('Wrong password!'), MessageBox.TYPE_WARNING, timeout=10, enable_input=False)
        else:
            self.error(err)
        return

    @safecb
    def playUrl(self, url):
        self.doStop()
        self.is_playing = True
        self.is_paused = False
        trace('PLAY:', url, type(url))
        pid = settingsRepo.vod_player_id
        sref = eServiceReference(pid, 0, url)
        sref.setName(self.video['title'])
        self.doPlay(sref, self.want_pos)
        self['title'].setText(self.video['title'])
        try:
            self.setDescription(self.video)
        except KeyError:
            d = self.db.getVideo(self.video['id'], self.video['type'])
            d.addCallback(self.setDescription).addErrback(self.error).addErrback(fatalError)

        d = posterCache.get(self.video['pic'].encode('utf-8'))
        d.addCallback(self.setPixmap).addErrback(self.error).addErrback(fatalError)
        self.popup()

    @safecb
    def setDescription(self, data):
        self['descr'].setText(data['description'].encode('utf-8'))

    @safecb
    def setPixmap(self, pixmap):
        self['poster'].instance.setPixmap(LoadPixmap(pixmap))

    def confirmStop(self):

        def cb(ret):
            if ret:
                self.stop()

        self.session.openWithCallback(cb, MessageBox, _('Exit movie?'), MessageBox.TYPE_YESNO)

    def stop(self, ret = RET_STOP):
        if ret == RET_STOP and not (self.atTheEnd() and self.video['type'] == TYPE_MOVIE):
            setVideoConfig(self.video['id'], self.video['type'], self.getPlayPos() / 90000)
        else:
            resetVideoConfig()
        self.doStop()
        pinManager.pin = self.protect_pin
        self.close(ret)

    def nextEpisode(self):
        self.stop(ret=RET_NEXT)

    def prevEpisode(self):
        self.stop(ret=RET_PREV)

    def seekAction(self, time_diff):
        if self.seek is None:
            self.startSeek(time_diff)
        else:
            self.seek.seekAction(time_diff)
        return

    def startSeek(self, diff):
        if not self.canSeek():
            return
        trace('startSeek')
        self.tick_timer.stop()
        self.active_components.remove(self['actions_seek'])
        self.seek = self.session.openWithCallback(self.endSeek, VideosSeek, self.getPlayPos() / 90000, self.getLength() / 90000, self.updateProgress)
        self.seek.setDiff(diff)
        self.lockShow()

    def updateProgress(self, time):
        s = self.getLength() / 90000
        p = time
        self['time'].setText('%d:%02d:%02d / %d:%02d:%02d' % (p / 3600,
         p / 60 % 60,
         p % 60,
         s / 3600,
         s / 60 % 60,
         s % 60))
        self['progress'].setValue(1000 * p / s)

    def endSeek(self, time):
        trace('endSeek', time)
        self.seek = None
        if time is None:
            return
        else:
            self.doSeek(time * 90000)
            self.tick_timer.start(1000)
            self.popup()
            return

    def pause(self):
        if not self.canSeek():
            return
        if self.is_paused:
            return
        self.is_paused = True
        self.doPause(self.is_paused)

    def unPause(self):
        if not self.canSeek():
            return
        if not self.is_paused:
            return
        self.is_paused = False
        self.doPause(self.is_paused)

    def playPause(self):
        if self.is_paused:
            self.unPause()
        else:
            self.pause()

    @safecb
    def error(self, err):
        e = trapException(err)
        if e == CancelledError:
            trace('Cancelled')
        else:
            trace('ERROR:', err)

    def event(self, what):
        if what == EV_START:
            trace('START')
            self.show()
        elif what == EV_PLAY:
            self.popup()
        if what == EV_PAUSE:
            self.show()
        elif what == EV_END:
            trace('END %s/%s' % (self.getPlayPos(), self.getLength()))
            self.is_playing = False
            if self.atTheEnd() or self.getLength() < 0:
                self.stop(RET_END)
            else:
                trace('Suspect connection error')
                self.reconnect()

    def reconnect(self):
        pid = settingsRepo.vod_player_id
        if pid != 5002:
            return
        self.deleteFailScreen()
        self.fails += 1
        if self.fails > 3:
            self.fail_screen = self.session.instantiateDialog(MessageBox, _('No connection to streaming server!'), type=MessageBox.TYPE_ERROR)
            return
        trace('reconnect! fails(%s)' % self.fails)
        self.want_pos = self.getPlayPos() / 90000 - 5
        self.play()
        self.fail_screen = self.session.instantiateDialog(MessageBox, _('Reconnecting to server...'), type=MessageBox.TYPE_WARNING)

    def deleteFailScreen(self):
        if self.fail_screen is not None:
            self.session.deleteDialog(self.fail_screen)
            self.fail_screen = None
        return

    def atTheEnd(self):
        return float(self.getPlayPos()) / float(self.getLength()) > 0.9

    def onStart(self):
        trace('onStart')
        self.event(EV_START)

    def onStop(self):
        trace('onStop')

    def onSOF(self):
        trace('onSOF')

    def onEnd(self):
        trace('onEnd')

    def onEOF(self):
        trace('onEOF')
        self.event(EV_END)

    def onUpdateInfo(self):
        trace('onUpdateInfo')
        if not (self.canSeek() and self.getLength() > 0):
            trace('cant seek yet')
            return
        if self.want_pos > 0:
            pos = max(self.want_pos - 15, 0)
            self.want_pos = 0
            trace('now at', self.getPlayPos(), 'seek to', pos * 90000)
            self.doSeek(pos * 90000)
        elif not self.play_sent:
            self.event(EV_PLAY)
            self.play_sent = True

    def doPlay(self, sref, pos):
        self.want_pos = pos
        self.play_sent = False
        self.session.nav.playService(sref)
        self.updateLabels()
        self.tick_timer.start(1000)

    def doStop(self):
        self.tick_timer.stop()
        self.session.nav.stopService()

    def doPause(self, pause):
        service = self.session.nav.getCurrentService()
        if service is None:
            return False
        else:
            pauseable = service.pause()
            if pauseable is None:
                return False
            if pause:
                pauseable.pause()
                self.event(EV_PAUSE)
            else:
                pauseable.unpause()
                self.event(EV_PLAY)
            return

    def canSeek(self):
        return self.getSeek() is not None

    def doSeek(self, pts):
        seek = self.getSeek()
        trace('doSeek', seek, pts)
        if seek is None:
            return
        else:
            seek.seekTo(min(max(0, pts), self.getLength() - 1))
            self.event(EV_PLAY)
            return

    def getPlayPos(self):
        seek = self.getSeek()
        if seek:
            p = seek.getPlayPosition()
            if not p[0]:
                return p[1]
        return 0

    def getLength(self):
        seek = self.getSeek()
        if seek:
            ret = seek.getLength()
            if not ret[0]:
                return ret[1] + 1
        return -1

    def updateLabels(self):
        if self.getLength() > 0:
            tot = self.getLength() / 90000
            pos = self.getPlayPos() / 90000
            self['progress'].setValue(1000 * pos / tot)
        else:
            tot = 0
            pos = 0
            self['progress'].setValue(1000)
        self['time'].setText('%d:%02d:%02d / %d:%02d:%02d' % (pos / 3600,
         pos / 60 % 60,
         pos % 60,
         tot / 3600,
         tot / 60 % 60,
         tot % 60))

    def getSeek(self):
        service = self.session.nav.getCurrentService()
        if service is None:
            return
        else:
            seek = service.seek()
            if seek is None or not seek.isCurrentlySeekable():
                return
            return seek


class VideosSeek(Screen):
    TIMEOUT = 3000

    def __init__(self, session, time, length, moveCallback):
        Screen.__init__(self, session)
        self.skinName = 'TVSeek'
        self['text'] = Label()
        self['actions'] = ActionMap(['OkCancelActions', 'DirectionActions'], {'ok': self.commitTime,
         'cancel': self.quit,
         'up': lambda : self.seekAction(+10),
         'down': lambda : self.seekAction(-10)}, -1)
        trace(time, length)
        self.time0 = time
        self.time = time
        self.length = length
        self.moveCallback = moveCallback
        self.timer = eTimer()
        self.timer.callback.append(self.commitTime)

    def setDiff(self, diff):
        self.time += diff
        self.updateDiff()

    def updateDiff(self):
        self.time = max(0, min(self.length, self.time))
        self.updateTime()
        self.timer.start(self.TIMEOUT)
        self.moveCallback(self.time)

    def updateTime(self):
        pos = self.time
        diff = self.time - self.time0
        trace(pos, diff)
        self['text'].setText('%d:%02d:%02d (%+02d:%02d)' % (pos / 3600,
         pos / 60 % 60,
         pos % 60,
         diff / 60,
         diff % 60))

    def commitTime(self):
        self.timer.stop()
        self.close(self.time)

    def seekAction(self, diff):
        self.time += diff
        self.updateDiff()

    def quit(self):
        self.timer.stop()
        self.close(None)
        return