# Embedded file name: src/api.py

from json import loads as json_loads
from datetime import datetime, timedelta
from urllib.parse import urlencode
from twisted.internet.defer import Deferred, succeed
from hashlib import md5
try:
    from typing import List, Dict, Optional, Tuple, Any
except ImportError:
    pass

from . import VERSION
from .base import APIException, HttpAgent as HttpService
from .utils import tdSec, secTd, getMAC, getBoxModel, trace
from .program import EpgCache, Program
from .settings_model import settingsRepo
try:
    from .loc import translate as _
except ImportError:
    from gettext import gettext as _

class Api(object):
    LOGIN_CODES = ['ACC_WRONG',
     'ACC_EMPTY',
     'ACC_NOSUB',
     'EMPTY_SUB']
    AUTH_CODES = ['WRONG_IP',
     'STIMEOUT',
     'BAD_SID',
     'WRONG_SID',
     'NO_SUCH_SESSION']

    def __init__(self, username, password, url, quality, language = 'en', http_service = None, title = 'IPTV'):
        self.username = username
        self.password = password
        self.quality = quality
        self.language = language
        if http_service is not None:
            self.http_service = http_service
        else:
            self.http_service = HttpService()
        self.title = title
        self.sid = None
        self.requests = []
        self.authorizing = False
        self.code = '%s/json' % url
        model = getBoxModel()
        mac = getMAC()
        self.user_agent = '%s-E2_%s_AM-%s' % (model, mac, VERSION)
        self.time_shift = 0
        self.settings = {}
        self.server_time = None
        self.packet_expire = None
        self.groups = []
        self.channels = {}
        self.fav_channels = []
        self.fav_videos = None
        self.account = None
        return

    def trace(self, *args):
        """You may use this to print debug information"""
        trace(*args)

    def get(self, params):
        """Public function to get data from api"""
        return self._get(params, 0)

    def hasSid(self):
        """Return True if session id has been assigned"""
        return self.sid is not None

    def authorize(self):
        """Public function to authorize"""
        self.sid = None
        self.authorizing = True
        self.trace('Authorization of username = %s' % self.username)
        d = self.http_service.getPage(self.authRequest().encode("ascii"))
        return d.addCallback(self.retProcess).addCallback(self.authCb).addErrback(self.authErr)

    def authCb(self, json):
        self.authorizing = False
        self.trace('authCallback')
        self.sid = self.authProcess(json)
        for r in self.requests:
            r.callback(self.sid)

        self.requests = []

    def authErr(self, err):
        self.trace('authErrback')
        self.authorizing = False
        for r in self.requests:
            r.errback(err)

        self.requests = []
        raise err

    def getSid(self):
        if self.sid:
            return succeed(self.sid)
        else:
            if not self.authorizing:
                self.authorize()
            d = Deferred()
            self.requests.append(d)
            return d

    def _get(self, params, depth):
        return self.getSid().addCallback(self.doGet, params, depth)

    def doGet(self, sid, params, depth):
        self.trace('doGet')
        d = self.http_service.getPage(self.makeRequest(sid, params).encode("ascii"))
        return d.addCallback(self.retProcess).addErrback(self.getErr, params, depth)

    def getErr(self, err, params, depth):
        self.trace('getErr:', err)
        err.trap(APIException)
        e = err.value
        if e.code not in self.AUTH_CODES:
            raise e
        self.sid = None
        if depth < 1:
            self.trace('retry', depth + 1)
            return self._get(params, depth + 1)
        else:
            raise e
            return

    def makeRequest(self, sid, params):
        params['sid'] = sid
        params['lng'] = self.language
        cmd = params['cmd']
        self.trace('%s?%s' % (cmd, urlencode(params)))
        return '%s/%s?%s' % (self.code, cmd, urlencode(params))

    def retProcess(self, reply):
        self.trace('=> GOT')
        try:
            data = json_loads(reply)
        except Exception as e:
            raise APIException('json error: ' + str(e))

        if 'error' in data:
            raise APIException(data['error']['message'].encode('utf-8'), data['error']['code'].encode('utf-8'))
        else:
            return data

    def authRequest(self):
        md5pass = md5(md5(self.username).hexdigest() + md5(self.password).hexdigest()).encode('utf-8').hexdigest()
        print('12345')
        print('%s/login?%s' % (self.code, urlencode({'login': self.username,
          'pass': md5pass,
          'with_cfg': '',
          'with_acc': '',
          'user_agent': self.user_agent})))
        return '%s/login?%s' % (self.code, urlencode({'login': self.username,
          'pass': md5pass,
          'with_cfg': '',
          'with_acc': '',
          'user_agent': self.user_agent}))

    def authProcess(self, data):
        self.packet_expire = None
        self.loadSettings(data['settings'])
        self.loadAccount(data['account'])
        self.loadTime(data['servertime'])
        return data['sid']

    def loadSettings(self, settings):
        """
        Update settings and all references to settings internals
        """
        settings['parental_pass'] = str(settings['parental_pass'])
        self.settings = settings
        self.time_shift = int(self.settings['time_shift'])
        self.trace('time_shift =', self.time_shift)

    def loadAccount(self, account):
        self.packet_expire = None
        self.account = account
        if not account['subscriptions']:
            account_id = 'ID:%s' % account['id'].encode('utf-8')
            raise APIException(_('No active subscriptions (%s)') % account_id, code='EMPTY_SUB')
        for s in account['subscriptions']:
            if 'end_date' in s:
                self.packet_expire = datetime.strptime(s['end_date'], '%Y-%m-%d')
                break

        return

    def loadTime(self, time):
        self.server_time = datetime.fromtimestamp(int(time))

    def now(self, channel):
        """
        returns time for live mode = real live minus time shift
        """
        if channel.has_timeshift:
            return datetime.now() - timedelta(seconds=self.time_shift * 3600)
        else:
            return datetime.now()

    def shiftTime(self, time):
        """
        :param time: original time
        :return: shifted time
        """
        return time + timedelta(seconds=self.time_shift * 3600)

    MEDIA_SERVER = 'media_server_id'
    TIME_SHIFT = 'time_shift'
    QUALITY = 'quality'

    def getSetting(self, name):
        if name == self.MEDIA_SERVER:
            server = self.settings['media_server_id']
            choices = [ (int(s['id']), s['title'].encode('utf-8')) for s in self.settings['media_servers'] ]
            return (server, choices)
        if name == self.TIME_SHIFT:
            choices = [ (x, str(x)) for x in range(0, 24) ]
            return (self.time_shift, choices)
        if name == self.QUALITY:
            choices = [('lq', _('Low')), ('mq', _('Default'))]
            return (self.quality, choices)
        raise Exception('Unknown name %s' % name)

    def setSettings(self, settings, pin = None):
        for k, v in list(settings.items()):
            pass

        params = {'cmd': 'set',
         'var': ','.join(list(settings.keys())),
         'val': ','.join(map(str, list(settings.values())))}
        if pin is not None:
            params['protect_code'] = pin
        return self.get(params).addCallback(self.loadSettings)

    def changeProtectCode(self, old, new):
        return self.setSettings({'parental_pass': new}, pin=old)

    def setQuality(self, quality):
        self.quality = quality

    def getAccountInfo(self):

        def f(data):
            self.loadAccount(data)

        return self.get({'cmd': 'get_account_info'}).addCallback(f)

    def getTimeShift(self):
        return self.time_shift

    def accountHasArchive(self):
        return int(self.account['subscriptions'][0]['option'][-1])

    def getChannels(self):

        def cb(data):
            allch = []
            archive_enabled = self.accountHasArchive()
            self.groups = []
            self.channels = {}
            for group in data['groups']:
                gr = Group.fromData(group)
                self.groups.append(gr)
                ch_list = []
                for channel in group['channels']:
                    cid = channel['id']
                    try:
                        ch = self.channels[cid]
                    except KeyError:
                        ch = Channel(channel)
                        self.channels[cid] = ch
                        if not archive_enabled:
                            ch.has_archive = False
                        allch.append(ch)

                    ch_list.append(ch)

                gr.channels = sorted(ch_list, key=lambda k: getattr(k, 'number'))

            allch.sort(key=lambda k: getattr(k, 'number'))
            grall = Group(gid=-1, title=_('All channels'), channels=allch, alias='ALL')
            self._loadFavouriteChannels()
            grfav = Group(gid=-2, title=_('Favourites'), channels=self.fav_channels, alias='FAVORITES')
            self.groups.insert(0, grall)
            self.groups.insert(0, grfav)
            if len(list(self.channels.keys())) == 0:
                raise APIException(_('Empty channels list, please retry later.'))
            return self.groups

        params = {'cmd': 'get_list_tv',
         'mode': 1}
        if self.quality == 'lq':
            params['quality'] = self.quality
        return self.get(params).addCallback(cb)

    def clearChannels(self):
        self.trace('Clear channels')
        self.groups = []
        self.channels = {}
        self.fav_channels = []

    def getEpgChannels(self, cids, time):
        d = self.get({'cmd': 'get_epg',
         'cid': ','.join(map(str, cids)),
         'from_uts': time.strftime('%s'),
         'hours': 4})

        def f(data):
            programs = {}
            for c in data['channels']:
                try:
                    cid = int(c['id'])
                except Exception as ex:
                    self.trace(ex)
                    continue

                programs[cid] = [ Program.fromData(e) for e in c['epg'] ]

            return programs

        return d.addCallback(f)

    def epgCurrent(self, channel, time):
        ecur, enxt = channel.epgcache.find(time)
        if ecur and enxt:
            return succeed((ecur, enxt))
        d = self.get({'cmd': 'get_epg',
         'cid': ','.join(map(str, list(self.channels.keys()))),
         'from_uts': time.strftime('%s'),
         'hours': 4})

        def f(data):
            for c in data['channels']:
                try:
                    cid = int(c['id'])
                except Exception as ex:
                    self.trace(ex)
                    continue

                ch = self.channels[cid]
                epglist = list([ Program.fromData(e) for e in c['epg'] ])
                ch.epgcache = EpgCache(epglist)

            print(channel.epgcache.find(time))
            return channel.epgcache.find(time)

        return d.addCallback(f)

    def epgArchive(self, channel, time):
        ecur, enxt = channel.epgcache.find(time)
        if ecur and enxt:
            return succeed((ecur, enxt))
        d = self.get({'cmd': 'get_epg',
         'cid': channel.id,
         'from_uts': (time - secTd(10800)).strftime('%s'),
         'hours': 8})

        def f(data):
            for c in data['channels']:
                cid = c['id']
                if type(cid) is not int:
                    self.trace('bad data', c)
                    continue
                ch = self.channels[cid]
                epglist = list([ Program.fromData(e) for e in c['epg'] ])
                ch.epgcache = EpgCache(epglist)

            print(channel.epgcache.find(time))
            return channel.epgcache.find(time)

        return d.addCallback(f)

    def epgCurrentList(self, cids, time):
        load = []
        epgs = {}
        for cid in cids:
            ch = self.channels[cid]
            epg = ch.epgcache.findCurrent(time)
            if epg:
                epgs[cid] = epg
                continue
            load.append(cid)

        if len(load) == 0:
            return succeed(epgs)

        def f(data):
            for c in data['channels']:
                cid = c['id']
                e = c['current']
                if e['begin'] and e['end']:
                    epgs[cid] = Program.fromData(e)

            return epgs

        return self.get({'cmd': 'get_epg_current',
         'cid': ','.join(map(str, cids)),
         'from_uts': time.strftime('%s')}).addCallback(f)

    def getStreamUrl(self, cid, pin, time = None):
        params = {'cmd': 'get_url_tv',
         'cid': cid,
         'time_shift': self.time_shift,
         'quality': self.quality}
        if pin:
            params['protect_code'] = pin
        if time:
            params['uts'] = time.strftime('%s')
        return self.get(params).addCallback(lambda data: data['url'].encode('utf-8'))

    def rangeEpg(self, cid, start, end):

        def f(data):
            try:
                channel = data['channels'][0]
            except IndexError:
                return []

            if not self.accountHasArchive():
                for i in channel['epg']:
                    i['has_archive'] = 0

            return [ Program.fromData(p) for p in channel['epg'] ]

        return self.get({'cmd': 'get_epg',
         'cid': cid,
         'from_uts': start.strftime('%s'),
         'time_shift': self.time_shift,
         'hours': tdSec(end - start) / 3600}).addCallback(f)

    def _loadFavouriteChannels(self):
        self.fav_channels = []
        for cid in settingsRepo.favorites:
            try:
                ch = self.channels[cid]
            except KeyError:
                continue

            self.fav_channels.append(ch)
            ch.is_favorite = True

        return self.fav_channels

    def storeFavoriteChannels(self):
        settingsRepo.favorites = [ ch.id for ch in self.fav_channels ]
        settingsRepo.storeConfig()

    def addFavouriteChannel(self, channel):
        channel.is_favorite = True
        self.fav_channels.append(channel)
        self.storeFavoriteChannels()

    def rmFavouriteChannel(self, channel):
        channel.is_favorite = False
        self.fav_channels.remove(channel)
        self.storeFavoriteChannels()

    def setFavoritesChannels(self, channels):
        self.fav_channels = self.groups[0].channels = channels
        self.storeFavoriteChannels()

    def getAudioLanguages(self):

        def makeLang(d):
            lang_id = d['title'].encode('utf-8')
            return {'id': lang_id,
             'title': lang_id}

        def f(data):
            return [ makeLang(lang) for lang in data['lang'] ]

        return self.get({'cmd': 'get_audio_lang'}).addCallback(f)

    def getVideos(self, page, limit, args):
        params = {'cmd': 'get_list_movie',
         'limit': limit,
         'extended': 0,
         'page': page + 1}
        for k, v in list(args.items()):
            if v is not None:
                params[k] = v

        self.trace('getVideos', (page * limit, (page + 1) * limit))

        def f(data):
            for d in data['groups']:
                d['title'] = d['title'].encode('utf-8')

            return (data['groups'], int(data['options']['count']))

        return self.get(params).addCallback(f)

    def getVideo(self, vid, vtype):

        def f(data):
            try:
                video = data['groups'][0]
            except IndexError:
                raise APIException('Video not found!', 'VIDEO_NOT_FOUND')

            video['title'] = video['title'].encode('utf-8')
            return video

        d = self.get({'cmd': 'get_list_movie',
         'extended': 1,
         'idlist': vid,
         'type': vtype})
        return d.addCallback(f)

    def getVideoUrl(self, vid, pin):
        params = {'cmd': 'get_url_movie',
         'cid': vid}
        if pin is not None:
            params['protect_code'] = pin
        return self.get(params).addCallback(lambda data: data['url'].encode('utf-8'))

    def getFavouriteVideos(self):

        def f(data):
            s = data['favorites']
            if len(s):
                self.fav_videos = list(map(int, s.split(',')))
            else:
                self.fav_videos = []
            return self.fav_videos

        return self.get({'cmd': 'get_favorites_movie'}).addCallback(f)

    def setFavouriteVideo(self, video, fav):

        def f(data):
            video['is_favorite'] = fav
            s = data['favorites']
            if len(s):
                self.fav_videos = list(map(int, s.split(',')))
            else:
                self.fav_videos = []
            return self.fav_videos

        def ready(l):
            newl = list(l)
            vid = int(video['id'])
            if fav and vid not in newl:
                newl.append(vid)
            elif vid in newl:
                newl.remove(vid)
            return self.get({'cmd': 'set_favorites_movie',
             'val': ','.join(map(str, newl))}).addCallback(f)

        if self.fav_videos is None:
            d = self.getFavouriteVideos().addCallback(ready)
        else:
            d = Deferred().addCallback(ready)
            d.callback(self.fav_videos)
        return d

    def getGenres(self):

        def f(data):
            genres = data['groups']
            for g in genres:
                g['title'] = g['title'].encode('utf-8')

            return genres

        return self.get({'cmd': 'get_genre_movie'}).addCallback(f)

    def getCountries(self):

        def f(data):
            countries = data['groups']
            for c in countries:
                c['title'] = c['title'].encode('utf-8')

            return countries

        return self.get({'cmd': 'get_country_movie'}).addCallback(f)

    def getVideoLanguages(self):

        def f(data):
            langs = data['groups']
            for lang in langs:
                lang['title'] = lang['title'].encode('utf-8')

            return langs

        return self.get({'cmd': 'get_lang_movie'}).addCallback(f)


class Channel(object):

    def __init__(self, d):
        self.id = int(d['id'])
        self.title = d['name'].encode('utf-8')
        self.number = int(d['number'])
        self.has_archive = self.has_timeshift = bool(d['has_archive'])
        self.icon = d['icon'].encode('utf-8')
        self.protected = bool(d['protected'])
        self.is_favorite = False
        self.audio = set(d.pop('audiotracks').encode('utf-8').split(','))
        self.epgcache = EpgCache([])

    def __repr__(self):
        return 'Channel[%s]' % self.title


class Group(object):

    def __init__(self, gid, title, alias, channels):
        self.id = gid
        self.title = title
        self.alias = alias
        self.channels = channels

    @staticmethod
    def fromData(d):
        return Group(gid=int(d['id']), title=d['user_title'].encode('utf-8'), alias=d['alias'].encode('utf-8'), channels=[])

    def copy(self):
        return Group(gid=self.id, title=self.title, alias=self.alias, channels=list(self.channels))

    def __repr__(self):
        return 'Group[%s]' % self.title


TYPE_MOVIE = 1
TYPE_IMAGE = 2
TYPE_SEASON = 3
TYPE_SERIES = 4
TYPE_COLLECTION = 5
TYPE_SERIAL = 6