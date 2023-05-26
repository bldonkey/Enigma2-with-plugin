# Embedded file name: src/langlist.py

try:
    from typing import Any, Optional, Tuple
except ImportError:
    pass

from .system import ChoiceList
from .api import Api
from .loc import translate as _
from .common import safecb, CallbackReceiver, fatalError
from .base import trapException
from .settings_model import settingsRepo

class LanguageList(ChoiceList, CallbackReceiver):

    def __init__(self, session, db):
        ChoiceList.__init__(self, session, [], title=_('Select language'))
        CallbackReceiver.__init__(self)
        self.db = db
        self.onFirstExecBegin.append(self._loadLangs)
        self.onLayoutFinish.remove(self.autoResize)

    def _getLangs(self):
        raise NotImplementedError()

    def _loadLangs(self):
        self._getLangs().addCallback(self._setLangs).addErrback(self.error).addErrback(fatalError)

    @safecb
    def _setLangs(self, langs):
        self.setChoices([(_('any'), 'ALL')] + [ (lang['title'], lang['id']) for lang in langs ])
        self.autoResize()

    @safecb
    def error(self, err):
        trapException(err)


class VideoLanguageList(LanguageList):

    def _getLangs(self):
        return self.db.getVideoLanguages()

    def ok(self):
        i = self.listbox.getSelectedIndex()
        if self.val_list:
            lang_id, lang_title = self.val_list[i], self.listbox.list[i]
            if lang_id == 'ALL':
                lang_title = ''
            self.close((lang_id, lang_title))
        else:
            self.close(None)
        return

    @staticmethod
    def saveLanguage(lang):
        settingsRepo.vod_audio_filter = lang

    @staticmethod
    def getLanguage():
        lang_id, _ = settingsRepo.vod_audio_filter
        if lang_id == 'ALL':
            return None
        else:
            return lang_id
            return None

    @staticmethod
    def getLanguageTitle():
        _, lang_title = settingsRepo.vod_audio_filter
        return lang_title


class AudioLanguageList(LanguageList):

    def __init__(self, session, db):
        LanguageList.__init__(self, session, db)

    def _getLangs(self):
        return self.db.getAudioLanguages()