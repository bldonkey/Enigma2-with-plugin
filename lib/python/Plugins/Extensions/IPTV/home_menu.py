# Embedded file name: src/home_menu.py
try:
    from typing import Optional
except ImportError:
    pass

from Components.ActionMap import ActionMap
from Screens.Screen import Screen
from Tools.Directories import resolveFilename, SCOPE_SKIN
from Tools.LoadPixmap import LoadPixmap
from enigma import eWidget, gFont, eSize, ePixmap, ePoint, eLabel, gRGB
from .grid import Scroll, StaticPlane, PlaneEntry
from .loc import translate as _
from .colors import colors

class EntranceEntry(PlaneEntry):
    width = 188
    height = 112

    def __init__(self, parent):
        self.parent = parent
        self.instance = eWidget(parent)
        self.active = False
        self.col = gRGB(colors['white'])
        self.col_bg = gRGB(colors['darkgray'])
        self.col_sel = gRGB(colors['gridsel'])
        self.font = gFont('TVSansBold', 24)
        self.instance.setBackgroundColor(self.col_bg)
        self.instance.setTransparent(0)
        self.instance.resize(eSize(self.width, self.height))
        self.icon = icon = ePixmap(self.instance)
        icon.setAlphatest(2)
        icon.resize(eSize(self.width, self.height))
        self.txt = txt = eLabel(self.instance)
        txt.setFont(self.font)
        txt.setForegroundColor(self.col)
        txt.setBackgroundColor(self.col_bg)
        txt.setVAlign(txt.alignTop)
        txt.setHAlign(txt.alignCenter)
        txt.setZPosition(1)
        txt.setTransparent(1)
        txt.resize(eSize(self.width, 37))
        txt.move(ePoint(0, 59))

    def setActive(self, active):
        if active == self.active:
            return
        self.active = active
        if active:
            self.txt.setBackgroundColor(self.col_sel)
            self.instance.setBackgroundColor(self.col_sel)
        else:
            self.txt.setBackgroundColor(self.col_bg)
            self.instance.setBackgroundColor(self.col_bg)
        self.instance.invalidate()

    def setData(self, data):
        self.txt.setText(data['title'])
        self.icon.setPixmap(data['pic'])
        self.instance.show()

    def show(self):
        self.instance.show()

    def hide(self):
        self.instance.hide()


class Entrance(Screen):
    _lastIdx = 0

    def __init__(self, session):
        Screen.__init__(self, session)
        self['scroll'] = scroll = Scroll()
        self['container'] = self.cont = StaticPlane(scroll)
        self.cont.onCreated.append(lambda : self.cont.setClass(EntranceEntry, 4, 1))
        self['actions'] = ActionMap(['OkCancelActions', 'DirectionActions', 'MenuActions'], {'ok': self.ok,
         'cancel': self.exit,
         'menu': self.exit,
         'left': self.cont.left,
         'right': self.cont.right}, -2)
        self.onLayoutFinish.append(self.start)

    def start(self):
        prefix = resolveFilename(SCOPE_SKIN, 'IPTV/icons/home/')
        items = [{'alias': 'settings',
          'title': _('Settings'),
          'pic': LoadPixmap(prefix + 'settings.png')},
         {'alias': 'plugins',
          'title': _('Plugins'),
          'pic': LoadPixmap(prefix + 'plugins.png')},
         {'alias': 'video',
          'title': _('Movies'),
          'pic': LoadPixmap(prefix + 'movies.png')},
         {'alias': 'enigma',
          'title': _('Sat TV'),
          'pic': LoadPixmap(prefix + 'enigma.png')}]
        self.cont.setList(items, Entrance._lastIdx)
        self.cont.frame.hide()

    def ok(self):
        i = self.cont.getSelected()
        Entrance._lastIdx = self.cont.getSelectionIndex()
        self.close(i['alias'])

    def exit(self):
        Entrance._lastIdx = 0
        self.close(None)
        return


class HomeMenuOpener(Screen):
    """Helper class to open HomeMenu"""

    def __init__(self, session):
        super(HomeMenuOpener, self).__init__(session)
        self['menu_actions'] = ActionMap(['MenuActions'], {'menu': self.openHomeMenu})

    def openHomeMenu(self):
        self.session.openWithCallback(self.menuClosed, Entrance)

    def menuClosed(self, ret):
        raise NotImplementedError()