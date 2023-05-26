# Embedded file name: src/common.py
"""
common utils for enigma2 plugin, not directly related to api logic
"""

from subprocess import call as os_call
try:
    from typing import Callable
except ImportError:
    pass

from Screens.Screen import Screen
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from enigma import eListboxPythonMultiContent
from .layer import eTimer
from .utils import trace
from .updater import fatalError

class CallbackReceiver(object):

    def __init__(self):
        self._wantCallbacks = True

    def stopCallbacks(self):
        """Function to disable callbacks for classes that don't inherit Screen"""
        del self._wantCallbacks

    def resumeCallbacks(self):
        self._wantCallbacks = True

    def isCallbacksEnabled(self):
        try:
            return self._wantCallbacks
        except AttributeError:
            return False


def safecb(callback):

    def wrapper(obj, *args):
        if obj.isCallbacksEnabled():
            return callback(obj, *args)
        else:
            trace('Ignore late callback', callback)
            return None

    return wrapper


class StaticTextService(StaticText):
    service = property(StaticText.getText, StaticText.setText)


def parseColorInt(s):
    return int(s[1:], 16)


_bg_timer = None

def showBackground():
    global _bg_timer
    return
    try:
        os_call(['showiframe', resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/bg.mvi')])
    except Exception as e:
        trace('Fail to set background', e)
        from enigma import eServiceReference, eTimer
        from NavigationInstance import instance as nav

        def playMp4():
            trace('Set mp4 background')
            sref = eServiceReference(4097, 0, 'file://' + resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/bg.mp4'))
            nav.playService(sref)

        _bg_timer = eTimer()
        _bg_timer.callback.append(playMp4)
        _bg_timer.start(1, True)


class AutoHideScreen(Screen):

    def __init__(self, session):
        super(AutoHideScreen, self).__init__(session)
        self._hide_timer = eTimer()
        self._hide_timer.callback.append(self.hide)

    def popup(self):
        trace('player popup!')
        if self.execing:
            self.show()

    def lockShow(self):
        self.show()
        self._hide_timer.stop()

    def show(self):
        trace('player show!')
        Screen.show(self)
        self._hide_timer.start(5000)

    def hide(self):
        trace('player hide!')
        self._hide_timer.stop()
        Screen.hide(self)


class ListBox(MenuList):
    """
    Adds some common methods to MenuList
    :ivar eListboxPythonMultiContent l:
    """

    def __init__(self, entries, enableWrapAround = True):
        MenuList.__init__(self, entries, enableWrapAround=enableWrapAround, content=eListboxPythonMultiContent)

    def getSelected(self):
        selection = self.getCurrent()
        if selection is not None:
            return selection[0]
        else:
            return

    def updateCurrent(self, entry):
        i = self.l.getCurrentSelectionIndex()
        self.list[i] = entry
        self.l.invalidateEntry(i)

    def updateEntry(self, i, entry):
        self.list[i] = entry
        self.l.invalidateEntry(i)


class Debounce(object):

    def __init__(self, func, interval):
        self._func = func
        self._interval = interval
        self._pending = False
        self._timer = eTimer()
        self._timer.callback.append(self.fire)

    def immediateCall(self):
        self._pending = False
        self._func()
        self._timer.start(self._interval, True)

    def call(self):
        if not self._timer.isActive():
            self._pending = False
            self._func()
            self._timer.start(self._interval, True)
        else:
            self._pending = True
            trace('debounce call')

    def fire(self):
        if self._pending:
            self._pending = False
            self._func()

    def stop(self):
        self._timer.stop()