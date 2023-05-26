# Embedded file name: src/tvplayer.py

try:
    from typing import Optional, Tuple, Dict, Any, Callable, TYPE_CHECKING
    if TYPE_CHECKING:
        from .chlist import TVChannels
except ImportError:
    pass

from datetime import datetime
from Components.ActionMap import NumberActionMap, ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Slider import Slider
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from enigma import iPlayableService, eServiceReference
from .api import Channel, Api
from .base import trapException, APIException, describeException, wasCancelled
from .cache import iconCache
from .history_model import HistoryEntry
from .tvhistory import TVHistory
from .common import AutoHideScreen, safecb, CallbackReceiver
from .layer import eTimer
from .loc import translate as _
from .notify import UpdateMessageHandler, expireNotifier, updateNotifier
from .settings import TVEnterPassword
from .settings_model import AudioMap, AudioMapEntry
from .system import MessageBox
from .updater import fatalError
from .utils import secTd, tdSec, trace
from .tvinfo import TVProgramInfo
from .home_menu import HomeMenuOpener
from .settings_model import settingsRepo
from .standby import PowerOffMenu, standbyManager
MODE_LIST, MODE_INFO, MODE_SEEK = list(range(3))

class NumberEnter(Screen):
    TIMEOUT = 1800

    def __init__(self, session, number):
        Screen.__init__(self, session)
        self.skinName = 'NumberZap'
        self['channel'] = Label(_('Channel:'))
        self['number'] = Label(str(number))
        self['actions'] = NumberActionMap(['SetupActions'], {'cancel': self.exit,
         'ok': self.keyOK,
         '1': self.keyNumberGlobal,
         '2': self.keyNumberGlobal,
         '3': self.keyNumberGlobal,
         '4': self.keyNumberGlobal,
         '5': self.keyNumberGlobal,
         '6': self.keyNumberGlobal,
         '7': self.keyNumberGlobal,
         '8': self.keyNumberGlobal,
         '9': self.keyNumberGlobal,
         '0': self.keyNumberGlobal})
        self.timer = eTimer()
        self.timer.callback.append(self.keyOK)
        self.timer.start(self.TIMEOUT)

    def exit(self):
        self.timer.stop()
        self.close(None)
        return

    def keyOK(self):
        self.timer.stop()
        self.close(int(self['number'].text))

    def keyNumberGlobal(self, number):
        self.timer.start(self.TIMEOUT)
        self['number'].text += str(number)
        if len(self['number'].text) > 5:
            self.keyOK()


class TVArchiveIcon(Screen):

    def __init__(self, session):
        super(TVArchiveIcon, self).__init__(session)
        self['play'] = Pixmap()
        self['pause'] = Pixmap()
        self._is_archive = False

    def show(self):
        if self._is_archive:
            Screen.show(self)
        else:
            self.hide()

    def showLive(self):
        self._is_archive = False
        self.hide()

    def showPlayArchive(self):
        self._is_archive = True
        self['play'].show()
        self['pause'].hide()

    def showPause(self):
        self._is_archive = True
        self['play'].hide()
        self['pause'].show()


class TVSeek(Screen):
    TIMEOUT = 3000

    def __init__(self, session, time, time_range, moveCallback):
        Screen.__init__(self, session)
        self['text'] = Label()
        self['actions'] = ActionMap(['OkCancelActions', 'DirectionActions'], {'ok': self._commitTime,
         'cancel': self.cancel,
         'up': self.seekRightShort,
         'down': self.seekLeftShort}, -1)
        self.time = time
        self.time_range = time_range
        self.diff = 0
        self.live = False
        self.moveCallback = moveCallback
        self.timer = eTimer()
        self.timer.callback.append(self._commitTime)

    def setRange(self, begin, end):
        self.time_range = (begin, end)
        self._updateTime()

    def clearRange(self):
        self.time_range = None
        self._updateTime()
        return

    def getTime(self):
        return self.time + secTd(self.diff)

    def updateDiff(self, delta):
        max_diff = tdSec(datetime.now() - secTd(ARCHIVE_DELAY) - self.time)
        if self.diff + delta < max_diff:
            self.diff += delta
            self.live = False
        else:
            self.live = True
        self._updateTime()
        self.timer.start(self.TIMEOUT)
        self.moveCallback(self.getTime())

    def _updateTime(self):
        if self.live:
            self['text'].setText('LIVE')
            return
        else:
            if self.diff % 60 > 0:
                diff_str = '%+02d:%02d' % (self.diff / 60, self.diff % 60)
            else:
                diff_str = '%+02d %s' % (self.diff / 60, _('min'))
            if self.time_range is None:
                self['text'].setText(diff_str)
            else:
                pos = tdSec(self.time + secTd(self.diff) - self.time_range[0])
                pos_str = '%d:%02d:%02d' % (pos / 3600, pos / 60 % 60, pos % 60)
                self['text'].setText('%s (%s)' % (pos_str, diff_str))
            return

    def _commitTime(self):
        self.timer.stop()
        self.close((self.live, self.getTime()))

    def seekLeft(self, delta):
        self.updateDiff(-delta)

    def seekRight(self, delta):
        self.updateDiff(+delta)

    def seekLeftShort(self):
        self.updateDiff(-10)

    def seekRightShort(self):
        self.updateDiff(+10)

    def cancel(self):
        self.timer.stop()
        self.close(None)
        return


class TVInfoBar(Screen):

    def __init__(self, session, db):
        super(TVInfoBar, self).__init__(session)
        self.skinName = 'TVInfoBar'
        self.db = db
        self['picon'] = Pixmap()
        self['number'] = Label()
        self['rec'] = Pixmap()
        self['title'] = Label()
        self['curName'] = Label()
        self['curTime'] = Label()
        self['nxtName'] = Label()
        self['nxtTime'] = Label()
        self['progress'] = Slider(0, 1000)
        self['progress'].setValue(0)
        self['recPlay'] = Pixmap()
        self['recPlay'].hide()
        self['recPause'] = Pixmap()
        self['recPause'].hide()
        self.archive_info_screen = self.session.instantiateDialog(TVArchiveIcon)
        self.onShow.append(self.archive_info_screen.hide)
        self.onHide.append(self.archive_info_screen.show)
        self.onClose.append(lambda : self.session.deleteDialog(self.archive_info_screen))

    def showChannel(self, channel, number):
        self['number'].setText(str(number))
        self['title'].setText(channel.title)
        self['picon'].instance.setPixmap(LoadPixmap(iconCache.get(channel.icon)))

    def showProgress(self, cur, time):
        self['curTime'].setText('%d %%' % cur.percent(time, 100))
        self['progress'].setValue(cur.percent(time, 1000))

    def showProgram(self, cur, nxt, time):
        trace('show program %s; %s;' % (cur, nxt))
        if cur is None:
            self['curName'].setText('')
            self['curTime'].setText('')
            self['progress'].setValue(0)
        else:
            fake_time = self.db.shiftTime(cur.begin)
            self['curName'].setText('%s -  %s' % (fake_time.strftime('%H:%M'), cur.title))
            self.showProgress(cur, time)
        if nxt is None:
            self['nxtName'].setText('')
        else:
            fake_time = self.db.shiftTime(nxt.begin)
            self['nxtName'].setText('%s -  %s' % (fake_time.strftime('%H:%M'), nxt.title))
        return

    def showLoading(self):
        self['curName'].setText(_('Loading...'))
        self['curTime'].setText('')
        self['nxtName'].setText('')
        self['nxtTime'].setText('')

    def showArchiveStatus(self, isArchive, paused):
        if isArchive:
            if not paused:
                self.archive_info_screen.showPlayArchive()
                self['recPlay'].show()
                self['recPause'].hide()
            else:
                self.archive_info_screen.showPause()
                self['recPlay'].hide()
                self['recPause'].show()
            if not self.shown:
                self.archive_info_screen.show()
        else:
            self.archive_info_screen.showLive()
            self['recPlay'].hide()
            self['recPause'].hide()


class TVPlayer(TVInfoBar, HomeMenuOpener, UpdateMessageHandler, AutoHideScreen, CallbackReceiver):
    ALLOW_SUSPEND = False

    def __init__(self, session, parent, db):
        super(TVPlayer, self).__init__(session, db)
        CallbackReceiver.__init__(self)
        self.subscribeNotifier(expireNotifier.onNotify)
        self.subscribeNotifier(updateNotifier.onNotify)
        ServiceEventTracker.setActiveInfoBar(self, None, None)
        self.parent = parent
        self.db = db
        self.seek = None
        self['actions'] = ActionMap(['OkCancelActions',
         'ColorActions',
         'TChannelActions',
         'TPluginActions',
         'THistoryActions'], {'ok': lambda : self.quit('list'),
         'cancel': self.infoHide,
         'nextChannel': lambda : self.channelUpDown(+1),
         'prevChannel': lambda : self.channelUpDown(-1),
         'info': self.info,
         'nextProgram': self.nextProgram,
         'prevProgram': self.prevProgram,
         'openHistory': self.showHistory,
         'stop': self.goToLive,
         'power': self.standBy,
         'powerMenu': self.openPowerMenu,
         'play': self.unPause,
         'pause': self.pause,
         'playpause': self.playPause,
         'red': lambda : self.quit('settings'),
         'green': lambda : self.quit('plugins'),
         'yellow': lambda : self.quit('video'),
         'blue': lambda : self.quit('enigma')}, -2)
        self['actions_seek'] = ActionMap(['TSeekActions'], {'seekRight': self.seekRight,
         'seekLeft': self.seekLeft,
         'seekFwd': self.seekFwd,
         'seekRwd': self.seekRwd,
         'seekFwdLong': self.seekFwdLong,
         'seekRwdLong': self.seekRwdLong})
        self['NumberActions'] = NumberActionMap(['NumberActions'], {'1': self.keyNumber,
         '2': self.keyNumber,
         '3': self.keyNumber,
         '4': self.keyNumber,
         '5': self.keyNumber,
         '6': self.keyNumber,
         '7': self.keyNumber,
         '8': self.keyNumber,
         '9': self.keyNumber,
         '0': self.keyNumber})
        self['actions_audio'] = ActionMap(['InfobarAudioSelectionActions', 'InfobarSubtitleSelectionActions'], {'audioSelection': self.audioSelection,
         'subtitleSelection': self.audioSelection})
        self['actions_video'] = ActionMap(['TVideoModeActions'], {'vmode': self.videoModeSelection})
        self.close_reason = None
        self.history = settingsRepo.history
        self.history.removeInvalid(self.db.channels)
        self.onClose.append(self.histSave)
        self.channel = None
        self.paused = False
        self.time = None
        self.channel_play_path = None
        self.playTimer = eTimer()
        self.playTimer.callback.append(self.playTick)
        self.defer_url = None
        self.epg = None
        self.epg_defer = None
        self.epgTimer = eTimer()
        self.epgTimer.callback.append(self.updateProgram)
        self.epgProgressTimer = eTimer()
        self.epgProgressTimer.callback.append(self.updateProgress)
        self.mode = MODE_INFO
        self.onClose.append(self.stop)
        self.protect_pin = None
        self.audio_map = self.audioLoad()
        self.onClose.append(self.audioSave)
        self.audio_selected = False
        self._event_tracker_audio = ServiceEventTracker(screen=self, eventmap={iPlayableService.evUpdatedInfo: self.audioSelect,
         iPlayableService.evStart: self.audioClear})
        self.fails = 0
        self.fail_screen = None
        self._event_tracker_player = ServiceEventTracker(screen=self, eventmap={iPlayableService.evEOF: self.playerEnded,
         iPlayableService.evUpdatedInfo: self.playerConnected})
        self.onClose.append(self.deleteFailScreen)
        standbyManager.onStandby.append(self.handleStandby)
        self.onClose.append(lambda : standbyManager.onStandby.remove(self.handleStandby))
        return

    def audioSelection(self):

        def save(i):
            service = self.session.nav.getCurrentService()
            audio = service and service.audioTracks()
            if not audio:
                return
            else:
                if i is not None and i < audio.getNumberOfTracks():
                    info = audio.getTrackInfo(i)
                    lang = info.getLanguage()
                    cid = self.channel.id
                    self.audio_map[cid] = AudioMapEntry(lang, i)
                return

        from .audio import AudioMenu
        self.session.openWithCallback(save, AudioMenu)

    def audioSelect(self):
        if self.audio_selected:
            return
        self.audio_selected = True
        cid = self.channel.id
        try:
            choice = self.audio_map[cid]
        except KeyError:
            return

        trace('set audio', choice.lang)
        service = self.session.nav.getCurrentService()
        audio = service and service.audioTracks()
        if not audio:
            return
        n = audio.getNumberOfTracks()
        if n > 0:
            i = audio.getCurrentTrack()
            if audio.getTrackInfo(i).getLanguage() == choice.lang:
                return
            for i in range(n):
                info = audio.getTrackInfo(i)
                if info.getLanguage() == choice.lang:
                    audio.selectTrack(i)
                    choice.idx = i
                    break

    def audioClear(self):
        self.audio_selected = False

    def audioLoad(self):
        return settingsRepo.audio

    def audioSave(self):
        settingsRepo.audio = AudioMap(self.audio_map)
        settingsRepo.storeConfig()

    def videoModeSelection(self):
        from .system import TVideoMode
        self.session.open(TVideoMode)

    def updateProgress(self, time = None):
        if time is None:
            time = self.getTime()
        if self.epg is not None:
            self.showProgress(self.epg, time)
        return

    def setMode(self, mode):
        self.mode = mode

    def getTime(self):
        if self.time:
            return self.time
        else:
            return self.db.now(self.channel)

    def playTick(self):
        trace('tick')
        self.time += secTd(TICK / 1000)

    def play(self, channel, time, skip_history = False):
        trace('play', channel.id, time)
        if channel == self.channel and time == self.time and not self.paused:
            return
        else:
            if not skip_history:
                self.histAppend()
            self.channel = channel
            self.time = time
            self.paused = False
            self.channel_play_path = self.parent.getPlayPath()
            self.session.nav.stopService()
            self.playTimer.stop()
            self.showChannel(self.channel, self.parent.getChannelNumber())
            self.popup()
            self.updateProgram()
            self.showArchiveStatus(self.time is not None, paused=False)
            if self.channel.protected:
                if self.protect_pin is not None:
                    self.getUrl(pin=self.protect_pin)
                else:
                    self.askPassword()
            else:
                self.protect_pin = None
                self.getUrl(pin=None)
            return

    def askPassword(self, ret = None):
        self.session.openWithCallback(self.getUrl, TVEnterPassword)

    def getUrl(self, pin):
        if self.channel.protected and pin is None:
            return
        else:
            if pin is not None:
                self.popup()
                self.protect_pin = pin
            if self.defer_url is not None:
                self.defer_url.cancel()
            self.defer_url = self.db.getStreamUrl(self.channel.id, pin, self.time)
            self.defer_url.addCallback(self.playUrl).addErrback(self.urlError)
            self.defer_url.addErrback(fatalError)
            return

    @safecb
    def urlError(self, err):
        e = trapException(err)
        if e == APIException and err.value.code == 'URL_PROTECTED':
            self.protect_pin = None
            self.session.openWithCallback(self.askPassword, MessageBox, _('Wrong password!'), MessageBox.TYPE_WARNING, timeout=10, enable_input=False)
        else:
            self.error(err)
        return

    @safecb
    def playUrl(self, url):
        trace('PLAY:', url)
        pid = settingsRepo.player_id
        sref = eServiceReference(pid, 0, self._addAudioToUrl(pid, url))
        sref.setName(self.channel.title)
        self.session.nav.playService(sref)
        if self.time:
            self.playTimer.start(TICK)

    def _addAudioToUrl(self, player, url):
        try:
            choice = self.audio_map[self.channel.id]
        except KeyError:
            return url

        if player == 5002:
            return url + '#sapp_audio_id=%d' % choice.idx
        else:
            return url

    def playerEnded(self):
        trace('player EOF')
        pid = settingsRepo.player_id
        if pid != 5002:
            return
        else:
            self.deleteFailScreen()
            self.fails += 1
            if self.fails > 3:
                self.fail_screen = self.session.instantiateDialog(MessageBox, _('No connection to streaming server!'), type=MessageBox.TYPE_ERROR)
                return
            trace('reconnect! fails(%s)' % self.fails)
            self.paused = True
            if self.time is not None:
                self.time -= secTd(60)
            self.play(self.channel, self.time, skip_history=True)
            self.fail_screen = self.session.instantiateDialog(MessageBox, _('Reconnecting to server...'), type=MessageBox.TYPE_WARNING)
            return

    def playerConnected(self):
        trace('player UpdateInfo')
        self.fails = 0
        self.deleteFailScreen()

    def deleteFailScreen(self):
        if self.fail_screen is not None:
            self.session.deleteDialog(self.fail_screen)
            self.fail_screen = None
        return

    def updateProgram(self):
        trace('update program')
        time = self.getTime()
        self.epg = None
        self.epgTimer.stop()
        self.epgProgressTimer.stop()
        cur, nxt = self.channel.epgcache.find(time)
        if cur and nxt:
            return self.epgShow((cur, nxt))
        else:
            trace('load epg')
            self.showLoading()
            if self.epg_defer is not None:
                self.epg_defer.cancel()
            if self.time is None:
                self.epg_defer = self.db.epgCurrent(self.channel, time)
            else:
                self.epg_defer = self.db.epgArchive(self.channel, time)
            self.epg_defer.addCallback(self.epgShow).addErrback(self.epgError).addErrback(fatalError)
            return

    @safecb
    def epgShow(self, result):
        cur, nxt = result
        self.epg = cur
        time = self.getTime()
        self.showProgram(cur, nxt, time)
        if cur:
            self.epgTimer.start(cur.timeLeftm(time) + 100)
            self.epgProgressTimer.start(5000)
            self.popup()

    def pause(self):
        if self.paused:
            return
        elif self.time is None and self.db.getTimeShift() == 0:
            return
        else:
            if self.channel.has_archive:
                service = self.session.nav.getCurrentService()
                pauseable = service and service.pause()
                if pauseable:
                    pauseable.pause()
                else:
                    self.session.nav.stopService()
                self.playTimer.stop()
                self.epgTimer.stop()
                self.epgProgressTimer.stop()
                self.paused = True
                if self.time is None:
                    self.time = self.db.now(self.channel)
                self.lockShow()
                self.showArchiveStatus(self.time is not None, paused=True)
            else:
                self.session.open(MessageBox, _("This channel doesn't have archive, pause not possible!"), MessageBox.TYPE_WARNING, timeout=5)
            return

    def unPause(self):
        if not self.paused:
            return
        self.play(self.channel, self.time, skip_history=True)

    def playPause(self):
        if self.paused:
            self.unPause()
        else:
            self.pause()

    def nextProgram(self):
        if self.epg is None or not self.channel.has_archive:
            trace('cant seek')
            return
        else:
            time = self.epg.end
            if time < datetime.now() - secTd(ARCHIVE_DELAY):
                self.play(self.channel, time)
            return

    def prevProgram(self):
        if self.epg is None or not self.channel.has_archive:
            trace('cant seek')
            return
        else:
            if self.epg_defer is not None:
                self.epg_defer.cancel()
            self.epg_defer = self.db.epgArchive(self.channel, self.epg.begin - secTd(1))
            self.epg_defer.addCallback(self.epgPrev).addErrback(self.epgError)
            return

    @safecb
    def epgPrev(self, result):
        cur, nxt = result
        self.play(self.channel, cur.begin)

    def startSeek(self, delta):
        if not self.channel.has_archive:
            trace('channel cant seek')
            return
        elif self.epg is None:
            trace('cant seek')
            return
        else:
            self.epgTimer.stop()
            self.epgProgressTimer.stop()
            time = self.getTime()
            if self.epg:
                time_range = (self.epg.begin, self.epg.end)
            else:
                time_range = None
            self.active_components.remove(self['actions_seek'])
            self.seek = self.session.openWithCallback(self.endSeek, TVSeek, time, time_range, self.updateSeekPos)
            self.seek.updateDiff(delta)
            self.setMode(MODE_SEEK)
            self.lockShow()
            return

    def endSeek(self, ret):
        self.seek = None
        self.setMode(MODE_INFO)
        trace('seek to', ret)
        if ret is None:
            self.updateProgram()
        else:
            live, time = ret
            self.play(self.channel, not live and time or None, skip_history=True)
        return

    def updateSeekPos(self, time):
        trace('update seek pos', time)
        if self.epg is None:
            return
        else:
            if self.epg.begin <= time < self.epg.end:
                self.updateProgress(time)
            else:
                self.seek['actions'].setEnabled(False)
                if self.epg_defer is not None:
                    self.epg_defer.cancel()
                self.epg_defer = self.db.epgArchive(self.channel, time)
                self.epg_defer.addCallback(self.epgShowSeek).addErrback(self.epgError)
            return

    @safecb
    def epgShowSeek(self, result):
        cur, nxt = result
        self.epg = cur
        if cur:
            self.seek.setRange(cur.begin, cur.end)
        else:
            self.seek.clearRange()
        self.showProgram(cur, nxt, self.seek.getTime())
        self.seek['actions'].setEnabled(True)

    def seekDelta(self, delta):
        if self.seek is not None:
            if delta > 0:
                self.seek.seekRight(delta)
            else:
                self.seek.seekLeft(abs(delta))
        else:
            self.startSeek(delta)
        return

    def seekLeft(self):
        self.seekDelta(-60)

    def seekRight(self):
        self.seekDelta(+1 * 60)

    def seekRwd(self):
        self.seekDelta(-300)

    def seekRwdLong(self):
        self.seekDelta(-600)

    def seekFwd(self):
        self.seekDelta(+5 * 60)

    def seekFwdLong(self):
        self.seekDelta(+10 * 60)

    def goToLive(self):
        if self.time is None:
            return
        else:
            self.play(self.channel, None)
            cb = lambda ret: self.popup()
            self.session.openWithCallback(cb, MessageBox, _('Live mode'), MessageBox.TYPE_INFO, timeout=4)
            return

    @safecb
    def epgError(self, err):
        if self.mode == MODE_SEEK:
            self.seek['actions'].setEnabled(True)
        self.error(err)

    @safecb
    def error(self, err):
        trapException(err)
        if wasCancelled(err):
            trace('Cancelled')
        elif self.execing:
            self.session.open(MessageBox, describeException(err), MessageBox.TYPE_ERROR, timeout=5)

    def stop(self):
        trace('player stop')
        self.session.nav.stopService()

    def quit(self, reason):
        trace('infobar close(reason=%s)' % reason)
        self.close_reason = reason
        self.close()

    def channelUpDown(self, delta):
        channel = self.parent.channelUpDown(delta)
        if channel is not None:
            self.play(channel, None)
        return

    def keyNumber(self, number):
        self.session.openWithCallback(self.numberEntered, NumberEnter, number)

    def numberEntered(self, number):
        trace('numberEntered', number)
        if number is None:
            return
        else:
            channel = self.parent.goToNumber(number)
            if channel is not None:
                self.play(channel, None)
            else:
                self.session.open(MessageBox, _('No channel with number %d') % number, MessageBox.TYPE_WARNING, timeout=5)
            return

    def info(self):
        if not self.shown:
            self.lockShow()
        elif self.epg is not None:
            self.openInfoScreen(self.epg)
        else:
            self.infoHide()
        return

    def infoHide(self):
        self.hide()

    def openInfoScreen(self, program):
        self.session.openWithCallback(self.infoHide, TVProgramInfo, program)

    def menuClosed(self, ret):
        if ret is not None:
            self.quit(ret)
        return

    def showHistory(self):

        def cb(entry):
            if entry is not None:
                self.histPlay(entry)
            return

        self.session.openWithCallback(cb, TVHistory, self.db, self.history.getList())

    def histAppend(self):
        if self.channel and not self.channel.protected:
            entry = HistoryEntry(self.channel_play_path, self.channel.id, self.time, self.epg)
            self.history.append(entry)

    def histPlay(self, state):
        channel = self.db.channels[state.cid]
        self.parent.goToHistory(state)
        self.play(channel, state.time)

    def histSave(self):
        settingsRepo.history = self.history
        settingsRepo.storeConfig()

    def powerOff(self):
        self.session.nav.stopService()
        sref = eServiceReference(1, 0, '')
        self.session.nav.playService(sref)
        if self.time is None or self.channel.protected:
            self.playTimer.stop()
            self.paused = True
            if self.channel.protected:
                self.channel = self.parent.goToFirst()
                self.showChannel(self.channel, self.parent.getChannelNumber())
                self.showProgram(None, None, self.getTime())
            self.epgTimer.stop()
            self.epgProgressTimer.stop()
        else:
            self.pause()
        return

    def powerOn(self):
        if self.time is None:
            self.play(self.channel, None)
        else:
            self.unPause()
        return

    def handleStandby(self, sleep):
        if sleep:
            self.powerOff()
        else:
            self.powerOn()

    def standBy(self):
        standbyManager.enterStandby(self.session)

    def openPowerMenu(self):
        self.session.open(PowerOffMenu)


ARCHIVE_DELAY = 1 * 60
TICK = 1 * 1000