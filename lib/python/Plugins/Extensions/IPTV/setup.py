# Embedded file name: src/setup.py
"""
initial setup - install all dependencies
"""

import os
import shutil
from Screens.MessageBox import MessageBox
from Components.Console import Console
from Components.config import config, ConfigInteger
from Tools.Directories import resolveFilename, SCOPE_SKIN
from . import NAME
from .loc import translate as _
from .utils import trace as _trace
config.iptv_setup = ConfigInteger(0)

def trace(*args):
    _trace('Setup:', ' '.join(map(str, args)))


def commandExists(command):
    """
    :param str command: executable
    :return bool: check that executable exists in $PATH
    """
    return any((os.access(os.path.join(path, command), os.X_OK) for path in os.environ['PATH'].split(os.pathsep)))


class ConsoleTask(object):
    console = None

    def __init__(self, cmd):
        self.cmd = cmd
        if self.console is None:
            ConsoleTask.console = Console()
        return

    def run(self, callback):

        def finished(result, retval, extra_args = None):
            callback((result, retval))

        self.console.ePopen(self.cmd, finished)
        return


class ScreenTask(object):

    def __init__(self, session, screen, *args, **kwargs):
        self.session = session
        self.screen = screen
        self.args = args
        self.kwargs = kwargs

    def run(self, callback):

        def closed(ret):
            trace('Screen closed', ret)
            callback(ret)

        self.session.openWithCallback(closed, self.screen, *self.args, **self.kwargs)


class SetupScreen(MessageBox):

    def __init__(self, session):
        MessageBox.__init__(self, session, _('Setup'), MessageBox.TYPE_INFO, enable_input=False)
        self.errors = []
        self.onShown.append(self.start)

    def start(self):
        self.onShown.remove(self.start)
        trace('start setup')
        gen = self.taskGenerator()

        def runNext(result):
            try:
                gen.send(result).run(callback=runNext)
            except StopIteration:
                return

        return runNext(None)

    REVISION = 5

    def taskGenerator(self):
        errors = 0
        self['text'].setText(_('Updating package list, please wait ...'))
        result, retval = yield ConsoleTask('opkg update')
        if retval != 0:
            errors += 1
            yield ScreenTask(self.session, MessageBox, _('Failed to update package list!') + ' (ret=%d)\n%s' % (retval, result), MessageBox.TYPE_WARNING, timeout=5)
        self['text'].setText(_('Checking dependencies'))
        install_list = []
        try:
            import json
        except ImportError as e:
            trace(e)
            install_list.append('python-json')

        try:
            import requests
        except ImportError as e:
            trace(e)
            install_list.append('python-requests')

        try:
            import subprocess
        except ImportError as e:
            trace(e)
            install_list.append('python-subprocess')

        if not commandExists('exteplayer3'):
            install_list.append('exteplayer3')
        if not commandExists('gstplayer'):
            install_list.append('gstplayer')
        for pkg in install_list:
            self['text'].setText(_('Installing %s') % pkg)
            result, retval = yield ConsoleTask('opkg install %s' % pkg)
            if retval != 0:
                errors += 1
                yield ScreenTask(self.session, MessageBox, _('Failed to install %s!') % pkg + ' (ret=%d)\n%s' % (retval, result), MessageBox.TYPE_WARNING, timeout=5)

        try:
            from Plugins.SystemPlugins.ServiceApp import serviceapp_client
        except ImportError as e:
            trace(e)
            self['text'].setText(_('Installing %s') % 'eServiceApp')
            result, retval = yield ConsoleTask('opkg install enigma2-plugin-systemplugins-serviceapp')
            if retval != 0:
                result, retval = yield ConsoleTask('opkg install enigma2-plugin-extensions-serviceapp')
                if retval != 0:
                    errors += 1
                    yield ScreenTask(self.session, MessageBox, _('Failed to install %s!') % 'eServiceApp' + ' (ret=%d)\n%s' % (retval, result), MessageBox.TYPE_WARNING, timeout=5)

        if not self.replaceBootlogo():
            message = _('Failed to set bootlogo')
            yield ScreenTask(self.session, MessageBox, message, MessageBox.TYPE_WARNING, timeout=5)
        try:
            self.moveConfigFile()
        except Exception as e:
            message = '%s: %s' % (_('Failed to move settings file'), str(e))
            yield ScreenTask(self.session, MessageBox, message, MessageBox.TYPE_WARNING, timeout=5)

        if errors > 0:
            message = _('Setup finished with %d errors.') % errors
            mt = MessageBox.TYPE_WARNING
            timeout = -1
        else:
            message = _('Setup successfully finished')
            mt = MessageBox.TYPE_INFO
            timeout = 3
        self['text'].setText(_('Finished!'))
        yield ScreenTask(self.session, MessageBox, message, mt, timeout=timeout)
        trace('SETUP FINISHED')
        self.updateRevision()
        self.close()

    def replaceBootlogo(self):
        """Replace system bootlogo with raduga"""
        return True
        bootlogo_path = '/usr/share/bootlogo.mvi'
        if not os.path.exists(bootlogo_path):
            trace('Can not find system bootlogo')
            return False
        import shutil
        try:
            custom = resolveFilename(SCOPE_SKIN, '%s/bg.mvi' % NAME)
            shutil.copy(custom, bootlogo_path)
        except Exception as e:
            trace('Failed to copy bootlogo', e)
            return False

        try:
            config.plugins.softwaremanager.overwriteBootlogoFiles.value = False
        except Exception as e:
            trace('Failed to set overwriteBootlogoFiles', e)
            return False

        return True

    def moveConfigFile(self):
        from Tools.Directories import resolveFilename, SCOPE_CONFIG, SCOPE_SYSETC
        cfg_old = resolveFilename(SCOPE_SYSETC, 'iptv-config.json')
        if os.path.isfile(cfg_old):
            trace('renaming config file')
            shutil.move(cfg_old, resolveFilename(SCOPE_CONFIG, 'iptv-config.json'))
            from .settings_model import settingsRepo
            settingsRepo.loadConfigFile()

    @classmethod
    def setupRequired(cls):
        return config.iptv_setup.value < cls.REVISION

    @classmethod
    def updateRevision(cls):
        config.iptv_setup.value = cls.REVISION
        config.iptv_setup.save()

    @classmethod
    def resetRevision(cls):
        config.iptv_setup.value = 0
        config.iptv_setup.save()