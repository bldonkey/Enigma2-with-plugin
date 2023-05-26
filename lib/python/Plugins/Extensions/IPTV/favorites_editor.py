# Embedded file name: src/favorites_editor.py

try:
    from typing import List, Any
except ImportError:
    pass

from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen
from Tools.Directories import SCOPE_SKIN, resolveFilename
from Tools.LoadPixmap import LoadPixmap
from enigma import gFont, eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_CENTER
from .api import Api, Group, Channel
from .cache import iconCache
from .chlist import GroupsListPanel
from .colors import colors
from .common import ListBox, CallbackReceiver
from .layer import SCALE
from .loc import translate as _
empty_icon = LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/logo.png'))

class SimpleChannelsListPanel(object):

    def __init__(self, ui, db):
        super(SimpleChannelsListPanel, self).__init__()
        self.db = db
        self.listbox = ui['channelsList'] = ListBox([])
        self.listbox.l.setFont(0, gFont('TVSansRegular', 26))
        self.listbox.l.setBuildFunc(self.makeEntry)
        ui['actions_channels'] = self.actions = ActionMap(['TListActions'], {'up': self.listbox.up,
         'down': self.listbox.down,
         'pageUp': self.listbox.pageUp,
         'pageDown': self.listbox.pageDown}, -1)

    def setGroup(self, group):
        self.listbox.setList([ (c,) for c in group.channels ])
        self.listbox.moveToIndex(0)

    star_icon = LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/star.png'))

    def makeEntry(self, channel):
        if channel.has_archive:
            col = colors['ared']
        else:
            col = None
        icon = LoadPixmap(iconCache.get(channel.icon))
        if icon is None:
            icon = empty_icon
        star = None
        if channel.is_favorite:
            star = self.star_icon
        return [channel,
         (eListboxPythonMultiContent.TYPE_TEXT,
          5,
          0,
          50,
          63,
          0,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          str(channel.number),
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
          433,
          63,
          0,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          channel.title),
         (eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND,
          619,
          15,
          27,
          27,
          star,
          colors['bgplane'],
          colors['bgsel'])]

    def getSelectedChannel(self):
        """
        :rtype: Channel | None
        """
        entry = self.listbox.getCurrent()
        return entry and entry[0]

    def moveEntryUp(self):
        listbox = self.listbox
        index = listbox.getSelectedIndex()
        if index == 0:
            return
        listbox.list[index - 1], listbox.list[index] = listbox.list[index], listbox.list[index - 1]
        listbox.l.invalidateEntry(index - 1)
        listbox.l.invalidateEntry(index)
        listbox.up()

    def moveEntryDown(self):
        listbox = self.listbox
        index = listbox.getSelectedIndex()
        if index + 1 == len(listbox.list):
            return
        listbox.list[index], listbox.list[index + 1] = listbox.list[index + 1], listbox.list[index]
        listbox.l.invalidateEntry(index)
        listbox.l.invalidateEntry(index + 1)
        listbox.down()

    def getList(self):
        return [ item[0] for item in self.listbox.list ]

    def setActive(self, active):
        self.actions.setEnabled(active)
        self.listbox.selectionEnabled(active)


class TVFavoritesEditor(Screen, CallbackReceiver):

    def __init__(self, session, db):
        super(TVFavoritesEditor, self).__init__(session)
        self.skinName = 'TVChannels'
        self.db = db
        self['caption'] = Label(self.db.title)
        self['header'] = Label(_('Groups'))
        self.channels = SimpleChannelsListPanel(self, self.db)
        self.groups = GroupsListPanel(self, self.groupChanged)
        self['actions'] = ActionMap(['OkCancelActions', 'DirectionActions'], {'ok': self.ok,
         'cancel': self.cancel,
         'left': self.left,
         'right': self.right}, -1)
        self['ordering_actions'] = ActionMap(['TSortActions', 'ColorActions'], {'moveUp': self.moveUp,
         'moveDown': self.moveDown,
         'red': self.moveUp,
         'green': self.moveDown})
        self['ordering_actions'].setEnabled(False)
        self.main_active = True
        self.onFirstExecBegin.append(self.start)

    def start(self):
        self.groups.setActive(False)
        self.groups.setGroups(self.db.groups)
        idx = 1
        self.groups.moveToIndex(idx)
        self.setGroup(self.db.groups[idx])

    def groupChanged(self, group, keyUp = False):
        pass

    def setGroup(self, group):
        self.channels.setGroup(group)
        self.groups.mark(group)
        self['caption'].setText('%s / %s' % (self.db.title, group.title))
        self['ordering_actions'].setEnabled(group.alias == 'FAVORITES')

    def ok(self):
        if self.main_active:
            channel = self.channels.getSelectedChannel()
            if channel is not None:
                self.toggleFavorite(channel)
        else:
            g = self.groups.getSelectedGroup()
            if g is not None:
                self.setGroup(g)
        return

    def toggleFavorite(self, channel):
        if channel.is_favorite:
            self.db.rmFavouriteChannel(channel)
        else:
            self.db.addFavouriteChannel(channel)
        group = self.groups.getMarkedGroup()
        if group.alias == 'FAVORITES':
            i = self.channels.listbox.getSelectionIndex()
            self.setGroup(group)
            self.channels.listbox.moveToIndex(max(0, i - 1))
        else:
            i = self.channels.listbox.getSelectionIndex()
            self.channels.listbox.l.invalidateEntry(i)

    def cancel(self):
        self.close()

    def left(self):
        if not self.main_active:
            self.groups.setActive(False)
            self.channels.setActive(True)
            self.main_active = True

    def right(self):
        if self.main_active:
            self.channels.setActive(False)
            self.groups.setActive(True)
            self.main_active = False

    def moveUp(self):
        self.channels.moveEntryUp()
        self._storeFavorites()

    def moveDown(self):
        self.channels.moveEntryDown()
        self._storeFavorites()

    def _storeFavorites(self):
        self.db.setFavoritesChannels(self.channels.getList())