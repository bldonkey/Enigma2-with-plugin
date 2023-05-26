# Embedded file name: src/settings_home.py

try:
    from typing import Any, TYPE_CHECKING
    if TYPE_CHECKING:
        from .main import StyleManager
except ImportError:
    pass

from . import VERSION
from .favorites_editor import TVFavoritesEditor
from .loc import translate as _
from .settings import TVSetupScreen, TVAccountInfo, TVPasswordChangeScreen
from .system import ChoiceList
from .setup import SetupScreen
from .api import Api
from .software_upgrade import UpgradeScreen

class TVSetupHome(ChoiceList):

    def __init__(self, session, db, style_mgr):
        choices = [(_('Main'), self.openMain),
         (_('Account'), self.openAccountInfo),
         (_('Change parental password'), self.changePass),
         (_('Edit favorite channels'), self.changeFavorites),
         (_('System settings'), self.openSystemSettings),
         (_('Install dependencies'), self.openProvision)]
        title = '%s (%s)' % (_('Settings'), '%s: %s' % (_('Plugin version'), VERSION))
        super(TVSetupHome, self).__init__(session, choices, title=title)
        self.db = db
        self.style_mgr = style_mgr
        self._changed = False

    def ok(self):
        i = self.listbox.getSelectionIndex()
        self.val_list[i]()

    def cancel(self):
        self.close(self._changed)

    def openMain(self):

        def cb(changed):
            self._changed = self._changed or changed

        self.session.openWithCallback(cb, TVSetupScreen, self.db)

    def openAccountInfo(self):
        self.session.open(TVAccountInfo, self.db)

    def openButtonsHelp(self):
        pass

    def changePass(self):
        self.session.open(TVPasswordChangeScreen, self.db)

    def changeFavorites(self):
        self.session.open(TVFavoritesEditor, self.db)

    def openSystemSettings(self):
        self.style_mgr.reset()
        openSystemSettings(self.session, callback=self.style_mgr.apply)

    def openSoftwareUpdate(self):
        self.style_mgr.reset()
        self.session.openWithCallback(lambda : self.style_mgr.apply(), UpgradeScreen)

    def openProvision(self):
        self.style_mgr.reset()
        self.session.openWithCallback(lambda : self.style_mgr.apply(), SetupScreen)


def openSystemSettings(session, callback = None):

    def cb(ret):
        if callback is not None:
            callback()
        return

    from Screens.Menu import mdom, Menu
    m = mdom.find("menu[@entryID='setup_selection']")
    session.openWithCallback(cb, Menu, m)