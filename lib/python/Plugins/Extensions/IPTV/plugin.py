# Embedded file name: src/plugin.py

from Screens.Screen import Screen
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.Standby import TryQuitMainloop
from . import NAME
try:
    from .loc import translate as _
except ImportError:

    def _(text):
        return text


class WizardScreen(Screen):

    def __init__(self, session, run = False):
        super(WizardScreen, self).__init__(session)
        self._run_plugin = run
        self.onFirstExecBegin.append(self.checkUpdate)

    def checkUpdate(self):
        try:
            from .updater import UpdaterScreen
            self.session.openWithCallback(self.start, UpdaterScreen)
        except ImportError as e:
            print('[IPTV] load error')
            import traceback
            traceback.print_exc()
            message = '%s\n%s' % (_('IPTV Critical error'), str(e))
            self.session.openWithCallback(self.close, MessageBox, message, MessageBox.TYPE_ERROR)

    def start(self, updated):
        if updated:
            print('[IPTV] restart after update')
            self.session.openWithCallback(self.reboot, MessageBox, _('Restarting enigma2 after update...'), MessageBox.TYPE_INFO, timeout=3)
        else:
            from .setup import SetupScreen
            if SetupScreen.setupRequired():
                print('[IPTV] setup')
                self.session.openWithCallback(self.run, SetupScreen)
            else:
                self.run()

    def run(self, ret = None):
        if self._run_plugin:
            from .main import Runner
            self.session.openWithCallback(self.close, Runner)
        else:
            self.close()

    def reboot(self, ret):
        self.session.open(TryQuitMainloop, retvalue=3)


def sessionStart(reason, session, **kwargs):
    print('[IPTV] sessionStart', reason, session)
    if reason == 0:
        from Tools.Notifications import AddNotification
        try:
            from .main import Runner
            if shallAutostart():
                AddNotification(Runner)
        except Exception as e:
            print('[IPTV] autoStart error', e)


def shallAutostart():
    try:
        from .settings_model import settingsRepo
        if settingsRepo.autostart == 0:
            return False
    except Exception as e:
        print('[IPTV] error:', e)

    return True


def pluginOpen(session, **kwargs):
    session.open(WizardScreen, run=True)


def menuOpen(menuid):
    if menuid == 'mainmenu':
        return [(NAME,
          pluginOpen,
          'media_player',
          -4)]
    else:
        return []


def wizardOpen(session, **kwargs):
    return WizardScreen(session)


def Plugins(path, **kwargs):
    return [PluginDescriptor(name=NAME, description='enigma2 IPTV and VOD plugin', where=PluginDescriptor.WHERE_PLUGINMENU, fnc=pluginOpen, icon='logo.png'),
     PluginDescriptor(name=NAME, description='', where=PluginDescriptor.WHERE_MENU, fnc=menuOpen),
     PluginDescriptor(name=NAME, description='updater', where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionStart),
     PluginDescriptor(name=NAME, description='', where=PluginDescriptor.WHERE_WIZARD, fnc=(99, wizardOpen))]