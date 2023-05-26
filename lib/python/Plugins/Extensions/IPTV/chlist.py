# Embedded file name: src/chlist.py

try:
    from typing import List, Callable, Optional, Tuple, Any, Union, Protocol

    class GroupCallback(Protocol):

        def __call__(self, group, keyUp = False):
            raise NotImplementedError()


    class ChannelCallback(Protocol):

        def __call__(self, channel, keyUp = False):
            raise NotImplementedError()


except ImportError:
    pass

from Components.Slider import Slider
from Screens.Screen import Screen
from Components.Pixmap import Pixmap
from Components.ActionMap import ActionMap
from Components.Label import Label
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, SCOPE_SKIN
from enigma import ePoint, eLabel, eSize
from enigma import gFont
from enigma import eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_HALIGN_CENTER, RT_VALIGN_CENTER, RT_WRAP
from datetime import datetime, timedelta
from .cache import iconCache
from .epg import LiveEpgCache
from .loc import translate as _
from .api import Api, Channel, Group
from .layer import eTimer, SCALE
from .common import fatalError, safecb, ListBox, CallbackReceiver, Debounce
from .base import trapException
from .utils import tdSec, secTd
from .program import Program
from .system import MessageBox
from .tvplayer import TVPlayer, ARCHIVE_DELAY
from .utils import toDate, trace
from .home_menu import HomeMenuOpener
from .colors import colors
from .standby import standbyNotifier
from .langlist import AudioLanguageList
from .chlist_model import ChannelsModel, EmptyListError
from .history_model import HistoryEntry
from .settings_model import settingsRepo, PlayState
folder_icon = LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/folder.png'))
folder_open_icon = LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/folder_open.png'))

class GroupsListPanel(object):
    ICON_PATH = resolveFilename(SCOPE_SKIN, 'IPTV/icons/groups/') + '%s.png'

    def __init__(self, ui, selectionChangedCallback):
        self.ui = ui
        self.selectionChangedCallback = selectionChangedCallback
        self.ui['groupsList'] = self.listbox = ListBox([])
        self.listbox.l.setFont(0, gFont('TVSansRegular', 25))
        self.listbox.l.setFont(1, gFont('TVSansBold', 25))
        self.listbox.onSelectionChanged.append(self.selectionChanged)
        ui['actions_groups'] = self.actions = ActionMap(['TListActions'], {'up': self.listbox.up,
         'down': self.listbox.down,
         'pageUp': self.listbox.pageUp,
         'pageDown': self.listbox.pageDown,
         'keyReleased': self.keyUp}, -1)
        self._marked_index = None
        return

    def keyUp(self):
        group = self.listbox.getSelected()
        self.selectionChangedCallback(group, keyUp=True)

    def setGroups(self, groups):
        self.listbox.setList([ self.makeEntry(g) for g in groups ])
        self._marked_index = None
        return

    def makeEntry(self, group, marked = False):
        if marked:
            icon = folder_open_icon
            font = 1
        else:
            icon = folder_icon
            font = 0
        return [group, (eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND,
          14,
          8,
          44,
          33,
          icon), (eListboxPythonMultiContent.TYPE_TEXT,
          75,
          5,
          477,
          40,
          font,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          group.title)]

    def mark(self, group):
        if self._marked_index is not None:
            g = self.listbox.list[self._marked_index][0]
            self.listbox.updateEntry(self._marked_index, self.makeEntry(g))
        if group is not None:
            for i, entry in enumerate(self.listbox.list):
                if entry[0] == group:
                    self.listbox.updateEntry(i, self.makeEntry(group, True))
                    self._marked_index = i
                    return

        self._marked_index = None
        return

    def getMarkedGroup(self):
        if self._marked_index is not None:
            return self.listbox.list[self._marked_index][0]
        else:
            return

    def selectionChanged(self):
        group = self.listbox.getSelected()
        self.selectionChangedCallback(group)

    def getSelectedGroup(self):
        return self.listbox.getSelected()

    def moveToIndex(self, index):
        self.listbox.moveToIndex(index)

    def setActive(self, active):
        self.actions.setEnabled(active)
        self.listbox.selectionEnabled(active)

    def show(self):
        self.ui['groupsList'].show()

    def hide(self):
        self.ui['groupsList'].hide()


col_mark = colors['fgsel']
empty_icon = LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/logo.png'))

class ChannelsListPanel(object):

    def __init__(self, ui, db, worker, selectionChangedCallback):
        super(ChannelsListPanel, self).__init__()
        self.db = db
        self.worker = worker
        self.selectionChangedCallback = selectionChangedCallback
        worker.onUpdate.append(self.updateEpgData)
        ui.onClose.append(lambda : worker.onUpdate.remove(self.updateEpgData))
        self._marked_id = None
        self._marked_index = None
        self._fonts = [gFont('TVSansRegular', 26), gFont('TVSansBold', 26)]
        self._font_calc = []
        self.listbox = ui['channelsList'] = ListBox([])
        self.listbox.l.setFont(0, self._fonts[0])
        self.listbox.l.setFont(1, self._fonts[1])
        self.listbox.l.setFont(2, gFont('TVSansRegular', 23))
        self.listbox.l.setBuildFunc(self.makeEntry)
        self.listbox.onSelectionChanged.append(self.selectionChanged)
        ui.onClose.append(lambda : self.listbox.onSelectionChanged.remove(self.selectionChanged))
        self._debounced = Debounce(self.selectionChangedFinal, 1000)
        ui['actions_channels'] = self.actions = ActionMap(['TListActions'], {'up': self.listbox.up,
         'down': self.listbox.down,
         'pageUp': self.listbox.pageUp,
         'pageDown': self.listbox.pageDown,
         'keyReleased': self.keyUp}, -1)
        ui.onLayoutFinish.append(self.initFontCalc)
        self._timer = eTimer()
        self._timer.callback.append(self.updateEpgData)
        self._progressTimer = eTimer()
        self._progressTimer.callback.append(self.updateProgramsProgress)
        self._progressTimer.start(300000)
        ui.onClose.append(self._stopTimers)
        return

    def initFontCalc(self):
        sz = self.listbox.instance.size()
        for i, font in enumerate(self._fonts):
            fc = eLabel(self.listbox.instance)
            fc.setFont(font)
            fc.resize(eSize(956, 95))
            fc.move(ePoint(sz.width() + 10, sz.height() + 10))
            fc.setNoWrap(1)
            self._font_calc.append(fc)

    def calculateWidth(self, txt, font):
        fc = self._font_calc[font]
        fc.setText(txt)
        return int(round(fc.calculateSize().width()))

    def keyUp(self):
        self._debounced.immediateCall()

    def setGroup(self, group):
        entries = [ (c, self.worker.getCurrent(c.id, self.db.now(c)), i + 1) for i, c in enumerate(group.channels) ]
        self.listbox.setList(entries)
        self.listbox.moveToIndex(0)

    def updateEpgData(self, values = None):
        next_update = datetime.now() + timedelta(days=1)
        for i, (channel, program, index) in enumerate(self.listbox.list):
            t = self.db.now(channel)
            if program is None or not program.isAt(t):
                program = self.worker.getCurrent(channel.id, t)
                self.listbox.updateEntry(i, (channel, program, index))
            if program is not None:
                next_update = min(next_update, program.end)

        self._timer.start(tdSec(next_update - datetime.now()))
        return

    def updateProgramsProgress(self):
        self.listbox.setList(self.listbox.list)

    def _stopTimers(self):
        self._timer.stop()
        self._progressTimer.stop()
        self._debounced.stop()

    def makeEntry(self, channel, program, index):
        if channel.id == self._marked_id:
            font = 1
        else:
            font = 0
        w = self.calculateWidth(channel.title, font)
        t = datetime.now()
        if channel.has_archive:
            col = colors['ared']
        else:
            col = None
        fgcol = colors['white']
        bgcol = colors['gray']
        if program is None:
            program = Program(t, t + timedelta(days=1), 'No Info', '', False)
        icon = LoadPixmap(iconCache.get(channel.icon))
        if icon is None:
            icon = empty_icon
        return [(channel, program, index),
         (eListboxPythonMultiContent.TYPE_TEXT,
          5,
          0,
          50,
          63,
          0,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          str(index),
          col,
          col),
         (eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND,
          58,
          8,
          61,
          48,
          icon,
          colors['bgplane'],
          colors['bgsel'],
          SCALE),
         (eListboxPythonMultiContent.TYPE_TEXT,
          123,
          0,
          w,
          63,
          font,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          channel.title),
         (eListboxPythonMultiContent.TYPE_TEXT,
          140 + w,
          0,
          437 - w,
          63,
          2,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          program.title),
         (eListboxPythonMultiContent.TYPE_PROGRESS,
          590,
          25,
          60,
          9,
          program.percent(t, 100),
          0,
          fgcol,
          fgcol,
          bgcol,
          bgcol)]

    def getSelectedChannel(self):
        entry = self.listbox.getCurrent()
        return entry and entry[0]

    def markSelected(self, mark = True):
        prev_marked = self._marked_id
        selected = self.getSelectedChannel()
        if mark and selected is not None:
            self._marked_id = selected.id
        else:
            self._marked_id = None
        if prev_marked is not None:
            for i, (channel, program, index) in enumerate(self.listbox.list):
                if channel.id == prev_marked or channel.id == self._marked_id:
                    self.listbox.updateEntry(i, (channel, program, index))

        return

    def selectionChanged(self):
        self.selectionChangedCallback(self.getSelectedChannel())
        self._debounced.call()

    def selectionChangedFinal(self):
        channel = self.getSelectedChannel()
        self.selectionChangedCallback(channel, keyUp=True)

    def moveToIndex(self, index):
        self.listbox.moveToIndex(index)

    def setActive(self, active):
        self.actions.setEnabled(active)
        self.listbox.selectionEnabled(active)


class BaseProgramsComponent(object):

    def __init__(self, listbox, db):
        super(BaseProgramsComponent, self).__init__()
        self.listbox = listbox
        self.db = db
        self.onLoading = []

    def makeEntry(self, program):
        t = self.db.shiftTime(program.begin)
        if program.has_archive:
            color = colors['ared']
        else:
            color = None
        return [program, (eListboxPythonMultiContent.TYPE_TEXT,
          3,
          0,
          67,
          39,
          0,
          RT_HALIGN_CENTER | RT_VALIGN_CENTER,
          t.strftime('%H:%M'),
          color,
          color), (eListboxPythonMultiContent.TYPE_TEXT,
          79,
          1,
          385,
          37,
          0,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER | RT_WRAP,
          program.title)]

    def showLoading(self, show):
        for f in self.onLoading:
            f(show)

    def getSelectedProgram(self):
        return self.listbox.getSelected()


class ProgramsListComponent(BaseProgramsComponent, CallbackReceiver):

    def __init__(self, listbox, db):
        super(ProgramsListComponent, self).__init__(listbox, db)
        self.db = db
        self._shown = True
        self._pending = None
        self.channel = None
        self.defer = None
        self.data = []
        self._idx = 0
        self.isUpdating = False
        self.timer = eTimer()
        self.timer.callback.append(self.updateEpgList)
        return

    def stop(self):
        if self.defer:
            self.defer.cancel()
        self.timer.stop()

    def clean(self):
        self._clean(clear_ui=True)

    def _clean(self, clear_ui):
        self.stop()
        if clear_ui:
            self.listbox.setList([])

    def setChannelAndTime(self, channel, time):
        self.stop()
        self.channel = channel
        begin, end = self.getRangeForTime(time)
        if self._shown:
            self._load(begin, end, time, center=True)
        else:
            self._pending = (begin, end, time)

    @staticmethod
    def getRangeForTime(time):
        begin = min(toDate(time), time - secTd(18000))
        end = max(toDate(time) + timedelta(days=1), time + secTd(18000))
        return (begin, end)

    @staticmethod
    def adjustProgramsList(data, index):
        """Cut programs from the beginning to put data[index] in the middle of the page"""
        page_size = 11
        start = (index % page_size - 6) % page_size
        if index > start:
            return (data[start:], index - start)
        else:
            return (data, index)

    @safecb
    def listReady(self, data, center, toFind):
        trace('listReady: center', center)
        self.showLoading(False)
        for i, p in enumerate(data):
            if p.end > toFind:
                break
        else:
            i = 0

        if center and i + 1 != len(data):
            data, i = self.adjustProgramsList(data, i)
        self.data = data
        self.listbox.setList([ self.makeEntry(item) for item in self.data ])
        self.listbox.moveToIndex(i)
        t = self.db.now(self.channel)
        for program in data:
            if program.isAt(t):
                self.timer.startLongTimer(program.timeLeft(t) + 1)
                break

    def updateEpgList(self):
        trace('updateEpgList')
        epg = self.getSelectedProgram()
        if epg is None:
            return
        else:
            time = epg.begin
            begin, end = self.getRangeForTime(time)
            self._load(begin, end, time, clear_ui=False)
            self.setChannelAndTime(self.channel, epg.begin)
            return

    def _load(self, begin, end, toFind, center = False, clear_ui = True):
        """Load programs in (begin, end) range and move selection to toFind when ready"""
        trace('load programs', begin, end)
        self.showLoading(True)
        self._clean(clear_ui)
        self.defer = self.db.rangeEpg(self.channel.id, begin, end)
        self.defer.addCallback(self.listReady, center, toFind).addErrback(self.error).addErrback(fatalError)

    def pageUp(self):
        idx = self.listbox.getSelectionIndex()
        if idx == 0:
            self.prevPage()
        else:
            self.listbox.pageUp()
            self.selectionChanged()

    def pageDown(self):
        idx = self.listbox.getSelectionIndex()
        if idx == len(self.listbox.list) - 1:
            self.nextPage()
        else:
            self.listbox.pageDown()
            self.selectionChanged()

    def up(self):
        idx = self.listbox.getSelectionIndex()
        if idx == 0:
            self.prevPage()
        else:
            self.listbox.up()
            self.selectionChanged()

    def down(self):
        idx = self.listbox.getSelectionIndex()
        if idx == len(self.listbox.list) - 1:
            self.nextPage()
        else:
            self.listbox.down()
            self.selectionChanged()

    def prevPage(self):
        if not self.data:
            return
        t = self.data[0].begin
        t0 = toDate(t)
        if tdSec(t - t0) > 18000:
            begin = t0
            end = t0 + timedelta(days=1)
        else:
            begin = t0 - timedelta(days=1)
            end = t
        self._load(begin, end, t - secTd(1))

    def nextPage(self):
        if not self.data:
            return
        t = self.data[-1].end
        t0 = toDate(t)
        if tdSec(t0 + timedelta(days=1) - t) > 18000:
            begin = t0
            end = t0 + timedelta(days=1)
        else:
            begin = t0
            end = t0 + timedelta(days=2)
        self._load(begin, end, t + secTd(1))

    def prevDay(self):
        epg = self.listbox.getSelected()
        if epg is None:
            return
        else:
            t0 = toDate(epg.begin) - timedelta(days=1)
            self._load(t0, t0 + timedelta(days=1), t0)
            return

    def nextDay(self):
        epg = self.listbox.getSelected()
        if epg is None:
            return
        else:
            t0 = toDate(epg.begin) + timedelta(days=1)
            self._load(t0, t0 + timedelta(days=1), t0)
            return

    def selectionChanged(self):
        pass

    def storeState(self):
        self._idx = self.listbox.getSelectedIndex()

    def recoverState(self):
        self.listbox.setList([ self.makeEntry(item) for item in self.data ])
        self.listbox.moveToIndex(self._idx)

    @safecb
    def error(self, err):
        trapException(err)
        trace('ERROR:', err)


class SearchSimilarComponent(BaseProgramsComponent, CallbackReceiver):

    def __init__(self, listbox, db):
        super(SearchSimilarComponent, self).__init__(listbox, db)
        self.data = []
        self._title = None
        self._cid = None
        self.defer = None
        return

    def stop(self):
        try:
            pass
        except AttributeError:
            pass

    def setChannelAndTitle(self, cid, title):
        self._cid = cid
        self._title = title
        t = datetime.now()
        d = self.db.rangeEpg(self._cid, t - timedelta(days=10), t + timedelta(days=10))
        d.addCallback(self.find).addErrback(self.error).addErrback(fatalError)

    @safecb
    def find(self, data):
        trace('search', self._title)
        words = self._title.split()
        if not words:
            return
        if len(words[0]) < 3:
            s = ' '.join(words[:2])
        else:
            s = words[0]
        result = []
        for e in data:
            if e.title.startswith(s):
                result.append(e)

        self.setData(result)

    def setData(self, data):
        trace('found', data)
        self.data = data
        self.listbox.setList([ self.makeEntry(item) for item in self.data ])

    def pageUp(self):
        self.listbox.pageUp()

    def pageDown(self):
        self.listbox.pageDown()

    def up(self):
        self.listbox.up()

    def down(self):
        self.listbox.down()

    def prevDay(self):
        p = self.getSelectedProgram()
        if p is None:
            return
        else:
            t0 = toDate(p.begin) - timedelta(days=1)
            self._focusOn(t0)
            return

    def nextDay(self):
        p = self.getSelectedProgram()
        if p is None:
            return
        else:
            t0 = toDate(p.begin) + timedelta(days=1)
            self._focusOn(t0)
            return

    def _focusOn(self, time):
        for i, p in enumerate(self.data):
            if p.end > time:
                break
        else:
            i = 0

        self.listbox.moveToIndex(i)

    @safecb
    def error(self, err):
        trapException(err)
        trace('error:', err)


class ProgramsPanel(object):

    def __init__(self, ui, db):
        super(ProgramsPanel, self).__init__()
        self.db = db
        self.ui = ui
        self.ui['programsList'] = self.listbox = ListBox([])
        self.listbox.l.setFont(0, gFont('TVSansRegular', 23))
        self.listbox.onSelectionChanged.append(self.selectionChanged)
        self.ui['descriptionLabel'] = Label()
        self.ui['loading'] = Label(_('Loading...'))
        self._programs = ProgramsListComponent(self.listbox, db)
        self._similar_programs = SearchSimilarComponent(self.listbox, db)
        for component in (self._programs, self._similar_programs):
            component.onLoading.append(self.showLoading)

        self._in_similar_mode = False
        self._component = self._programs
        self._shown = True
        ui['actions_programs'] = self.actions = ActionMap(['TListActions', 'TEpgListActions'], {'up': lambda : self._component.up(),
         'down': lambda : self._component.down(),
         'pageUp': lambda : self._component.pageUp(),
         'pageDown': lambda : self._component.pageDown(),
         'nextDay': lambda : self._component.nextDay(),
         'prevDay': lambda : self._component.prevDay()}, -1)
        self.ui.onClose.extend([self._programs.stopCallbacks,
         self._programs.stop,
         self._similar_programs.stopCallbacks,
         self._similar_programs.stop])

    def selectionChanged(self):
        epg = self.getSelectedProgram()
        if epg:
            self.ui['programDate'].setText(epg.begin.strftime('%a %d/%m/%Y'))
            self.ui['descriptionLabel'].setText(epg.description)
        else:
            self.ui['descriptionLabel'].setText('')

    def getSelectedProgram(self):
        return self._component.getSelectedProgram()

    def clean(self):
        self._component.stop()

    def setChannelAndTime(self, channel, time):
        trace('setChannelAndTime', channel, time)
        self.ui['channelName'].setText(channel.title)
        if self._in_similar_mode:
            self.toggleSimilar()
        self._component.setChannelAndTime(channel, time)

    def setActive(self, active):
        self.actions.setEnabled(active)
        self.listbox.selectionEnabled(active)

    def showLoading(self, show):
        if self._shown and show:
            self.ui['loading'].show()
        else:
            self.ui['loading'].hide()

    def show(self):
        self._shown = True
        self.listbox.show()
        for w in ['channelName',
         'programDate',
         'line1',
         'descriptionLabel']:
            self.ui[w].show()

    def hide(self):
        self._shown = False
        self.listbox.hide()
        for w in ['channelName',
         'programDate',
         'line1',
         'descriptionLabel',
         'loading']:
            self.ui[w].hide()

    def toggleSimilar(self):
        self._component.stop()
        if self._in_similar_mode:
            self._component = self._programs
            self._programs.recoverState()
        else:
            epg = self.getSelectedProgram()
            if epg is None:
                return
            self._component = self._similar_programs
            self._programs.storeState()
            self._similar_programs.setChannelAndTitle(self._programs.channel.id, epg.title)
        self._in_similar_mode = not self._in_similar_mode
        return


class InfoViewModel(object):

    def __init__(self, db, worker):
        self.db = db
        self.worker = worker
        self.onChanged = []
        self._channel = None
        self._timer = eTimer()
        self._timer.callback.append(self._update)
        self.worker.onUpdate.append(self._updateIfChanged)
        return

    def destroy(self):
        self.worker.onUpdate.remove(self._updateIfChanged)
        self._timer.stop()

    def getTime(self):
        return self.db.now(self._channel)

    def setChannel(self, channel):
        self._channel = channel
        if channel is not None:
            self._update()
        else:
            self._timer.stop()
            self._notify([])
        return

    def _update(self):
        t = self.getTime()
        ps = self.worker.getCurrentFollowing(self._channel.id, t)
        if len(ps):
            self._timer.start(int((ps[0].end - datetime.now()).total_seconds() * 1000) + 1)
        else:
            self._timer.stop()
        self._notify(ps)

    def _updateIfChanged(self, cids):
        if self._channel and self._channel.id in cids:
            self._update()

    def _notify(self, ps):
        for f in self.onChanged:
            f(ps)


class InfoPanel(object):

    def __init__(self, ui, db, worker):
        self.ui = ui
        ui['programTitle'] = Label()
        ui['programStart'] = Label()
        ui['programEnd'] = Label()
        ui['programProgress'] = Slider(0, 1000)
        ui['programDescription'] = Label()
        ui['line2'] = Label()
        ui['nextList'] = self.listbox = ListBox([])
        self.listbox.l.setFont(0, gFont('TVSansRegular', 22))
        self.ui_elements = ('channelName', 'programDate', 'line1', 'programTitle', 'programStart', 'programEnd', 'programProgress', 'programDescription', 'line2', 'nextList')
        self._title_height = 0
        self._desc_top = 0
        self._desc_height = 0
        self._widget_top = {}
        self._widget_list = ('programStart', 'programProgress', 'programEnd')
        self.ui.onLayoutFinish.append(self._initLayout)
        self.model = InfoViewModel(db, worker)
        self.model.onChanged.append(self.update)
        self.ui.onClose.append(self.model.destroy)

    def showProgramInfo(self, program, time):
        self.ui['programDate'].setText(program.begin.strftime('%a %d/%m/%Y'))
        self.ui['programTitle'].setText(program.title)
        self.ui['programStart'].setText(program.begin.strftime('%H:%M'))
        self.ui['programEnd'].setText(program.end.strftime('%H:%M'))
        self.ui['programProgress'].setValue(program.percent(time, 1000))
        self.ui['programDescription'].setText(program.description)
        self._updateLayout()

    def showNextPrograms(self, programs):
        self.listbox.setList([ self.makeEntry(p) for p in programs ])
        self.listbox.selectionEnabled(False)

    def _initLayout(self):
        self._title_height = self.ui['programTitle'].instance.size().height()
        self._desc_top = self.ui['programDescription'].instance.position().y()
        self._desc_height = self.ui['programDescription'].instance.size().height()
        for k in self._widget_list:
            self._widget_top[k] = self.ui[k].instance.position().y()

    def _updateLayout(self):
        title_widget = self.ui['programTitle'].instance
        desc_widget = self.ui['programDescription'].instance
        height = min(title_widget.calculateSize().height(), self._title_height * 4)
        dh = height - self._title_height
        title_widget.resize(eSize(title_widget.size().width(), height))
        desc_widget.move(ePoint(desc_widget.position().x(), self._desc_top + dh))
        desc_widget.resize(eSize(desc_widget.size().width(), self._desc_height - dh))
        for k in self._widget_list:
            widget = self.ui[k].instance
            widget.move(ePoint(widget.position().x(), self._widget_top[k] + dh))

    @staticmethod
    def makeEntry(program):
        return [program, (eListboxPythonMultiContent.TYPE_TEXT,
          0,
          3,
          67,
          32,
          0,
          RT_HALIGN_LEFT,
          program.begin.strftime('%H:%M')), (eListboxPythonMultiContent.TYPE_TEXT,
          67,
          3,
          410,
          30,
          0,
          RT_HALIGN_LEFT,
          program.title)]

    def clean(self):
        self.ui['programDate'].setText('')
        self.ui['programTitle'].setText('')
        self.ui['programStart'].setText('')
        self.ui['programEnd'].setText('')
        self.ui['programProgress'].setValue(0)
        self.ui['programDescription'].setText('')

    def setChannel(self, channel):
        if channel is not None:
            self.ui['channelName'].setText(channel.title)
        else:
            self.ui['channelName'].setText('')
        self.model.setChannel(channel)
        return

    def update(self, ps):
        if len(ps):
            self.showProgramInfo(ps[0], self.model.getTime())
        else:
            self.clean()
        self.showNextPrograms(ps[1:])

    def setActive(self, active):
        pass

    def show(self):
        for w in self.ui_elements:
            self.ui[w].show()

    def hide(self):
        for w in self.ui_elements:
            self.ui[w].hide()


class TVChannels(HomeMenuOpener):
    MODE_INFO, MODE_ARCHIVE, MODE_GROUPS = list(range(3))

    def __init__(self, session, groups, playstate, db):
        super(TVChannels, self).__init__(session)
        self.db = db
        self.worker = LiveEpgCache(db)
        self.worker.startUpdate()
        self.onClose.append(self.worker.stop)
        standbyNotifier.onStandbyChanged.append(self.suspendWorker)
        self.onClose.append(lambda : standbyNotifier.onStandbyChanged.remove(self.suspendWorker))
        self.player = self.session.instantiateDialog(TVPlayer, self, self.db)
        self['caption'] = Label(self.db.title)
        self['header'] = Label()
        self['channelName'] = Label()
        self['programDate'] = Label()
        self['line1'] = Label()
        self.channels = ChannelsListPanel(self, self.db, self.worker, self.channelChanged)
        self.info = InfoPanel(self, self.db, self.worker)
        self.programs = ProgramsPanel(self, self.db)
        self.groups = GroupsListPanel(self, self.groupChanged)
        self.mode = self.MODE_INFO
        self.programs.hide()
        self.groups.hide()
        self.main_active = True
        self.programs.setActive(False)
        self.groups.setActive(False)
        self['circle0'] = Pixmap()
        self['circle1'] = Pixmap()
        self['circle2'] = Pixmap()
        self['circle_active'] = Pixmap()
        self.model = ChannelsModel(self.db, groups)
        try:
            self.groups_data = self.model.filterByLanguage(settingsRepo.audio_filter)
        except EmptyListError:
            self.groups_data = self.model.filterByLanguage('ALL')
            settingsRepo.audio_filter = 'ALL'

        self['actions'] = ActionMap(['OkCancelActions',
         'DirectionActions',
         'ColorActions',
         'InfobarAudioSelectionActions',
         'InfobarSubtitleSelectionActions',
         'TPluginActions',
         'THistoryActions',
         'TSearchActions'], {'ok': self.ok,
         'cancel': self.cancel,
         'left': self.left,
         'right': self.right,
         'openHistory': self.searchSimilar,
         'audioSelection': self.selectLanguage,
         'subtitleSelection': self.selectLanguage}, -1)
        default_path = (1, 0)
        if playstate is not None:
            self.saved_path = self.model.findPath(playstate) or default_path
            self.saved_time = playstate.time
        else:
            self.saved_path = default_path
            self.saved_time = None
        self.onFirstExecBegin.append(self.start)
        self.onShown.append(self.listOpened)
        return

    def suspendWorker(self, sleep):
        if sleep:
            self.worker.suspend()
        else:
            self.worker.startUpdate()

    def start(self):
        self.groups.setGroups(self.groups_data)
        if self.saved_path is not None:
            self.recoverState(self.saved_path, self.saved_time)
            channel = self.channels.getSelectedChannel()
            if channel is None:
                return
            self.session.execDialog(self.player)
            self.player.play(channel, self.saved_time)
            self.channels.markSelected()
        return

    def quit(self, ret):
        trace('Quit channels, return', ret)
        self.onShown.remove(self.listOpened)
        if self.saved_path is not None:
            g_idx, c_idx = self.saved_path
            g = self.groups_data[g_idx]
            settingsRepo.play_state = PlayState(g.id, g.channels[c_idx].id, self.saved_time)
            settingsRepo.storeConfig()
        self.session.deleteDialog(self.player)
        self.close(ret)
        return

    def searchSimilar(self):
        if not self.main_active and self.mode == self.MODE_ARCHIVE:
            self.programs.toggleSimilar()

    def selectLanguage(self):
        if self.main_active:
            self.session.openWithCallback(self.setLanguage, AudioLanguageList, self.db)

    def setLanguage(self, lang):
        if lang is None:
            return
        else:
            try:
                self.groups_data = self.model.filterByLanguage(lang)
                settingsRepo.audio_filter = lang
                self.groups.setGroups(self.groups_data)
                self.setGroup(self.groups.getSelectedGroup())
            except EmptyListError:
                self.session.open(MessageBox, _('No channels found with language %s.') % lang, MessageBox.TYPE_INFO, timeout=5)

            return

    def groupChanged(self, group, keyUp = False):
        pass

    def channelChanged(self, channel, keyUp = False):
        trace('channelChanged', channel, 'keyUp=%s' % keyUp)
        if channel is None:
            self.programs.clean()
            self.info.setChannel(None)
            return
        else:
            if keyUp:
                self.programs.setChannelAndTime(channel, self.db.now(channel))
            else:
                self.programs.clean()
                self.info.setChannel(channel)
            return

    def highlightCircle(self, n):
        pos = self['circle%d' % n].instance.position()
        self['circle_active'].instance.move(pos)
        self['header'].setText([_('Now'), _('Teleguide'), _('Groups')][self.mode])

    def setGroup(self, group):
        self.channels.setGroup(group)
        self.groups.mark(group)
        language = self.model.getLanguage()
        if language == 'ALL':
            self['caption'].setText('%s - %s' % (self.db.title, group.title))
        else:
            self['caption'].setText('%s - %s - %s' % (self.db.title, group.title, language))

    def setMode(self, mode):
        trace('setMode', mode)
        panels = [self.info, self.programs, self.groups]
        p = panels[self.mode]
        p.setActive(False)
        p.hide()
        self.mode = mode
        p = panels[self.mode]
        p.show()
        if self.mode == self.MODE_INFO:
            self.activateMainPanel()
        self.highlightCircle(self.mode)

    def activateSecondaryPanel(self):
        self.channels.setActive(False)
        panel = [self.info, self.programs, self.groups][self.mode]
        panel.setActive(True)
        self.main_active = False

    def activateMainPanel(self):
        panel = [self.info, self.programs, self.groups][self.mode]
        panel.setActive(False)
        self.channels.setActive(True)
        self.main_active = True

    def ok(self):
        if self.main_active:
            channel = self.channels.getSelectedChannel()
            if channel is None:
                return
            self.session.execDialog(self.player)
            self.player.play(channel, None)
            self.channels.markSelected()
        elif self.mode == self.MODE_ARCHIVE:
            channel = self.channels.getSelectedChannel()
            if channel is None:
                return
            epg = self.programs.getSelectedProgram()
            if channel.has_archive and epg is not None and epg.begin < datetime.now() - secTd(ARCHIVE_DELAY):
                self.session.execDialog(self.player)
                self.player.play(channel, epg.begin)
                self.channels.markSelected()
        elif self.mode == self.MODE_GROUPS:
            g = self.groups.getSelectedGroup()
            if g is not None:
                self.setGroup(g)
            self.left()
        return

    def cancel(self):
        if self.saved_path is None:
            self.quit('enigma')
        else:
            self.recoverState(self.saved_path, self.saved_time)
            self.session.execDialog(self.player)
            self.player.hide()
        return

    def listOpened(self):
        trace('listOpened')
        ret = self.player.close_reason
        self.player.close_reason = None
        if ret is None:
            return
        else:
            self.saved_path = (self.groups.listbox.getSelectedIndex(), self.channels.listbox.getSelectedIndex())
            self.saved_time = self.player.time
            if ret == 'list':
                channel = self.channels.getSelectedChannel()
                if channel is not None:
                    self.programs.setChannelAndTime(channel, self.player.getTime())
            else:
                self.quit(ret)
            return

    def recoverState(self, play_path, time):
        trace('recover', play_path, time)
        gidx, cidx = play_path
        self.groups.moveToIndex(gidx)
        self.setGroup(self.groups_data[gidx])
        self.channels.moveToIndex(cidx)
        channel = self.channels.getSelectedChannel()
        if channel is None:
            return
        else:
            self.programs.setChannelAndTime(channel, time or self.db.now(channel))
            if time:
                self.setMode(self.MODE_ARCHIVE)
                self.activateSecondaryPanel()
            else:
                self.setMode(self.MODE_INFO)
            return

    def left(self):
        if self.main_active:
            self.setMode((self.mode - 1) % 3)
            if self.mode == self.MODE_INFO:
                self.activateMainPanel()
            else:
                self.activateSecondaryPanel()
        else:
            self.activateMainPanel()

    def right(self):
        if not self.main_active or self.mode == self.MODE_INFO:
            self.setMode((self.mode + 1) % 3)
        if self.mode == self.MODE_INFO:
            self.activateMainPanel()
        else:
            self.activateSecondaryPanel()

    def getPlayPath(self):
        return (self.groups.listbox.getSelectedIndex(), self.channels.listbox.getSelectedIndex())

    def channelUpDown(self, delta):
        if delta > 0:
            self.channels.listbox.up()
        else:
            self.channels.listbox.down()
        self.channels.markSelected()
        return self.channels.getSelectedChannel()

    def goToNumber(self, number, time = None):
        """
        Switch to channel with given index in the group
        Specify time to start archive or live
        """
        g = self.groups.getSelectedGroup()
        gidx = self.groups.listbox.getSelectionIndex()
        cidx = number - 1
        try:
            g.channels[cidx]
        except IndexError:
            return None

        self.recoverState((gidx, cidx), time)
        self.channels.markSelected()
        return self.channels.getSelectedChannel()

    def getChannelNumber(self):
        return self.channels.listbox.getSelectedIndex() + 1

    def goToFirst(self):
        """
        Open first channel in all channels list
        """
        for gidx, g in enumerate(self.groups_data):
            if g.alias == 'ALL':
                self.recoverState((gidx, 0), None)
                self.channels.markSelected()
                return self.channels.listbox.getSelected()

        raise AssertionError('group all not found')
        return

    def goToHistory(self, state):
        """
        Try to navigate to channel from the HistoryEntry, may be ignored if the required channel is filtered out.
        """
        self.channels.markSelected(False)
        if state.path is None:
            return
        else:
            try:
                g = self.groups_data[state.path[0]]
            except IndexError:
                return

            path = self.model.findPath(PlayState(g.id, state.cid, state.time))
            if path:
                self.recoverState(path, state.time)
                self.channels.markSelected()
            return

    def menuClosed(self, ret):
        if ret is not None:
            self.quit(ret)
        return