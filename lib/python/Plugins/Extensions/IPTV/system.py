# Embedded file name: src/system.py
"""
copied from enigma2
"""

try:
    from typing import Any, Optional
except ImportError:
    pass

from Screens.Screen import Screen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ActionMap import ActionMap
from Components.config import config
from Components.MenuList import MenuList
from enigma import iServiceInformation, ePoint, eSize
from .layer import eTimer
from .utils import trace
from .loc import translate as _

class TVideoMode(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self['videomode'] = Label()
        self['actions'] = ActionMap(['TVideoModeActions'], {'vmode': self.selectVMode})
        self.Timer = eTimer()
        self.Timer.callback.append(self.quit)
        self.selectVMode()

    def selectVMode(self):
        policy = config.av.policy_43
        if self.isWideScreen():
            policy = config.av.policy_169
        idx = policy.choices.index(policy.value)
        idx = (idx + 1) % len(policy.choices)
        policy.value = policy.choices[idx]
        self['videomode'].setText(policy.value)
        self.Timer.start(1000, True)

    def isWideScreen(self):
        from Components.Converter.ServiceInfo import WIDESCREEN
        service = self.session.nav.getCurrentService()
        info = service and service.info()
        return info and info.getInfo(iServiceInformation.sAspect) in WIDESCREEN

    def quit(self):
        self.Timer.stop()
        self.close()


class MessageBox(Screen):
    TYPE_YESNO = 0
    TYPE_INFO = 1
    TYPE_WARNING = 2
    TYPE_ERROR = 3

    def __init__(self, session, text, type = TYPE_YESNO, timeout = -1, enable_input = True, default = True, list = None, title = None):
        Screen.__init__(self, session)
        self.skinName = 'TVMessageBox'
        self['text'] = Label(text)
        self['title'] = Label()
        self['ErrorPixmap'] = Pixmap()
        self['QuestionPixmap'] = Pixmap()
        self['InfoPixmap'] = Pixmap()
        self['WarningPixmap'] = Pixmap()
        if type != self.TYPE_ERROR:
            self['ErrorPixmap'].hide()
        if type != self.TYPE_YESNO:
            self['QuestionPixmap'].hide()
        if type != self.TYPE_INFO:
            self['InfoPixmap'].hide()
        if type != self.TYPE_WARNING:
            self['WarningPixmap'].hide()
        self.type = type
        self.text = text
        if title is None:
            self.title = [_('Question'),
             _('Information'),
             _('Warning'),
             _('Error')][self.type]
        else:
            self.title = title
        self.timerRunning = False
        self.timeout = timeout
        if timeout > 0:
            self.timer = eTimer()
            self.timer.callback.append(self.timerTick)
            self.onExecBegin.append(self.startTimer)
            if self.execing:
                self.timerTick()
            else:
                self.onShown.append(self.__onShown)
            self.timerRunning = True
        else:
            self.timerRunning = False
        list = list or []
        if type == self.TYPE_YESNO:
            if list:
                self.list = list
            elif default:
                self.list = [(_('yes'), True), (_('no'), False)]
            else:
                self.list = [(_('no'), False), (_('yes'), True)]
        else:
            self.list = list
        self['list'] = MenuList(self.list)
        if not self.list:
            self['list'].hide()
        if enable_input:
            self['actions'] = ActionMap(['OkCancelActions', 'DirectionActions'], {'cancel': self.cancel,
             'ok': self.ok,
             'up': self.up,
             'down': self.down,
             'left': self.left,
             'right': self.right}, -1)
        self['title'].setText(self.title)
        self.onLayoutFinish.append(self.autoResize)
        return

    def autoResize(self):
        from enigma import eSize, ePoint, gFont
        try:
            w = self['list'].instance
            w.setFont(gFont('TVSansSemi', 25))
            w.setHAlign(1)
        except AttributeError as e:
            trace('error', e)

        w0 = self.instance.size().width()
        h0 = self.instance.size().height()
        p0 = self.instance.position()
        offset = self['text'].instance.position().y()
        size = self['text'].instance.calculateSize()
        textw = size.width() + 100
        if textw < 380:
            textw = 380
        texth = size.height()
        if texth > 530:
            texth = 530
        trace('Calculated:', (size.width(), size.height()), (textw, texth), (self['text'].instance.size().width(), self['text'].instance.size().height()))
        self['text'].instance.resize(eSize(textw, texth))
        listh = len(self.list) * 60
        if listh > 200:
            listh = 200
        if self.type == self.TYPE_YESNO:
            listw = 65
        else:
            listw = min(textw, 370)
        self['list'].instance.resize(eSize(listw, listh))
        self['list'].instance.move(ePoint(23 + (textw - listw) / 2, offset + texth))
        w = textw + 46
        h = offset + texth + listh + 7
        self.instance.resize(eSize(w, h))
        self.instance.move(ePoint(p0.x() + (w0 - w) / 2, p0.y() + (h0 - h) / 2))

    def __onShown(self):
        self.onShown.remove(self.__onShown)
        self.timerTick()

    def startTimer(self):
        self.timer.start(1000)

    def stopTimer(self):
        if self.timerRunning:
            del self.timer
            self.onExecBegin.remove(self.startTimer)
            self['title'].setText(self.title)
            self.timerRunning = False

    def timerTick(self):
        if self.execing:
            self.timeout -= 1
            self['title'].setText(self.title + ' (' + str(self.timeout) + ')')
            if self.timeout == 0:
                self.timer.stop()
                self.timerRunning = False
                self.timeoutCallback()

    def timeoutCallback(self):
        self.ok()

    def cancel(self):
        self.close(False)

    def ok(self):
        if self.list:
            self.close(self['list'].getCurrent()[1])
        else:
            self.close(True)

    def up(self):
        self.move(self['list'].instance.moveUp)

    def down(self):
        self.move(self['list'].instance.moveDown)

    def left(self):
        self.move(self['list'].instance.pageUp)

    def right(self):
        self.move(self['list'].instance.pageDown)

    def move(self, direction):
        self['list'].instance.moveSelection(direction)
        self.stopTimer()

    def __repr__(self):
        return str(type(self)) + '(' + self.text + ')'


class ChoiceList(Screen):

    def __init__(self, session, choices, value = None, title = ''):
        Screen.__init__(self, session)
        self.skinName = 'TVChoiceBox'
        self['list'] = self.listbox = MenuList([])
        self['title'] = Label(title)
        self['actions'] = ActionMap(['OkCancelActions'], {'ok': self.ok,
         'cancel': self.cancel})
        self.setChoices(choices)
        if value is not None:
            self.onFirstExecBegin.append(lambda : self.moveToValue(value))
        self.onLayoutFinish.append(self.autoResize)
        return

    def setChoices(self, choices):
        self.val_list = [ x[1] for x in choices ]
        self.listbox.setList([ x[0] for x in choices ])

    def moveToValue(self, value):
        if value is not None:
            i = self.val_list.index(value)
            self.listbox.moveToIndex(i)
        return

    def autoResize(self):
        self.listbox.instance.setTextOffset(ePoint(10, 0))
        l_sz = self.listbox.instance.size()
        h = l_sz.height() / 8 * min(len(self.listbox.list), 8)
        self.listbox.instance.resize(eSize(l_sz.width(), h))
        w_sz = self.instance.size()
        self.instance.resize(eSize(w_sz.width(), w_sz.height() - l_sz.height() + h))

    def ok(self):
        i = self.listbox.getSelectionIndex()
        if self.val_list:
            self.close(self.val_list[i])
        else:
            self.close(None)
        return

    def cancel(self):
        self.close(None)
        return