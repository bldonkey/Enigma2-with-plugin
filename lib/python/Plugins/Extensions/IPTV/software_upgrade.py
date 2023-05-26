# Embedded file name: src/software_upgrade.py

import os
from twisted.internet.defer import Deferred
from Components.Opkg import OpkgComponent
from Screens.MessageBox import MessageBox
from . import NAME, VERSION
from .loc import translate as _
from .common import CallbackReceiver, safecb
from .utils import trace
from .base import HttpAgent, trapException
from .updater import iUpdater, PREFIX
from .setup import SetupScreen

class IpkgException(Exception):
    pass


class PackageChecker(object):
    """Run code similar to SoftwarePanel to check if online flash will be required"""
    STATE_INIT, STATE_UPDATE, STATE_LIST = list(range(3))

    def __init__(self):
        self.ipkg = IpkgComponent()
        self.ipkg.addCallback(self._ipkgCallback)
        self.d = Deferred(self.cancel)
        self.st = self.STATE_INIT

    def getNumberOfPackages(self):
        """Return number of upgradable packages"""
        self.st = self.STATE_UPDATE
        self.ipkg.startCmd(IpkgComponent.CMD_UPDATE)
        return self.d

    def _ipkgCallback(self, event, param):
        if event == IpkgComponent.EVENT_ERROR:
            if self.st == self.STATE_UPDATE:
                message = _('Failed to update package list!')
            else:
                message = _('Failed to list packages!')
            self.d.errback(IpkgException(message))
        elif event == IpkgComponent.EVENT_DONE:
            if self.st == self.STATE_UPDATE:
                self.st = self.STATE_LIST
                self.ipkg.startCmd(IpkgComponent.CMD_UPGRADE_LIST)
            else:
                return self.d.callback(len(self.ipkg.fetchedList))

    def cancel(self):
        self.ipkg.stop()


class UpgradeScreen(MessageBox, CallbackReceiver):

    def __init__(self, session):
        MessageBox.__init__(self, session, _('Updating package list, please wait ...'), MessageBox.TYPE_INFO, enable_input=False)
        CallbackReceiver.__init__(self)
        self.onLayoutFinish.append(self.checkPackageNumber)
        self.checker = PackageChecker()
        self.onClose.append(self.checker.cancel)

    def checkPackageNumber(self):
        trace('checking for number of packages')
        self.checker.getNumberOfPackages().addCallback(self.packageNumberReady).addErrback(self.error)

    @safecb
    def packageNumberReady(self, number):
        trace('%d updates available' % number)
        if number == 0:
            self.session.openWithCallback(self.exit, MessageBox, _('No updates found'), MessageBox.TYPE_INFO)
        elif number <= 200:
            from Plugins.Extensions.Infopanel.SoftwarePanel import SoftwarePanel
            self.session.openWithCallback(self.exit, SoftwarePanel)
        else:
            self['text'].setText(_('Checking external media for backup'))
            self.checkMedia()

    def checkMedia(self):
        if MediaHelper().findMedia('/media/hdd'):
            trace('downloading plugin')
            ipk_dir = '/media/hdd/images/ipk'
            if not os.path.exists(ipk_dir):
                os.makedirs(ipk_dir)
            ipk = os.path.join(ipk_dir, '%s.ipk' % (PREFIX + NAME.lower()))
            if os.path.exists(ipk):
                os.unlink(ipk)
            self['text'].setText(_('Creating plugin backup'))
            downloadPlugin(ipk).addCallback(self.pluginReady).addErrback(self.pluginError)
        else:
            message = _('Could not find suitable media - insert USB stick with sufficient free space and try again!')
            self.session.openWithCallback(self.exit, MessageBox, message, MessageBox.TYPE_WARNING)

    @safecb
    def pluginReady(self, ret):
        self.startFlashTool()

    @safecb
    def pluginError(self, err):
        trapException(err)
        self.session.openWithCallback(self.exit, MessageBox, str(err), MessageBox.TYPE_ERROR)

    def startFlashTool(self):
        trace('starting flash screen')
        SetupScreen.resetRevision()
        cfg_dir = '/media/hdd/images/config'
        if not os.path.exists(cfg_dir):
            os.makedirs(cfg_dir)
        with open(os.path.join(cfg_dir, 'myrestore.sh'), 'w') as f:
            f.write('#!/bin/sh\nopkg install "%s"\n' % pluginUrl())
        for suffix in ('settings', 'plugins'):
            open(os.path.join(cfg_dir, suffix), 'w').close()

        noplugins = os.path.join(cfg_dir, 'noplugins')
        if os.path.exists(noplugins):
            os.unlink(noplugins)
        from Plugins.SystemPlugins.SoftwareManager.Flash_online import FlashOnline
        self.session.openWithCallback(self.exit, FlashOnline)

    @safecb
    def error(self, err):
        err.trap(IpkgException)
        self.session.openWithCallback(self.exit, MessageBox, str(err), MessageBox.TYPE_ERROR)

    def exit(self, *retval):
        self.close()


def pluginUrl():
    return iUpdater.url + '%s_%s_all.ipk' % (PREFIX + NAME.lower(), VERSION)


def downloadPlugin(dst):
    http = HttpAgent()
    return http.downloadPage(pluginUrl(), dst)


class MediaHelper(object):
    """Run code similar to FlashOnline to check that suitable media is inserted"""

    def __init__(self):
        with open('/proc/diskstats') as f:
            disks = [ line.split()[0:3] for line in f.readlines() ]
            self.diskstats = [ (int(x[0]), int(x[1])) for x in disks if x[2].startswith('sd') ]

    def checkIfDevice(self, path):
        st_dev = os.stat(path).st_dev
        return (os.major(st_dev), os.minor(st_dev)) in self.diskstats

    @staticmethod
    def spaceAvail(path):
        if '/mmc' not in path and os.path.isdir(path) and os.access(path, os.W_OK):
            try:
                statvfs = os.statvfs(path)
                return statvfs.f_bavail * statvfs.f_frsize / 1048576
            except Exception as err:
                trace(err)

        return 0

    def findMedia(self, path):
        return os.path.isdir(path) and self.checkIfDevice(path) and self.spaceAvail(path) > 500