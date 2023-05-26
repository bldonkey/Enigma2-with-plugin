# Embedded file name: src/standby.py

try:
    from typing import Callable, List
except ImportError:
    pass

from Screens.Standby import TryQuitMainloop
from .system import ChoiceList
from .loc import translate as _
from .utils import trace

class StandbyNotifier(object):
    """
    Put your functions to onStandbyChanged
    """

    def __init__(self):
        from Components.config import config
        config.misc.standbyCounter.addNotifier(self.enterStandby, initial_call=False)
        self.onStandbyChanged = []

    def enterStandby(self, configElement):
        trace('enter standby! have %d callbacks' % len(self.onStandbyChanged))
        for f in self.onStandbyChanged:
            f(sleep=True)

        from Screens.Standby import inStandby
        inStandby.onClose.append(self.exitStandby)

    def exitStandby(self):
        trace('exit standby! have %d callbacks' % len(self.onStandbyChanged))
        for f in self.onStandbyChanged:
            f(sleep=False)


standbyNotifier = StandbyNotifier()

class StandbyManager(object):
    """
    Use this class to enter and exit standby and run our hooks before
    """

    def __init__(self):
        self.onStandby = []

    def _callHooks(self, sleep):
        for f in self.onStandby:
            f(sleep)

    def enterStandby(self, session):
        trace('power off')
        from Screens.Standby import Standby
        self._callHooks(True)
        session.openWithCallback(self._exitStandby, Standby)

    def _exitStandby(self, ret):
        trace('power on')
        self._callHooks(False)


standbyManager = StandbyManager()

class PowerOffMenu(ChoiceList):

    def __init__(self, session):
        choices = [(_('Standby'), self.standBy),
         (_('Deep standby'), lambda : self.tryQuitMainLoop(1)),
         (_('Restart enigma2'), lambda : self.tryQuitMainLoop(3)),
         (_('Reboot'), lambda : self.tryQuitMainLoop(2))]
        super(PowerOffMenu, self).__init__(session, choices, title=_('Standby / restart'))

    def ok(self):
        i = self.listbox.getSelectionIndex()
        self.val_list[i]()

    def standBy(self):
        standbyManager.enterStandby(self.session)
        self.close()

    def tryQuitMainLoop(self, retvalue):
        self.session.open(TryQuitMainloop, retvalue=retvalue)