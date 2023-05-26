# Embedded file name: src/notify.py

try:
    from typing import Optional, List, Tuple, Dict
except ImportError:
    pass

from Screens.Screen import Screen
from Screens.Standby import TryQuitMainloop
from datetime import datetime, timedelta
from .updater import UpdaterException, iUpdater
from .loc import translate as _, ngettext
from .utils import tdSec, trace
from .layer import eTimer
from .common import fatalError
from .base import trapException
from .api import Api
from .system import MessageBox
from .standby import standbyNotifier

class Message(object):

    def __init__(self, text, type = MessageBox.TYPE_INFO, list = None):
        self.text = text
        self.type = type
        self.list = list


class NotificationMessage(Screen):

    def __init__(self, session):
        super(NotificationMessage, self).__init__(session)
        self._pending_notifications = {}
        self._ignore_show = False
        self.onShown.append(self.showPendingNotification)

    def subscribeNotifier(self, notifier):
        notifier.append(self.notificationReceived)
        self.onClose.append(lambda : notifier.remove(self.notificationReceived))

    def notificationReceived(self, name, message):
        self._pending_notifications[name] = message
        if self.execing:
            self.showPendingNotification()

    def showPendingNotification(self):
        if self._ignore_show:
            return
        if self._pending_notifications:
            name, message = self._pending_notifications.popitem()
            self._ignore_show = True
            self.session.openWithCallback(lambda ret: self.notificationClosed(name, ret), MessageBox, text=message.text, type=message.type, list=message.list)

    def notificationClosed(self, name, ret):
        self._ignore_show = False
        trace('notification %s closed with ret %s' % (name, ret))
        self.showPendingNotification()


class ExpireNotifier(object):
    """
    Put your functions to onNotify
    """
    MESSAGE_NAME = 'expire'

    def __init__(self):
        self.onNotify = []
        self.db = None
        self.timer = eTimer()
        self.timer.callback.append(self.renewAndCheck)
        standbyNotifier.onStandbyChanged.append(self.standbyChanged)
        return

    def start(self, db):
        self.db = db
        self.timer.stop()
        return self.check()

    def renewAndCheck(self):
        self.timer.stop()
        if self.db is None:
            return
        else:
            return self.db.getAccountInfo().addCallbacks(lambda ret: self.check(), self.error).addErrback(fatalError)

    def check(self):
        trace('check expire')
        if self.db.packet_expire is None:
            return
        else:
            days = (self.db.packet_expire - datetime.now()).days
            trace('expire in', days)
            if days > 7:
                days = min(days, 100)
                self.timer.startLongTimer(tdSec(timedelta(days=days - 7)))
                return
            message = ngettext('%s subscription expire in %d day', '%s subscription expire in %d days', days) % (self.db.title, days)
            for f in self.onNotify:
                f(self.MESSAGE_NAME, Message(message))

            self.timer.startLongTimer(tdSec(timedelta(days=1)))
            return message
            return

    def error(self, err):
        """errors just printed"""
        trapException(err)
        trace('check error:', err)
        self.timer.startLongTimer(tdSec(timedelta(days=1)))

    def stop(self):
        self.timer.stop()

    def standbyChanged(self, sleep):
        if sleep:
            self.stop()
        else:
            self.renewAndCheck()


expireNotifier = ExpireNotifier()

class UpdateNotifier(object):
    MESSAGE_NAME = 'update_available'

    def __init__(self):
        self.onNotify = []
        self.interval = tdSec(timedelta(days=3))
        self._timer = eTimer()
        self._timer.callback.append(self.check)

    def start(self):
        self._timer.startLongTimer(self.interval)

    def check(self):
        d = iUpdater.checkUpdate()
        d.addCallback(self._checked).addErrback(self._error).addErrback(fatalError)

    def _checked(self, available):
        if available:
            choices = [(_('Yes'), True), (_('Postpone'), False)]
            m = Message(_('IPTV plugin update available. Install?'), list=choices)
            for f in self.onNotify:
                f(self.MESSAGE_NAME, m)

        self.start()

    def _error(self, err):
        err.trap(UpdaterException)
        trace('Error in checking update:', err)
        self.start()

    def stop(self):
        self._timer.stop()


updateNotifier = UpdateNotifier()

class UpdateMessageHandler(NotificationMessage):

    def notificationClosed(self, name, ret):
        if name == UpdateNotifier.MESSAGE_NAME and ret:
            self.session.openWithCallback(self._updateFinished, InstallUpdateScreen)
        else:
            super(UpdateMessageHandler, self).notificationClosed(name, ret)

    def _updateFinished(self, result):
        updated, message = result
        if not updated:
            self.session.open(MessageBox, message, MessageBox.TYPE_ERROR)
            return

        def reboot(ret):
            self.session.open(TryQuitMainloop, retvalue=3)

        self.session.openWithCallback(reboot, MessageBox, _('Restarting enigma2 after update...'), MessageBox.TYPE_INFO, timeout=3)


class InstallUpdateScreen(MessageBox):

    def __init__(self, session):
        MessageBox.__init__(self, session, _('Installing updates...'), MessageBox.TYPE_INFO, enable_input=False)
        self.onFirstExecBegin.append(self.start)

    def start(self):

        def finished(result):
            output, retval = result
            self.close((retval == 0, output))

        def error(err):
            err.trap(UpdaterException)
            self.close((False, err.getErrorMessage()))

        iUpdater.installUpdate().addCallback(finished).addErrback(error).addErrback(fatalError)