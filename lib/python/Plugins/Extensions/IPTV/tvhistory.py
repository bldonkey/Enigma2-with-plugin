# Embedded file name: src/tvhistory.py

try:
    from typing import List, Any, Dict
except ImportError:
    pass

from datetime import datetime
from twisted.internet.defer import CancelledError
from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen
from Tools.Directories import resolveFilename, SCOPE_SKIN
from Tools.LoadPixmap import LoadPixmap
from enigma import gFont, eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_CENTER, RT_WRAP
from .base import trapException, describeException
from .common import CallbackReceiver, ListBox, safecb
from .loc import translate as _
from .system import MessageBox
from .updater import fatalError
from .utils import secTd, trace
from .program import Program
from .api import Api
from .history_model import HistoryEntry
live_pic = LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/icon_live.png'))
rec_pic = LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/icon_archive.png'))

class TVHistory(Screen, CallbackReceiver):

    def __init__(self, session, db, history):
        Screen.__init__(self, session)
        CallbackReceiver.__init__(self)
        self.listbox = ListBox([])
        self.listbox.l.setFont(0, gFont('TVSansRegular', 29))
        self['list'] = self.listbox
        self['header'] = Label(_('Watch history'))
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions', 'THistoryActions'], {'ok': self.ok,
         'cancel': self.exit,
         'openHistory': self.exit,
         'blue': self.ok}, -1)
        self.setTitle(_('History'))
        self.onFirstExecBegin.append(self.start)
        self.history = history
        self.db = db
        trace('History:', self.history)

    def start(self):
        toload = []
        for h in self.history:
            if h.time is None:
                toload.append(h.cid)

        time = datetime.now() - secTd(self.db.time_shift * 3600)
        self.db.epgCurrentList(toload, time).addCallback(self.showList).addErrback(self.error).addErrback(fatalError)
        return

    @safecb
    def showList(self, epg_data):
        entries = []
        for h in reversed(self.history):
            if h.time is None:
                program = epg_data.get(h.cid, None)
                time = self.db.now(self.db.channels[h.cid])
                if program and not program.isAt(time):
                    program = None
            else:
                program = h.epg
            entries.append(self.makeEntry(h, self.db.channels[h.cid].title, program, h.time or self.db.now(self.db.channels[h.cid]), h.time is not None))

        self.listbox.setList(entries)
        return

    @staticmethod
    def makeEntry(h, title, epg, time, archive):
        """
        :param HistoryEntry h: internal data
        :param str title: channel title
        :param Program|None epg: program to show
        :param datetime time: play time within program range
        :param bool archive: show rec symbol
        :return: list entry
        """
        entry = [h]
        if archive:
            entry.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND,
             4,
             11,
             19,
             19,
             rec_pic))
        else:
            entry.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND,
             4,
             11,
             19,
             19,
             live_pic))
        if epg:
            text = '%s (%s)' % (title, epg.title)
            entry.append((eListboxPythonMultiContent.TYPE_PROGRESS,
             646,
             11,
             114,
             19,
             epg.percent(time, 100)))
        else:
            text = title
        entry.append((eListboxPythonMultiContent.TYPE_TEXT,
         32,
         0,
         600,
         40,
         0,
         RT_HALIGN_LEFT | RT_VALIGN_CENTER | RT_WRAP,
         text))
        return entry

    def ok(self):
        h = self.listbox.getSelected()
        i = self.listbox.getSelectionIndex()
        if h is None:
            return
        else:
            del self.history[len(self.history) - i - 1]
            self.close(h)
            return

    def exit(self):
        self.close(None)
        return

    @safecb
    def error(self, err):
        e = trapException(err)
        if e == CancelledError:
            trace('Cancelled')
        else:
            trace('ERROR:', err)
            self.session.open(MessageBox, describeException(err), MessageBox.TYPE_ERROR, timeout=5)