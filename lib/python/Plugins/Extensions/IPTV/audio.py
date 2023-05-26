# Embedded file name: src/audio.py

from Screens.Screen import Screen
from Components.ServiceEventTracker import ServiceEventTracker
from Components.ActionMap import ActionMap
from Components.Label import Label
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from Tools.ISO639 import LanguageCodes
from enigma import iPlayableService
from enigma import gFont, eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_CENTER
from .loc import translate as _
from .utils import trace
from .common import ListBox

class AudioMenu(Screen):

    def __init__(self, session):
        Screen.__init__(self, session)
        self.skinName = 'TVChoiceBox'
        self['list'] = self.listbox = ListBox([])
        self.listbox.l.setFont(0, gFont('TVSansRegular', 28))
        self['title'] = Label(_('Select audio track'))
        self['actions'] = ActionMap(['OkCancelActions'], {'ok': self.ok,
         'cancel': self.cancel}, -1)
        self.select_pixmap = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/icon_live.png'))
        self._event_tracker = ServiceEventTracker(screen=self, eventmap={iPlayableService.evUpdatedInfo: self.buildList})
        self.buildList()

    def makeEntry(self, track, language, description, selected):
        entry = [track, (eListboxPythonMultiContent.TYPE_TEXT,
          29,
          0,
          250,
          40,
          0,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          description), (eListboxPythonMultiContent.TYPE_TEXT,
          307,
          0,
          205,
          40,
          0,
          RT_HALIGN_LEFT | RT_VALIGN_CENTER,
          language)]
        if selected:
            entry.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND,
             6,
             11,
             19,
             19,
             self.select_pixmap))
        return entry

    def buildList(self):
        audio = self.getAudio()
        if audio is None:
            return
        else:
            current = audio.getCurrentTrack()
            tracks = []
            for i in range(audio.getNumberOfTracks()):
                info = audio.getTrackInfo(i)
                lang_str = info.getLanguage()
                langs = []
                for lang in lang_str.split('/'):
                    if lang in LanguageCodes:
                        langs.append(LanguageCodes[lang][0])
                    elif lang == 'und':
                        langs.append(_('Unknown'))
                    else:
                        langs.append(lang)

                tracks.append(self.makeEntry(i, ' / '.join(langs), info.getDescription(), i == current))

            self.listbox.setList(tracks)
            self.listbox.moveToIndex(current)
            return

    def getAudio(self):
        service = self.session.nav.getCurrentService()
        return service and service.audioTracks()

    def ok(self):
        track = self.listbox.getSelected()
        if track is None:
            return
        else:
            audio = self.getAudio()
            if audio and audio.getNumberOfTracks() > track:
                audio.selectTrack(track)
                self.close(self.listbox.getSelectedIndex())
            else:
                trace('cant select audio track!')
            return

    def cancel(self):
        self.close(None)
        return