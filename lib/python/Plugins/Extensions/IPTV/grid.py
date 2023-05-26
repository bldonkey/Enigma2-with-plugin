# Embedded file name: src/grid.py

try:
    from typing import Optional, Type, Tuple
    from six.moves import xrange
except ImportError:
    pass

from Components.GUIComponent import GUIComponent
from Tools.LoadPixmap import LoadPixmap
from enigma import eSlider, ePoint, eWidget, ePixmap, eSize
from .layer import eTimer
from .utils import trace

class Scroll(GUIComponent):
    GUI_WIDGET = eSlider

    def __init__(self):
        GUIComponent.__init__(self)
        self.start = 0
        self.end = 0
        self.size = 1

    def setRange(self, size):
        self.size = size
        self.update()

    def setStartEnd(self, start, end):
        self.start = start
        self.end = end
        self.update()

    def update(self):
        r = self.end - self.start
        if self.size <= r:
            s = 1000
            p = 0
        else:
            s = max(50, 1000 * r / self.size)
            p = (1000 - s) * self.start / (self.size - r)
        if self.instance:
            self.instance.setStartEnd(p, p + s)

    def postWidgetCreate(self, instance):
        instance.setRange(0, 1000)
        self.update()


class PlaneEntry(object):
    """Base class for all grid entries"""
    width = 0
    height = 0
    frame_file = None
    offset = (0, 0)

    def __init__(self, parent):
        pass

    def setActive(self, active):
        raise NotImplementedError()

    def setData(self, data):
        raise NotImplementedError()

    def show(self):
        raise NotImplementedError()

    def hide(self):
        raise NotImplementedError()


class Plane(GUIComponent):
    """
    You may append your handlers to these lists
    :ivar list[() -> None] onCreated:
    :ivar list[(object) -> None] onSelectionChanged:
    :ivar list[PlaneEntry] widgets:
    """

    def __init__(self):
        GUIComponent.__init__(self)
        self.parent = None
        self.frame = None
        self.onCreated = []
        self.onSelectionChanged = []
        self.timer = eTimer()
        self.timer.callback.append(self.doMove)
        self._steps = 0
        self._x = 0
        self._y = 0
        self._dx = 0
        self._dy = 0
        self.Lx = 0
        self.Ly = 0
        self.idx = 0
        self.start = 0
        self.count = 0
        self.view = []
        self.widgets = []
        return

    def getSelected(self):
        try:
            return self.view[self.idx]
        except IndexError:
            return None

        return None

    def getSelectionIndex(self):
        if self.view:
            return self.start + self.idx
        else:
            return None
            return None

    def getRange(self):
        return (self.start, self.start + len(self.widgets))

    def right(self):
        self.widgets[self.idx].setActive(False)
        newidx = self.idx + 1
        if self.start + newidx >= self.count:
            pass
        elif newidx >= len(self.widgets):
            self.start += self.Lx
            self.idx = (self.Ly - 1) * self.Lx
            self.renderList()
        else:
            self.idx = newidx
        self.widgets[self.idx].setActive(True)
        self.moveFrame()

    def left(self):
        self.widgets[self.idx].setActive(False)
        newidx = self.idx - 1
        if self.start + newidx < 0:
            pass
        elif newidx < 0:
            self.start -= self.Lx
            self.idx = self.Lx - 1
            self.renderList()
        else:
            self.idx = newidx
        self.widgets[self.idx].setActive(True)
        self.moveFrame()

    def down(self):
        self.widgets[self.idx].setActive(False)
        newidx = self.idx + self.Lx
        if newidx < len(self.view):
            self.idx = newidx
        elif newidx < len(self.widgets):
            self.idx = len(self.view) - 1
        elif self.start + len(self.widgets) < self.count:
            self.start += self.Lx
            self.idx = min(self.count - 1 - self.start, self.idx)
            self.renderList()
        self.widgets[self.idx].setActive(True)
        self.moveFrame()

    def up(self):
        self.widgets[self.idx].setActive(False)
        newidx = self.idx - self.Lx
        if newidx >= 0:
            self.idx = newidx
        elif self.start > 0:
            self.start -= self.Lx
            self.renderList()
        self.widgets[self.idx].setActive(True)
        self.moveFrame()

    def setClass(self, Item, Lx = 0, Ly = 0):
        trace('Grid setClass', Item, Lx, Ly)
        self.widgets = []
        self.Lx = Lx
        self.Ly = Ly
        sw = Item.width
        sh = Item.height
        total_size = self.instance.size()
        bx = (total_size.width() - Item.width * Lx) / (Lx + 1)
        by = (total_size.height() - Item.height * Ly) / (Ly + 1)
        for i in range(Lx * Ly):
            w = Item(self.instance)
            w.instance.move(ePoint(bx + i % Lx * (sw + bx), by + i / Lx * (sh + by)))
            self.widgets.append(w)

        if Item.frame_file is not None:
            pixmap = LoadPixmap(Item.frame_file)
            self.frame.setPixmap(pixmap)
            self.frame.resize(pixmap.size())
        else:
            self.frame.setPixmap(None)
            self.frame.resize(eSize(0, 0))
        index = self.start + self.idx
        self.idx = index % len(self.widgets)
        self.start = index - self.idx
        self.moveFrame()
        return

    def renderList(self):
        """Override to make this class work"""
        pass

    def GUIcreate(self, parent):
        self.parent = parent
        self.instance = eWidget(parent)
        self.frame = ePixmap(self.instance)
        self.frame.setScale(0)
        self.frame.setAlphatest(2)
        self.frame.setZPosition(2)

    def applySkin(self, desktop, parent):
        super(Plane, self).applySkin(desktop, parent)
        for f in self.onCreated:
            f()

    def GUIdelete(self):
        self.widgets = []
        self.frame = None
        self.instance = None
        return

    def moveFrame(self):
        w = self.widgets[self.idx]
        p = w.instance.position()
        dx, dy = w.offset
        self.frame.move(ePoint(p.x() + dx, p.y() + dy))
        s = self.getSelected()
        for f in self.onSelectionChanged:
            f(s)

    def startMove(self, x, y):
        self._steps = 5
        p = self.frame.position()
        self._x = p.x()
        self._y = p.y()
        self._dx = (x - p.x()) / float(self._steps)
        self._dy = (y - p.y()) / float(self._steps)
        self.timer.start(100)

    def doMove(self):
        self._x += self._dx
        self._y += self._dy
        self.frame.move(ePoint(int(self._x + self._dx), int(self._y + self._dy)))
        self._steps -= 1
        if self._steps == 1:
            self.timer.stop()
        elif self._steps == 3:
            self.widgets[self.idx].setActive(True)


class StaticPlane(Plane):

    def __init__(self, scroll):
        Plane.__init__(self)
        self.scroll = scroll
        self.list = []

    def setList(self, list, index = 0):
        self.list = list
        self.count = len(list)
        self.list = list
        self.widgets[self.idx].setActive(False)
        self.start = index / len(self.widgets)
        self.idx = index % len(self.widgets)
        self.widgets[self.idx].setActive(True)
        if len(self.list) > len(self.widgets):
            self.scroll.setRange(len(self.list))
            self.scroll.show()
        else:
            self.scroll.hide()
        self.renderList()
        self.moveFrame()

    def renderList(self):
        self.view = self.list[self.start:self.start + len(self.widgets)]
        for i in range(len(self.view)):
            self.widgets[i].setData(self.view[i])
            self.widgets[i].show()

        for i in range(len(self.view), len(self.widgets)):
            self.widgets[i].hide()

        self.scroll.setStartEnd(self.start, self.start + len(self.widgets))
        if len(self.view):
            self.frame.show()
        else:
            self.frame.hide()


class DynamicPlane(Plane):

    def __init__(self, viewChangedCallback, scroll):
        Plane.__init__(self)
        self.viewChanged = viewChangedCallback
        self.scroll = scroll

    def clear(self):
        pass

    def setSlice(self, start, index):
        self.widgets[self.idx].setActive(False)
        self.idx = index - start
        self.start = start
        if self.idx >= len(self.widgets):
            self.idx = index % len(self.widgets)
            self.start = index - self.idx
        self.widgets[self.idx].setActive(True)
        self.moveFrame()
        self.view = []
        self.count = 0
        self.renderList()

    def setViewList(self, l, count):
        self.count = count
        if self.count <= len(l):
            self.scroll.hide()
        else:
            self.scroll.setRange(self.count)
            self.scroll.show()
        self.view = l
        for i in range(len(l)):
            self.widgets[i].setData(l[i])
            self.widgets[i].show()

        for i in range(len(l), len(self.widgets)):
            self.widgets[i].hide()

        if len(l):
            self.frame.show()
        else:
            self.frame.hide()
        s = self.getSelected()
        for f in self.onSelectionChanged:
            f(s)

    def renderList(self):
        start, end = self.getRange()
        self.scroll.setStartEnd(start, end)
        self.viewChanged()