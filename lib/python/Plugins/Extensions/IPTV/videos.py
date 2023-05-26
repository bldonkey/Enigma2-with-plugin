# Embedded file name: src/videos.py

try:
    from typing import List, Any, Tuple, Dict
    from six.moves import xrange
except ImportError:
    pass

from enigma import ePoint, eSize, eWidget, eLabel, ePixmap, gRGB
from enigma import gFont
from Screens.Screen import Screen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ActionMap import ActionMap
from Components.ScrollLabel import ScrollLabel
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from skin import parseColor
from twisted.internet.defer import Deferred, CancelledError, succeed
from .api import TYPE_MOVIE, TYPE_SEASON, TYPE_SERIES, TYPE_COLLECTION, TYPE_SERIAL, Api
from .cache import posterCache
from .loc import translate as _
from .common import safecb, fatalError, showBackground, CallbackReceiver
from .base import trapException, describeException, wasCancelled
from .grid import Scroll, DynamicPlane, PlaneEntry
from .settings_model import settingsRepo, VideoPathElement
from .utils import trace, formatLength
from .kb import VirtualKB
from .settings import cfg
from .system import MessageBox, ChoiceList
from .videos_player import RET_PREV, RET_NEXT, RET_END, VideosPlayer, pinManager
from .colors import colors
from .langlist import VideoLanguageList
from .videos_model import Caption
TYPES = ['TYPE_TOP',
 'TYPE_MOVIE',
 'TYPE_IMAGE',
 'TYPE_SEASON',
 'TYPE_SERIES',
 'TYPE_COLLECTION',
 'TYPE_SERIAL']

class ListEntry(PlaneEntry):
    width = 781
    height = 51
    offset = (-5, -5)
    frame_file = resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/f2.png')

    def __init__(self, parent):
        self.parent = parent
        self.instance = eWidget(parent)
        self.active = False
        self.col = gRGB(colors['white'])
        self.col_bg = gRGB(colors['darkgray'])
        self.col_sel = gRGB(colors['fgwall'])
        self.font = gFont('TVSansBold', 23)
        self.font_sel = gFont('TVSansBold', 25)
        self.font1 = gFont('TVSansRegular', 22)
        self.font1_sel = gFont('TVSansRegular', 25)
        self.instance.setBackgroundColor(self.col_bg)
        self.instance.setTransparent(0)
        self.instance.resize(eSize(self.width, self.height))
        xoff = 10
        icon = ePixmap(self.instance)
        icon.setAlphatest(1)
        icon.setScale(0)
        pixmap = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/icon_serie.png'))
        icon.setPixmap(pixmap)
        size = pixmap.size()
        icon.resize(size)
        icon.move(ePoint(xoff, (self.height - size.height()) / 2))
        self.icon = icon
        xoff += size.width() + 20
        txt = eLabel(self.instance)
        txt.setFont(self.font)
        txt.setForegroundColor(self.col)
        txt.setBackgroundColor(self.col_bg)
        txt.setVAlign(txt.alignCenter)
        txt.setHAlign(txt.alignLeft)
        txt.setTransparent(0)
        txth = 60
        yoff = (self.height - txth) / 2
        txt.move(ePoint(xoff, yoff))
        txt.resize(eSize(self.width - xoff - 10, txth))
        self.txt = txt
        txt = eLabel(self.instance)
        txt.setFont(self.font1)
        txt.setForegroundColor(self.col)
        txt.setBackgroundColor(self.col_bg)
        txt.setVAlign(txt.alignCenter)
        txt.setHAlign(txt.alignRight)
        txth = 55
        yoff = (self.height - txth) / 2
        txt.move(ePoint(self.width - 168, yoff))
        txt.resize(eSize(155, txth))
        self.txt1 = txt

    def setActive(self, active):
        if active == self.active:
            return
        self.active = active
        if active:
            self.txt.setFont(self.font_sel)
            self.txt.setForegroundColor(self.col_sel)
            self.txt1.setFont(self.font1_sel)
            self.txt1.setForegroundColor(self.col_sel)
        else:
            self.txt.setFont(self.font)
            self.txt.setForegroundColor(self.col)
            self.txt1.setFont(self.font1)
            self.txt1.setForegroundColor(self.col)

    def setData(self, data):
        if data is None:
            self.txt.setText(_('Loading...'))
            self.txt1.setText('')
        else:
            self.txt.setText(data['title'])
            t = int(data['time'])
            if t > 0:
                self.txt1.setText('%d %s' % (t / 60, _('min')))
            else:
                self.txt1.setText('')
        return

    def show(self):
        self.instance.show()

    def hide(self):
        self.instance.hide()


class Poster(PlaneEntry):
    width = 182
    height = 262
    offset = (-13, -13)
    frame_file = resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/post_fr.png')

    def __init__(self, parent):
        self.parent = parent
        self.instance = eWidget(parent)
        self.active = False
        self.defer = Deferred()
        self.url = None
        self.col = gRGB(colors['white'])
        self.col_bg = gRGB(colors['darkgray'])
        self.col_sel = gRGB(colors['fgwall'])
        self.font = gFont('TVSansBold', 24)
        self.font_sel = gFont('TVSansBold', 25)
        self.instance.setBackgroundColor(self.col_bg)
        self.instance.setTransparent(0)
        txt = eLabel(self.instance)
        txt.setForegroundColor(self.col)
        txt.setBackgroundColor(self.col_bg)
        txt.setVAlign(txt.alignCenter)
        txt.setHAlign(txt.alignCenter)
        txt.setZPosition(1)
        txt.setTransparent(0)
        self.txt = txt
        icon = ePixmap(self.instance)
        icon.setAlphatest(1)
        icon.setBorderColor(parseColor('#ff000000'))
        icon.setScale(1)
        icon.setZPosition(1)
        self.icon = icon
        size = eSize(self.width, self.height)
        self.instance.resize(size)
        self.txt.setFont(self.font)
        self.iconw = size.width()
        self.iconh = size.height()
        self.iconW = int(self.iconw * 1.1)
        self.iconH = int(self.iconh * 1.1)
        self.icon.resize(eSize(self.iconw, self.iconh))
        self.txt.resize(eSize(self.iconw, self.iconh))
        self.txt.move(ePoint(0, 0))
        self.icon.move(ePoint(0, 0))
        return

    def setActive(self, active):
        if active == self.active:
            return
        self.active = active
        pos = self.icon.position()
        dx = (self.iconW - self.iconw) / 2
        dy = (self.iconH - self.iconh) / 2
        if active:
            self.icon.move(ePoint(pos.x() - dx, pos.y() - dy))
            self.icon.resize(eSize(self.iconW, self.iconH))
            self.icon.setBorderWidth(10)
            self.txt.setFont(self.font_sel)
            self.txt.setForegroundColor(self.col_sel)
        else:
            self.icon.move(ePoint(pos.x() + dx, pos.y() + dy))
            self.icon.resize(eSize(self.iconw, self.iconh))
            self.icon.setBorderWidth(0)
            self.txt.setFont(self.font)
            self.txt.setForegroundColor(self.col)

    def setData(self, data):
        if data is not None:
            trace('setData', data['pic'])
            url = data['pic'].encode('utf-8')
            if self.url == url:
                return
            self.txt.setText(data['title'])
            self.txt.show()
            self.icon.hide()
            self.url = url
            if self.defer:
                self.defer.cancel()
            self.defer = posterCache.get(url)
            self.defer.addCallback(self.setPoster)
            self.defer.addErrback(self.error).addErrback(fatalError)
        else:
            self.txt.setText(_('Loading...'))
            self.txt.show()
            self.icon.hide()
            self.url = None
            if self.defer:
                self.defer.cancel()
        return

    def setPoster(self, pixmap):
        trace('setPoster', pixmap)
        self.icon.setPixmap(LoadPixmap(pixmap))
        self.txt.hide()
        self.icon.show()

    def error(self, err):
        e = trapException(err)
        if e == CancelledError:
            trace('poster canceled')
        else:
            trace('error', err)

    def show(self):
        self.instance.show()

    def hide(self):
        self.instance.hide()


MODE_CASUAL = 0
MODE_SEASONS = 1
MODE_SERIES = 2

class PaginationService(CallbackReceiver):

    def __init__(self, db):
        super(PaginationService, self).__init__()
        self.db = db
        self.page_size = 16
        self.max_size = self.page_size * 2
        self.count = 0
        self.data_start = 0
        self.data = []
        self.defer = None
        self.args = {}
        return

    def getVideos(self, page, limit):
        return self.db.getVideos(page, limit, self.args)

    def reset(self, args):
        self.args = args
        self.count = 0
        self.data_start = 0
        self.data = []

    def totalCount(self):
        return self.count

    def getSliceFromCache(self, start, end):
        """Return slice of requested size with items available from cache or filled with None"""
        end = min(end, self.count)
        result = [None] * (end - start)
        for i in range(max(start, self.data_start), min(end, self.data_start + len(self.data))):
            result[i - start] = self.data[i - self.data_start]

        return (result, self.count)

    def getSlice(self, start, end):
        """Return Deferred which resolves with requested slice. Download performed when necessary"""
        return self.loadFirst(start, end)

    def loadFirst(self, start, end):
        if self.data_start <= start < self.data_start + len(self.data):
            return self.loadSecond(start, end)
        else:
            if self.defer:
                self.defer.cancel()
            self.defer = self.getVideos(start / self.page_size, self.page_size)
            return self.defer.addCallback(self.onLoadFirst, start, end)

    @safecb
    def onLoadFirst(self, data, start, end):
        trace('onLoadFirst')
        l, self.count = data
        new_start = start / self.page_size * self.page_size
        if new_start + len(self.data) == self.data_start:
            self.data = l + self.data
        else:
            self.data = l
        self.data_start = new_start
        if len(self.data) > self.page_size * 2:
            self.data = self.data[:self.page_size * 2]
        return self.loadSecond(start, end)

    def loadSecond(self, start, end):
        end = min(end, self.count)
        trace('loadSecond', (start, end))
        if self.data_start <= end <= self.data_start + len(self.data):
            return self.dataReady(start, end)
        else:
            if self.defer:
                self.defer.cancel()
            self.defer = self.getVideos(end / self.page_size, self.page_size)
            return self.defer.addCallback(self.onLoadSecond, start, end)

    @safecb
    def onLoadSecond(self, data, start, end):
        trace('onLoadSecond')
        l, count = data
        new_start = end / self.page_size * self.page_size
        if new_start == self.data_start + len(self.data):
            self.data = self.data + l
        else:
            raise AssertionError('Second must be continuous')
        if len(self.data) > self.page_size * 2:
            self.data = self.data[self.page_size:]
            self.data_start += self.page_size
        return self.dataReady(start, end)

    def dataReady(self, start, end):
        trace('dataReady', (start, end), 'from', (self.data_start, self.data_start + len(self.data)))
        return succeed((self.data[start - self.data_start:end - self.data_start], self.count))


class VideosInfoPanel(CallbackReceiver):

    def __init__(self, ui, db):
        super(VideosInfoPanel, self).__init__()
        self.db = db
        ui['title'] = Label()
        ui['description'] = Label()
        self.ui = ui
        self.ui.onClose.append(self.stopCallbacks)
        self._title_height = 0
        self._desc_top = 0
        self._desc_height = 0
        self.ui.onLayoutFinish.append(self._initLayout)

    def _initLayout(self):
        self._title_height = self.ui['title'].instance.size().height()
        self._desc_top = self.ui['description'].instance.position().y()
        self._desc_height = self.ui['description'].instance.size().height()

    def _updateLayout(self):
        title_widget = self.ui['title'].instance
        desc_widget = self.ui['description'].instance
        height = min(title_widget.calculateSize().height(), self._title_height * 6)
        dh = height - self._title_height
        title_widget.resize(eSize(title_widget.size().width(), height))
        desc_widget.move(ePoint(desc_widget.position().x(), self._desc_top + dh))
        desc_widget.resize(eSize(desc_widget.size().width(), self._desc_height - dh))

    def showMovie(self, data):
        if data is None:
            self._showMovieData(None)
        else:
            d = self.db.getVideo(data['id'], data['type']).addCallback(self._showMovieData)
            d.addErrback(self._error).addErrback(fatalError)
        return

    @safecb
    def _showMovieData(self, data):
        if data is None:
            self.ui['title'].setText('')
            self.ui['description'].setText('')
        else:
            for k, v in list(data.items()):
                print(k, v)

            self.ui['title'].setText(data['title'])
            labels = (('year', _('Year')),
             ('country', _('Country')),
             ('age', _('Age')),
             ('length', _('Length')),
             ('quality', _('Quality')),
             ('genres', _('Genres')))
            data['acters'] = ', '.join((s.strip() for s in data.get('acters', '').split('\n')))
            try:
                length = int(data['time'])
                if length:
                    data['length'] = formatLength(length)
                else:
                    data['lenght'] = None
            except KeyError:
                data['length'] = None

            try:
                data['quality'] = ('720p', '1080p')[int(data['quality'] or 0) - 1]
            except (IndexError, ValueError):
                data['quality'] = None

            txt = ''
            for k, label in labels:
                if k in data and data[k]:
                    txt += '%s: %s\n' % (label, data[k].encode('utf-8'))
                else:
                    trace('missing', k)

            txt += '%s\n' % data.get('description', '').encode('utf-8')
            self.ui['description'].setText(txt)
        self._updateLayout()
        return

    @safecb
    def _error(self, err):
        trapException(err)
        trace('error:', err)


class VideosWall(Screen, CallbackReceiver):

    def __init__(self, session, db, args, caption, video = None):
        super(VideosWall, self).__init__(session)
        CallbackReceiver.__init__(self)
        self.db = db
        self['poster'] = Pixmap()
        self['title'] = Label()
        self['genre'] = Label()
        self['caption'] = Label(str(caption))
        self['text'] = Label()
        self['text'].hide()
        self['scroll'] = scroll = Scroll()
        self.cont = DynamicPlane(self.sliceChanged, scroll)
        self.cont.onCreated.append(lambda : self.applyView(cfg.viewmode.value))
        self['container'] = self.cont
        self['blue'] = Label(_('Add to favourites'))
        self['red'] = Label(_('View'))
        self['key_red'] = Pixmap()
        self.info = VideosInfoPanel(self, db)
        self['actions'] = ActionMap(['OkCancelActions', 'TDirectionActions', 'ColorActions'], {'up': self.cont.up,
         'down': self.cont.down,
         'right': self.cont.right,
         'left': self.cont.left,
         'keyReleased': self.sliceChangedFinal,
         'ok': self.ok,
         'cancel': self.exit,
         'red': self.selectView,
         'blue': self.toggleFavourite}, -1)
        self['actions_audio'] = ActionMap(['InfobarAudioSelectionActions', 'InfobarSubtitleSelectionActions'], {'audioSelection': self.selectLanguage,
         'subtitleSelection': self.selectLanguage})
        self.onFirstExecBegin.append(self.start)
        self._slice_changed = False
        self.args = args
        self.page_service = PaginationService(db)
        self.onClose.append(self.page_service.stopCallbacks)
        self.mode = MODE_CASUAL
        self.path = []
        self.caption = caption
        self.video = video

    def start(self):
        trace('start wall')
        self.cont.onSelectionChanged.append(self.selectionChanged)
        if self.video is not None:
            self.path = self.loadPath()
            if len(self.path) > 0:
                self.mode, self.args, start, index = self.path.pop()
            else:
                start, index = (0, 0)
            self.setList(start, index)
            self.play(self.video, settingsRepo.video_state.time)
        else:
            self.setList()
        return

    def setList(self, start = 0, index = 0):
        trace('setList', self.mode)
        if self.mode == MODE_SERIES:
            self.applyView('list')
            self['red'].hide()
            self['key_red'].hide()
        else:
            self.applyView(cfg.viewmode.value)
            self['red'].show()
            self['key_red'].show()
        self['caption'].setText(str(self.caption))
        self.page_service.reset(self.args)
        self.cont.setSlice(start, index)
        self.sliceChangedFinal()

    def selectionChanged(self, sel):
        trace('selectionChanged')
        self.info.showMovie(sel)

    def sliceChanged(self):
        start, end = self.cont.getRange()
        trace('sliceChanged', (start, end))
        self._slice_changed = True
        data, count = self.page_service.getSliceFromCache(start, end)
        self.cont.setViewList(data, count)

    def sliceChangedFinal(self):
        if not self._slice_changed:
            return
        self['text'].hide()
        start, end = self.cont.getRange()
        trace('sliceChangedFinal', (start, end))
        self._slice_changed = False
        self.page_service.getSlice(start, end).addCallback(self.dataReady).addErrback(self.error).addErrback(fatalError)

    @safecb
    def dataReady(self, result):
        data, count = result
        self.cont.setViewList(data, count)
        if count == 0:
            if 'word' in self.args:
                self['text'].setText(_("No results found for '%s'") % self.args['word'])
            elif 'idlist' in self.args:
                self['text'].setText(_('Favourites list is empty'))
            else:
                self['text'].setText(_('Empty'))
            self['text'].show()
        else:
            self['text'].hide()

    @safecb
    def error(self, err):
        trapException(err)
        if wasCancelled(err):
            trace('Cancelled')
        else:
            trace('ERROR:', err)
            self.session.open(MessageBox, describeException(err), MessageBox.TYPE_ERROR, timeout=5)

    def ok(self):
        sel = self.cont.getSelected()
        if sel is None:
            return
        else:
            trace(list(sel.keys()))
            self.enter(True)
            return

    def selectView(self):
        if self.mode != MODE_SERIES:
            cfg.viewmode.selectNext()
            cfg.viewmode.save()
            self.setList(self.cont.getRange()[0], self.cont.getSelectionIndex())

    def applyView(self, view):
        if view == 'wall':
            self.cont.setClass(Poster, 4, 2)
        elif view == 'list':
            self.cont.setClass(ListEntry, 1, 10)
        else:
            raise Exception('Bad view for setClass')

    def toggleFavourite(self):
        sel = self.cont.getSelected()
        if sel is None:
            return
        else:
            fav = int(sel['is_favorite'])
            d = self.db.setFavouriteVideo(sel, not fav).addCallback(self.favChanged, sel)
            d.addErrback(self.error).addErrback(fatalError)
            return

    @safecb
    def favChanged(self, ret, video):
        if video['is_favorite']:
            self.session.open(MessageBox, _('Film added to favourites'), MessageBox.TYPE_INFO, timeout=3)
        else:
            self.session.open(MessageBox, _('Film removed from favourites'), MessageBox.TYPE_INFO, timeout=3)
        trace('favourites changed')
        if 'idlist' in self.args:
            start = self.cont.getRange()[0]
            index = self.cont.getSelectionIndex()
            self.args['idlist'] = ','.join(map(str, ret))
            trace('TEST', index, len(ret))
            index = min(index, len(ret) - 1)
            self.setList(min(start, index), index)
        else:
            self.selectionChanged(self.cont.getSelected())

    def selectLanguage(self):
        if self.mode == MODE_CASUAL:
            self.session.openWithCallback(self.applyLanguage, VideoLanguageList, self.db)

    def applyLanguage(self, ret):
        if ret is not None:
            lang_id, lang_title = ret
            VideoLanguageList.saveLanguage(ret)
            if lang_id != 'ALL':
                self.args['lang'] = lang_id
            else:
                self.args.pop('lang', None)
            self.caption.setLang(lang_title)
            self.setList()
        return

    def savePath(self):
        path = []
        start = self.cont.getRange()[0]
        index = self.cont.getSelectionIndex()
        if index is None:
            return
        else:
            for item in self.path + [(self.mode,
              self.args,
              start,
              index)]:
                mode, args, start, index = item
                trace(item)
                if mode == MODE_CASUAL:
                    continue
                else:
                    parent = int(args['parent'])
                    path.append(VideoPathElement(mode, parent, start, index))

            trace('save path', path)
            settingsRepo.video_path = path
            settingsRepo.storeConfig()
            return

    @staticmethod
    def loadPath():
        return [ (p.mode,
         {'parent': p.parent,
          'order': 1},
         p.start,
         p.index) for p in settingsRepo.video_path ]

    def exit(self):
        if len(self.path) == 0:
            self.close()
        else:
            self.mode, self.args, start, index = self.path.pop()
            self.caption.pop()
            self.setList(start, index)

    def enter(self, ret):
        if not ret:
            return
        ret = self.cont.getSelected()
        start = self.cont.getRange()[0]
        index = self.cont.getSelectionIndex()
        saved = (self.mode,
         self.args.copy(),
         start,
         index)
        vtype = int(ret['type'])
        trace('enter type', TYPES[vtype], 'mode', self.mode)
        if self.mode == MODE_CASUAL:
            if vtype == TYPE_MOVIE or vtype == TYPE_SERIES:
                return self.play(ret)
            if vtype == TYPE_SERIAL:
                s = int(ret['seasons'])
                if s == 1:
                    self.mode = MODE_SEASONS
                elif s == 0:
                    self.mode = MODE_SERIES
                else:
                    raise Exception('Bad seasons %s' % s)
            else:
                self.mode = MODE_CASUAL
        elif self.mode == MODE_SEASONS:
            self.mode = MODE_SERIES
        else:
            if self.mode == MODE_SERIES:
                return self.play(ret)
            raise Exception('Bad mode %s' % self.mode)
        self.path.append(saved)
        self.caption.append(ret['title'])
        self.args = {'parent': ret['id']}
        if self.mode == MODE_SERIES or self.mode == MODE_SEASONS:
            self.args['order'] = 1
        self.setList()

    def play(self, ret, time = 0):
        trace('play movie', ret['id'])
        if ret is not None:
            self.session.openWithCallback(self.playFinished, VideosPlayer, self.db, ret, time)
        return

    def playFinished(self, ret):
        trace('play finished')
        self.savePath()
        showBackground()
        if self.mode == MODE_SERIES:

            def playSelected(sel):
                trace('play selected', sel)
                if sel is not None:
                    self['actions'].setEnabled(True)
                    self.cont.onSelectionChanged.remove(playSelected)
                    self.ok()
                return

            self['actions'].setEnabled(False)
            index = self.cont.getSelectionIndex()
            if (ret == RET_NEXT or ret == RET_END) and index is not None and index + 1 < self.page_service.totalCount():
                self.cont.onSelectionChanged.append(playSelected)
                self.cont.right()
                self.sliceChangedFinal()
            elif ret == RET_PREV and index and index > 0:
                self.cont.onSelectionChanged.append(playSelected)
                self.cont.left()
                self.sliceChangedFinal()
            else:
                pinManager.clear()
                self['actions'].setEnabled(True)
        else:
            pinManager.clear()
        return


class VideosInfo(Screen, CallbackReceiver):

    def __init__(self, session, db, video, caption):
        super(VideosInfo, self).__init__(session)
        CallbackReceiver.__init__(self)
        self.db = db
        self.video = video
        self['poster'] = Pixmap()
        self['title'] = Label(video['title'])
        self['genres'] = Label()
        self['country'] = Label()
        self['caption'] = Label(' / '.join(caption + [video['title']]))
        self['description'] = ScrollLabel()
        if int(video['type']) == TYPE_SERIAL:
            if int(video['seasons']) == 1:
                self['ok'] = Label(_('Go to seasons list'))
            else:
                self['ok'] = Label(_('Go to series list'))
        elif int(video['type']) == TYPE_SEASON:
            self['ok'] = Label(_('Go to series list'))
        elif int(video['type']) == TYPE_COLLECTION:
            self['ok'] = Label(_('Go to chapters list'))
        else:
            self['ok'] = Label(_('Watch movie'))
        if video['is_favorite']:
            self['blue'] = Label(_('Remove from favourites'))
        else:
            self['blue'] = Label(_('Add to favourites'))
        self['actions'] = ActionMap(['OkCancelActions', 'TListActions', 'ColorActions'], {'ok': self.ok,
         'cancel': self.exit,
         'up': self['description'].pageUp,
         'down': self['description'].pageDown,
         'pageUp': self['description'].pageUp,
         'pageDown': self['description'].pageDown,
         'blue': self.toggleFavourite}, -1)
        self.onShown.append(self.start)
        self.onClose.append(self.stop)
        self.defer = None
        return

    def start(self):
        self.onShown.remove(self.start)
        self.defer = self.db.getVideo(self.video['id'], self.video['type'])
        self.defer.addCallback(self.setData).addErrback(self.error).addErrback(fatalError)

    @safecb
    def setData(self, data):
        self.video['description'] = data['description']
        self['genres'].setText(data['genre'].encode('utf-8'))
        self['country'].setText(data['country'].encode('utf-8'))
        txt = data['description'].encode('utf-8')
        txt += '\n\n'
        labels = {'acters': _('Cast'),
         'director': _('Director'),
         'operator': _('Operator'),
         'composer': _('Composer')}
        data['acters'] = ', '.join((s.strip() for s in data.get('acters', '').split('\n')))
        for k in ['acters',
         'director',
         'operator',
         'composer']:
            if k in data:
                txt += '%s: %s\n' % (labels[k], data[k].encode('utf-8'))
            else:
                trace('missing', k)

        self['description'].setText(txt)
        self.defer = posterCache.get(data['pic'].encode('utf-8'))
        self.defer.addCallback(self.setPoster).addErrback(self.error).addErrback(fatalError)

    @safecb
    def setPoster(self, pixmap):
        self['poster'].instance.setPixmap(LoadPixmap(pixmap))

    @safecb
    def error(self, err):
        e = trapException(err)
        if e == CancelledError:
            trace('Cancelled')
        else:
            trace('ERROR:', err)

    def stop(self):
        self.defer.cancel()

    def ok(self):
        self.close(True)

    def exit(self):
        self.close(False)

    def toggleFavourite(self):
        fav = int(self.video['is_favorite'])
        d = self.db.setFavouriteVideo(self.video, not fav).addCallback(self.favChanged)
        d.addErrback(self.error).addErrback(fatalError)

    @safecb
    def favChanged(self, ret):
        if self.video['is_favorite']:
            self.session.open(MessageBox, _('Film added to favourites'), MessageBox.TYPE_INFO, timeout=3)
            self['blue'] = Label(_('Remove from favourites'))
        else:
            self.session.open(MessageBox, _('Film removed from favourites'), MessageBox.TYPE_INFO, timeout=3)
            self['blue'] = Label(_('Add to favourites'))


class SearchKeyboard(VirtualKB):

    def __init__(self, session, languages):
        VirtualKB.__init__(self, session, languages, title=_('Search'))
        self.skinName = 'VirtualKB'
        self['blue'] = Label(_('History'))
        self['actions_blue'] = ActionMap(['ColorActions'], {'blue': self.openSearchHistory}, -3)

    def openSearchHistory(self):

        def selected(s):
            if s:
                self['text'].setText(s)

        requests = settingsRepo.search_requests
        self.session.openWithCallback(selected, ChoiceList, [ (r, r) for r in requests ], title=_('Recent search requests'))

    def ok(self):
        s = self['text'].getText()
        if s:
            settingsRepo.search_requests.addNew(s)
            settingsRepo.storeConfig()
        VirtualKB.ok(self)