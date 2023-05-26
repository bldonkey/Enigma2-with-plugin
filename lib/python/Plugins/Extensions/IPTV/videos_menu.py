# Embedded file name: src/videos_menu.py

try:
    from typing import Any, Dict
except ImportError:
    pass

from datetime import datetime
from twisted.internet.defer import CancelledError
from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN, SCOPE_SKIN
from Tools.LoadPixmap import LoadPixmap
from enigma import eWidget, gFont, eSize, ePixmap, ePoint, eLabel, gRGB
from .base import trapException, describeException, CachedRequest
from .common import safecb, CallbackReceiver
from .grid import Scroll, StaticPlane, PlaneEntry
from .loc import translate as _
from .utils import trace
from .system import MessageBox
from .updater import fatalError
from .videos import VideosWall, SearchKeyboard
from .api import TYPE_COLLECTION, TYPE_SERIAL
from .colors import colors
from .langlist import VideoLanguageList
from .api import Api
from .videos_model import Caption

class VideosHome(Screen, CallbackReceiver):
    MODE_HOME, MODE_GENRES, MODE_COUNTRIES = list(range(3))

    def __init__(self, session, db):
        super(VideosHome, self).__init__(session)
        CallbackReceiver.__init__(self)
        self.db = db
        self.genres = CachedRequest(self.db.getGenres)
        self.countries = CachedRequest(self.db.getCountries)
        scroll = self['scroll'] = Scroll()
        self.entries = [{'id': 'all',
          'title': _('All movies')},
         {'id': 'new',
          'title': _('New')},
         {'id': 'genres',
          'title': _('Genres')},
         {'id': 'countries',
          'title': _('Countries')},
         {'id': 'collections',
          'title': _('Collections')},
         {'id': 'search',
          'title': _('Search')},
         {'id': 'my',
          'title': _('Favourites')},
         {'id': 'series',
          'title': _('Series')}]
        for item in self.entries:
            item['pic'] = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/icons/movies/%s.png' % item['id']))

        self.cont = self['container'] = StaticPlane(scroll)
        self.cont.onCreated.append(self.setList)
        self.caption = Caption(self.db.title)
        self['caption'] = Label(str(self.caption))
        self.onShown.append(self.updateCaption)
        self['actions'] = ActionMap(['OkCancelActions', 'DirectionActions'], {'ok': self.ok,
         'cancel': self.exit,
         'left': self.cont.left,
         'right': self.cont.right,
         'up': self.cont.up,
         'down': self.cont.down}, -2)
        self['actions_audio'] = ActionMap(['InfobarAudioSelectionActions', 'InfobarSubtitleSelectionActions'], {'audioSelection': self.selectLanguage,
         'subtitleSelection': self.selectLanguage})
        self.mode = self.MODE_HOME
        self.idx = 0

    def setList(self):
        self['caption'].setText(str(self.caption))
        if self.mode == self.MODE_HOME:
            self.cont.setClass(CategoryEntry, 8, 4)
            self.cont.setList(self.entries, self.idx)

    @safecb
    def setListSecondary(self, data):
        self['caption'].setText(str(self.caption))
        if self.mode == self.MODE_GENRES or self.mode == self.MODE_COUNTRIES:
            self.cont.setClass(GenresEntry, 4, 11)
            self.cont.setList(data)

    def ok(self):
        sel = self.cont.getSelected()
        if sel is None:
            return
        elif self.mode == self.MODE_HOME:
            return self.enter(sel)
        else:
            if self.mode == self.MODE_GENRES:
                args = {'genre': sel['id'],
                 'lang': self.getLanguge()}
            elif self.mode == self.MODE_COUNTRIES:
                args = {'country': sel['id'],
                 'lang': self.getLanguge()}
            self.session.open(VideosWall, self.db, args, self.caption + [sel['title']])
            return

    def exit(self):
        if self.mode == self.MODE_HOME:
            self.close()
        else:
            self.caption.pop()
            self.mode = self.MODE_HOME
            self.setList()

    def enter(self, sel):
        args = {'lang': self.getLanguge()}
        if sel['id'] == 'all':
            pass
        elif sel['id'] == 'new':
            year = datetime.now().year - 1
            args['year'] = '>%d' % year
        elif sel['id'] == 'collections':
            args['type'] = TYPE_COLLECTION
        elif sel['id'] == 'series':
            args['type'] = TYPE_SERIAL
        else:
            if sel['id'] == 'my':
                return self.loadFavourites()
            if sel['id'] == 'search':
                return self.openSearch()
            if sel['id'] == 'genres' or sel['id'] == 'countries':
                self.idx = self.cont.getSelectionIndex()
                self.caption.append(sel['title'])
                if sel['id'] == 'genres':
                    self.mode = self.MODE_GENRES
                    return self.showGenres()
                if sel['id'] == 'countries':
                    self.mode = self.MODE_COUNTRIES
                    return self.showCountries()
        self.session.open(VideosWall, self.db, args, self.caption + [sel['title']])

    def loadFavourites(self):
        d = self.db.getFavouriteVideos().addCallback(self.favouritesReady)
        d.addErrback(self.error).addErrback(fatalError)

    @safecb
    def favouritesReady(self, l):
        if not l:
            self.session.open(MessageBox, _('Nothing is added to favourites so far.'), MessageBox.TYPE_INFO)
            return
        args = {'idlist': ','.join(map(str, l))}
        self.session.open(VideosWall, self.db, args, self.caption + [_('Favourites')])

    def showGenres(self):
        self.genres.get().addCallback(self.setListSecondary).addErrback(self.error).addErrback(fatalError)

    def showCountries(self):
        self.countries.get().addCallback(self.setListSecondary).addErrback(self.error).addErrback(fatalError)

    @safecb
    def error(self, err):
        e = trapException(err)
        if e == CancelledError:
            trace('Cancelled')
        else:
            self.session.open(MessageBox, describeException(err), MessageBox.TYPE_ERROR, timeout=5)

    def openSearch(self, ret = None):
        self.session.openWithCallback(self.searchMovie, SearchKeyboard, ['en_EN', 'ru_RU'])

    def searchMovie(self, word):
        if word is None:
            return
        else:
            if 3 <= len(word) <= 50:
                args = {'word': word}
                self.session.open(VideosWall, self.db, args, self.caption + [_('Search'), word])
            else:
                self.session.openWithCallback(self.openSearch, MessageBox, _('Please enter at least 3 symbols'), MessageBox.TYPE_WARNING)
            return

    def selectLanguage(self):
        self.session.openWithCallback(self.applyLanguage, VideoLanguageList, self.db)

    def getLanguge(self):
        return VideoLanguageList.getLanguage()

    def applyLanguage(self, ret):
        if ret is not None:
            VideoLanguageList.saveLanguage(ret)
        return

    def updateCaption(self):
        self.caption.setLang(VideoLanguageList.getLanguageTitle())
        self['caption'].setText(str(self.caption))


class CategoryEntry(PlaneEntry):
    width = 137
    height = 89

    def __init__(self, parent):
        self.parent = parent
        self.instance = eWidget(parent)
        self.active = False
        self.col = gRGB(colors['white'])
        self.col_bg = gRGB(colors['darkgray'])
        self.col_sel = gRGB(colors['gridsel'])
        self.font = gFont('TVSansBold', 17)
        self.instance.setBackgroundColor(self.col_bg)
        self.instance.setTransparent(0)
        self.instance.resize(eSize(self.width, self.height))
        self.icon = icon = ePixmap(self.instance)
        icon.setAlphatest(2)
        icon.resize(eSize(self.width, self.height))
        self.txt = txt = eLabel(self.instance)
        txt.setFont(self.font)
        txt.setForegroundColor(self.col)
        txt.setBackgroundColor(self.col_bg)
        txt.setVAlign(txt.alignTop)
        txt.setHAlign(txt.alignCenter)
        txt.setZPosition(1)
        txt.setTransparent(1)
        txt.resize(eSize(self.width, 30))
        txt.move(ePoint(0, 59))

    def setActive(self, active):
        if active == self.active:
            return
        self.active = active
        if active:
            self.txt.setBackgroundColor(self.col_sel)
            self.instance.setBackgroundColor(self.col_sel)
        else:
            self.txt.setBackgroundColor(self.col_bg)
            self.instance.setBackgroundColor(self.col_bg)
        self.instance.invalidate()

    def setData(self, data):
        self.txt.setText(data['title'])
        self.icon.setPixmap(data['pic'])
        self.instance.show()

    def show(self):
        self.instance.show()

    def hide(self):
        self.instance.hide()


class GenresEntry(PlaneEntry):
    width = 283
    height = 43

    def __init__(self, parent):
        self.parent = parent
        self.instance = eWidget(parent)
        self.active = False
        self.col = gRGB(colors['white'])
        self.col_bg = gRGB(colors['darkgray'])
        self.col_sel = gRGB(colors['gridsel'])
        self.font = gFont('TVSansSemi', 17)
        self.instance.setBackgroundColor(self.col_bg)
        self.instance.setTransparent(0)
        self.instance.resize(eSize(self.width, self.height))
        self.icon = icon = ePixmap(self.instance)
        icon.setAlphatest(2)
        icon.resize(eSize(self.width, self.height))
        icon.setPixmap(LoadPixmap(resolveFilename(SCOPE_SKIN, 'IPTV/icons/movies/folder.png')))
        self.txt = txt = eLabel(self.instance)
        txt.setFont(self.font)
        txt.setForegroundColor(self.col)
        txt.setBackgroundColor(self.col_bg)
        txt.setVAlign(txt.alignCenter)
        txt.setHAlign(txt.alignLeft)
        txt.setZPosition(1)
        txt.setTransparent(1)
        xoff, yoff = (60, 6)
        txt.resize(eSize(self.width - xoff - 4, self.height - yoff * 2))
        txt.move(ePoint(xoff, yoff))

    def setActive(self, active):
        if active == self.active:
            return
        self.active = active
        if active:
            self.txt.setBackgroundColor(self.col_sel)
            self.instance.setBackgroundColor(self.col_sel)
        else:
            self.txt.setBackgroundColor(self.col_bg)
            self.instance.setBackgroundColor(self.col_bg)
        self.instance.invalidate()

    def setData(self, data):
        self.txt.setText(data['title'])

    def show(self):
        self.instance.show()

    def hide(self):
        self.instance.hide()