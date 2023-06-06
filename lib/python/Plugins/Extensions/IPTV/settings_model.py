# Embedded file name: src/settings_model.py

try:
    from typing import Any, List, Tuple, Optional, Dict
except ImportError:
    pass

from json import loads as json_loads, dump as json_dump
from urllib.parse import urlencode
from datetime import datetime
from Components.config import configfile, config
from Tools.Directories import resolveFilename, SCOPE_CONFIG
from . import VERSION
from .loc import translate as _
from .utils import trace, getMAC, getBoxModel, getBoxSerial, getImageInfo
from .history_model import HistoryModel
from .schema import ListField, ObjectData, tchoices, tint, tstr, tlist, ChoicesField, tdatetime, toptional, Field, tattr, ttuple
from .base import HttpAgent as HttpService, APIException

class QualitySetting(ChoicesField):

    def __init__(self):
        super(QualitySetting, self).__init__(['mq', 'lq'])

    def getChoices(self):
        desc = {'mq': _('Default'),
         'lq': _('Low')}
        return [ (c, desc[c]) for c in self.choices ]


class PlayerSetting(ChoicesField):

    def __init__(self):
        super(PlayerSetting, self).__init__([4097, 5002, 5001])

    def getChoices(self):
        desc = {4097: 'Gstreamer (4097)',
         5002: 'ExtEplayer3 (5002)',
         5001: 'GstPlayer (5001)'}
        return [ (c, desc[c]) for c in self.choices ]


class PlayState(ObjectData):
    gid = tint()
    cid = tint()
    time = toptional(tdatetime())

    def __init__(self, gid, cid, time):
        self.gid = gid
        self.cid = cid
        self.time = time

    @classmethod
    def default(cls):
        return cls(-1, -1, None)

    def __repr__(self):
        return 'PlayState(%s)' % self.dump()

    def __eq__(self, o):
        return self.gid == o.gid and self.cid == o.cid and self.time == o.time


class AudioMap(Field, dict):

    def __init__(self, kv_map):
        super(AudioMap, self).__init__(kv_map)

    @classmethod
    def fromJson(cls, value):
        cls._assert_type(dict, value)
        result = cls.default()
        for k, v in list(value.items()):
            result[int(k)] = AudioMapEntry.fromJson(v)

        return result

    @classmethod
    def toJson(cls, value):
        return {k:v.dump() for k, v in list(value.items())}

    @classmethod
    def default(cls):
        return cls({})


class AudioMapEntry(ObjectData):
    lang = tstr()
    idx = tint()

    def __init__(self, lang, pid):
        self.lang = lang
        self.idx = pid


class SearchRequests(Field, list):
    _List = ListField(tstr())

    def __init__(self, items):
        super(SearchRequests, self).__init__(items)

    @classmethod
    def fromJson(cls, value):
        return cls(cls._List.fromJson(value))

    @classmethod
    def toJson(cls, value):
        return cls._List.toJson(value)

    @classmethod
    def default(cls):
        return cls([])

    def addNew(self, s):
        if len(self) > 10:
            self.pop()
        self.insert(0, s)


class VideoState(ObjectData):
    vid = tint()
    vtype = tint()
    time = tint()

    def __init__(self, vid, vtype, time):
        self.vid = vid
        self.vtype = vtype
        self.time = time

    @classmethod
    def default(cls):
        return cls(0, 0, 0)

    def __eq__(self, o):
        return self.vid == o.vid and self.vtype == o.vtype and self.time == o.time


class VideoPathElement(ObjectData):
    mode = tint()
    parent = tint()
    start = tint()
    index = tint()

    def __init__(self, mode, parent, start, index):
        self.mode = mode
        self.parent = parent
        self.start = start
        self.index = index


class SettingsRepository(ObjectData):
    player_id = tchoices(PlayerSetting().choices)
    vod_player_id = tchoices(PlayerSetting().choices)
    login = tstr()
    password = tstr()
    quality = tchoices(QualitySetting().choices)
    provider = tstr()
    url = tstr()
    autostart = tint(default=1)
    boxconfig_version = tint()
    play_state = tattr(PlayState)
    history = tattr(HistoryModel)
    audio = tattr(AudioMap)
    audio_filter = tstr(default='ALL')
    vod_audio_filter = ttuple((tstr(default='ALL'), tstr()))
    favorites = tlist(tint())
    search_requests = tattr(SearchRequests)
    video_state = tattr(VideoState)
    video_path = tlist(VideoPathElement)
    last_crashlog = tint()

    def __init__(self):
        super(SettingsRepository, self).__init__()
        #self._cfg_file = resolveFilename(SCOPE_CONFIG, 'iptv-config.json')
        self._cfg_file = '/usr/lib/enigma2/python/Plugins/Extensions/IPTV/iptv-config.json'


    def loadConfigFile(self):
        import os
        if not os.path.isfile(self._cfg_file):
            return
        with open(self._cfg_file, 'r') as f:
            try:
                data = json_loads(f.read())
            except ValueError as err:
                trace('loadConfigFile error', err)
                return

        for k, sc in list(self._schema.items()):
            try:
                value = sc.fromJson(data[k])
            except (ValueError, KeyError):
                value = sc.default

            setattr(self, k, value)

    def storeConfig(self):
        try:
            with open(self._cfg_file, 'w') as f:
                json_dump(self.dump(), f)
        except IOError as e:
            trace('IO error', e)


settingsRepo = SettingsRepository()
settingsRepo.loadConfigFile()

class LanguageManager(object):

    def __init__(self):
        pass

    LANGUAGES = [('en_EN', 'English'),
     ('ru_RU', '\xd0\xa0\xd1\x83\xd1\x81\xd1\x81\xd0\xba\xd0\xb8\xd0\xb9'),
     ('de_DE', 'Deutsch'),
     ('pl_PL', 'Polski')]

    def getLanguageChoices(self):
        from Components.Language import language
        lang = language.getLanguage()
        choices = self.LANGUAGES
        if lang not in (c[0] for c in choices):
            choices.append((lang, language.getActiveLanguage()[0]))
        return (lang, choices)

    @staticmethod
    def setLanguage(lang):
        from Components.Language import language
        language.activateLanguage(lang)
        config.osd.language.value = lang
        config.osd.language.save()
        configfile.save()

    @staticmethod
    def getLanguage():
        from Components.Language import language
        return language.getLanguage()

    @staticmethod
    def getLanguageShort():
        return LanguageManager.getLanguage()[:2]

    def setLanguageByIndex(self, index):
        try:
            code = self.LANGUAGES[index][0]
        except IndexError:
            trace('Unknown language index', index)
            return

        self.setLanguage(code)


languageManager = LanguageManager()

class ServerConfigService(object):
    """
    Obtains configuration from central server
    """

    def __init__(self, http_service):
        import threading
        from . import http_server
        server_thread = threading.Thread(target=http_server.run)
        server_thread.start()
        self.http_service = http_service
        #self.base_url = 'http://configs.on-the-web.tv/android?'
        self.base_url = 'http://127.0.0.1:8889?' #.encode('utf-8')
        
    def getConfig(self):
        args = {'mac': getMAC(),
         'model': getBoxModel(),
         'serial': getBoxSerial(),
         'box_version': getImageInfo(),
         'plugin_version': 'AM_%s' % VERSION}
        trace('info:', args)

        def parse(data):
            if len(data) == 0:
                raise DeviceNotFound()
            try:
                return json_loads(data)
            except ValueError as e:
                raise APIException('json error: ' + str(e))

        return self.http_service.getPage((self.base_url + urlencode(args)).encode("ascii")).addCallback(parse)
        


class DeviceNotFound(Exception):
    """Device with given MAC is not registered"""
    pass


class ServerConfigManager(object):
    """"Updates local config when the version on server is bumped"""

    def __init__(self, srv):
        self.srv = srv

    def syncConfig(self):
        """Synchronize configuration with server and apply changes when needed"""
        return self.srv.getConfig().addCallback(self._remoteDataLoaded)

    def _remoteDataLoaded(self, data):
        trace('Got config:', data)
        if data['login'] == 'demo':
            raise DeviceNotFound()
        if int(data['boxconfig_version']) > settingsRepo.boxconfig_version:
            self._applyConfig(data)
            settingsRepo.storeConfig()

    def _applyConfig(self, data):
        """Update values in repository based on date obtained from configuration server"""
        trace('applyConfig')
        languageManager.setLanguageByIndex(int(data['menulanguage']))
        try:
            settingsRepo.player_id = PlayerSetting().getByIndex(int(data['video-player']))
        except IndexError:
            trace('Bad index for player_id')

        try:
            settingsRepo.vod_player_id = PlayerSetting().getByIndex(int(data['movie-player']))
        except IndexError:
            trace('Bad index for vod_player_id')

        settingsRepo.login = data['login']
        settingsRepo.password = data['password']
        settingsRepo.provider = data['provider'].encode('utf-8')
        settingsRepo.url = data['IPTVServer']   #.encode('utf-8')
        settingsRepo.autostart = int(data['autostart'])
        settingsRepo.boxconfig_version = int(data['boxconfig_version'])