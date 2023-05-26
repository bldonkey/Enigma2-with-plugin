# Embedded file name: src/settings.py

try:
    from typing import Any
except ImportError:
    pass

from Screens.Screen import Screen
from Screens.InputBox import InputBox
from Components.config import config, ConfigElement, ConfigSubsection, ConfigText, ConfigSelection, getConfigListEntry
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Input import Input
from enigma import gFont
from Components.config import KEY_LEFT, KEY_RIGHT, KEY_DELETE, KEY_BACKSPACE, KEY_HOME, KEY_END, KEY_TOGGLEOW, KEY_ASCII, KEY_TIMEOUT, KEY_NUMBERS
from Components.config import getKeyNumber
from enigma import getPrevAsciiCode
from .api import APIException, Api
from .system import MessageBox
from .loc import translate as _
from .common import CallbackReceiver, fatalError, safecb
from .base import trapException, describeException
from .utils import trace
from .settings_model import PlayerSetting, QualitySetting, settingsRepo, languageManager, VideoState

class ConfigNumberText(ConfigElement):

    def __init__(self, default = ''):
        ConfigElement.__init__(self)
        self.marked_pos = 0
        self.allmarked = default != ''
        self.overwrite = False
        self.text = ''
        self.value = self.last_value = self.default = default

    def validateMarker(self):
        textlen = len(self.text)
        if self.marked_pos > textlen:
            self.marked_pos = textlen
        if self.marked_pos < 0:
            self.marked_pos = 0

    def insertChar(self, ch, pos, owr):
        if owr:
            self.text = self.text[0:pos] + ch + self.text[pos + 1:]
        else:
            self.text = self.text[0:pos] + ch + self.text[pos:]

    def deleteChar(self, pos):
        self.text = self.text[0:pos] + self.text[pos + 1:]

    def deleteAllChars(self):
        self.text = ''
        self.marked_pos = 0

    def handleKey(self, key):
        if key == KEY_DELETE:
            if self.allmarked:
                self.deleteAllChars()
                self.allmarked = False
            else:
                self.deleteChar(self.marked_pos)
        elif key == KEY_BACKSPACE:
            if self.allmarked:
                self.deleteAllChars()
                self.allmarked = False
            elif self.marked_pos > 0:
                self.deleteChar(self.marked_pos - 1)
                self.marked_pos -= 1
        elif key == KEY_LEFT:
            if self.allmarked:
                self.marked_pos = len(self.text)
                self.allmarked = False
            else:
                self.marked_pos -= 1
        elif key == KEY_RIGHT:
            if self.allmarked:
                self.marked_pos = 0
                self.allmarked = False
            else:
                self.marked_pos += 1
        elif key == KEY_HOME:
            self.allmarked = False
            self.marked_pos = 0
        elif key == KEY_END:
            self.allmarked = False
            self.marked_pos = len(self.text)
        elif key == KEY_TOGGLEOW:
            self.overwrite = not self.overwrite
        elif key == KEY_ASCII:
            newChar = chr(getPrevAsciiCode())
            if self.allmarked:
                self.deleteAllChars()
                self.allmarked = False
            self.insertChar(newChar, self.marked_pos, False)
            self.marked_pos += 1
        elif key in KEY_NUMBERS:
            newChar = str(getKeyNumber(key))
            if self.allmarked:
                self.deleteAllChars()
                self.allmarked = False
            self.insertChar(newChar, self.marked_pos, False)
            self.marked_pos += 1
        elif key == KEY_TIMEOUT:
            return
        self.validateMarker()
        self.changed()

    def getValue(self):
        try:
            return self.text.encode('utf-8')
        except UnicodeDecodeError:
            trace('Broken UTF8!')
            return self.text

    def setValue(self, val):
        try:
            self.text = val.decode('utf-8')
        except UnicodeDecodeError:
            self.text = val.decode('utf-8', 'ignore')
            trace('Broken UTF8!')

    value = property(getValue, setValue)

    def getText(self):
        return self.text.encode('utf-8')

    def getMulti(self, selected):
        if self.allmarked:
            mark = list(range(0, len(self.text)))
        else:
            mark = [self.marked_pos]
        return (selected and 'mtext' or 'text', self.text.encode('utf-8') + ' ', mark)

    def onSelect(self, session):
        self.allmarked = self.value != ''

    def onDeselect(self, session):
        self.marked_pos = 0
        if not self.last_value == self.value:
            self.changedFinal()
            self.last_value = self.value

    def getHTML(self, id):
        return '<input type="text" name="' + id + '" value="' + self.value + '" /><br>\n'

    def unsafeAssign(self, value):
        self.value = str(value)


class ConfigNumberPassword(ConfigNumberText):

    def __init__(self, default = '', censor = '*'):
        ConfigNumberText.__init__(self, default)
        self._censor = censor
        self._shown_pos = None
        return

    def _applyCensor(self):
        self._shown_pos = None
        return

    def insertChar(self, ch, pos, owr):
        ConfigNumberText.insertChar(self, ch, pos, owr)
        self._shown_pos = pos

    def deleteChar(self, pos):
        ConfigNumberText.deleteChar(self, pos)
        self._shown_pos = None
        return

    def deleteAllChars(self):
        ConfigNumberText.deleteAllChars(self)
        self._shown_pos = None
        return

    def getMulti(self, selected):
        mode, text, mark = ConfigNumberText.getMulti(self, selected)
        censored = (self._censor * (len(text) - 1)).encode('utf-8')
        p = self._shown_pos
        if p is not None:
            censored = censored[:p] + text[p] + censored[p + 1:]
        return (mode, censored + ' ', mark)

    def onDeselect(self, session):
        ConfigNumberText.onDeselect(self, session)
        self._shown_pos = None
        return


def initServiceApp():
    """:rtype: bool"""
    try:
        from Plugins.SystemPlugins.ServiceApp import serviceapp_client
    except ImportError as e:
        trace('serviceapp client no found!', e)
        return False

    return True


cfg = config.iptv = ConfigSubsection()
cfg.history = ConfigText(default='')
cfg.viewmode = ConfigSelection(['wall', 'list'])

def getVideoConfig():
    st = settingsRepo.video_state
    return (st.vid, st.vtype, st.time)


def setVideoConfig(vid, vtype, time):
    settingsRepo.video_state = VideoState(vid, vtype, time)
    settingsRepo.storeConfig()


def resetVideoConfig():
    setVideoConfig(0, 0, 0)


class TVPasswordChangeScreen(ConfigListScreen, Screen, CallbackReceiver):

    def __init__(self, session, db):
        Screen.__init__(self, session)
        CallbackReceiver.__init__(self)
        self.db = db
        self['header'] = Label(_('Change password'))
        self['red'] = Label(_('Cancel'))
        self['green'] = Label(_('OK'))
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions'], {'ok': self.ok,
         'cancel': self.cancel,
         'green': self.ok,
         'red': self.cancel}, -2)
        self._old_pass = ConfigNumberPassword()
        self._new_pass = ConfigNumberPassword()
        ConfigListScreen.__init__(self, [getConfigListEntry(_('Old password'), self._old_pass), getConfigListEntry(_('New password'), self._new_pass)], session)
        self.onLayoutFinish.append(self.fixFont)

    def fixFont(self):
        try:
            self['config'].instance.setFont(gFont('TVSansRegular', 29))
        except AttributeError as e:
            trace('error', e)

    def ok(self):
        changed = self._old_pass.isChanged() or self._new_pass.isChanged()
        if not changed:
            self.close()
            return
        d = self.db.changeProtectCode(self._old_pass.value, self._new_pass.value)
        d.addCallback(self.passwordChanged).addErrback(self.error).addErrback(fatalError)

    @safecb
    def passwordChanged(self, result):
        trace(result)
        self.session.openWithCallback(lambda ret: self.close(), MessageBox, _('Password changed successfully'), MessageBox.TYPE_INFO, timeout=5)

    @safecb
    def error(self, err):
        e = trapException(err)
        if e == APIException and err.value.code == 'URL_PROTECTED':
            self.session.open(MessageBox, _('Wrong old password! Changes not saved!'), MessageBox.TYPE_WARNING, timeout=5, enable_input=False)
        else:
            self.session.open(MessageBox, describeException(err), MessageBox.TYPE_ERROR, timeout=5)

    def cancel(self):
        self.close()


def decorateChoices(choices):
    return [ (value, '\xe2\x97\x80 %s \xe2\x96\xb6' % title) for value, title in choices ]


class TVSetupScreen(ConfigListScreen, Screen, CallbackReceiver):

    def __init__(self, session, db):
        Screen.__init__(self, session)
        CallbackReceiver.__init__(self)
        self.db = db
        trace('setup')
        self['actions'] = ActionMap(['SetupActions', 'ColorActions'], {'green': self.apply,
         'red': self.cancel,
         'ok': self.ok,
         'cancel': self.cancel}, -2)
        self['red'] = Label(_('Cancel'))
        self['green'] = Label(_('OK'))

        def makeSelection(field, value):
            return ConfigSelection(decorateChoices(field.getChoices()), value)

        self.player_id = makeSelection(PlayerSetting(), settingsRepo.player_id)
        self.vod_player_id = makeSelection(PlayerSetting(), settingsRepo.vod_player_id)
        self.quality = makeSelection(QualitySetting(), settingsRepo.quality)
        v, choices = languageManager.getLanguageChoices()
        self.language = ConfigSelection(decorateChoices(choices), v)
        v, choices = db.getSetting(db.MEDIA_SERVER)
        self.server = ConfigSelection(decorateChoices(choices), v)
        cfg_list = [getConfigListEntry(_('Language'), self.language),
         getConfigListEntry(_('Quality'), self.quality),
         getConfigListEntry(_('Server'), self.server),
         getConfigListEntry(_('TV Player ID'), self.player_id),
         getConfigListEntry(_('VOD Player ID'), self.vod_player_id)]
        ConfigListScreen.__init__(self, cfg_list, session)
        self.onLayoutFinish.append(self.fixFont)

    def fixFont(self):
        try:
            self['config'].instance.setFont(gFont('TVSansRegular', 29))
        except AttributeError as e:
            trace('error', e)

    def ok(self):
        sel = self['config'].getCurrent()
        if not sel:
            return
        self.apply()

    def apply(self):
        params = {}
        if self.language.isChanged():
            lang = self.language.value
            languageManager.setLanguage(lang)
        if self.quality.isChanged():
            settingsRepo.quality = self.quality.value
        if self.server.isChanged():
            params[self.db.MEDIA_SERVER] = self.server.value
        if self.player_id.isChanged():
            settingsRepo.player_id = self.player_id.value
        if self.vod_player_id.isChanged():
            settingsRepo.vod_player_id = self.vod_player_id.value
        settingsRepo.storeConfig()
        changed = any((item[1].isChanged() for item in self['config'].list))
        if params:
            self.db.setSettings(params).addCallback(self.remoteUpdated).addErrback(self.error).addErrback(fatalError)
        elif changed:
            self.close(True)
        else:
            self.close(False)

    @safecb
    def remoteUpdated(self, ret):
        self.close(True)

    def cancel(self):
        for x in self['config'].list:
            x[1].cancel()

        self.close(False)

    @safecb
    def error(self, err):
        trapException(err)

        def cb(ret):
            self.close(True)

        msg = '%s %s' % (_('Failed to save settings'), describeException(err))
        self.session.openWithCallback(cb, MessageBox, msg, MessageBox.TYPE_ERROR)


class TVEnterPassword(InputBox):

    def __init__(self, session, title = _('Enter protect password:'), type = Input.PIN):
        InputBox.__init__(self, session, title, type=type)


class TVAccountInfo(Screen):

    def __init__(self, session, db):
        super(TVAccountInfo, self).__init__(session)
        self.db = db
        self['idLabel'] = Label()
        self['header'] = Label(_('Subscription'))
        self['nameLabel'] = Label(_('Name:'))
        self['name'] = Label()
        self['startLabel'] = Label(_('Start:'))
        self['start'] = Label()
        self['endLabel'] = Label(_('End:'))
        self['end'] = Label()
        self['daysLabel'] = Label(_('Days left:'))
        self['days'] = Label()
        self['actions'] = ActionMap(['OkCancelActions'], {'ok': self.close,
         'cancel': self.close})
        self.onFirstExecBegin.append(self.showValues)

    def showValues(self):
        self['idLabel'].setText('ID: %s' % self.db.account['id'].encode('utf-8'))
        subs = self.db.account['subscriptions']
        if not subs:
            return
        s = subs[0]
        self['name'].setText(s['title'].encode('utf-8'))

        def extract(text):
            if text is not None:
                return text.encode('utf-8')
            else:
                return _('Unknown')
                return

        self['start'].setText(extract(s['begin_date']))
        self['end'].setText(extract(s['end_date']))
        self['days'].setText(extract(s['rest_of_days']))